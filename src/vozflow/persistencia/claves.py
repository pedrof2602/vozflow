"""Claves de acceso a servicios externos, en el llavero del escritorio (RF-025).

El servicio es ``vozflow`` y el nombre de usuario, el del proveedor. La clave nunca se escribe
en la base, el historial ni los registros, y tampoco sale en ningún mensaje de error.
"""

import keyring
import keyring.errors

from vozflow.persistencia.errores import DatoInvalido

SERVICIO = "vozflow"
PROVEEDORES_CON_CLAVE = ("anthropic", "openrouter")  # Ollama es local y no usa clave


class LlaveroNoDisponible(Exception):
    """El llavero no responde (bloqueado, ausente o con error); el mensaje se puede mostrar."""


def _no_disponible(proveedor: str) -> LlaveroNoDisponible:
    return LlaveroNoDisponible(
        f"No se pudo usar el llavero del escritorio para la clave de {proveedor}: "
        "¿está desbloqueado y corriendo?"
    )


class Claves:
    def __repr__(self) -> str:
        return "Claves(servicio='vozflow')"

    def guardar(self, proveedor: str, clave: str) -> None:
        self._validar(proveedor)
        limpia = clave.strip()
        if not limpia:
            raise DatoInvalido("La clave no puede estar vacía")
        try:
            keyring.set_password(SERVICIO, proveedor, limpia)
        except keyring.errors.KeyringError:
            raise _no_disponible(proveedor) from None

    def leer(self, proveedor: str) -> str | None:
        self._validar(proveedor)
        try:
            return keyring.get_password(SERVICIO, proveedor)
        except keyring.errors.KeyringError:
            raise _no_disponible(proveedor) from None

    def existe(self, proveedor: str) -> bool:
        return bool(self.leer(proveedor))

    def borrar(self, proveedor: str) -> bool:
        """``False`` si no había clave guardada."""
        self._validar(proveedor)
        try:
            keyring.delete_password(SERVICIO, proveedor)
        except keyring.errors.PasswordDeleteError:
            return False
        except keyring.errors.KeyringError:
            raise _no_disponible(proveedor) from None
        return True

    @staticmethod
    def _validar(proveedor: str) -> None:
        if proveedor not in PROVEEDORES_CON_CLAVE:
            raise DatoInvalido(
                f"El proveedor «{proveedor}» no usa clave (solo {', '.join(PROVEEDORES_CON_CLAVE)})"
            )
