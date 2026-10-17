"""El filtro de repeticiones: una tecla mantenida repite ``pulsado`` y eso no es otra pulsación."""

from vozflow.atajos.puerto import (
    AccionDeAtajo,
    Despachador,
    EventoDeAtajo,
    FaseDeAtajo,
    FiltroDeRepeticion,
)

M, A = AccionDeAtajo.MANTENER, AccionDeAtajo.ALTERNAR
P, S = FaseDeAtajo.PULSADO, FaseDeAtajo.SOLTADO


def _pasa(filtro: FiltroDeRepeticion, accion: AccionDeAtajo, fase: FaseDeAtajo) -> bool:
    return filtro.permitir(EventoDeAtajo(accion, fase))


# ---- mantener -----------------------------------------------------------------------------


def test_mantener_deja_pasar_pulsar_y_luego_soltar() -> None:
    filtro = FiltroDeRepeticion()

    assert _pasa(filtro, M, P) is True
    assert _pasa(filtro, M, S) is True


def test_mantener_ignora_los_pulsar_repetidos_de_una_tecla_apretada() -> None:
    filtro = FiltroDeRepeticion()

    resultados = [_pasa(filtro, M, P) for _ in range(5)]

    assert resultados == [True, False, False, False, False]


def test_mantener_ignora_un_soltar_sin_haber_pulsado() -> None:
    assert _pasa(FiltroDeRepeticion(), M, S) is False


def test_mantener_permite_un_nuevo_ciclo_tras_soltar() -> None:
    filtro = FiltroDeRepeticion()
    secuencia = [(M, P), (M, P), (M, S), (M, S), (M, P), (M, S)]

    assert [_pasa(filtro, a, f) for a, f in secuencia] == [True, False, True, False, True, True]


# ---- alternar ---------------------------------------------------------------------------------


def test_alternar_deja_pasar_un_pulsar_por_cada_pulsacion_y_nunca_el_soltar() -> None:
    filtro = FiltroDeRepeticion()
    secuencia = [(A, P), (A, S), (A, P), (A, S)]

    assert [_pasa(filtro, a, f) for a, f in secuencia] == [True, False, True, False]


def test_alternar_ignora_la_repeticion_mientras_la_tecla_sigue_apretada() -> None:
    filtro = FiltroDeRepeticion()
    secuencia = [(A, P), (A, P), (A, P), (A, S), (A, P)]

    assert [_pasa(filtro, a, f) for a, f in secuencia] == [True, False, False, False, True]


# ---- las acciones son independientes ------------------------------------------------------------


def test_mantener_y_alternar_no_se_interfieren() -> None:
    filtro = FiltroDeRepeticion()

    assert _pasa(filtro, M, P) is True
    assert _pasa(filtro, A, P) is True  # otra acción: no es una repetición
    assert _pasa(filtro, M, S) is True


def test_reiniciar_olvida_las_teclas_que_estaban_apretadas() -> None:
    filtro = FiltroDeRepeticion()
    _pasa(filtro, M, P)

    filtro.reiniciar()

    assert _pasa(filtro, M, P) is True


# ---- despachador ----------------------------------------------------------------------------------


def test_el_despachador_filtra_y_entrega_en_orden() -> None:
    recibidos: list[EventoDeAtajo] = []
    despachador = Despachador(recibidos.append)

    for fase in (P, P, S):
        despachador.emitir(M, fase)
    despachador.emitir(A, P)

    assert recibidos == [
        EventoDeAtajo(M, P),
        EventoDeAtajo(M, S),
        EventoDeAtajo(A, P),
    ]


def test_el_despachador_no_entrega_nada_tras_detenerse() -> None:
    recibidos: list[EventoDeAtajo] = []
    despachador = Despachador(recibidos.append)
    despachador.detener()

    despachador.emitir(M, P)

    assert recibidos == []


def test_un_error_en_quien_recibe_no_detiene_la_escucha() -> None:
    recibidos: list[EventoDeAtajo] = []

    def al_evento(evento: EventoDeAtajo) -> None:
        recibidos.append(evento)
        if len(recibidos) == 1:
            raise RuntimeError("falló quien me recibe")

    despachador = Despachador(al_evento)

    despachador.emitir(M, P)  # esta entrega lanza, pero no debe propagarse
    despachador.emitir(M, S)

    assert [e.fase for e in recibidos] == [P, S]


def test_al_detenerse_se_olvidan_las_teclas_apretadas() -> None:
    recibidos: list[EventoDeAtajo] = []
    despachador = Despachador(recibidos.append)
    despachador.emitir(M, P)
    despachador.detener()

    despachador.reanudar()
    despachador.emitir(M, P)

    assert [e.fase for e in recibidos] == [P, P]


# ---- traducir: se comporta como mantener ---------------------------------------------------


def test_traducir_deja_pasar_pulsar_y_luego_soltar() -> None:
    filtro = FiltroDeRepeticion()

    assert _pasa(filtro, AccionDeAtajo.TRADUCIR, P) is True
    assert _pasa(filtro, AccionDeAtajo.TRADUCIR, S) is True


def test_traducir_ignora_las_repeticiones_y_los_soltar_de_mas() -> None:
    filtro = FiltroDeRepeticion()
    assert _pasa(filtro, AccionDeAtajo.TRADUCIR, S) is False
    assert _pasa(filtro, AccionDeAtajo.TRADUCIR, P) is True

    assert _pasa(filtro, AccionDeAtajo.TRADUCIR, P) is False
    assert _pasa(filtro, AccionDeAtajo.TRADUCIR, S) is True


def test_las_tres_acciones_no_se_interfieren() -> None:
    filtro = FiltroDeRepeticion()

    assert _pasa(filtro, M, P) and _pasa(filtro, AccionDeAtajo.TRADUCIR, P)
    assert _pasa(filtro, A, P)
    assert _pasa(filtro, AccionDeAtajo.TRADUCIR, S) and _pasa(filtro, M, S)
    assert _pasa(filtro, A, S) is False
