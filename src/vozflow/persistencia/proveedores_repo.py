"""Proveedores de reescritura (RF-024, RF-025). La clave de acceso vive en el llavero, no acá."""

import sqlite3
from urllib.parse import urlparse

from vozflow.dominio.reescritura import (
    DIRECCION_DE_OLLAMA,
    PROVEEDORES,
    TIEMPO_MAXIMO_S,
    TIEMPO_MINIMO_S,
    Proveedor,
)
from vozflow.persistencia.errores import DatoInvalido

__all__ = ["DIRECCION_DE_OLLAMA", "ProveedoresRepo"]

_COLUMNAS = "id, activo, modelo, direccion, tiempo_maximo_s"


def _proveedor(fila: sqlite3.Row) -> Proveedor:
    return Proveedor(
        id=fila["id"],
        activo=bool(fila["activo"]),
        modelo=fila["modelo"],
        direccion=fila["direccion"],
        tiempo_maximo_s=fila["tiempo_maximo_s"],
    )


class ProveedoresRepo:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._base = base
        with base:  # los tres proveedores existen siempre, apagados y sin modelo
            for id_ in PROVEEDORES:
                base.execute(
                    "INSERT OR IGNORE INTO proveedor (id, direccion) VALUES (?, ?)",
                    (id_, DIRECCION_DE_OLLAMA if id_ == "ollama" else ""),
                )

    def listar(self) -> list[Proveedor]:
        filas = self._base.execute(f"SELECT {_COLUMNAS} FROM proveedor").fetchall()
        por_id = {f["id"]: _proveedor(f) for f in filas}
        return [por_id[i] for i in PROVEEDORES]

    def obtener(self, id_: str) -> Proveedor:
        self._validar_id(id_)
        fila = self._base.execute(
            f"SELECT {_COLUMNAS} FROM proveedor WHERE id = ?", (id_,)
        ).fetchone()
        return _proveedor(fila)

    def activo(self) -> Proveedor | None:
        fila = self._base.execute(f"SELECT {_COLUMNAS} FROM proveedor WHERE activo = 1").fetchone()
        return _proveedor(fila) if fila else None

    def configurar(
        self,
        id_: str,
        *,
        modelo: str | None = None,
        direccion: str | None = None,
        tiempo_maximo_s: int | None = None,
    ) -> Proveedor:
        self._validar_id(id_)
        cambios: dict[str, object] = {}
        if modelo is not None:
            cambios["modelo"] = modelo.strip()
        if direccion is not None:
            cambios["direccion"] = self._validar_direccion(id_, direccion)
        if tiempo_maximo_s is not None:
            if not TIEMPO_MINIMO_S <= tiempo_maximo_s <= TIEMPO_MAXIMO_S:
                raise DatoInvalido(
                    f"El tiempo máximo tiene que estar entre {TIEMPO_MINIMO_S} y "
                    f"{TIEMPO_MAXIMO_S} segundos"
                )
            cambios["tiempo_maximo_s"] = tiempo_maximo_s
        if cambios:
            asignaciones = ", ".join(f"{columna} = ?" for columna in cambios)
            with self._base:
                self._base.execute(
                    f"UPDATE proveedor SET {asignaciones} WHERE id = ?", [*cambios.values(), id_]
                )
        return self.obtener(id_)

    def activar(self, id_: str) -> Proveedor:
        """Deja activo solo a ``id_``. Pide que tenga un modelo elegido."""
        if not self.obtener(id_).modelo:
            raise DatoInvalido(f"Elegí un modelo para {id_} antes de activarlo")
        with self._base:
            self._base.execute("UPDATE proveedor SET activo = 0")
            self._base.execute("UPDATE proveedor SET activo = 1 WHERE id = ?", (id_,))
        return self.obtener(id_)

    def desactivar(self) -> None:
        """Apaga a todos; la configuración de cada uno se conserva."""
        with self._base:
            self._base.execute("UPDATE proveedor SET activo = 0")

    # ---- internos ---------------------------------------------------------------------------

    @staticmethod
    def _validar_id(id_: str) -> None:
        if id_ not in PROVEEDORES:
            raise DatoInvalido(
                f"No existe el proveedor «{id_}» (los posibles son {', '.join(PROVEEDORES)})"
            )

    @staticmethod
    def _validar_direccion(id_: str, direccion: str) -> str:
        if id_ != "ollama":
            raise DatoInvalido("La dirección solo se configura para Ollama")
        limpia = direccion.strip().rstrip("/")
        analizada = urlparse(limpia)
        if analizada.scheme not in ("http", "https") or not analizada.netloc:
            raise DatoInvalido("La dirección de Ollama tiene que ser una URL http o https")
        return limpia
