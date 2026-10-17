"""Qué modo usa cada aplicación (RF-021)."""

import sqlite3

from vozflow.dominio.modos import Asignacion
from vozflow.persistencia.errores import DatoInvalido


def _clave(aplicacion: str) -> str:
    return aplicacion.strip().lower()


class AsignacionesRepo:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._base = base

    def asignar(self, aplicacion: str, modo_id: int, *, es_terminal: bool = False) -> Asignacion:
        clave = _clave(aplicacion)
        if not clave:
            raise DatoInvalido("La aplicación es obligatoria")
        try:
            with self._base:
                self._base.execute(
                    "INSERT INTO asignacion (aplicacion, modo_id, es_terminal) VALUES (?, ?, ?) "
                    "ON CONFLICT (aplicacion) DO UPDATE SET modo_id = excluded.modo_id, "
                    "es_terminal = excluded.es_terminal",
                    (clave, modo_id, int(es_terminal)),
                )
        except sqlite3.IntegrityError as error:
            raise DatoInvalido("Ese modo no existe") from error
        return Asignacion(clave, modo_id, es_terminal)

    def obtener(self, aplicacion: str) -> Asignacion | None:
        fila = self._base.execute(
            "SELECT aplicacion, modo_id, es_terminal FROM asignacion WHERE aplicacion = ?",
            (_clave(aplicacion),),
        ).fetchone()
        return Asignacion(fila[0], fila[1], bool(fila[2])) if fila else None

    def listar(self) -> list[Asignacion]:
        filas = self._base.execute(
            "SELECT aplicacion, modo_id, es_terminal FROM asignacion ORDER BY aplicacion"
        ).fetchall()
        return [Asignacion(f[0], f[1], bool(f[2])) for f in filas]

    def quitar(self, aplicacion: str) -> bool:
        with self._base:
            return (
                self._base.execute(
                    "DELETE FROM asignacion WHERE aplicacion = ?", (_clave(aplicacion),)
                ).rowcount
                > 0
            )
