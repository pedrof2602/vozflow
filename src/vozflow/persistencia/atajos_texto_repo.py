"""Atajos de texto (RF-020)."""

import sqlite3

from vozflow.dominio.atajos_texto import AtajoTexto
from vozflow.dominio.claves import normalizar_clave
from vozflow.persistencia.errores import DatoDuplicado, DatoInvalido

_MAXIMO_DISPARADOR = 100


class AtajosTextoRepo:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._base = base

    def agregar(self, disparador: str, reemplazo: str) -> AtajoTexto:
        disparador = " ".join(disparador.split())
        self._validar(disparador, reemplazo)
        try:
            with self._base:
                cursor = self._base.execute(
                    "INSERT INTO atajo_texto (disparador, disparador_norm, reemplazo) "
                    "VALUES (?, ?, ?)",
                    (disparador, normalizar_clave(disparador), reemplazo),
                )
        except sqlite3.IntegrityError as error:
            raise DatoDuplicado(f"Ya hay un atajo con el disparador «{disparador}»") from error
        return AtajoTexto(disparador, reemplazo, int(cursor.lastrowid or 0))

    def reemplazar(self, disparador: str, reemplazo: str) -> bool:
        """Cambia el reemplazo de un disparador que ya existe."""
        if not reemplazo.strip():
            raise DatoInvalido("El reemplazo es obligatorio")
        with self._base:
            return (
                self._base.execute(
                    "UPDATE atajo_texto SET reemplazo = ? WHERE disparador_norm = ?",
                    (reemplazo, normalizar_clave(disparador)),
                ).rowcount
                > 0
            )

    def listar(self) -> list[AtajoTexto]:
        filas = self._base.execute(
            "SELECT id, disparador, reemplazo FROM atajo_texto ORDER BY id"
        ).fetchall()
        return [AtajoTexto(f["disparador"], f["reemplazo"], f["id"]) for f in filas]

    def borrar(self, id_: int) -> bool:
        with self._base:
            return self._base.execute("DELETE FROM atajo_texto WHERE id = ?", (id_,)).rowcount > 0

    def borrar_disparador(self, disparador: str) -> bool:
        with self._base:
            return (
                self._base.execute(
                    "DELETE FROM atajo_texto WHERE disparador_norm = ?",
                    (normalizar_clave(disparador),),
                ).rowcount
                > 0
            )

    @staticmethod
    def _validar(disparador: str, reemplazo: str) -> None:
        if not disparador:
            raise DatoInvalido("El disparador es obligatorio")
        if len(disparador) > _MAXIMO_DISPARADOR:
            raise DatoInvalido(f"El disparador no puede pasar de {_MAXIMO_DISPARADOR} caracteres")
        if not reemplazo.strip():
            raise DatoInvalido("El reemplazo es obligatorio")
