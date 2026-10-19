"""Una tecla, una cosa: dictar sin IA, mejorar con IA, y mejorar y traducir (003, RT-002 a RT-005)."""

from collections.abc import Callable, Iterator

import pytest

from tests.dobles import ReescritorFalso
from tests.integracion.test_aplicacion import _esperar
from tests.integracion.test_aplicacion_reescritura import ClavesFalsas, Entorno
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.dominio.dictado import EstadoDelDictado as E

DICTAR, MEJORAR, TRADUCIR = (
    AccionDeAtajo.MANTENER,
    AccionDeAtajo.MEJORAR,
    AccionDeAtajo.TRADUCIR,
)


@pytest.fixture
def crear() -> Iterator[Callable[..., Entorno]]:
    creados: list[Entorno] = []

    def fabrica(**kwargs: object) -> Entorno:
        e = Entorno(**kwargs)  # type: ignore[arg-type]
        creados.append(e)
        return e

    yield fabrica
    for e in creados:
        e.cerrar()


def _dictar(e: Entorno, accion: AccionDeAtajo) -> None:
    """Mantiene y suelta la tecla; vuelve cuando el dictado terminó."""
    m = e.montaje
    m.escucha.pulsar(accion)
    assert m.espera_estado(E.ESCUCHANDO)
    m.escucha.soltar(accion)
    assert _esperar(lambda: m.app.estado in (E.INACTIVO, E.ERROR))


def _insertado(e: Entorno) -> str:
    return e.montaje.insertor.insertados[-1][0]


# ---- dictar: nunca usa la IA (RT-002) ----------------------------------------------------------------------------


