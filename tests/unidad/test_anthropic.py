"""Reescritor de Anthropic: ``POST /v1/messages`` con la clave en ``x-api-key``."""

import json
import logging

import httpx
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from vozflow.llm.anthropic import ReescritorAnthropic
from vozflow.llm.puerto import ReescrituraFallida

CLAVE = "sk-ant-secreta-123456"


class Servidor:
    def __init__(self, respuesta: httpx.Response | Exception, eco: bool = False) -> None:
        self.respuesta = respuesta
        self.eco = eco
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        if self.eco:  # un servidor que repite en el cuerpo lo que recibió, clave incluida
            return httpx.Response(401, text=f"clave inválida: {pedido.headers.get('x-api-key')}")
        return self.respuesta

    def reescritor(
        self, clave: str = CLAVE, modelo: str = "claude-haiku-5-5"
    ) -> ReescritorAnthropic:
        return ReescritorAnthropic(modelo, clave, transporte=httpx.MockTransport(self))


def _bien(texto: str = "Texto reescrito.", motivo: str = "end_turn") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "type": "message",
            "role": "assistant",
            "content": [{"type": "text", "text": texto}],
            "stop_reason": motivo,
        },
    )


def test_manda_el_pedido_a_v1_messages_con_las_cabeceras_de_autenticacion() -> None:
    servidor = Servidor(_bien())

    servidor.reescritor().reescribir("hola mundo", "Corregí.", 15)

    (pedido,) = servidor.pedidos
    assert pedido.method == "POST" and str(pedido.url) == "https://api.anthropic.com/v1/messages"
    assert pedido.headers["x-api-key"] == CLAVE
    assert pedido.headers["anthropic-version"] == "2023-06-01"
    assert pedido.headers["content-type"] == "application/json"
    assert "authorization" not in pedido.headers


def test_el_cuerpo_lleva_modelo_instruccion_texto_y_un_tope_de_tokens() -> None:
    servidor = Servidor(_bien())

    servidor.reescritor(modelo="claude-haiku-5-5").reescribir("hola mundo", "Corregí.", 15)

    cuerpo = json.loads(servidor.pedidos[0].content)
    assert cuerpo["model"] == "claude-haiku-5-5"
    assert cuerpo["system"] == "Corregí."
    assert cuerpo["messages"] == [{"role": "user", "content": "hola mundo"}]
    assert 256 <= cuerpo["max_tokens"] <= 8192


def test_un_texto_largo_pide_mas_tokens_que_uno_corto() -> None:
    corto, largo = Servidor(_bien()), Servidor(_bien())

    corto.reescritor().reescribir("hola", "y", 15)
    largo.reescritor().reescribir("palabra " * 600, "y", 15)

    assert (
        json.loads(largo.pedidos[0].content)["max_tokens"]
        > json.loads(corto.pedidos[0].content)["max_tokens"]
    )


def test_une_los_bloques_de_texto_de_la_respuesta() -> None:
    respuesta = httpx.Response(
        200,
        json={
            "content": [
                {"type": "text", "text": "Uno. "},
                {"type": "thinking", "thinking": "no va"},
                {"type": "text", "text": "Dos."},
            ],
            "stop_reason": "end_turn",
        },
    )

    assert Servidor(respuesta).reescritor().reescribir("x", "y", 15) == "Uno. Dos."


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.ConnectError("sin red"),
        httpx.ReadTimeout("lento"),
        httpx.Response(200, json={"content": [], "stop_reason": "end_turn"}),
        httpx.Response(200, json={"content": [{"type": "text", "text": "  "}]}),
        httpx.Response(200, json={}),
        httpx.Response(200, text="no es json"),
        _bien("cortado", motivo="max_tokens"),
        _bien("rechazado", motivo="refusal"),
        httpx.Response(400, json={"error": {"type": "invalid_request_error", "message": "mal"}}),
        httpx.Response(401, json={"error": {"type": "authentication_error", "message": "x"}}),
        httpx.Response(403, json={"error": {"type": "permission_error", "message": "x"}}),
        httpx.Response(429, json={"error": {"type": "rate_limit_error", "message": "x"}}),
        httpx.Response(500, json={"error": {"type": "api_error", "message": "x"}}),
        httpx.Response(529, json={"error": {"type": "overloaded_error", "message": "x"}}),
    ],
)
def test_cualquier_problema_es_una_reescritura_fallida(
    respuesta: httpx.Response | Exception,
) -> None:
    with pytest.raises(ReescrituraFallida):
        Servidor(respuesta).reescritor().reescribir("hola", "Corregí.", 15)


@pytest.mark.parametrize(
    ("codigo", "debe_decir"),
    [(401, "clave"), (403, "clave"), (429, "límite|demasiad"), (500, "error"), (529, "error")],
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


class _Recolector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.mensajes: list[str] = []

    def emit(self, registro: logging.LogRecord) -> None:
        self.mensajes.append(registro.getMessage())


def test_no_acepta_una_clave_vacia() -> None:
    with pytest.raises(ValueError, match="clave"):
        ReescritorAnthropic("claude-haiku-5-5", "  ")


def test_el_repr_no_muestra_la_clave() -> None:
    assert CLAVE not in repr(ReescritorAnthropic("claude-haiku-5-5", CLAVE))
