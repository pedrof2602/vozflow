"""Cliente común de los portales: registrar, pedir y esperar la respuesta, escuchar."""

import re
from unittest.mock import Mock

import pytest
from jeepney import DBusAddress, MatchRule, Message, new_method_call

from tests.dobles_dbus import ConexionPortalFalsa, Guion
from vozflow.dbus_portal import (
    ClientePortal,
    ErrorDePortal,
    SolicitudDenegada,
    nuevo_token,
    ruta_de_solicitud,
    valor,
)

GLOBAL_SHORTCUTS = "org.freedesktop.portal.GlobalShortcuts"
REMOTE_DESKTOP = "org.freedesktop.portal.RemoteDesktop"


def _cliente(conexion: ConexionPortalFalsa, asegurar_entrada: Mock | None = None) -> ClientePortal:
    return ClientePortal(conexion, asegurar_entrada=asegurar_entrada or Mock())


# ---- funciones puras ----------------------


def test_la_ruta_de_la_solicitud_usa_el_nombre_unico_sin_los_puntos() -> None:
    ruta = ruta_de_solicitud(":1.579", "vozflow_abc")

    assert ruta == "/org/freedesktop/portal/desktop/request/1_579/vozflow_abc"


def test_los_tokens_son_validos_y_no_se_repiten() -> None:
    tokens = {nuevo_token() for _ in range(200)}

    assert len(tokens) == 200
    assert all(re.fullmatch(r"vozflow_[0-9a-f]{12}", t) for t in tokens)


def test_valor_desenvuelve_las_variantes_de_un_diccionario() -> None:
    resultados = {"session_handle": ("s", "/sesion/1"), "restore_token": ("s", "tok")}

    assert valor(resultados, "session_handle") == "/sesion/1"
    assert valor(resultados, "ausente") is None
    assert valor(resultados, "ausente", "otro") == "otro"


# ---- registrar la aplicación ----------------------


def test_registrar_envia_el_id_de_la_aplicacion_una_sola_vez() -> None:
    conexion = ConexionPortalFalsa()
    cliente = _cliente(conexion)

    cliente.registrar_aplicacion()
    cliente.registrar_aplicacion()

    registros = conexion.llamadas_a("Register")
    assert len(registros) == 1
    assert registros[0].body == ("vozflow", {})


def test_registrar_tolera_que_la_conexion_ya_este_asociada() -> None:
    conexion = ConexionPortalFalsa(
        {"Register": Guion(error="Could not register app ID: Connection already associated")}
    )

    _cliente(conexion).registrar_aplicacion()  # no lanza


def test_si_falta_la_entrada_de_escritorio_la_crea_y_reintenta() -> None:
    conexion = ConexionPortalFalsa(
        {"Register": [Guion(error="App info not found for 'vozflow'"), Guion()]}
    )
    asegurar = Mock()

    _cliente(conexion, asegurar).registrar_aplicacion()

    asegurar.assert_called_once()
    assert len(conexion.llamadas_a("Register")) == 2


def test_si_tras_crear_la_entrada_sigue_fallando_explica_que_hacer() -> None:
    conexion = ConexionPortalFalsa({"Register": Guion(error="App info not found for 'vozflow'")})

    with pytest.raises(ErrorDePortal, match=r"vozflow\.desktop"):
        _cliente(conexion).registrar_aplicacion()


def test_cualquier_otro_error_de_registro_se_informa_tal_cual() -> None:
    conexion = ConexionPortalFalsa({"Register": Guion(error="Boom inesperado")})

    with pytest.raises(ErrorDePortal, match="Boom inesperado"):
        _cliente(conexion).registrar_aplicacion()


# ---- versión de una interfaz ----------------------


def test_version_de_una_interfaz() -> None:
    conexion = ConexionPortalFalsa({"Get": Guion(retorno=(("u", 2),), firma="v")})

    assert _cliente(conexion).version_de(REMOTE_DESKTOP) == 2


def test_una_interfaz_ausente_tiene_version_cero() -> None:
    conexion = ConexionPortalFalsa({"Get": Guion(error="No such interface")})

    assert _cliente(conexion).version_de(GLOBAL_SHORTCUTS) == 0


# ---- pedir y esperar la respuesta ----------------------


def _construir(token: str) -> tuple[object, ...]:
    return ({"handle_token": ("s", token)},)


def test_solicitar_devuelve_el_codigo_y_los_resultados() -> None:
    conexion = ConexionPortalFalsa(
        {"CreateSession": Guion(respuesta=(0, {"session_handle": ("s", "/sesion/1")}))}
    )

    respuesta = _cliente(conexion).solicitar(GLOBAL_SHORTCUTS, "CreateSession", "a{sv}", _construir)

    assert respuesta.codigo == 0
    assert valor(respuesta.resultados, "session_handle") == "/sesion/1"


def test_solicitar_se_suscribe_antes_de_llamar_y_se_da_de_baja_al_terminar() -> None:
    conexion = ConexionPortalFalsa({"CreateSession": Guion(respuesta=(0, {}))})

    _cliente(conexion).solicitar(GLOBAL_SHORTCUTS, "CreateSession", "a{sv}", _construir)

    assert conexion.registro == ["AddMatch", "llamada:CreateSession", "RemoveMatch"]


def test_solicitar_pone_el_token_en_las_opciones_y_la_cola_no_queda_registrada() -> None:
    conexion = ConexionPortalFalsa({"CreateSession": Guion(respuesta=(0, {}))})

    _cliente(conexion).solicitar(GLOBAL_SHORTCUTS, "CreateSession", "a{sv}", _construir)

    assert re.fullmatch(r"vozflow_[0-9a-f]{12}", conexion.token_de("CreateSession"))
    assert conexion._filtros == []


