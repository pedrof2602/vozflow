import logging

import pytest

from vozflow import registro


@pytest.fixture(autouse=True)
def _limpiar_secretos() -> None:
    registro.olvidar_secretos()


def _emitir(mensaje: str, *args: object) -> logging.LogRecord:
    return logging.LogRecord("vozflow.prueba", logging.INFO, __file__, 1, mensaje, args, None)


def test_enmascara_un_secreto_registrado_en_el_mensaje() -> None:
    registro.registrar_secreto("sk-ant-1234567890")
    filtro = registro.FiltroDeSecretos()
    entrada = _emitir("llamando con la clave sk-ant-1234567890 al servicio")

    assert filtro.filter(entrada) is True
    assert "sk-ant-1234567890" not in entrada.getMessage()
    assert "***" in entrada.getMessage()


def test_enmascara_un_secreto_pasado_como_argumento() -> None:
    registro.registrar_secreto("clave-secreta")
    filtro = registro.FiltroDeSecretos()
    entrada = _emitir("cabecera %s", "Bearer clave-secreta")

    filtro.filter(entrada)

    assert "clave-secreta" not in entrada.getMessage()


def test_no_toca_mensajes_sin_secretos() -> None:
    registro.registrar_secreto("clave-secreta")
    filtro = registro.FiltroDeSecretos()
    entrada = _emitir("grabando %d segundos", 3)

    filtro.filter(entrada)

    assert entrada.getMessage() == "grabando 3 segundos"


def test_ignora_secretos_demasiado_cortos() -> None:
    # Un «secreto» de un carácter enmascararía medio mensaje: se rechaza.
    registro.registrar_secreto("a")
    filtro = registro.FiltroDeSecretos()
    entrada = _emitir("la casa")

    filtro.filter(entrada)

    assert entrada.getMessage() == "la casa"


def test_describir_texto_informa_el_largo_sin_revelar_el_contenido() -> None:
    texto = "esto es lo que dicté en voz alta"

    descripcion = registro.describir_texto(texto)

    assert "dicté" not in descripcion
    assert str(len(texto)) in descripcion


def test_configurar_registro_instala_el_filtro_en_el_manejador_raiz(
    caplog: pytest.LogCaptureFixture,
) -> None:
    registro.registrar_secreto("token-privado")
    registro.configurar_registro(logging.INFO)
    logger = logging.getLogger("vozflow.prueba")

    with caplog.at_level(logging.INFO, logger="vozflow.prueba"):
        logger.info("usando token-privado")

    assert "token-privado" not in caplog.text
