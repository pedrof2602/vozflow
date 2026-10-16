"""El servicio D-Bus de vozflow: lo que llama el atajo de GNOME (``dbus-send ... Toggle``)."""

import os
import subprocess
import threading
import time
from collections.abc import Callable, Iterator

import pytest
from jeepney import (
    DBusAddress,
    HeaderFields,
    Message,
    MessageFlag,
    MessageType,
    new_method_call,
    new_signal,
)

from tests.dobles_dbus import ConexionServidorFalsa
from vozflow.servicio_dbus import (
    INTERFAZ,
    NOMBRE_DEL_SERVICIO,
    RUTA,
    InstanciaYaEnEjecucion,
    ServicioDBus,
)


def _llamada(
    miembro: str = "Toggle",
    ruta: str = RUTA,
    interfaz: str = INTERFAZ,
    sin_respuesta: bool = False,
) -> Message:
    destino = DBusAddress(ruta, bus_name=NOMBRE_DEL_SERVICIO, interface=interfaz)
    mensaje = new_method_call(destino, miembro)
    if sin_respuesta:  # como hace `dbus-send` sin --print-reply
        mensaje.header.flags = MessageFlag.no_reply_expected
    return mensaje


def _esperar(condicion: Callable[[], bool], segundos: float = 3.0) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.005)
    return False


@pytest.fixture
def servicio() -> Iterator[tuple[ServicioDBus, ConexionServidorFalsa, list[int]]]:
    conexion = ConexionServidorFalsa()
    alternados: list[int] = []
    instancia = ServicioDBus(lambda: alternados.append(1), abrir_conexion=lambda: conexion)
    instancia.iniciar()
    yield instancia, conexion, alternados
    instancia.detener()


# ---- ponerse en marcha -------------------------------------------------------------------------


def test_pide_el_nombre_sin_ponerse_en_cola(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]],
) -> None:
    _, conexion, _ = servicio

    assert conexion.peticiones[0].body == (NOMBRE_DEL_SERVICIO, 4)  # 4 = no ponerse en cola


def test_si_el_nombre_ya_esta_tomado_hay_otra_instancia_corriendo() -> None:
    conexion = ConexionServidorFalsa(codigo_del_nombre=3)
    servicio = ServicioDBus(lambda: None, abrir_conexion=lambda: conexion)

    with pytest.raises(InstanciaYaEnEjecucion, match="ya está corriendo"):
        servicio.iniciar()

    assert conexion.cerrada is True


def test_no_se_puede_iniciar_dos_veces(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]],
) -> None:
    instancia, _, _ = servicio

    with pytest.raises(RuntimeError, match="ya está iniciado"):
        instancia.iniciar()


# ---- atender llamadas ----------------------------------------------------------------------------


def test_toggle_dispara_el_callback_y_responde(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]],
) -> None:
    _, conexion, alternados = servicio

    conexion.entrantes.append(_llamada())

    assert _esperar(lambda: len(alternados) == 1)
    assert _esperar(lambda: len(conexion.enviados) == 1)
    assert conexion.enviados[0].header.message_type is MessageType.method_return


def test_si_quien_llama_no_espera_respuesta_no_se_la_manda(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]],
) -> None:
    _, conexion, alternados = servicio

    conexion.entrantes.append(_llamada(sin_respuesta=True))

    assert _esperar(lambda: len(alternados) == 1)
    time.sleep(0.05)
    assert conexion.enviados == []


def test_cada_llamada_es_un_alternar(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]],
) -> None:
    _, conexion, alternados = servicio

    for _ in range(3):
        conexion.entrantes.append(_llamada(sin_respuesta=True))

    assert _esperar(lambda: len(alternados) == 3)


