"""Contrato de ``Reescritor`` (``contracts/puertos.md``): lo cumple toda implementación."""

from collections.abc import Callable
from enum import Enum, auto
from typing import Any

import httpx
import pytest

from tests.dobles import ReescritorFalso
from vozflow.llm.anthropic import ReescritorAnthropic
from vozflow.llm.ollama import ReescritorOllama
from vozflow.llm.openrouter import ReescritorOpenRouter
from vozflow.llm.puerto import Reescritor, ReescrituraFallida

CLAVE = "sk-secreto-no-debe-salir-123456"


class Escenario(Enum):
    BIEN = auto()
    RED_CAIDA = auto()
    RESPUESTA_VACIA = auto()
    TIEMPO_AGOTADO = auto()
    CLAVE_RECHAZADA = auto()  # el servidor responde 401 y repite la clave en el cuerpo


def _doble(escenario: Escenario) -> Reescritor:
    fallos = {
        Escenario.RED_CAIDA: "No se pudo conectar",
        Escenario.RESPUESTA_VACIA: "El proveedor devolvió una respuesta vacía",
        Escenario.TIEMPO_AGOTADO: "El proveedor no respondió a tiempo",
        Escenario.CLAVE_RECHAZADA: "El proveedor rechazó la clave",
    }
    return ReescritorFalso("Texto reescrito.", fallos.get(escenario))


def _manejador(cuerpo_con_texto: Callable[[str], dict[str, Any]], escenario: Escenario):  # type: ignore[no-untyped-def]
    """Un servidor HTTP simulado que se porta como pide el escenario."""

    def manejar(pedido: httpx.Request) -> httpx.Response:
        if escenario is Escenario.RED_CAIDA:
            raise httpx.ConnectError("sin conexión")
        if escenario is Escenario.TIEMPO_AGOTADO:
            raise httpx.ReadTimeout("lento")
        if escenario is Escenario.CLAVE_RECHAZADA:  # repite lo que recibió, clave incluida
            return httpx.Response(401, text=f"rechazado: {dict(pedido.headers)}")
        texto = "" if escenario is Escenario.RESPUESTA_VACIA else "Texto reescrito."
        return httpx.Response(200, json=cuerpo_con_texto(texto))

    return manejar


def _ollama(escenario: Escenario) -> Reescritor:
    manejador = _manejador(lambda t: {"message": {"role": "assistant", "content": t}}, escenario)
    return ReescritorOllama("llama3.2", transporte=httpx.MockTransport(manejador))


def _anthropic(escenario: Escenario) -> Reescritor:
    manejador = _manejador(lambda t: {"content": [{"type": "text", "text": t}]}, escenario)
    return ReescritorAnthropic("claude-haiku-5-5", CLAVE, transporte=httpx.MockTransport(manejador))


def _openrouter(escenario: Escenario) -> Reescritor:
    manejador = _manejador(lambda t: {"choices": [{"message": {"content": t}}]}, escenario)
    return ReescritorOpenRouter("openai/gpt-x", CLAVE, transporte=httpx.MockTransport(manejador))


FABRICAS: dict[str, Callable[[Escenario], Reescritor]] = {
    "doble": _doble,
    "ollama": _ollama,
    "anthropic": _anthropic,
    "openrouter": _openrouter,
}


@pytest.fixture(params=list(FABRICAS))
def fabrica(request: pytest.FixtureRequest) -> Callable[[Escenario], Reescritor]:
    return FABRICAS[request.param]


def test_devuelve_el_texto_reescrito(fabrica: Callable[[Escenario], Reescritor]) -> None:
    assert fabrica(Escenario.BIEN).reescribir("hola   mundo", "Corregí.", 15) == "Texto reescrito."


@pytest.mark.parametrize(
    "escenario",
    [
        Escenario.RED_CAIDA,
        Escenario.RESPUESTA_VACIA,
        Escenario.TIEMPO_AGOTADO,
        Escenario.CLAVE_RECHAZADA,
    ],
)
def test_cualquier_falla_es_una_reescritura_fallida(
    fabrica: Callable[[Escenario], Reescritor], escenario: Escenario
) -> None:
    with pytest.raises(ReescrituraFallida):
        fabrica(escenario).reescribir("hola", "Corregí.", 15)


@pytest.mark.parametrize("escenario", [e for e in Escenario if e is not Escenario.BIEN])
def test_el_mensaje_del_error_nunca_contiene_la_clave_ni_el_texto(
    fabrica: Callable[[Escenario], Reescritor], escenario: Escenario
) -> None:
    with pytest.raises(ReescrituraFallida) as error:
        fabrica(escenario).reescribir("texto privado del usuario", "Corregí.", 15)

    mensaje = str(error.value)
    assert CLAVE not in mensaje and "texto privado" not in mensaje
    assert mensaje.strip()  # y dice algo
