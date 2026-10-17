"""Lo que queda en el historial después de cada dictado (T087)."""

import time

import pytest

from tests.integracion.test_aplicacion import Montaje, _dictar_mantenido
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.configuracion import ConfiguracionDeBase
from vozflow.insercion.puerto import ResultadoInsercion
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.historial import HistorialRepo
from vozflow.ventana.puerto import InfoVentana


class Entorno:
    def __init__(self, **montaje: object) -> None:
        self.base = abrir_base(":memory:")
        self.historial = HistorialRepo(self.base)
        self.montaje = Montaje(
            configuracion=ConfiguracionDeBase(self.base),
            historial=self.historial,
            **montaje,  # type: ignore[arg-type]
        )
        self.montaje.app.iniciar()

    def dictar(self) -> None:
        _dictar_mantenido(self.montaje)

    def cerrar(self) -> None:
        self.montaje.app.detener()


@pytest.fixture
def entorno() -> object:
    creados: list[Entorno] = []

    def crear(**montaje: object) -> Entorno:
        e = Entorno(**montaje)
        creados.append(e)
        return e

    yield crear
    for e in creados:
        e.cerrar()


def test_un_dictado_insertado_queda_guardado_con_sus_datos(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno(texto="eh hola mundo", ventana=InfoVentana("ptyxis", "titulo secreto", 3))

    e.dictar()

    (dictado,) = e.historial.listar()
    assert dictado.estado == "insertado"
    assert dictado.texto_crudo == "eh hola mundo" and dictado.texto_final == "Hola mundo."
    assert dictado.idioma == "es" and dictado.aplicacion == "ptyxis"
    assert dictado.duracion_audio_ms >= 1000 and dictado.duracion_proceso_ms >= 0
    assert dictado.reescrito is False and dictado.proveedor == ""


def test_guarda_el_modo_con_el_que_se_dicto(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno(ventana=InfoVentana("ptyxis", "x", 3))
    terminal = e.base.execute("SELECT id FROM modo WHERE nombre = 'Terminal'").fetchone()[0]
    e.base.execute("INSERT INTO asignacion (aplicacion, modo_id) VALUES ('ptyxis', ?)", (terminal,))

    e.dictar()

    assert e.historial.listar()[0].modo_id == terminal


def test_si_no_se_pudo_insertar_queda_guardado_para_recuperarlo(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno(texto="mensaje importante", resultado=ResultadoInsercion.fallido("sin ventana"))

    e.dictar()

    (dictado,) = e.historial.listar()
    assert dictado.estado == "no_insertado" and dictado.texto_final == "Mensaje importante."


def test_un_dictado_no_insertado_se_puede_reinsertar_despues(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno(resultado=ResultadoInsercion.fallido("sin ventana"))
    e.dictar()
    e.montaje.insertor.resultado = ResultadoInsercion.exito()
    id_ = e.historial.listar()[0].id

    resultado = e.historial.reinsertar(id_, e.montaje.insertor, e.montaje.insertor.insertados[0][1])

    assert resultado.insertado is True and e.historial.obtener(id_).estado == "insertado"


def test_un_dictado_vacio_no_se_guarda(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno(segundos=0.3)

    e.dictar()

    assert e.historial.contar() == 0


def test_borra_eso_no_se_guarda(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno(texto="escribe esto borra eso")

    e.dictar()

    assert e.historial.contar() == 0


def test_si_falla_el_microfono_no_hay_nada_que_guardar(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno()
    e.montaje.grabadora.fallar_al_iniciar = OSError("sin micrófono")

    e.montaje.escucha.pulsar(AccionDeAtajo.MANTENER)
    e.montaje.escucha.soltar(AccionDeAtajo.MANTENER)
    time.sleep(0.3)

    assert e.historial.contar() == 0


def test_con_el_historial_apagado_no_se_guarda_nada() -> None:
    base = abrir_base(":memory:")
    historial = HistorialRepo(base, activo=lambda: False)
    montaje = Montaje(configuracion=ConfiguracionDeBase(base), historial=historial)
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.insertor.insertados and historial.contar() == 0
    finally:
        montaje.app.detener()


def test_si_el_historial_falla_el_dictado_se_inserta_igual(entorno) -> None:  # type: ignore[no-untyped-def]
    e = entorno()

    def roto(**_: object) -> None:
        raise RuntimeError("disco lleno")

    e.montaje.app._historial.guardar = roto

    e.dictar()

    assert len(e.montaje.insertor.insertados) == 1
