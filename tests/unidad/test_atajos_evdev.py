"""Escucha de teclas con evdev: análisis de nombres, máquina de estados y dispositivos."""

import logging
import threading
import time
from collections.abc import Iterator

import pytest
from evdev import ecodes

from tests.dobles import Reloj, TecladoFalso
from vozflow.atajos.evdev import (
    Combinacion,
    DispositivoDeEntrada,
    EscuchaEvdev,
    MaquinaDeTeclas,
    SinPermisoDeTeclado,
    SinTeclados,
    es_teclado_real,
    parsear_atajo,
)
from vozflow.atajos.puerto import AccionDeAtajo, EventoDeAtajo, FaseDeAtajo

M, A = AccionDeAtajo.MANTENER, AccionDeAtajo.ALTERNAR
P, S = FaseDeAtajo.PULSADO, FaseDeAtajo.SOLTADO

CTRL_D = ecodes.KEY_RIGHTCTRL
CTRL_I = ecodes.KEY_LEFTCTRL
ALT_I = ecodes.KEY_LEFTALT
SHIFT_I = ecodes.KEY_LEFTSHIFT
ESPACIO = ecodes.KEY_SPACE
TECLA_D = ecodes.KEY_D
TECLA_C = ecodes.KEY_C
ABAJO, ARRIBA, REPITE = 1, 0, 2

# ---- análisis de nombres de tecla --------------------------------------------------------------


@pytest.mark.parametrize(
    ("texto", "tecla", "modificadores", "solo"),
    [
        ("RightCtrl", ecodes.KEY_RIGHTCTRL, set(), True),
        ("rightctrl", ecodes.KEY_RIGHTCTRL, set(), True),
        ("RightAlt", ecodes.KEY_RIGHTALT, set(), True),
        ("RightShift", ecodes.KEY_RIGHTSHIFT, set(), True),
        ("RightSuper", ecodes.KEY_RIGHTMETA, set(), True),
        ("Ctrl+Alt+Space", ESPACIO, {"ctrl", "alt"}, False),
        ("<Control><Alt>space", ESPACIO, {"ctrl", "alt"}, False),
        ("CTRL+ALT+d", TECLA_D, {"ctrl", "alt"}, False),
        ("<Super>d", TECLA_D, {"super"}, False),
        ("F9", ecodes.KEY_F9, set(), False),
        ("<Control>F12", ecodes.KEY_F12, {"ctrl"}, False),
        ("ScrollLock", ecodes.KEY_SCROLLLOCK, set(), False),
        ("Shift+Control+7", ecodes.KEY_7, {"shift", "ctrl"}, False),
    ],
)
def test_entiende_los_nombres_de_tecla_de_gnome_del_portal_y_de_evdev(
    texto: str, tecla: int, modificadores: set[str], solo: bool
) -> None:
    assert parsear_atajo(texto) == Combinacion(tecla, frozenset(modificadores), solo)


@pytest.mark.parametrize(
    "texto", ["", "Ctrl", "Control+Alt", "TeclaQueNoExiste", "Ctrl+Alt+Nada", "+", "<>"]
)
def test_rechaza_nombres_que_no_son_una_combinacion_valida(texto: str) -> None:
    with pytest.raises(ValueError, match=r"atajo|tecla|modificador"):
        parsear_atajo(texto)


# ---- máquina de estados: combinaciones con tecla ---------------------------------------------------


def _maquina(**acciones: str) -> MaquinaDeTeclas:
    return MaquinaDeTeclas({AccionDeAtajo(a): parsear_atajo(t) for a, t in acciones.items()})


def _tecla(
    maquina: MaquinaDeTeclas, codigo: int, valor: int, ahora: float = 0.0, d: str = "kb"
) -> list[EventoDeAtajo]:
    return maquina.tecla(d, codigo, valor, ahora)


