"""Modos de dictado (RF-021)."""

import sqlite3
from typing import Any

from vozflow.dominio.claves import normalizar_clave
from vozflow.dominio.comandos_voz import SaltoDeLinea
from vozflow.dominio.modos import SALTOS_DE_LINEA, TIPOS_DE_PEGADO, Modo, TipoDePegado
from vozflow.persistencia.errores import DatoDuplicado, DatoInvalido

_COLUMNAS = (
    "id, nombre, es_general, quitar_muletillas, puntuacion_automatica, comandos_de_voz, "
    "reescribir, instruccion, tipo_pegado, salto_de_linea"
)
_BOOLEANOS = ("quitar_muletillas", "puntuacion_automatica", "comandos_de_voz", "reescribir")
_EDITABLES = {*_BOOLEANOS, "nombre", "instruccion", "tipo_pegado", "salto_de_linea"}


def _modo(fila: sqlite3.Row) -> Modo:
    return Modo(
        id=fila["id"],
        nombre=fila["nombre"],
        es_general=bool(fila["es_general"]),
        quitar_muletillas=bool(fila["quitar_muletillas"]),
        puntuacion_automatica=bool(fila["puntuacion_automatica"]),
        comandos_de_voz=bool(fila["comandos_de_voz"]),
        reescribir=bool(fila["reescribir"]),
        instruccion=fila["instruccion"],
        tipo_pegado=fila["tipo_pegado"],
        salto_de_linea=fila["salto_de_linea"],
    )


class ModosRepo:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._base = base

    def listar(self) -> list[Modo]:
        filas = self._base.execute(f"SELECT {_COLUMNAS} FROM modo ORDER BY id").fetchall()
        return [_modo(f) for f in filas]

    def obtener(self, nombre: str) -> Modo | None:
        clave = normalizar_clave(nombre)
        return next((m for m in self.listar() if normalizar_clave(m.nombre) == clave), None)

    def por_id(self, id_: int) -> Modo | None:
        fila = self._base.execute(f"SELECT {_COLUMNAS} FROM modo WHERE id = ?", (id_,)).fetchone()
        return _modo(fila) if fila else None

    def general(self) -> Modo:
        fila = self._base.execute(f"SELECT {_COLUMNAS} FROM modo WHERE es_general = 1").fetchone()
        return _modo(fila)

    def crear(
        self,
        nombre: str,
        *,
        quitar_muletillas: bool = True,
        puntuacion_automatica: bool = True,
        comandos_de_voz: bool = True,
        reescribir: bool = False,
        instruccion: str = "",
        tipo_pegado: TipoDePegado = "automatico",
        salto_de_linea: SaltoDeLinea = "conservar",
    ) -> Modo:
        datos: dict[str, Any] = {
            "nombre": nombre,
            "quitar_muletillas": quitar_muletillas,
            "puntuacion_automatica": puntuacion_automatica,
            "comandos_de_voz": comandos_de_voz,
            "reescribir": reescribir,
            "instruccion": instruccion,
            "tipo_pegado": tipo_pegado,
            "salto_de_linea": salto_de_linea,
        }
        datos = self._validar(datos, ocupado_por=None)
        columnas = ", ".join(datos)
        marcas = ", ".join("?" for _ in datos)
        with self._base:
            cursor = self._base.execute(
                f"INSERT INTO modo ({columnas}) VALUES ({marcas})", list(datos.values())
            )
        modo = self.por_id(int(cursor.lastrowid or 0))
        assert modo is not None
        return modo

    def actualizar(self, id_: int, **cambios: Any) -> Modo:
        actual = self.por_id(id_)
        if actual is None:
            raise DatoInvalido("No existe ese modo")
        desconocidos = set(cambios) - _EDITABLES
        if desconocidos:
            raise DatoInvalido(f"No se puede cambiar: {', '.join(sorted(desconocidos))}")
        datos = self._validar(cambios, ocupado_por=id_)
        if datos:
            asignaciones = ", ".join(f"{columna} = ?" for columna in datos)
            with self._base:
                self._base.execute(
                    f"UPDATE modo SET {asignaciones} WHERE id = ?", [*datos.values(), id_]
                )
        modo = self.por_id(id_)
        assert modo is not None
        return modo

    def borrar(self, id_: int) -> bool:
        modo = self.por_id(id_)
        if modo is None:
            return False
        if modo.es_general:
            raise DatoInvalido("El modo general no se puede borrar")
        with self._base:
            self._base.execute("DELETE FROM modo WHERE id = ?", (id_,))
        return True

    # ---- internos --------------------------------------------------------------------------

    def _validar(self, datos: dict[str, Any], *, ocupado_por: int | None) -> dict[str, Any]:
        limpios = dict(datos)
        if "nombre" in limpios:
            nombre = " ".join(str(limpios["nombre"]).split())
            if not nombre:
                raise DatoInvalido("El nombre del modo es obligatorio")
            otro = next(
                (
                    m
                    for m in self.listar()
                    if normalizar_clave(m.nombre) == normalizar_clave(nombre)
                    and m.id != ocupado_por
                ),
                None,
            )
            if otro is not None:
                raise DatoDuplicado(f"Ya hay un modo llamado «{otro.nombre}»")
            limpios["nombre"] = nombre
        if "tipo_pegado" in limpios and limpios["tipo_pegado"] not in TIPOS_DE_PEGADO:
            raise DatoInvalido(
                f"El tipo de pegado tiene que ser uno de {', '.join(TIPOS_DE_PEGADO)}"
            )
        if "salto_de_linea" in limpios and limpios["salto_de_linea"] not in SALTOS_DE_LINEA:
            raise DatoInvalido(
                f"El salto de línea tiene que ser uno de {', '.join(SALTOS_DE_LINEA)}"
            )
        for clave in _BOOLEANOS:
            if clave in limpios:
                limpios[clave] = int(bool(limpios[clave]))
        if "instruccion" in limpios:
            limpios["instruccion"] = str(limpios["instruccion"]).strip()
        return limpios