def test_dictar_con_la_tecla_normal_no_llama_al_servicio_aunque_todo_este_activo(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender()  # asistente activo y, además, el modo con reescritura (como antes de la 003)

    _dictar(e, DICTAR)

    assert _insertado(e) == "Hola mundo." and e.reescritor.llamadas == []
    assert e.fabricados == []  # ni siquiera se prepara un cliente


def test_empezar_y_terminar_tampoco_usa_la_ia(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender()
    m = e.montaje

    m.escucha.pulsar(AccionDeAtajo.ALTERNAR)
    m.escucha.soltar(AccionDeAtajo.ALTERNAR)  # cada pulsación es completa
    assert m.espera_estado(E.ESCUCHANDO)
    m.escucha.pulsar(AccionDeAtajo.ALTERNAR)
    m.escucha.soltar(AccionDeAtajo.ALTERNAR)
    assert _esperar(lambda: m.app.estado in (E.INACTIVO, E.ERROR))

    assert _insertado(e) == "Hola mundo." and e.reescritor.llamadas == []


def test_dictar_sin_ia_no_guarda_proveedor_en_el_historial(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender()

    _dictar(e, DICTAR)

    dictado = e.historial.listar()[0]
    assert dictado.reescrito is False and dictado.proveedor == ""


# ---- mejorar (RT-003, RT-004) -------------------------------------------------------------------------------------


def test_mejorar_pule_el_texto_aunque_el_modo_no_lo_pida(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender(en_el_modo=False)  # el interruptor del modo ya no decide

    _dictar(e, MEJORAR)

    assert _insertado(e) == "Texto reescrito." and len(e.reescritor.llamadas) == 1


def test_mejorar_aplica_el_estilo_del_modo(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender(en_el_modo=False)
    e.modos.actualizar(e.modos.general().id, instruccion="tono profesional y breve")

    _dictar(e, MEJORAR)

    instruccion = e.reescritor.llamadas[0][1]
    assert "tono profesional y breve" in instruccion


def test_mejorar_no_traduce(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender(en_el_modo=False)

    _dictar(e, MEJORAR)

    instruccion = e.reescritor.llamadas[0][1]
    assert "No traduzcas" in instruccion and "Traducí todo" not in instruccion


def test_mejorar_deja_registrado_quien_lo_hizo(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender(en_el_modo=False)

    _dictar(e, MEJORAR)

    dictado = e.historial.listar()[0]
    assert dictado.reescrito is True and dictado.proveedor == "anthropic"


def test_mejorar_con_el_asistente_apagado_inserta_el_texto_limpio_y_avisa(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()

    _dictar(e, MEJORAR)  # nunca se prendió el asistente

    assert _insertado(e) == "Hola mundo." and e.reescritor.llamadas == []
    assert any("apagado" in aviso.lower() for aviso in e.montaje.avisos)
    assert e.historial.listar()[0].estado == "insertado"


def test_mejorar_sin_clave_inserta_el_texto_limpio_y_avisa(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(claves=ClavesFalsas())
    e.encender(en_el_modo=False)

    _dictar(e, MEJORAR)

    assert _insertado(e) == "Hola mundo."
    assert any("clave" in aviso.lower() for aviso in e.montaje.avisos)


def test_si_el_servicio_falla_mejorar_inserta_el_texto_limpio(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso(fallo="Anthropic no respondió a tiempo"))
    e.encender(en_el_modo=False)

    _dictar(e, MEJORAR)

    assert _insertado(e) == "Hola mundo."
    assert any("no respondió a tiempo" in aviso for aviso in e.montaje.avisos)
    assert e.historial.listar()[0].estado == "insertado"


def test_el_texto_mejorado_expande_los_atajos_de_texto_despues(crear) -> None:  # type: ignore[no-untyped-def]
    from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo

    e = crear(texto="gracias mi firma", reescritor=ReescritorFalso("Gracias. mi firma"))
    e.encender(en_el_modo=False)
    AtajosTextoRepo(e.base).agregar("mi firma", "Saludos, Pedro")

    _dictar(e, MEJORAR)

    assert "Saludos, Pedro" in _insertado(e)


# ---- mejorar y traducir (RT-005) -----------------------------------------------------------------------------------


def test_mejorar_y_traducir_pide_las_dos_cosas_en_una_sola_llamada(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender(en_el_modo=False)
    e.modos.actualizar(e.modos.general().id, instruccion="tono profesional")

    _dictar(e, TRADUCIR)

    assert len(e.reescritor.llamadas) == 1
    instruccion = e.reescritor.llamadas[0][1]
    assert "inglés" in instruccion and "tono profesional" in instruccion
    assert "mejor" in instruccion.lower() or "corregí" in instruccion.lower()
    assert _insertado(e) == "Texto reescrito."


def test_mejorar_y_traducir_sin_asistente_no_inserta_nada(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()

    _dictar(e, TRADUCIR)

    assert e.montaje.insertor.insertados == []
    assert e.montaje.app.estado is E.ERROR
    assert e.historial.listar()[0].estado == "no_insertado"


def test_si_falla_la_de_mejorar_y_traducir_el_texto_queda_en_el_historial(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso(fallo="Anthropic no respondió a tiempo"))
    e.encender(en_el_modo=False)

    _dictar(e, TRADUCIR)

    assert e.montaje.insertor.insertados == []
    assert e.historial.listar()[0].motivo == "traduccion_fallo"


# ---- qué se está haciendo mientras se graba (RT-008) -------------------------------------------------------------


def test_la_aplicacion_dice_la_intencion_mientras_graba_y_la_olvida_despues(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender(en_el_modo=False)
    m = e.montaje
    assert m.app.intencion_en_curso is None

    m.escucha.pulsar(MEJORAR)
    assert m.espera_estado(E.ESCUCHANDO)
    assert m.app.intencion_en_curso == "mejorar"
    m.escucha.soltar(MEJORAR)
    assert _esperar(lambda: m.app.estado in (E.INACTIVO, E.ERROR))

    assert m.app.intencion_en_curso is None


@pytest.mark.parametrize(
    ("accion", "esperada"),
    [(DICTAR, "dictar"), (AccionDeAtajo.ALTERNAR, "dictar"), (TRADUCIR, "traducir")],
)
def test_cada_tecla_marca_su_intencion(crear, accion, esperada) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    m = e.montaje

    m.escucha.pulsar(accion)
    assert m.espera_estado(E.ESCUCHANDO)

    assert m.app.intencion_en_curso == esperada
    m.escucha.soltar(accion)
    if accion is AccionDeAtajo.ALTERNAR:
        m.escucha.pulsar(accion)
        m.escucha.soltar(accion)
    assert _esperar(lambda: m.app.estado in (E.INACTIVO, E.ERROR))