def test_una_combinacion_se_activa_al_apretar_su_tecla_con_los_modificadores() -> None:
    m = _maquina(alternar="Ctrl+Alt+Space")

    assert _tecla(m, CTRL_I, ABAJO) == []
    assert _tecla(m, ALT_I, ABAJO) == []
    assert _tecla(m, ESPACIO, ABAJO) == [EventoDeAtajo(A, P)]
    assert _tecla(m, ESPACIO, ARRIBA) == [EventoDeAtajo(A, S)]


def test_sin_los_modificadores_exactos_no_se_activa() -> None:
    m = _maquina(alternar="Ctrl+Alt+Space")

    assert _tecla(m, ESPACIO, ABAJO) == []  # sin modificadores
    _tecla(m, ESPACIO, ARRIBA)
    _tecla(m, CTRL_I, ABAJO)
    assert _tecla(m, ESPACIO, ABAJO) == []  # falta Alt
    _tecla(m, ESPACIO, ARRIBA)
    _tecla(m, ALT_I, ABAJO)
    _tecla(m, SHIFT_I, ABAJO)
    assert _tecla(m, ESPACIO, ABAJO) == []  # sobra Shift


def test_cualquier_lado_del_modificador_sirve() -> None:
    m = _maquina(alternar="Ctrl+Alt+Space")
    _tecla(m, CTRL_D, ABAJO)
    _tecla(m, ecodes.KEY_RIGHTALT, ABAJO)

    assert _tecla(m, ESPACIO, ABAJO) == [EventoDeAtajo(A, P)]


def test_soltar_un_modificador_requerido_tambien_suelta_el_atajo() -> None:
    m = _maquina(mantener="Ctrl+Alt+d")
    _tecla(m, CTRL_I, ABAJO)
    _tecla(m, ALT_I, ABAJO)
    _tecla(m, TECLA_D, ABAJO)

    assert _tecla(m, CTRL_I, ARRIBA) == [EventoDeAtajo(M, S)]
    assert _tecla(m, TECLA_D, ARRIBA) == []  # ya estaba suelto


def test_la_repeticion_de_una_tecla_apretada_no_es_otra_pulsacion() -> None:
    m = _maquina(mantener="F9")
    assert _tecla(m, ecodes.KEY_F9, ABAJO) == [EventoDeAtajo(M, P)]

    assert [_tecla(m, ecodes.KEY_F9, REPITE) for _ in range(5)] == [[]] * 5
    assert _tecla(m, ecodes.KEY_F9, ARRIBA) == [EventoDeAtajo(M, S)]


def test_otras_teclas_no_hacen_nada() -> None:
    m = _maquina(mantener="F9")

    assert _tecla(m, TECLA_C, ABAJO) == []
    assert _tecla(m, TECLA_C, ARRIBA) == []


# ---- máquina de estados: un modificador solo ------------------------------------------------------------


def test_un_modificador_solo_se_activa_tras_250_ms_sin_tocar_otra_tecla() -> None:
    m = _maquina(mantener="RightCtrl")

    assert _tecla(m, CTRL_D, ABAJO, 0.0) == []
    assert m.vencimiento() == pytest.approx(0.25)
    assert m.tick(0.2) == []
    assert m.tick(0.25) == [EventoDeAtajo(M, P)]
    assert m.vencimiento() is None
    assert _tecla(m, CTRL_D, ARRIBA, 1.0) == [EventoDeAtajo(M, S)]


def test_un_modificador_soltado_antes_de_250_ms_no_cuenta() -> None:
    m = _maquina(mantener="RightCtrl")
    _tecla(m, CTRL_D, ABAJO, 0.0)

    assert _tecla(m, CTRL_D, ARRIBA, 0.1) == []
    assert m.tick(1.0) == []
    assert m.vencimiento() is None


def test_usar_el_modificador_en_otro_atajo_no_dispara_el_dictado() -> None:
    m = _maquina(mantener="RightCtrl")
    _tecla(m, CTRL_D, ABAJO, 0.0)

    assert _tecla(m, TECLA_C, ABAJO, 0.05) == []  # Ctrl derecho + C
    assert m.tick(1.0) == []
    assert _tecla(m, CTRL_D, ARRIBA, 1.1) == []


