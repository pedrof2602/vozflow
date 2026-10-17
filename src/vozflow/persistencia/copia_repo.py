"""Exportar e importar la copia de seguridad (RF-022), en una sola transacción."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from vozflow.dominio.claves import normalizar_clave
from vozflow.dominio.copia import (
    AsignacionCopia,
    AtajoCopia,
    Copia,
    CopiaInvalida,
    ModoCopia,
    PalabraCopia,
    interpretar,
    serializar,
    validar_asignaciones,
)

_BANDERAS = ("quitar_muletillas", "puntuacion_automatica", "comandos_de_voz", "reescribir")


@dataclass(frozen=True)
class ResumenImportacion:
    diccionario: int
    atajos_de_texto: int
    modos: int
    asignaciones: int


class CopiaRepo:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._base = base

    # ---- exportar -----------------------------------------------------------------------

    def exportar(self, creado_en: datetime | None = None) -> str:
        momento = (creado_en or datetime.now(UTC)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        base = self._base
        modos = base.execute("SELECT * FROM modo").fetchall()
        nombre_del_modo = {m["id"]: m["nombre"] for m in modos}
        copia = Copia(
            creado_en=momento,
            diccionario=tuple(
                PalabraCopia(f["palabra"], f["nota"])
                for f in base.execute("SELECT palabra, nota FROM entrada_diccionario")
            ),
            atajos_de_texto=tuple(
                AtajoCopia(f["disparador"], f["reemplazo"])
                for f in base.execute("SELECT disparador, reemplazo FROM atajo_texto")
            ),
            modos=tuple(
                ModoCopia(
                    nombre=m["nombre"],
                    es_general=bool(m["es_general"]),
                    quitar_muletillas=bool(m["quitar_muletillas"]),
                    puntuacion_automatica=bool(m["puntuacion_automatica"]),
                    comandos_de_voz=bool(m["comandos_de_voz"]),
                    reescribir=bool(m["reescribir"]),
                    instruccion=m["instruccion"],
                    tipo_pegado=m["tipo_pegado"],
                    salto_de_linea=m["salto_de_linea"],
                )
                for m in modos
            ),
            asignaciones=tuple(
                AsignacionCopia(
                    f["aplicacion"], nombre_del_modo[f["modo_id"]], bool(f["es_terminal"])
                )
                for f in base.execute("SELECT aplicacion, modo_id, es_terminal FROM asignacion")
            ),
        )
        return serializar(copia)

    def exportar_a(self, destino: Path, creado_en: datetime | None = None) -> None:
        destino.write_text(self.exportar(creado_en), encoding="utf-8")

    # ---- importar -----------------------------------------------------------------------

    def importar_de(self, origen: Path) -> ResumenImportacion:
        try:
            texto = origen.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise CopiaInvalida(f"No se pudo leer el archivo {origen}") from error
        return self.importar(texto)

    def importar(self, texto: str) -> ResumenImportacion:
        """Mezcla el archivo con lo que hay: actualiza lo que existe y nunca borra. Todo o nada."""
        copia = interpretar(texto)
        base = self._base
        existentes = {normalizar_clave(f["nombre"]): f for f in base.execute("SELECT * FROM modo")}
        validar_asignaciones(copia, [f["nombre"] for f in existentes.values()])
        general = next(f for f in existentes.values() if f["es_general"])
        with base:  # una sola transacción: si algo falla, no queda nada a medias
            destino_de_modo = self._importar_modos(copia.modos, existentes, general)
            for palabra in copia.diccionario:
                base.execute(
                    "INSERT INTO entrada_diccionario (palabra, palabra_norm, nota) "
                    "VALUES (?, ?, ?) ON CONFLICT (palabra_norm) "
                    "DO UPDATE SET nota = excluded.nota",
                    (palabra.palabra, normalizar_clave(palabra.palabra), palabra.nota),
                )
            for atajo in copia.atajos_de_texto:
                base.execute(
                    "INSERT INTO atajo_texto (disparador, disparador_norm, reemplazo) "
                    "VALUES (?, ?, ?) ON CONFLICT (disparador_norm) "
                    "DO UPDATE SET reemplazo = excluded.reemplazo",
                    (atajo.disparador, normalizar_clave(atajo.disparador), atajo.reemplazo),
                )
            for asignacion in copia.asignaciones:
                base.execute(
                    "INSERT INTO asignacion (aplicacion, modo_id, es_terminal) VALUES (?, ?, ?) "
                    "ON CONFLICT (aplicacion) DO UPDATE SET modo_id = excluded.modo_id, "
                    "es_terminal = excluded.es_terminal",
                    (
                        asignacion.aplicacion,
                        destino_de_modo(asignacion.modo),
                        int(asignacion.es_terminal),
                    ),
                )
        return ResumenImportacion(
            len(copia.diccionario),
            len(copia.atajos_de_texto),
            len(copia.modos),
            len(copia.asignaciones),
        )

    def _importar_modos(
        self,
        modos: tuple[ModoCopia, ...],
        existentes: dict[str, sqlite3.Row],
        general: sqlite3.Row,
    ) -> Callable[[str], int]:
        """Crea o actualiza los modos y devuelve cómo resolver el nombre de uno a su número."""
        ids: dict[str, int] = {clave: fila["id"] for clave, fila in existentes.items()}
        for modo in modos:
            clave = normalizar_clave(modo.nombre)
            if modo.es_general:
                # El general no cambia de nombre: lo que el archivo llame así apunta a él.
                ids[clave] = general["id"]
                self._actualizar_banderas(general["id"], modo)
            elif clave in ids:
                self._actualizar_banderas(ids[clave], modo)
            else:
                ids[clave] = self._crear(modo)
        return lambda nombre: ids[normalizar_clave(nombre)]

    def _actualizar_banderas(self, id_: int, modo: ModoCopia) -> None:
        asignaciones = ", ".join(f"{b} = ?" for b in _BANDERAS)
        self._base.execute(
            f"UPDATE modo SET {asignaciones}, instruccion = ?, tipo_pegado = ?, "
            "salto_de_linea = ? WHERE id = ?",
            (
                *(int(getattr(modo, b)) for b in _BANDERAS),
                modo.instruccion,
                modo.tipo_pegado,
                modo.salto_de_linea,
                id_,
            ),
        )

    def _crear(self, modo: ModoCopia) -> int:
        cursor = self._base.execute(
            "INSERT INTO modo (nombre, quitar_muletillas, puntuacion_automatica, comandos_de_voz, "
            "reescribir, instruccion, tipo_pegado, salto_de_linea) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                modo.nombre,
                *(int(getattr(modo, b)) for b in _BANDERAS),
                modo.instruccion,
                modo.tipo_pegado,
                modo.salto_de_linea,
            ),
        )
        return int(cursor.lastrowid or 0)
