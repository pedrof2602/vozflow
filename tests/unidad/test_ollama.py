"""Reescritor de Ollama (local): ``POST /api/chat`` sin streaming."""

import json

import httpx
import pytest

from vozflow.llm.ollama import ReescritorOllama
from vozflow.llm.puerto import ReescrituraFallida

DIRECCION = "http://127.0.0.1:11434"


class Servidor:
    def __init__(self, respuesta: httpx.Response | Exception) -> None:
        self.respuesta = respuesta
        self.pedidos: list[httpx.Request] = []

    def __call__(self, pedido: httpx.Request) -> httpx.Response:
        self.pedidos.append(pedido)
        if isinstance(self.respuesta, Exception):
            raise self.respuesta
        return self.respuesta

    def reescritor(self, modelo: str = "llama3.2", direccion: str = DIRECCION) -> ReescritorOllama:
        return ReescritorOllama(modelo, direccion, transporte=httpx.MockTransport(self))


def _bien(texto: str = "Texto reescrito.") -> httpx.Response:
    return httpx.Response(
        200, json={"message": {"role": "assistant", "content": texto}, "done": True}
    )


def test_manda_el_pedido_a_api_chat_sin_streaming() -> None:
    servidor = Servidor(_bien())

    servidor.reescritor("llama3.2").reescribir("hola mundo", "Corregí.", 15)

    (pedido,) = servidor.pedidos
    cuerpo = json.loads(pedido.content)
    assert pedido.method == "POST" and str(pedido.url) == f"{DIRECCION}/api/chat"
    assert cuerpo["model"] == "llama3.2" and cuerpo["stream"] is False
    assert cuerpo["messages"] == [
        {"role": "system", "content": "Corregí."},
        {"role": "user", "content": "hola mundo"},
    ]


def test_pide_que_no_piense_en_voz_alta() -> None:
    servidor = Servidor(_bien())

    servidor.reescritor().reescribir("x", "y", 15)

    assert json.loads(servidor.pedidos[0].content)["think"] is False


def test_devuelve_el_contenido_sin_espacios_sobrantes() -> None:
    assert Servidor(_bien("  Hola.\n")).reescritor().reescribir("x", "y", 15) == "Hola."


def test_acepta_la_direccion_con_barra_final_y_otro_puerto() -> None:
    servidor = Servidor(_bien())

    servidor.reescritor(direccion="http://192.168.1.5:9999/").reescribir("x", "y", 15)

    assert str(servidor.pedidos[0].url) == "http://192.168.1.5:9999/api/chat"


@pytest.mark.parametrize(
    "respuesta",
    [
        httpx.ConnectError("sin servidor"),
        httpx.ConnectTimeout("lento"),
        httpx.ReadTimeout("lento"),
        httpx.RemoteProtocolError("cortado"),
        httpx.Response(200, json={"message": {"content": ""}}),
        httpx.Response(200, json={"message": {"content": "   \n"}}),
        httpx.Response(200, json={"message": {}}),
        httpx.Response(200, json={}),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, text="no es json"),
        httpx.Response(200, json={"message": {"content": "cortado"}, "done_reason": "length"}),
        httpx.Response(404, json={"error": "model 'llama3.2' not found"}),
        httpx.Response(500, text="boom"),
        httpx.Response(503, text="ocupado"),
    ],
)
def test_cualquier_problema_es_una_reescritura_fallida(
    respuesta: httpx.Response | Exception,
) -> None:
    with pytest.raises(ReescrituraFallida):
        Servidor(respuesta).reescritor().reescribir("hola", "Corregí.", 15)


def test_un_modelo_que_no_esta_instalado_se_explica() -> None:
    servidor = Servidor(httpx.Response(404, json={"error": "model 'x' not found"}))

    with pytest.raises(ReescrituraFallida, match="modelo"):
        servidor.reescritor("x").reescribir("hola", "y", 15)


def test_un_servidor_caido_se_explica() -> None:
    with pytest.raises(ReescrituraFallida, match="Ollama"):
        Servidor(httpx.ConnectError("no")).reescritor().reescribir("hola", "y", 15)


def test_el_tiempo_maximo_llega_al_cliente() -> None:
    capturado: dict[str, object] = {}

    def manejador(pedido: httpx.Request) -> httpx.Response:
        capturado.update(pedido.extensions["timeout"])
        return _bien()

    ReescritorOllama("m", DIRECCION, transporte=httpx.MockTransport(manejador)).reescribir(
        "x", "y", 7
    )

    assert capturado == {"connect": 7, "read": 7, "write": 7, "pool": 7}


def test_el_mensaje_de_error_no_incluye_el_texto_dictado() -> None:
    with pytest.raises(ReescrituraFallida) as error:
        Servidor(httpx.Response(500, text="eco: texto privado")).reescritor().reescribir(
            "texto privado", "y", 15
        )

    assert "texto privado" not in str(error.value)