def test_si_ya_habia_otra_tecla_apretada_el_modificador_solo_no_cuenta() -> None:
    m = _maquina(mantener="RightCtrl")
    _tecla(m, SHIFT_I, ABAJO, 0.0)

    _tecla(m, CTRL_D, ABAJO, 0.1)

    assert m.vencimiento() is None


def test_ya_activo_apretar_otra_tecla_no_corta_el_dictado() -> None:
    m = _maquina(mantener="RightCtrl")
    _tecla(m, CTRL_D, ABAJO, 0.0)
    m.tick(0.3)

    assert _tecla(m, TECLA_C, ABAJO, 0.5) == []
    assert _tecla(m, CTRL_D, ARRIBA, 0.6) == [EventoDeAtajo(M, S)]


# ---- varios dispositivos y desconexión ----------------------------------------------------------------------


def test_las_teclas_de_varios_teclados_se_suman() -> None:
    m = _maquina(alternar="Ctrl+Alt+Space")
    _tecla(m, CTRL_I, ABAJO, d="interno")
    _tecla(m, ALT_I, ABAJO, d="externo")

    assert _tecla(m, ESPACIO, ABAJO, d="externo") == [EventoDeAtajo(A, P)]


def test_un_teclado_que_se_desconecta_suelta_lo_que_tenia_apretado() -> None:
    m = _maquina(mantener="F9")
    _tecla(m, ecodes.KEY_F9, ABAJO, d="externo")

    assert m.dispositivo_perdido("externo", 1.0) == [EventoDeAtajo(M, S)]


def test_perder_un_teclado_sin_teclas_apretadas_no_emite_nada() -> None:
    m = _maquina(mantener="F9")

    assert m.dispositivo_perdido("externo", 1.0) == []


def test_perder_el_teclado_durante_un_modificador_pendiente_lo_cancela() -> None:
    m = _maquina(mantener="RightCtrl")
    _tecla(m, CTRL_D, ABAJO, 0.0)

    assert m.dispositivo_perdido("kb", 0.1) == []
    assert m.tick(1.0) == []


def test_no_se_pierde_la_tecla_si_otro_teclado_la_sigue_apretando() -> None:
    m = _maquina(mantener="F9")
    _tecla(m, ecodes.KEY_F9, ABAJO, d="a")
    _tecla(m, ecodes.KEY_F9, ABAJO, d="b")

    assert m.dispositivo_perdido("a", 1.0) == []
    assert _tecla(m, ecodes.KEY_F9, ARRIBA, d="b") == [EventoDeAtajo(M, S)]


# ---- qué dispositivos se escuchan ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("nombre", "esperado"),
    [
        ("AT Translated Set 2 keyboard", True),
        ("Telink Wireless Receiver", True),
        ("Logitech K380", True),
        ("ydotoold virtual device", False),
        ("YDOTOOLD VIRTUAL DEVICE", False),
        ("Virtual keyboard", False),
        ("Power Button", False),
        ("Sleep Button", False),
        ("Video Bus", False),
    ],
)
def test_solo_se_escuchan_los_teclados_reales(nombre: str, esperado: bool) -> None:
    teclas = (
        {ecodes.KEY_A, ecodes.KEY_LEFTCTRL, ecodes.KEY_SPACE}
        if nombre not in ("Power Button", "Sleep Button", "Video Bus")
        else {ecodes.KEY_POWER}
    )

    assert es_teclado_real(nombre, teclas) is esperado


# ---- el adaptador completo, con dispositivos simulados --------------------------------------------------------------


@pytest.fixture
def teclados() -> Iterator[list[TecladoFalso]]:
    lista: list[TecladoFalso] = []
    yield lista
    for teclado in lista:
        teclado.destruir()


def _nuevo(
    teclados: list[TecladoFalso], nombre: str = "AT Translated Set 2 keyboard"
) -> TecladoFalso:
    teclado = TecladoFalso(f"/dev/input/event{len(teclados) + 4}", nombre)
    teclados.append(teclado)
    return teclado