@pytest.mark.parametrize(("codigo", "texto"), [(1, "cancel"), (2, "falló")])
def test_un_codigo_distinto_de_cero_es_una_solicitud_denegada(codigo: int, texto: str) -> None:
    conexion = ConexionPortalFalsa({"Start": Guion(respuesta=(codigo, {}))})

    with pytest.raises(SolicitudDenegada, match=texto) as error:
        _cliente(conexion).solicitar(REMOTE_DESKTOP, "Start", "a{sv}", _construir)

    assert error.value.codigo == codigo
    assert conexion.registro[-1] == "RemoveMatch"


def test_si_el_portal_no_responde_se_informa_el_tiempo_agotado() -> None:
    conexion = ConexionPortalFalsa(
        {"Start": Guion()}
    )  # el método responde, pero nunca llega Response

    with pytest.raises(ErrorDePortal, match="tiempo"):
        _cliente(conexion).solicitar(REMOTE_DESKTOP, "Start", "a{sv}", _construir, timeout_s=0.01)

    assert conexion.registro[-1] == "RemoveMatch"


def test_un_error_del_metodo_se_informa_y_se_da_de_baja_la_suscripcion() -> None:
    conexion = ConexionPortalFalsa({"Start": Guion(error="No puedo con esto")})

    with pytest.raises(ErrorDePortal, match="No puedo con esto"):
        _cliente(conexion).solicitar(REMOTE_DESKTOP, "Start", "a{sv}", _construir)

    assert conexion.registro == ["AddMatch", "llamada:Start", "RemoveMatch"]


def test_una_respuesta_que_llegara_antes_de_suscribirse_se_perderia() -> None:
    """Documenta por qué se suscribe primero: el doble descarta lo emitido sin suscriptor."""
    conexion = ConexionPortalFalsa({"X": Guion(respuesta=(0, {}))})

    conexion.send_and_get_reply(_mensaje_con_token("X", "tok"))  # sin suscripción previa
    with conexion.filter(_regla_response()) as cola, pytest.raises(TimeoutError):
        conexion.recv_until_filtered(cola, timeout=0.01)


def _mensaje_con_token(metodo: str, token: str) -> Message:
    destino = DBusAddress("/p", bus_name="org.x", interface="org.x.I")
    return new_method_call(destino, metodo, "a{sv}", ({"handle_token": ("s", token)},))


def _regla_response() -> MatchRule:
    return MatchRule(type="signal", interface="org.freedesktop.portal.Request", member="Response")


# ---- llamadas simples y señales ----------------------


def test_llamar_devuelve_el_cuerpo_de_la_respuesta() -> None:
    conexion = ConexionPortalFalsa({"NotifyKeyboardKeysym": Guion(retorno=(5,), firma="u")})

    cuerpo = _cliente(conexion).llamar(
        REMOTE_DESKTOP, "NotifyKeyboardKeysym", "oa{sv}iu", ("/sesion/1", {}, 0xF1, 1)
    )

    assert cuerpo == (5,)
    assert conexion.llamadas_a("NotifyKeyboardKeysym")[0].body == ("/sesion/1", {}, 0xF1, 1)


def test_llamar_informa_el_error_del_metodo() -> None:
    conexion = ConexionPortalFalsa({"NotifyKeyboardKeysym": Guion(error="sesión cerrada")})

    with pytest.raises(ErrorDePortal, match="sesión cerrada"):
        _cliente(conexion).llamar(
            REMOTE_DESKTOP, "NotifyKeyboardKeysym", "oa{sv}iu", ("/s", {}, 1, 1)
        )


def test_escuchar_recibe_las_senales_pedidas_en_orden() -> None:
    conexion = ConexionPortalFalsa()
    cliente = _cliente(conexion)

    with cliente.escuchar(GLOBAL_SHORTCUTS, ["Activated", "Deactivated"]) as senales:
        for miembro in ("Activated", "Deactivated"):
            conexion.emitir(
                "/org/freedesktop/portal/desktop",
                GLOBAL_SHORTCUTS,
                miembro,
                "osta{sv}",
                ("/sesion/1", "mantener", 123, {}),
            )
        primera = senales.recibir(timeout_s=0.1)
        segunda = senales.recibir(timeout_s=0.1)

    assert primera is not None and primera.miembro == "Activated"
    assert segunda is not None and segunda.miembro == "Deactivated"
    assert primera.cuerpo[1] == "mantener"
    assert conexion.registro.count("AddMatch") == 2 and conexion.registro.count("RemoveMatch") == 2


def test_escuchar_devuelve_none_si_no_llega_nada_en_el_tiempo_dado() -> None:
    conexion = ConexionPortalFalsa()

    with _cliente(conexion).escuchar(GLOBAL_SHORTCUTS, ["Activated"]) as senales:
        assert senales.recibir(timeout_s=0.01) is None


def test_escuchar_no_pierde_senales_que_llegan_seguidas() -> None:
    conexion = ConexionPortalFalsa()

    with _cliente(conexion).escuchar(GLOBAL_SHORTCUTS, ["Activated", "Deactivated"]) as senales:
        for _ in range(10):
            conexion.emitir(
                "/org/freedesktop/portal/desktop",
                GLOBAL_SHORTCUTS,
                "Activated",
                "osta{sv}",
                ("/sesion/1", "x", 1, {}),
            )
        recibidas = [senales.recibir(timeout_s=0.01) for _ in range(10)]

    assert all(r is not None for r in recibidas)


def test_cerrar_cierra_la_conexion() -> None:
    conexion = ConexionPortalFalsa()

    _cliente(conexion).cerrar()

    assert conexion.cerrada is True
