"""``EscuchaDeGnome``: el atajo de GNOME más el servicio D-Bus al que llama."""

import time

import pytest
from jeepney import DBusAddress, MessageFlag, new_method_call

from tests.dobles import GSettingsFalso
from tests.dobles_dbus import ConexionServidorFalsa
from vozflow.atajos.gnome import EscuchaDeGnome
from vozflow.atajos.gsettings import RUTA_PROPIA, AtajoDeGnome, leer_lista
from vozflow.atajos.puerto import AccionDeAtajo, AtajoOcupado, EventoDeAtajo, FaseDeAtajo
from vozflow.servicio_dbus import (
    INTERFAZ,
    NOMBRE_DEL_SERVICIO,
    RUTA,
    InstanciaYaEnEjecucion,
    ServicioDBus,
)

A = AccionDeAtajo.ALTERNAR
P = FaseDeAtajo.PULSADO


def _toggle() -> object:
    mensaje = new_method_call(
        DBusAddress(RUTA, bus_name=NOMBRE_DEL_SERVICIO, interface=INTERFAZ), "Toggle"
    )
    mensaje.header.flags = MessageFlag.no_reply_expected
    return mensaje


def _montar(
    codigo_del_nombre: int = 1,
) -> tuple[EscuchaDeGnome, GSettingsFalso, ConexionServidorFalsa]:
    gsettings = GSettingsFalso()
    conexion = ConexionServidorFalsa(codigo_del_nombre)
    escucha = EscuchaDeGnome(
        atajo=AtajoDeGnome(ejecutar=gsettings),
        crear_servicio=lambda al_alternar: ServicioDBus(
            al_alternar, abrir_conexion=lambda: conexion
        ),
    )
    return escucha, gsettings, conexion


def _esperar(condicion, segundos: float = 3.0) -> bool:  # type: ignore[no-untyped-def]
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.005)
    return False


def test_registra_el_atajo_y_cada_toggle_es_un_alternar() -> None:
    escucha, gsettings, conexion = _montar()
    recibidos: list[EventoDeAtajo] = []
    escucha.iniciar({A: "Ctrl+Alt+Space"}, recibidos.append)

    assert leer_lista(gsettings) == [RUTA_PROPIA]
    for _ in range(3):  # una pulsación tras otra: ninguna se pierde por «tecla apretada»
        conexion.entrantes.append(_toggle())
    assert _esperar(lambda: len(recibidos) == 3)
    assert recibidos == [EventoDeAtajo(A, P)] * 3
    escucha.detener()


def test_al_detener_retira_el_atajo_y_cierra_el_servicio() -> None:
    escucha, gsettings, conexion = _montar()
    escucha.iniciar({A: "<Control><Alt>space"}, lambda _: None)

    escucha.detener()
    escucha.detener()

    assert leer_lista(gsettings) == []
    assert conexion.cerrada is True


def test_una_tecla_ocupada_se_informa_y_no_deja_nada_registrado() -> None:
    escucha, gsettings, conexion = _montar()
    gsettings.precargar(
        "org.gnome.desktop.wm.keybindings", "activate-window-menu", "['<Alt>space']"
    )

    with pytest.raises(AtajoOcupado):
        escucha.iniciar({A: "<Alt>space"}, lambda _: None)

    assert leer_lista(gsettings) == []
    assert conexion.cerrada is True  # y el servicio que ya había arrancado se detuvo


def test_otra_instancia_corriendo_se_detecta_antes_de_tocar_gsettings() -> None:
    escucha, gsettings, _ = _montar(codigo_del_nombre=3)

    with pytest.raises(InstanciaYaEnEjecucion):
        escucha.iniciar({A: "<Control><Alt>space"}, lambda _: None)

    assert gsettings.llamadas == []


def test_solo_maneja_la_accion_alternar() -> None:
    escucha, _, _ = _montar()

    with pytest.raises(ValueError, match="alternar"):
        escucha.iniciar({AccionDeAtajo.MANTENER: "F9"}, lambda _: None)


def test_un_modificador_solo_no_sirve_como_atajo_de_gnome() -> None:
    escucha, _, _ = _montar()

    with pytest.raises(ValueError, match="modificador"):
        escucha.iniciar({A: "RightCtrl"}, lambda _: None)


def test_no_se_puede_iniciar_dos_veces() -> None:
    escucha, _, _ = _montar()
    escucha.iniciar({A: "<Control><Alt>space"}, lambda _: None)

    with pytest.raises(RuntimeError, match="ya está iniciada"):
        escucha.iniciar({A: "<Control><Alt>space"}, lambda _: None)
    escucha.detener()
