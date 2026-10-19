"""La barra de texto de las descargas: «██████░░░░ 62 % · 300/480 MB» (002, RP-004)."""

import sys
from typing import TextIO

_MEGABYTE = 1_000_000


def barra_de_texto(hechos: int, total: int, ancho: int = 20) -> str:
    """Una línea con la barra, el porcentaje y los megas; sin total no inventa un porcentaje."""
    if total <= 0:
        return f"Descargando… {hechos // _MEGABYTE} MB"
    hechos = min(max(hechos, 0), total)
    porcentaje = hechos * 100 // total
    llenas = ancho * hechos // total
    return (
        f"{'█' * llenas}{'░' * (ancho - llenas)} {porcentaje} % · "
        f"{hechos // _MEGABYTE}/{total // _MEGABYTE} MB"
    )


class BarraDeTexto:
    """Se pasa como ``al_avance``. En una terminal se redibuja en su línea; si no, escribe una
    línea cada 10 %, para no llenar un registro."""

    def __init__(self, salida: TextIO | None = None, ancho: int = 20) -> None:
        self._salida = salida or sys.stderr
        self._ancho = ancho
        self._decena = -1
        self._escribio = False

    def __call__(self, hechos: int, total: int) -> None:
        linea = barra_de_texto(hechos, total, self._ancho)
        if self._salida.isatty():
            self._salida.write(f"\r{linea}")
            self._salida.flush()
            self._escribio = True
            return
        decena = 10 if total <= 0 else min(10, hechos * 10 // total)
        if total > 0 and decena == self._decena:
            return
        self._decena = decena
        self._salida.write(f"{linea}\n")
        self._escribio = True

    def terminar(self) -> None:
        if self._escribio and self._salida.isatty():
            self._salida.write("\n")
            self._salida.flush()
