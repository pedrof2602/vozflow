"""La escucha completa: cada acción con su técnica, y la cadena de respaldo (T046)."""

from collections.abc import Callable, Mapping

import pytest

from tests.dobles import EscuchaFalsa
from vozflow.atajos import crear_escucha
from vozflow.atajos.compuesta import EscuchaCompuesta, NingunAdaptadorSirve
from vozflow.atajos.evdev import SinPermisoDeTeclado, SinTeclados
from vozflow.atajos.gsettings import ErrorDeGSettings
from vozflow.atajos.puerto import (
    AccionDeAtajo,
    AlEvento,
    AtajoOcupado,
    EscuchaDeAtajos,
    EventoDeAtajo,
    FaseDeAtajo,
)
from vozflow.servicio_dbus import InstanciaYaEnEjecucion

M, A = AccionDeAtajo.MANTENER, AccionDeAtajo.ALTERNAR
ATAJOS = {M: "RightCtrl", A: "<Control><Alt>space"}


class EscuchaQueFalla(EscuchaFalsa):
    def __init__(self, error: Exception, registro: list[str], nombre: str) -> None:
        super().__init__()
        self._error = error
        self._registro = registro
        self._nombre = nombre

    def iniciar(self, atajos: Mapping[AccionDeAtajo, str], al_evento: AlEvento) -> None:
        self._registro.append(f"iniciar {self._nombre}")
        raise self._error

    def detener(self) -> None:
        self._registro.append(f"detener {self._nombre}")


class EscuchaQueAvisa(EscuchaFalsa):
    def __init__(self, registro: list[str], nombre: str) -> None:
        super().__init__()
        self._registro = registro
        self._nombre = nombre
        self.atajos: Mapping[AccionDeAtajo, str] = {}

    def iniciar(self, atajos: Mapping[AccionDeAtajo, str], al_evento: AlEvento) -> None:
        self._registro.append(f"iniciar {self._nombre}")
        self.atajos = dict(atajos)
        super().iniciar(atajos, al_evento)

    def detener(self) -> None:
        self._registro.append(f"detener {self._nombre}")
        super().detener()


def _fabrica(escucha: EscuchaDeAtajos) -> Callable[[], EscuchaDeAtajos]:
    return lambda: escucha


# ---- cada acción con su técnica --------------------------------------------------------------------


def test_cada_accion_se_reparte_a_su_adaptador_con_solo_su_atajo() -> None:
    registro: list[str] = []
    gnome, evdev = EscuchaQueAvisa(registro, "gnome"), EscuchaQueAvisa(registro, "evdev")
    escucha = EscuchaCompuesta({A: [_fabrica(gnome)], M: [_fabrica(evdev)]})

    escucha.iniciar(ATAJOS, lambda _: None)

    assert gnome.atajos == {A: "<Control><Alt>space"}
    assert evdev.atajos == {M: "RightCtrl"}


def test_los_eventos_de_los_dos_adaptadores_llegan_a_quien_escucha() -> None:
    gnome, evdev = EscuchaFalsa(), EscuchaFalsa()
    recibidos: list[EventoDeAtajo] = []
    escucha = EscuchaCompuesta({A: [_fabrica(gnome)], M: [_fabrica(evdev)]})
    escucha.iniciar(ATAJOS, recibidos.append)

    evdev.pulsar(M)
    gnome.pulsar(A)
    evdev.soltar(M)

    assert recibidos == [
        EventoDeAtajo(M, FaseDeAtajo.PULSADO),
        EventoDeAtajo(A, FaseDeAtajo.PULSADO),
        EventoDeAtajo(M, FaseDeAtajo.SOLTADO),
    ]


def test_una_accion_sin_atajo_configurado_no_arranca_su_adaptador() -> None:
    registro: list[str] = []
    gnome, evdev = EscuchaQueAvisa(registro, "gnome"), EscuchaQueAvisa(registro, "evdev")
    escucha = EscuchaCompuesta({A: [_fabrica(gnome)], M: [_fabrica(evdev)]})

    escucha.iniciar({A: "<Control><Alt>space"}, lambda _: None)

    assert registro == ["iniciar gnome"]


# ---- cadena de respaldo ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        SinPermisoDeTeclado("sin permiso"),
        SinTeclados("no hay"),
        ErrorDeGSettings("gsettings falló"),
        AtajoOcupado("ocupado"),
    ],
)
def test_si_el_primer_adaptador_falla_se_pasa_al_siguiente(error: Exception) -> None:
    registro: list[str] = []
    primero = EscuchaQueFalla(error, registro, "primero")
    segundo = EscuchaQueAvisa(registro, "segundo")
    escucha = EscuchaCompuesta({M: [_fabrica(primero), _fabrica(segundo)]})

    escucha.iniciar({M: "RightCtrl"}, lambda _: None)

    assert registro == ["iniciar primero", "detener primero", "iniciar segundo"]