def _escucha(
    teclados: list[TecladoFalso], reloj: Reloj | None = None, **argumentos: object
) -> EscuchaEvdev:
    return EscuchaEvdev(
        listar_dispositivos=lambda: list(teclados),
        reloj=reloj or Reloj(),
        con_hilo=False,
        **argumentos,  # type: ignore[arg-type]
    )


def test_lee_un_teclado_y_traduce_las_teclas_a_eventos(teclados: list[TecladoFalso]) -> None:
    teclado = _nuevo(teclados)
    recibidos: list[EventoDeAtajo] = []
    escucha = _escucha(teclados)
    escucha.iniciar({M: "F9"}, recibidos.append)

    teclado.enviar((ecodes.KEY_F9, ABAJO))
    escucha.bombear()
    teclado.enviar((ecodes.KEY_F9, ARRIBA))
    escucha.bombear()

    assert recibidos == [EventoDeAtajo(M, P), EventoDeAtajo(M, S)]
    escucha.detener()


def test_ignora_el_teclado_virtual_de_ydotoold_y_lo_cierra(teclados: list[TecladoFalso]) -> None:
    real = _nuevo(teclados)
    virtual = _nuevo(teclados, "ydotoold virtual device")
    recibidos: list[EventoDeAtajo] = []
    escucha = _escucha(teclados)
    escucha.iniciar({M: "F9"}, recibidos.append)

    virtual.enviar((ecodes.KEY_F9, ABAJO))  # lo que vozflow mismo escribe con ydotool
    escucha.bombear()

    assert recibidos == []
    assert virtual.cerrado is True and real.cerrado is False
    escucha.detener()


def test_escucha_todos_los_teclados_reales(teclados: list[TecladoFalso]) -> None:
    interno = _nuevo(teclados)
    externo = _nuevo(teclados, "Telink Wireless Receiver")
    recibidos: list[EventoDeAtajo] = []
    escucha = _escucha(teclados)
    escucha.iniciar({A: "Ctrl+Alt+Space"}, recibidos.append)

    interno.enviar((ecodes.KEY_LEFTCTRL, ABAJO), (ecodes.KEY_LEFTALT, ABAJO))
    externo.enviar((ecodes.KEY_SPACE, ABAJO))
    escucha.bombear()

    assert recibidos == [EventoDeAtajo(A, P)]
    escucha.detener()


def test_un_modificador_solo_se_activa_cuando_pasan_250_ms(teclados: list[TecladoFalso]) -> None:
    teclado = _nuevo(teclados)
    reloj = Reloj()
    recibidos: list[EventoDeAtajo] = []
    escucha = _escucha(teclados, reloj)
    escucha.iniciar({M: "RightCtrl"}, recibidos.append)

    teclado.enviar((ecodes.KEY_RIGHTCTRL, ABAJO))
    escucha.bombear()
    assert recibidos == []

    reloj.ahora = 0.3
    escucha.bombear()
    assert recibidos == [EventoDeAtajo(M, P)]
    escucha.detener()


def test_un_teclado_desconectado_suelta_la_tecla_y_la_escucha_sigue(
    teclados: list[TecladoFalso],
) -> None:
    interno = _nuevo(teclados)
    externo = _nuevo(teclados, "Telink Wireless Receiver")
    recibidos: list[EventoDeAtajo] = []
    escucha = _escucha(teclados)
    escucha.iniciar({M: "F9"}, recibidos.append)
    externo.enviar((ecodes.KEY_F9, ABAJO))
    escucha.bombear()

    externo.desconectado = True
    externo.enviar()  # despierta el select
    escucha.bombear()
    interno.enviar((ecodes.KEY_F9, ABAJO))
    escucha.bombear()

    assert recibidos[:2] == [EventoDeAtajo(M, P), EventoDeAtajo(M, S)]  # nunca queda «pegada»
    assert recibidos[2:] == [EventoDeAtajo(M, P)]  # y el otro teclado sigue funcionando
    escucha.detener()


