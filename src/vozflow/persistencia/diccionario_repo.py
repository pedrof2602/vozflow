"""Entradas del diccionario personal (RF-019)."""

import sqlite3
from dataclasses import dataclass

from vozflow.dominio.claves import normalizar_clave
from vozflow.persistencia.errores import DatoDuplicado, DatoInvalido

_MAXIMO = 80


@dataclass(frozen=True)
class EntradaDiccionario:
    id: int
    palabra: str
    nota: str = ""


class DiccionarioRepo:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._base = base

    def agregar(self, palabra: str, nota: str = "") -> EntradaDiccionario:
        palabra = palabra.strip()
        if not palabra:
            raise DatoInvalido("La palabra es obligatoria")
        if len(palabra) > _MAXIMO:
            raise DatoInvalido(f"La palabra no puede pasar de {_MAXIMO} caracteres")
        try:
            with self._base:
                cursor = self._base.execute(
                    "INSERT INTO entrada_diccionario (palabra, palabra_norm, nota) "
                    "VALUES (?, ?, ?)",
                    (palabra, normalizar_clave(palabra), nota.strip()),
                )
        except sqlite3.IntegrityError as error:
            raise DatoDuplicado(f"«{palabra}» ya está en el diccionario") from error
        return EntradaDiccionario(int(cursor.lastrowid or 0), palabra, nota.strip())

    def listar(self) -> list[EntradaDiccionario]:
        filas = self._base.execute(
            "SELECT id, palabra, nota FROM entrada_diccionario ORDER BY id"
        ).fetchall()
        return [EntradaDiccionario(f["id"], f["palabra"], f["nota"]) for f in filas]

    def borrar(self, id_: int) -> bool:
        with self._base:
            return (
                self._base.execute("DELETE FROM entrada_diccionario WHERE id = ?", (id_,)).rowcount
                > 0
            )

    def borrar_palabra(self, palabra: str) -> bool:
        with self._base:
            return (
                self._base.execute(
                    "DELETE FROM entrada_diccionario WHERE palabra_norm = ?",
                    (normalizar_clave(palabra),),
                ).rowcount
                > 0
            )