def test_si_ninguno_sirve_y_hubo_un_atajo_ocupado_se_informa_ese_error() -> None:
    registro: list[str] = []
    escucha = EscuchaCompuesta(
        {
            A: [
                _fabrica(
                    EscuchaQueFalla(AtajoOcupado("<Control><Alt>space ya lo usa X"), registro, "a")
                )
            ]
        }
    )

    with pytest.raises(AtajoOcupado, match="ya lo usa X"):
        escucha.iniciar({A: "<Control><Alt>space"}, lambda _: None)


def test_si_ninguno_sirve_se_explica_el_motivo_de_cada_uno() -> None:
    registro: list[str] = []
    escucha = EscuchaCompuesta(
        {
            M: [
                _fabrica(EscuchaQueFalla(SinPermisoDeTeclado("grupo input"), registro, "evdev")),
                _fabrica(EscuchaQueFalla(SinTeclados("sin teclados"), registro, "otro")),
            ]
        }
    )

    with pytest.raises(NingunAdaptadorSirve) as error:
        escucha.iniciar({M: "RightCtrl"}, lambda _: None)

    mensaje = str(error.value)
    assert "mantener" in mensaje and "grupo input" in mensaje and "sin teclados" in mensaje


def test_otra_instancia_corriendo_no_se_esquiva_con_otro_adaptador() -> None:
    registro: list[str] = []
    primero = EscuchaQueFalla(InstanciaYaEnEjecucion("ya está corriendo"), registro, "gnome")
    segundo = EscuchaQueAvisa(registro, "segundo")
    escucha = EscuchaCompuesta({A: [_fabrica(primero), _fabrica(segundo)]})

    with pytest.raises(InstanciaYaEnEjecucion):
        escucha.iniciar({A: "<Control><Alt>space"}, lambda _: None)

    assert "iniciar segundo" not in registro


def test_un_atajo_mal_escrito_es_un_error_de_configuracion_y_no_pasa_al_siguiente() -> None:
    registro: list[str] = []
    primero = EscuchaQueFalla(ValueError("No existe la tecla 'x'"), registro, "primero")
    segundo = EscuchaQueAvisa(registro, "segundo")
    escucha = EscuchaCompuesta({M: [_fabrica(primero), _fabrica(segundo)]})

    with pytest.raises(ValueError, match="tecla"):
        escucha.iniciar({M: "x"}, lambda _: None)

    assert "iniciar segundo" not in registro


def test_si_falla_una_accion_se_detienen_las_que_ya_habian_arrancado() -> None:
    registro: list[str] = []
    evdev = EscuchaQueAvisa(registro, "evdev")
    gnome = EscuchaQueFalla(ErrorDeGSettings("falló"), registro, "gnome")
    escucha = EscuchaCompuesta({M: [_fabrica(evdev)], A: [_fabrica(gnome)]})

    with pytest.raises(NingunAdaptadorSirve):
        escucha.iniciar(ATAJOS, lambda _: None)

    assert "detener evdev" in registro


# ---- ciclo de vida -------------------------------------------------------------------------------------------------


def test_detener_detiene_todo_y_es_inofensivo_si_se_repite() -> None:
    registro: list[str] = []
    gnome, evdev = EscuchaQueAvisa(registro, "gnome"), EscuchaQueAvisa(registro, "evdev")
    escucha = EscuchaCompuesta({A: [_fabrica(gnome)], M: [_fabrica(evdev)]})
    escucha.iniciar(ATAJOS, lambda _: None)

    escucha.detener()
    escucha.detener()

    assert registro.count("detener gnome") == 1 and registro.count("detener evdev") == 1


def test_no_se_puede_iniciar_dos_veces_y_se_puede_volver_a_iniciar_tras_detener() -> None:
    escucha = EscuchaCompuesta({M: [lambda: EscuchaFalsa()]})
    escucha.iniciar({M: "RightCtrl"}, lambda _: None)

    with pytest.raises(RuntimeError, match="ya está iniciada"):
        escucha.iniciar({M: "RightCtrl"}, lambda _: None)

    escucha.detener()
    escucha.iniciar({M: "RightCtrl"}, lambda _: None)
    escucha.detener()


# ---- la configuración por defecto ----------------------------------------------------------------------------------------


def test_crear_escucha_arma_gnome_para_alternar_y_evdev_para_mantener() -> None:
    escucha = crear_escucha()

    assert isinstance(escucha, EscuchaCompuesta)
    nombres = {
        accion: [f().__class__.__name__ for f in fabricas]
        for accion, fabricas in escucha.candidatas.items()
    }
    assert nombres == {A: ["EscuchaDeGnome"], M: ["EscuchaEvdev"]}
