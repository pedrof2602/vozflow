"""Ventana activa por AT-SPI: un ayudante con el Python del sistema (el que trae ``gi``).

Es una ayuda opcional: ante cualquier fallo o demora devuelve ``None`` y nunca estorba.
"""

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from vozflow.ventana.puerto import InfoVentana

_AYUDANTE = Path(__file__).with_name("ayudante_atspi.py")
_PYTHON_DEL_SISTEMA = "/usr/bin/python3"
_TIEMPO_MAXIMO_S = 0.5

Ejecutor = Callable[[list[str], float], str]

_registro = logging.getLogger(__name__)


def _ejecutar(comando: list[str], timeout_s: float) -> str:
    return subprocess.run(
        comando, capture_output=True, text=True, timeout=timeout_s, check=True
    ).stdout


class VentanaActivaAtspi:
    def __init__(self, ejecutar: Ejecutor = _ejecutar, timeout_s: float = _TIEMPO_MAXIMO_S) -> None:
        self._ejecutar = ejecutar
        self._timeout_s = timeout_s

    def consultar(self) -> InfoVentana | None:
        comando = [_PYTHON_DEL_SISTEMA, "-I", str(_AYUDANTE)]
        try:
            salida = self._ejecutar(comando, self._timeout_s)
        except (subprocess.SubprocessError, OSError) as error:
            _registro.debug("El ayudante de AT-SPI no respondió: %s", type(error).__name__)
            return None
        return _interpretar(salida)


def _interpretar(salida: str) -> InfoVentana | None:
    try:
        datos = json.loads(salida)
    except ValueError:
        return None
    if not isinstance(datos, dict):
        return None
    aplicacion, titulo, pid = datos.get("aplicacion"), datos.get("titulo"), datos.get("pid")
    if not (isinstance(aplicacion, str) and isinstance(titulo, str) and isinstance(pid, int)):
        return None
    return InfoVentana(aplicacion=aplicacion.strip().lower(), titulo=titulo, pid=pid)
