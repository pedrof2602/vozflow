"""Portapapeles de Wayland con ``wl-copy`` y ``wl-paste``.

Se copia al portapapeles y a la selección primaria para que Shift+Insert (el pegado universal)
y Ctrl+V vean el mismo texto. ``wl-paste`` se usa solo con un tope de 200 ms porque en GNOME se
queda colgado si nadie le responde.
"""

import subprocess
from collections.abc import Callable
from typing import Protocol

_TOPE_DE_LECTURA_S = 0.2
_TOPE_DE_ESCRITURA_S = 2.0

Ejecutor = Callable[[list[str], str | None, float, bool], "subprocess.CompletedProcess[str]"]


class PortapapelesNoLegible(Exception):
    """No hubo forma de leer el contenido previo (no es texto, o no respondió a tiempo)."""


class Portapapeles(Protocol):
    def leer(self) -> str:
        """El texto actual (``""`` si está vacío). Lanza ``PortapapelesNoLegible``."""
        ...

    def copiar(self, texto: str, *, tambien_primaria: bool) -> None: ...

    def limpiar(self) -> None: ...


def _ejecutar(
    comando: list[str], entrada: str | None, timeout_s: float, capturar: bool
) -> subprocess.CompletedProcess[str]:
    # wl-copy deja un proceso sirviendo la selección que hereda las tuberías: si se capturaran,
    # subprocess esperaría para siempre. Por eso solo se captura al leer.
    destino = subprocess.PIPE if capturar else subprocess.DEVNULL
    return subprocess.run(
        comando,
        input=entrada,
        text=True,
        stdout=destino,
        stderr=destino,
        timeout=timeout_s,
        check=False,
    )


class PortapapelesWayland:
    def __init__(self, ejecutar: Ejecutor = _ejecutar) -> None:
        self._ejecutar = ejecutar

    def leer(self) -> str:
        try:
            resultado = self._ejecutar(
                ["wl-paste", "--no-newline", "--type", "text/plain"],
                None,
                _TOPE_DE_LECTURA_S,
                True,
            )
        except (subprocess.TimeoutExpired, OSError) as error:
            raise PortapapelesNoLegible("wl-paste no respondió a tiempo") from error
        if resultado.returncode == 0:
            return resultado.stdout
        if "nothing is copied" in (resultado.stderr or "").lower():
            return ""
        raise PortapapelesNoLegible("El portapapeles no tiene texto")

    def copiar(self, texto: str, *, tambien_primaria: bool) -> None:
        self._escribir([], texto)
        if tambien_primaria:
            self._escribir(["--primary"], texto)

    def limpiar(self) -> None:
        self._escribir(["--clear"], None)
        self._escribir(["--primary", "--clear"], None)

    def _escribir(self, opciones: list[str], texto: str | None) -> None:
        try:
            resultado = self._ejecutar(["wl-copy", *opciones], texto, _TOPE_DE_ESCRITURA_S, False)
        except subprocess.TimeoutExpired as error:
            raise OSError("wl-copy no respondió a tiempo") from error
        if resultado.returncode != 0:
            raise OSError(f"wl-copy falló (código {resultado.returncode})")
