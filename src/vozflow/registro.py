"""Registro de eventos sin datos sensibles.

Nunca se escriben en el registro las claves de acceso ni el texto dictado.
"""

import logging
from collections.abc import Mapping
from typing import Any

_LARGO_MINIMO_DE_SECRETO = 4
_MASCARA = "***"
_secretos: set[str] = set()
_fabrica_original = logging.getLogRecordFactory()


def registrar_secreto(valor: str) -> None:
    """Marca un valor para que aparezca enmascarado en cualquier registro."""
    if len(valor) >= _LARGO_MINIMO_DE_SECRETO:
        _secretos.add(valor)


def olvidar_secretos() -> None:
    _secretos.clear()


def describir_texto(texto: str) -> str:
    """Describe un texto dictado por su largo, sin mostrar su contenido."""
    return f"<texto de {len(texto)} caracteres>"


def _enmascarar(valor: str) -> str:
    for secreto in _secretos:
        valor = valor.replace(secreto, _MASCARA)
    return valor


def _enmascarar_argumento(argumento: object) -> object:
    return _enmascarar(argumento) if isinstance(argumento, str) else argumento


def _enmascarar_registro(registro: logging.LogRecord) -> None:
    if not _secretos:
        return
    if isinstance(registro.msg, str):
        registro.msg = _enmascarar(registro.msg)
    argumentos = registro.args
    if isinstance(argumentos, tuple):
        registro.args = tuple(_enmascarar_argumento(a) for a in argumentos)
    elif isinstance(argumentos, Mapping):
        registro.args = {k: _enmascarar_argumento(v) for k, v in argumentos.items()}


class FiltroDeSecretos(logging.Filter):
    """Enmascara los secretos registrados en el mensaje y sus argumentos."""

    def filter(self, record: logging.LogRecord) -> bool:
        _enmascarar_registro(record)
        return True


def _fabrica_con_mascara(*args: Any, **kwargs: Any) -> logging.LogRecord:
    registro = _fabrica_original(*args, **kwargs)
    _enmascarar_registro(registro)
    return registro


def configurar_registro(nivel: int = logging.INFO) -> None:
    """Configura el registro raíz; el enmascarado vale para todos los emisores."""
    logging.basicConfig(level=nivel, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    raiz = logging.getLogger()
    raiz.setLevel(nivel)
    for manejador in raiz.handlers:
        if not any(isinstance(f, FiltroDeSecretos) for f in manejador.filters):
            manejador.addFilter(FiltroDeSecretos())
    logging.setLogRecordFactory(_fabrica_con_mascara)