def test_detecta_un_teclado_que_se_conecta_despues(teclados: list[TecladoFalso]) -> None:
    _nuevo(teclados)
    reloj = Reloj()
    recibidos: list[EventoDeAtajo] = []
    escucha = _escucha(teclados, reloj, intervalo_de_busqueda_s=2.0)
    escucha.iniciar({M: "F9"}, recibidos.append)
    nuevo = _nuevo(teclados, "Teclado USB")

    nuevo.enviar((ecodes.KEY_F9, ABAJO))
    escucha.bombear()
    assert recibidos == []  # aún no lo conoce

    reloj.ahora = 2.5
    escucha.bombear()  # vuelve a buscar y lo encuentra
    nuevo.enviar((ecodes.KEY_F9, ARRIBA))
    nuevo.enviar((ecodes.KEY_F9, ABAJO))
    escucha.bombear()

    assert EventoDeAtajo(M, P) in recibidos
    escucha.detener()


def test_nunca_toma_el_teclado_en_exclusivo(teclados: list[TecladoFalso]) -> None:
    teclado = _nuevo(teclados)
    escucha = _escucha(teclados)

    escucha.iniciar({M: "F9"}, lambda _: None)  # si llamara a grab(), la prueba fallaría
    teclado.enviar((ecodes.KEY_F9, ABAJO))
    escucha.bombear()
    escucha.detener()


def test_no_registra_ninguna_pulsacion(
    teclados: list[TecladoFalso], caplog: pytest.LogCaptureFixture
) -> None:
    teclado = _nuevo(teclados)
    escucha = _escucha(teclados)
    escucha.iniciar({M: "F9"}, lambda _: None)

    with caplog.at_level(logging.DEBUG):
        teclado.enviar((ecodes.KEY_F9, ABAJO), (ecodes.KEY_A, ABAJO), (ecodes.KEY_A, ARRIBA))
        escucha.bombear()

    mensajes = " ".join(r.getMessage() for r in caplog.records if r.name.startswith("vozflow"))
    assert "KEY_" not in mensajes and str(ecodes.KEY_F9) not in mensajes
    escucha.detener()


def test_sin_teclados_dice_que_no_hay_nada_que_escuchar() -> None:
    escucha = EscuchaEvdev(listar_dispositivos=lambda: [], con_hilo=False)

    with pytest.raises(SinTeclados):
        escucha.iniciar({M: "F9"}, lambda _: None)


def test_sin_permiso_explica_como_arreglarlo() -> None:
    def sin_permiso() -> list[DispositivoDeEntrada]:
        raise SinPermisoDeTeclado("No se puede leer /dev/input")

    escucha = EscuchaEvdev(listar_dispositivos=sin_permiso, con_hilo=False)

    with pytest.raises(SinPermisoDeTeclado, match="input"):
        escucha.iniciar({M: "F9"}, lambda _: None)


def test_un_atajo_con_nombre_invalido_se_rechaza_al_iniciar(teclados: list[TecladoFalso]) -> None:
    _nuevo(teclados)

    with pytest.raises(ValueError, match="tecla"):
        _escucha(teclados).iniciar({M: "TeclaQueNoExiste"}, lambda _: None)


# ---- el hilo real ----------------------------------------------------------------------------------------------------------


def _esperar(condicion, segundos: float = 3.0) -> bool:  # type: ignore[no-untyped-def]
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.01)
    return False


def test_el_hilo_lee_los_teclados_y_se_detiene_limpiamente(teclados: list[TecladoFalso]) -> None:
    teclado = _nuevo(teclados)
    recibidos: list[EventoDeAtajo] = []
    hilos_antes = threading.active_count()
    escucha = EscuchaEvdev(listar_dispositivos=lambda: list(teclados))

    escucha.iniciar({M: "F9"}, recibidos.append)
    teclado.enviar((ecodes.KEY_F9, ABAJO))
    assert _esperar(lambda: recibidos == [EventoDeAtajo(M, P)])
    teclado.enviar((ecodes.KEY_F9, ARRIBA))
    assert _esperar(lambda: len(recibidos) == 2)

    escucha.detener()
    assert threading.active_count() == hilos_antes
    assert teclado.cerrado is True
