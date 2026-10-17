"""Reescritor de OpenRouter: formato compatible con OpenAI, clave en ``Authorization``."""

import json
import logging

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vozflow.llm.openrouter import ReescritorOpenRouter
from vozflow.llm.puerto import ReescrituraFallida

CLAVE = "sk-or-secreta-123456"


class Servidor:
    def __init__(self, respuesta: httpx.Response | Exception, eco: bool = False) -> None:
        self.respuesta = respuesta
        self.eco = eco
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        if self.eco:
            return httpx.Response(
                401, text=f"clave inválida: {pedido.headers.get('authorization')}"
            )
        return self.respuesta

    def reescritor(
        self, clave: str = CLAVE, modelo: str = "anthropic/claude-haiku-5-5"
    ) -> ReescritorOpenRouter:
        return ReescritorOpenRouter(modelo, clave, transporte=httpx.MockTransport(self))


def _bien(texto: str = "Texto reescrito.", motivo: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": texto}, "finish_reason": motivo}
            ]
        },
    )


def test_manda_el_pedido_a_chat_completions_con_bearer() -> None:
    servidor = Servidor(_bien())

    servidor.reescritor().reescribir("hola mundo", "Corregí.", 15)

    (pedido,) = servidor.pedidos
    assert pedido.method == "POST"
    assert str(pedido.url) == "https://openrouter.ai/api/v1/chat/completions"
    assert pedido.headers["authorization"] == f"Bearer {CLAVE}"
    assert pedido.headers["content-type"] == "application/json"


def test_el_cuerpo_lleva_modelo_mensajes_y_un_tope() -> None:
    servidor = Servidor(_bien())

    servidor.reescritor(modelo="openai/gpt-x").reescribir("hola mundo", "Corregí.", 15)

    cuerpo = json.loads(servidor.pedidos[0].content)
    assert cuerpo["model"] == "openai/gpt-x"
    assert cuerpo["messages"] == [
        {"role": "system", "content": "Corregí."},
        {"role": "user", "content": "hola mundo"},
    ]
    assert 256 <= cuerpo["max_tokens"] <= 8192
    assert cuerpo.get("stream", False) is False


def test_devuelve_el_contenido_sin_espacios_sobrantes() -> None:
    assert Servidor(_bien("  Hola.\n")).reescritor().reescribir("x", "y", 15) == "Hola."


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.ConnectError("sin red"),
        httpx.ReadTimeout("lento"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": ""}}]}),
        httpx.Response(200, json={"choices": [{"message": {"content": None}}]}),
        httpx.Response(200, json={"choices": [{}]}),
        httpx.Response(200, json={}),
        httpx.Response(200, text="no es json"),
        # OpenRouter puede devolver un error embebido con código 200
        httpx.Response(200, json={"error": {"code": 502, "message": "proveedor caído"}}),
        _bien("cortado", motivo="length"),
        _bien("filtrado", motivo="content_filter"),
        httpx.Response(401, json={"error": {"message": "No auth credentials found"}}),
        httpx.Response(402, json={"error": {"message": "Insufficient credits"}}),
        httpx.Response(429, json={"error": {"message": "rate limited"}}),
        httpx.Response(500, json={"error": {"message": "x"}}),
        httpx.Response(502, json={"error": {"message": "x"}}),
    ],
)
def test_cualquier_problema_es_una_reescritura_fallida(
    respuesta: httpx.Response | Exception,
) -> None:
    with pytest.raises(ReescrituraFallida):
        Servidor(respuesta).reescritor().reescribir("hola", "Corregí.", 15)


@pytest.mark.parametrize(
    ("codigo", "debe_decir"),
    [(401, "clave"), (402, "crédito"), (429, "límite|demasiad"), (500, "error"), (502, "error")],
)
def test_cada_codigo_se_explica(codigo: int, debe_decir: str) -> None:
    with pytest.raises(ReescrituraFallida, match=debe_decir):
        Servidor(httpx.Response(codigo, json={})).reescritor().reescribir("x", "y", 15)


def test_un_servidor_que_repite_la_clave_no_la_filtra_al_mensaje() -> None:
    with pytest.raises(ReescrituraFallida) as error:
        Servidor(httpx.Response(500), eco=True).reescritor().reescribir("x", "y", 15)

    assert CLAVE not in str(error.value) and CLAVE not in repr(error.value)
    assert error.value.__cause__ is None and error.value.__context__ is None


_CLAVES = st.text(
    alphabet=st.characters(min_codepoint=33, max_codepoint=126), min_size=8, max_size=40
)


class _Recolector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.mensajes: list[str] = []

    def emit(self, registro: logging.LogRecord) -> None:
        self.mensajes.append(registro.getMessage())


@settings(max_examples=50, deadline=None)
@given(_CLAVES)
def test_la_clave_no_aparece_ni_en_el_error_ni_en_los_registros(clave: str) -> None:
    registro = logging.getLogger()
    manejador = _Recolector()
    registro.addHandler(manejador)
    nivel = registro.level
    registro.setLevel(logging.DEBUG)
    try:
        with pytest.raises(ReescrituraFallida) as error:
            Servidor(httpx.Response(401), eco=True).reescritor(clave).reescribir("x", "y", 15)
    finally:
        registro.removeHandler(manejador)
        registro.setLevel(nivel)

    assert clave not in str(error.value)
    assert not [m for m in manejador.mensajes if clave in m]


def test_no_acepta_una_clave_vacia() -> None:
    with pytest.raises(ValueError, match="clave"):
        ReescritorOpenRouter("m", "")


def test_el_repr_no_muestra_la_clave() -> None:
    assert CLAVE not in repr(ReescritorOpenRouter("m", CLAVE))
