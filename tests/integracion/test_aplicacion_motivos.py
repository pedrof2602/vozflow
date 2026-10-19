"""Cuando un dictado falla: el motivo al historial y el aviso en palabras llanas (002, RP-021/022)."""

from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.dobles import ReescritorFalso
from tests.integracion.test_aplicacion import _dictar_mantenido
from tests.integracion.test_aplicacion_reescritura import Entorno
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.audio.captura import ErrorDeAudio
from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.insercion.puerto import ResultadoInsercion
from vozflow.mensajes import explicar
from vozflow.transcripcion.motor import ErrorDeTranscripcion, Transcripcion


@pytest.fixture
def crear() -> Iterator[Callable[..., Entorno]]:
    creados: list[Entorno] = []

    def fabrica(**kwargs: Any) -> Entorno:
        e = Entorno(**kwargs)
        creados.append(e)
        return e

    yield fabrica
    for e in creados:
        e.cerrar()


def _frase(codigo: str) -> str:
    explicacion = explicar(codigo)
    return f"{explicacion.que_paso} {explicacion.que_hacer}"


# ---- el pegado ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", ["pegado_fallo", "sin_portapapeles"])
def test_un_pegado_fallido_guarda_su_codigo_en_el_historial(crear, codigo: str) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.montaje.insertor.resultado = ResultadoInsercion.fallido("detalle técnico", codigo)

    _dictar_mantenido(e.montaje)

    guardado = e.historial.listar()[0]
    assert guardado.estado == "no_insertado" and guardado.motivo == codigo


@pytest.mark.parametrize("codigo", ["pegado_fallo", "sin_portapapeles"])
def test_el_aviso_de_un_pegado_fallido_sale_del_catalogo(crear, codigo: str) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.montaje.insertor.resultado = ResultadoInsercion.fallido("detalle técnico", codigo)

    _dictar_mantenido(e.montaje)

    assert e.montaje.avisos[-1] == _frase(codigo)
    assert "detalle técnico" not in e.montaje.avisos[-1]


def test_un_fallo_sin_codigo_usa_el_generico(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.montaje.insertor.resultado = ResultadoInsercion.fallido("algo raro")

    _dictar_mantenido(e.montaje)

    assert e.historial.listar()[0].motivo == "generico"
    assert e.montaje.avisos[-1] == _frase("generico")


def test_un_pegado_exitoso_no_guarda_motivo(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()

    _dictar_mantenido(e.montaje)

    guardado = e.historial.listar()[0]
    assert guardado.estado == "insertado" and guardado.motivo == ""


def test_el_texto_no_insertado_sigue_recuperable(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.montaje.insertor.resultado = ResultadoInsercion.fallido("x", "pegado_fallo")

    _dictar_mantenido(e.montaje)

    assert e.montaje.app.texto_sin_insertar == e.historial.listar()[0].texto_final
    assert e.montaje.sin_insertar


# ---- la traducción -------------------------------------------------------------------------------------------


def test_una_traduccion_fallida_guarda_traduccion_fallo(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso(fallo="Anthropic no respondió a tiempo"))
    e.encender(en_el_modo=False)

    e.dictar_traduciendo()

    guardado = e.historial.listar()[0]
    assert guardado.estado == "no_insertado" and guardado.motivo == "traduccion_fallo"


# ---- el micrófono y el modelo --------------------------------------------------------------------------------


@pytest.mark.parametrize("codigo", ["microfono_ocupado", "sin_microfono"])
def test_un_error_del_microfono_avisa_con_el_catalogo(crear, codigo: str) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.montaje.grabadora.fallar_al_iniciar = ErrorDeAudio("detalle técnico", codigo=codigo)

    e.montaje.escucha.pulsar(AccionDeAtajo.MANTENER)
    assert e.montaje.espera_estado(E.ERROR)

    assert e.montaje.avisos[-1] == _frase(codigo)


def test_un_modelo_faltante_avisa_con_el_catalogo(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()

    def roto(audio, pista, idioma) -> Transcripcion:  # type: ignore[no-untyped-def]
        raise ErrorDeTranscripcion("falta", codigo="modelo_faltante")

    e.montaje.motor.transcribir = roto

    _dictar_mantenido(e.montaje)

    assert e.montaje.avisos[-1] == _frase("modelo_faltante")


def test_el_error_de_audio_sin_codigo_explicito_es_micro_ocupado() -> None:
    assert ErrorDeAudio("x").codigo == "microfono_ocupado"


def test_el_error_de_transcripcion_sin_codigo_explicito_es_generico() -> None:
    assert ErrorDeTranscripcion("x").codigo == "generico"