@pytest.mark.parametrize(
    ("llamada", "error"),
    [
        (_llamada(miembro="Otro"), "UnknownMethod"),
        (_llamada(ruta="/otra/ruta"), "UnknownObject"),
        (_llamada(interfaz="com.otra.Interfaz"), "UnknownMethod"),
    ],
)
def test_lo_que_no_es_toggle_se_rechaza_sin_alternar(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]], llamada: Message, error: str
) -> None:
    _, conexion, alternados = servicio

    conexion.entrantes.append(llamada)

    assert _esperar(lambda: len(conexion.enviados) == 1)
    respuesta = conexion.enviados[0]
    assert respuesta.header.message_type is MessageType.error
    assert error in str(respuesta.header.fields[HeaderFields.error_name])
    assert alternados == []


def test_responde_a_ping_e_introspect(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]],
) -> None:
    _, conexion, _ = servicio

    conexion.entrantes.append(_llamada("Ping", interfaz="org.freedesktop.DBus.Peer"))
    conexion.entrantes.append(
        _llamada("Introspect", interfaz="org.freedesktop.DBus.Introspectable")
    )

    assert _esperar(lambda: len(conexion.enviados) == 2)
    xml = conexion.enviados[1].body[0]
    assert NOMBRE_DEL_SERVICIO in xml and "Toggle" in xml


def test_las_senales_y_respuestas_ajenas_se_ignoran(
    servicio: tuple[ServicioDBus, ConexionServidorFalsa, list[int]],
) -> None:
    _, conexion, alternados = servicio

    conexion.entrantes.append(new_signal(DBusAddress("/x", interface="x.Y"), "Algo"))
    conexion.entrantes.append(_llamada(sin_respuesta=True))

    assert _esperar(lambda: len(alternados) == 1)
    assert conexion.enviados == []


def test_un_error_en_el_callback_no_mata_el_servicio() -> None:
    conexion = ConexionServidorFalsa()
    llamadas: list[int] = []

    def alternar() -> None:
        llamadas.append(1)
        if len(llamadas) == 1:
            raise RuntimeError("falló quien me llama")

    servicio = ServicioDBus(alternar, abrir_conexion=lambda: conexion)
    servicio.iniciar()
    try:
        conexion.entrantes.append(_llamada())
        conexion.entrantes.append(_llamada(sin_respuesta=True))

        assert _esperar(lambda: len(llamadas) == 2)
        assert conexion.enviados[0].header.message_type is MessageType.error
    finally:
        servicio.detener()


# ---- detenerse --------------------------------------------------------------------------------------------


def test_detener_cierra_la_conexion_y_el_hilo() -> None:
    antes = threading.active_count()
    conexion = ConexionServidorFalsa()
    servicio = ServicioDBus(lambda: None, abrir_conexion=lambda: conexion)
    servicio.iniciar()

    servicio.detener()
    servicio.detener()  # inofensivo si se repite

    assert conexion.cerrada is True
    assert threading.active_count() == antes


def test_tras_detener_se_puede_volver_a_iniciar() -> None:
    conexiones = [ConexionServidorFalsa(), ConexionServidorFalsa()]
    servicio = ServicioDBus(lambda: None, abrir_conexion=lambda: conexiones.pop(0))

    servicio.iniciar()
    servicio.detener()
    servicio.iniciar()
    servicio.detener()


# ---- con el bus de la sesión de verdad -------------------------------------------------------------------------

hay_bus = bool(os.environ.get("DBUS_SESSION_BUS_ADDRESS"))


@pytest.mark.skipif(not hay_bus, reason="No hay bus de sesión de D-Bus")
def test_con_el_bus_real_dbus_send_alterna_y_una_segunda_instancia_se_rechaza() -> None:
    nombre = f"com.vozflow.Prueba{os.getpid()}"
    alternados: list[int] = []
    servicio = ServicioDBus(lambda: alternados.append(1), nombre=nombre)
    servicio.iniciar()
    try:
        subprocess.run(
            [
                "dbus-send",
                "--session",
                "--type=method_call",
                f"--dest={nombre}",
                RUTA,
                f"{INTERFAZ}.Toggle",
            ],
            check=True,
            timeout=5,
        )
        assert _esperar(lambda: len(alternados) == 1)

        with pytest.raises(InstanciaYaEnEjecucion):
            ServicioDBus(lambda: None, nombre=nombre).iniciar()
    finally:
        servicio.detener()
