import pytest

from vozflow.dominio.dictado import (
    EstadoDelDictado,
    EstadoDictado,
    Evento,
    TransicionInvalida,
)

Estado = EstadoDelDictado


def _en(estado: EstadoDelDictado) -> EstadoDictado:
    """Lleva una máquina nueva hasta el estado pedido por el camino normal."""
    maquina = EstadoDictado()
    camino = {
        Estado.INACTIVO: [],
        Estado.ESCUCHANDO: [Evento.PULSAR],
        Estado.TRANSCRIBIENDO: [Evento.PULSAR, Evento.SOLTAR],
        Estado.INSERTANDO: [Evento.PULSAR, Evento.SOLTAR, Evento.TEXTO_LISTO],
        Estado.ERROR: [Evento.PULSAR, Evento.FALLO],
    }[estado]
    for evento in camino:
        maquina.manejar(evento)
    assert maquina.estado is estado
    return maquina


def _estado(maquina: EstadoDictado) -> EstadoDelDictado:
    # mypy no sabe que manejar() cambia el estado y estrecha el tipo tras un assert.
    return maquina.estado


def test_arranca_inactivo() -> None:
    assert EstadoDictado().estado is Estado.INACTIVO


def test_camino_feliz_recorre_todos_los_estados() -> None:
    maquina = EstadoDictado()
    visitados = [maquina.estado]

    for evento in (Evento.PULSAR, Evento.SOLTAR, Evento.TEXTO_LISTO, Evento.INSERTADO):
        assert maquina.manejar(evento) is True
        visitados.append(maquina.estado)

    assert visitados == [
        Estado.INACTIVO,
        Estado.ESCUCHANDO,
        Estado.TRANSCRIBIENDO,
        Estado.INSERTANDO,
        Estado.INACTIVO,
    ]


@pytest.mark.parametrize("desde", [Estado.ESCUCHANDO, Estado.TRANSCRIBIENDO])
def test_dictado_muy_corto_o_sin_voz_vuelve_a_inactivo(desde: EstadoDelDictado) -> None:
    maquina = _en(desde)

    assert maquina.manejar(Evento.SIN_VOZ) is True

    assert maquina.estado is Estado.INACTIVO


@pytest.mark.parametrize("desde", [Estado.ESCUCHANDO, Estado.TRANSCRIBIENDO, Estado.INSERTANDO])
def test_un_fallo_lleva_a_error(desde: EstadoDelDictado) -> None:
    maquina = _en(desde)

    maquina.manejar(Evento.FALLO)

    assert maquina.estado is Estado.ERROR


def test_desde_error_se_vuelve_a_inactivo() -> None:
    maquina = _en(Estado.ERROR)

    maquina.manejar(Evento.REINICIAR)

    assert maquina.estado is Estado.INACTIVO


def test_desde_error_pulsar_empieza_un_dictado_nuevo() -> None:
    maquina = _en(Estado.ERROR)

    assert maquina.manejar(Evento.PULSAR) is True

    assert maquina.estado is Estado.ESCUCHANDO


@pytest.mark.parametrize("desde", [Estado.TRANSCRIBIENDO, Estado.INSERTANDO])
def test_pulsar_durante_el_procesamiento_se_ignora(desde: EstadoDelDictado) -> None:
    maquina = _en(desde)

    assert maquina.manejar(Evento.PULSAR) is False

    assert maquina.estado is desde


@pytest.mark.parametrize(
    "estado", [Estado.INACTIVO, Estado.TRANSCRIBIENDO, Estado.INSERTANDO, Estado.ERROR]
)
def test_soltar_fuera_de_escuchando_se_ignora(estado: EstadoDelDictado) -> None:
    maquina = _en(estado)

    assert maquina.manejar(Evento.SOLTAR) is False

    assert maquina.estado is estado


def test_pulsar_mientras_escucha_se_ignora_por_la_repeticion_de_tecla() -> None:
    maquina = _en(Estado.ESCUCHANDO)

    assert maquina.manejar(Evento.PULSAR) is False

    assert maquina.estado is Estado.ESCUCHANDO


def test_alternar_empieza_y_termina_la_grabacion() -> None:
    maquina = EstadoDictado()

    assert maquina.manejar(Evento.ALTERNAR) is True
    assert _estado(maquina) is Estado.ESCUCHANDO
    assert maquina.manejar(Evento.ALTERNAR) is True
    assert _estado(maquina) is Estado.TRANSCRIBIENDO


@pytest.mark.parametrize("estado", [Estado.TRANSCRIBIENDO, Estado.INSERTANDO])
def test_alternar_durante_el_procesamiento_se_ignora(estado: EstadoDelDictado) -> None:
    maquina = _en(estado)

    assert maquina.manejar(Evento.ALTERNAR) is False

    assert maquina.estado is estado


@pytest.mark.parametrize(
    ("estado", "evento"),
    [
        (Estado.INACTIVO, Evento.TEXTO_LISTO),
        (Estado.INACTIVO, Evento.INSERTADO),
        (Estado.ESCUCHANDO, Evento.TEXTO_LISTO),
        (Estado.TRANSCRIBIENDO, Evento.INSERTADO),
        (Estado.INACTIVO, Evento.REINICIAR),
    ],
)
def test_un_evento_interno_fuera_de_lugar_es_un_error_de_programa(
    estado: EstadoDelDictado, evento: Evento
) -> None:
    maquina = _en(estado)

    with pytest.raises(TransicionInvalida):
        maquina.manejar(evento)

    assert maquina.estado is estado


def test_avisa_cada_cambio_de_estado_y_no_los_ignorados() -> None:
    cambios: list[tuple[EstadoDelDictado, EstadoDelDictado]] = []
    maquina = EstadoDictado(al_cambiar=lambda antes, despues: cambios.append((antes, despues)))

    maquina.manejar(Evento.SOLTAR)  # se ignora
    maquina.manejar(Evento.PULSAR)
    maquina.manejar(Evento.SOLTAR)

    assert cambios == [
        (Estado.INACTIVO, Estado.ESCUCHANDO),
        (Estado.ESCUCHANDO, Estado.TRANSCRIBIENDO),
    ]
