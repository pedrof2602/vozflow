"""Historial de dictados (RF-027, RF-030) con búsqueda de texto completo."""

import re
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from vozflow.dominio.historial import ESTADOS_DEL_HISTORIAL, Dictado, EstadoDelHistorial
from vozflow.insercion.puerto import Destino, Insertor, ResultadoInsercion
from vozflow.persistencia.errores import DatoInvalido

_FORMATO = "%Y-%m-%dT%H:%M:%S.%fZ"
_COLUMNAS = (
    "id, creado_en, texto_crudo, texto_final, idioma, duracion_audio_ms, duracion_proceso_ms, "
    "aplicacion, modo_id, reescrito, proveedor, estado"
)


class _Portapapeles(Protocol):
    def copiar(self, texto: str, *, tambien_primaria: bool) -> None: ...


def _dictado(fila: sqlite3.Row) -> Dictado:
    return Dictado(
        id=fila["id"],
        creado_en=datetime.strptime(fila["creado_en"], _FORMATO).replace(tzinfo=UTC),
        texto_crudo=fila["texto_crudo"],
        texto_final=fila["texto_final"],
        idioma=fila["idioma"],
        duracion_audio_ms=fila["duracion_audio_ms"],
        duracion_proceso_ms=fila["duracion_proceso_ms"],
        aplicacion=fila["aplicacion"],
        modo_id=fila["modo_id"],
        reescrito=bool(fila["reescrito"]),
        proveedor=fila["proveedor"],
        estado=fila["estado"],
    )


def _consulta_segura(consulta: str) -> str | None:
    """Palabras entre comillas y con prefijo, así los signos raros no rompen la sintaxis."""
    palabras = re.findall(r"\w+", consulta)
    return " ".join(f'"{p}"*' for p in palabras) or None


class HistorialRepo:
    def __init__(self, base: sqlite3.Connection, activo: Callable[[], bool] = lambda: True) -> None:
        self._base = base
        self._activo = activo

    def guardar(
        self,
        *,
        texto_crudo: str,
        texto_final: str,
        duracion_audio_ms: int,
        duracion_proceso_ms: int,
        estado: EstadoDelHistorial,
        idioma: str = "",
        aplicacion: str = "",
        modo_id: int | None = None,
        reescrito: bool = False,
        proveedor: str = "",
        creado_en: datetime | None = None,
    ) -> Dictado | None:
        """Guarda un dictado. Con el historial apagado no escribe nada y devuelve ``None``."""
        if estado not in ESTADOS_DEL_HISTORIAL:
            raise DatoInvalido("El estado del dictado no es válido")
        if duracion_audio_ms <= 0:
            raise DatoInvalido("La duración del audio tiene que ser mayor que cero")
        if duracion_proceso_ms < 0:
            raise DatoInvalido("La duración del proceso no puede ser negativa")
        if not self._activo():
            return None
        momento = (creado_en or datetime.now(UTC)).astimezone(UTC).strftime(_FORMATO)
        with self._base:
            cursor = self._base.execute(
                "INSERT INTO dictado (creado_en, texto_crudo, texto_final, idioma, "
                "duracion_audio_ms, duracion_proceso_ms, aplicacion, modo_id, reescrito, "
                "proveedor, estado) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    momento,
                    texto_crudo,
                    texto_final,
                    idioma,
                    duracion_audio_ms,
                    duracion_proceso_ms,
                    aplicacion,
                    modo_id,
                    int(reescrito),
                    proveedor,
                    estado,
                ),
            )
        guardado = self.obtener(int(cursor.lastrowid or 0))
        assert guardado is not None
        return guardado

    def obtener(self, id_: int) -> Dictado | None:
        fila = self._base.execute(
            f"SELECT {_COLUMNAS} FROM dictado WHERE id = ?", (id_,)
        ).fetchone()
        return _dictado(fila) if fila else None

    def listar(self, limite: int = 50, desplazamiento: int = 0) -> list[Dictado]:
        filas = self._base.execute(
            f"SELECT {_COLUMNAS} FROM dictado ORDER BY creado_en DESC, id DESC LIMIT ? OFFSET ?",
            (limite, desplazamiento),
        ).fetchall()
        return [_dictado(f) for f in filas]

    def contar(self) -> int:
        return int(self._base.execute("SELECT COUNT(*) FROM dictado").fetchone()[0])

    def buscar(self, consulta: str, limite: int = 50) -> list[Dictado]:
        """Busca sobre el texto final, sin distinguir mayúsculas ni acentos, por prefijo."""
        segura = _consulta_segura(consulta)
        if segura is None:
            return self.listar(limite)
        columnas = ", ".join(f"d.{c.strip()}" for c in _COLUMNAS.split(","))
        filas = self._base.execute(
            f"SELECT {columnas} FROM dictado d JOIN dictado_fts f ON f.rowid = d.id "
            "WHERE dictado_fts MATCH ? ORDER BY d.creado_en DESC, d.id DESC LIMIT ?",
            (segura, limite),
        ).fetchall()
        return [_dictado(f) for f in filas]

    def copiar(self, id_: int, portapapeles: _Portapapeles) -> bool:
        dictado = self.obtener(id_)
        if dictado is None:
            return False
        portapapeles.copiar(dictado.texto_final, tambien_primaria=False)
        return True

    def reinsertar(self, id_: int, insertor: Insertor, destino: Destino) -> ResultadoInsercion:
        dictado = self.obtener(id_)
        if dictado is None:
            return ResultadoInsercion.fallido("Ese dictado ya no está en el historial")
        resultado = insertor.insertar(dictado.texto_final, destino)
        if resultado.insertado:
            with self._base:
                self._base.execute("UPDATE dictado SET estado = 'insertado' WHERE id = ?", (id_,))
        return resultado

    def borrar(self, id_: int) -> bool:
        with self._base:
            return self._base.execute("DELETE FROM dictado WHERE id = ?", (id_,)).rowcount > 0

    def borrar_todo(self) -> int:
        with self._base:
            return self._base.execute("DELETE FROM dictado").rowcount
