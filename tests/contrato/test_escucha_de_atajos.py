"""Contrato de ``EscuchaDeAtajos`` (contracts/puertos.md, RF-001 a RF-004).

La misma batería corre contra el doble y contra cada adaptador real armado sobre su doble de
sistema (``evdev`` con teclados simulados, el atajo de GNOME con un servicio D-Bus simulado…).
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, field

import pytest
from evdev import ecodes

from tests.dobles import EscuchaFalsa, GSettingsFalso, Reloj, TecladoFalso
from tests.dobles_dbus import ConexionServidorFalsa, llamada_toggle
from vozflow.atajos.compuesta import EscuchaCompuesta
from vozflow.atajos.evdev import EscuchaEvdev
from vozflow.atajos.gnome import EscuchaDeGnome
from vozflow.atajos.gsettings import AtajoDeGnome
from vozflow.atajos.puerto import (
    AccionDeAtajo,
    AtajoOcupado,
    EscuchaDeAtajos,
    EventoDeAtajo,
    FaseDeAtajo,
)
from vozflow.servicio_dbus import ServicioDBus

M, A = AccionDeAtajo.MANTENER, AccionDeAtajo.ALTERNAR
P, S = FaseDeAtajo.PULSADO, FaseDeAtajo.SOLTADO
ATAJOS = {M: "RightCtrl", A: "<Control><Alt>space"}


@dataclass
class Montaje:
    """Una escucha lista para probar y la forma de simular lo que hace la persona."""

    escucha: EscuchaDeAtajos
    pulsar: Callable[[AccionDeAtajo], None]
    soltar: Callable[[AccionDeAtajo], None]
    recibidos: list[EventoDeAtajo] = field(default_factory=list)
    ocupar: Callable[[str], None] | None = None
    limpiar: Callable[[], None] | None = None


def _doble() -> Montaje:
    escucha = EscuchaFalsa()
    return Montaje(escucha, escucha.pulsar, escucha.soltar, ocupar=escucha.ocupar)


def _teclas_de_evdev(
    escucha: EscuchaEvdev, teclado: TecladoFalso, reloj: Reloj
) -> dict[AccionDeAtajo, tuple[Callable[[], None], Callable[[], None]]]:
    """Cómo se aprietan y se sueltan los atajos de ``ATAJOS`` en el teclado simulado."""
    abajo, arriba = 1, 0

    def pulsar_mantener() -> None:
        teclado.enviar((ecodes.KEY_RIGHTCTRL, abajo))
        escucha.bombear()
        reloj.ahora += 0.3  # un modificador solo cuenta tras 250 ms sin tocar otra tecla
        escucha.bombear()

    def soltar_mantener() -> None:
        teclado.enviar((ecodes.KEY_RIGHTCTRL, arriba))
        escucha.bombear()

    def pulsar_alternar() -> None:
        teclado.enviar(
            (ecodes.KEY_LEFTCTRL, abajo), (ecodes.KEY_LEFTALT, abajo), (ecodes.KEY_SPACE, abajo)
        )
        escucha.bombear()

    def soltar_alternar() -> None:
        teclado.enviar(
            (ecodes.KEY_SPACE, arriba), (ecodes.KEY_LEFTALT, arriba), (ecodes.KEY_LEFTCTRL, arriba)
        )
        escucha.bombear()

    return {M: (pulsar_mantener, soltar_mantener), A: (pulsar_alternar, soltar_alternar)}


def _evdev() -> Montaje:
    """El adaptador de evdev sobre un teclado simulado; la persona se simula con teclas."""
    teclado = TecladoFalso("/dev/input/event4", "AT Translated Set 2 keyboard")
    reloj = Reloj()
    escucha = EscuchaEvdev(listar_dispositivos=lambda: [teclado], reloj=reloj, con_hilo=False)
    teclas = _teclas_de_evdev(escucha, teclado, reloj)
    return Montaje(
        escucha,
        pulsar=lambda accion: teclas[accion][0](),
        soltar=lambda accion: teclas[accion][1](),
        limpiar=teclado.destruir,
    )


def _compuesta() -> Montaje:
    """La escucha completa, como la arma ``crear_escucha``: GNOME para alternar, evdev para mantener."""
    teclado = TecladoFalso("/dev/input/event4", "AT Translated Set 2 keyboard")
    reloj = Reloj()
    evdev = EscuchaEvdev(listar_dispositivos=lambda: [teclado], reloj=reloj, con_hilo=False)
    teclas = _teclas_de_evdev(evdev, teclado, reloj)
    gsettings = GSettingsFalso()
    servicios: list[ServicioDBus] = []

    def crear_servicio(al_alternar: Callable[[], None]) -> ServicioDBus:
        servicios.append(ServicioDBus(al_alternar, abrir_conexion=ConexionServidorFalsa))
        return servicios[-1]

    gnome = EscuchaDeGnome(atajo=AtajoDeGnome(ejecutar=gsettings), crear_servicio=crear_servicio)
    escucha = EscuchaCompuesta({A: [lambda: gnome], M: [lambda: evdev]})

    def pulsar(accion: AccionDeAtajo) -> None:
        if accion is M:
            teclas[M][0]()
        else:  # lo que hace `dbus-send` cuando GNOME detecta el atajo
            servicios[-1]._atender(llamada_toggle(sin_respuesta=True))

    def soltar(accion: AccionDeAtajo) -> None:
        if accion is M:
            teclas[M][1]()  # el atajo de GNOME no avisa al soltar: no hay nada que simular

    def ocupar(atajo: str) -> None:
        gsettings.precargar("org.gnome.desktop.wm.keybindings", "otra-funcion", f"['{atajo}']")

    return Montaje(escucha, pulsar, soltar, ocupar=ocupar, limpiar=teclado.destruir)


@pytest.fixture(
    params=[
        pytest.param(_doble, id="doble"),
        pytest.param(_evdev, id="evdev"),
        pytest.param(_compuesta, id="completa"),
    ]
)
def montaje(request: pytest.FixtureRequest) -> Iterator[Montaje]:
    fabrica: Callable[[], Montaje] = request.param
    montaje = fabrica()
    yield montaje
    montaje.escucha.detener()
    if montaje.limpiar is not None:
        montaje.limpiar()


def _iniciar(montaje: Montaje) -> None:
    montaje.escucha.iniciar(ATAJOS, montaje.recibidos.append)


# ---- mantener ------------------------------------------------------------------------------


def test_mantener_entrega_pulsado_y_despues_soltado(montaje: Montaje) -> None:
    _iniciar(montaje)

    montaje.pulsar(M)
    montaje.soltar(M)

    assert montaje.recibidos == [EventoDeAtajo(M, P), EventoDeAtajo(M, S)]


def test_mantener_ignora_la_repeticion_de_una_tecla_apretada(montaje: Montaje) -> None:
    _iniciar(montaje)

    for _ in range(4):
        montaje.pulsar(M)
    montaje.soltar(M)

    assert montaje.recibidos == [EventoDeAtajo(M, P), EventoDeAtajo(M, S)]


def test_mantener_ignora_un_soltar_que_no_corresponde(montaje: Montaje) -> None:
    _iniciar(montaje)

    montaje.soltar(M)

    assert montaje.recibidos == []


# ---- alternar --------------------------------------------------------------------------------


def test_alternar_entrega_un_pulsado_por_cada_pulsacion_y_nunca_soltado(
    montaje: Montaje,
) -> None:
    _iniciar(montaje)

    for _ in range(2):
        montaje.pulsar(A)
        montaje.soltar(A)

    assert montaje.recibidos == [EventoDeAtajo(A, P), EventoDeAtajo(A, P)]


def test_las_dos_acciones_conviven(montaje: Montaje) -> None:
    _iniciar(montaje)

    montaje.pulsar(M)
    montaje.pulsar(A)
    montaje.soltar(A)
    montaje.soltar(M)

    assert montaje.recibidos == [
        EventoDeAtajo(M, P),
        EventoDeAtajo(A, P),
        EventoDeAtajo(M, S),
    ]


# ---- ciclo de vida --------------------------------------------------------------------------------


def test_tras_detener_ya_no_se_entregan_eventos(montaje: Montaje) -> None:
    _iniciar(montaje)
    montaje.escucha.detener()

    montaje.pulsar(M)

    assert montaje.recibidos == []


def test_detener_es_inofensivo_si_no_se_inicio_o_se_repite(montaje: Montaje) -> None:
    montaje.escucha.detener()
    _iniciar(montaje)
    montaje.escucha.detener()
    montaje.escucha.detener()


def test_se_puede_volver_a_iniciar_tras_detener(montaje: Montaje) -> None:
    _iniciar(montaje)
    montaje.escucha.detener()
    _iniciar(montaje)

    montaje.pulsar(M)

    assert montaje.recibidos == [EventoDeAtajo(M, P)]


def test_iniciar_dos_veces_seguidas_es_un_error_de_programa(montaje: Montaje) -> None:
    _iniciar(montaje)

    with pytest.raises(RuntimeError, match="ya está iniciada"):
        _iniciar(montaje)


# ---- atajo ocupado (RF-003) ------------------------------------------------------------------------


def test_una_combinacion_ya_usada_por_otra_funcion_es_atajo_ocupado(montaje: Montaje) -> None:
    if montaje.ocupar is None:
        pytest.skip("Este adaptador no puede saber si una combinación está ocupada")
    montaje.ocupar(ATAJOS[A])

    with pytest.raises(AtajoOcupado, match="Control"):
        _iniciar(montaje)
