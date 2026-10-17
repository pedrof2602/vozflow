"""Teclas por el portal RemoteDesktop: la sesión se abre para cada pegado y se cierra enseguida."""

from pathlib import Path
from unittest.mock import Mock

import pytest
from jeepney import HeaderFields

from tests.dobles_dbus import ConexionPortalFalsa, Guion
from vozflow.dbus_portal import ClientePortal, ErrorDePortal
from vozflow.insercion.portal_remoto import TecladorPortal
from vozflow.insercion.puerto import FalloDeTeclado

SESION = "/org/freedesktop/portal/desktop/session/1_42/vozflow_s"
CTRL, SHIFT, INSERT, V = 0xFFE3, 0xFFE1, 0xFF63, 0x76


def _guion(**cambios: Guion | list[Guion]) -> dict[str, Guion | list[Guion]]:
    base: dict[str, Guion | list[Guion]] = {
        "CreateSession": Guion(respuesta=(0, {"session_handle": ("s", SESION)})),
        "SelectDevices": Guion(respuesta=(0, {})),
        "Start": Guion(respuesta=(0, {"restore_token": ("s", "token-nuevo")})),
    }
    base.update(cambios)
    return base


class Montaje:
    def __init__(self, tmp_path: Path, guion: dict[str, Guion | list[Guion]] | None = None) -> None:
        self.conexion = ConexionPortalFalsa(guion or _guion())
        self.ruta_token = tmp_path / "config" / "portal-token"
        self.pausas: list[float] = []
        self.aperturas = 0
        self.teclador = TecladorPortal(
            abrir_cliente=self._abrir, ruta_token=self.ruta_token, dormir=self.pausas.append
        )

    def _abrir(self) -> ClientePortal:
        self.aperturas += 1
        return ClientePortal(self.conexion, asegurar_entrada=Mock())

    def notificaciones(self) -> list[tuple[int, int]]:
        return [
            (int(m.body[2]), int(m.body[3]))
            for m in self.conexion.llamadas_a("NotifyKeyboardKeysym")
        ]


@pytest.fixture
def montaje(tmp_path: Path) -> Montaje:
    return Montaje(tmp_path)


# ---- no abre nada hasta que hay algo que pegar ----------------------------------------------


def test_crear_el_teclador_no_abre_ninguna_sesion(montaje: Montaje) -> None:
    assert montaje.aperturas == 0
    assert montaje.conexion.llamadas == []


# ---- el armado de los mensajes ---------------------------------------------------------------


def test_crea_la_sesion_con_sus_dos_tokens(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    (opciones,) = montaje.conexion.llamadas_a("CreateSession")[0].body
    assert opciones["handle_token"][0] == "s" and opciones["session_handle_token"][0] == "s"
    assert opciones["handle_token"][1] != opciones["session_handle_token"][1]


def test_registra_la_aplicacion_antes_de_pedir_la_sesion(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    nombres = [m for m in montaje.conexion.registro if m.startswith("llamada:")]
    assert nombres.index("llamada:Register") < nombres.index("llamada:CreateSession")


def test_pide_solo_teclado_y_que_el_permiso_se_recuerde(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    sesion, opciones = montaje.conexion.llamadas_a("SelectDevices")[0].body
    assert sesion == SESION
    assert opciones["types"] == ("u", 1)
    assert opciones["persist_mode"] == ("u", 2)
    assert "restore_token" not in opciones


def test_reutiliza_el_token_guardado(montaje: Montaje) -> None:
    montaje.ruta_token.parent.mkdir(parents=True)
    montaje.ruta_token.write_text("token-viejo\n")

    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    _, opciones = montaje.conexion.llamadas_a("SelectDevices")[0].body
    assert opciones["restore_token"] == ("s", "token-viejo")


def test_inicia_con_la_ventana_padre_vacia(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    sesion, padre, opciones = montaje.conexion.llamadas_a("Start")[0].body
    assert (sesion, padre) == (SESION, "") and "handle_token" in opciones


def test_guarda_el_token_nuevo_que_responde_start_solo_para_su_dueno(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    assert montaje.ruta_token.read_text() == "token-nuevo"
    assert montaje.ruta_token.stat().st_mode & 0o777 == 0o600


def test_si_start_no_trae_token_no_se_toca_el_guardado(tmp_path: Path) -> None:
    montaje = Montaje(tmp_path, _guion(Start=Guion(respuesta=(0, {}))))
    montaje.ruta_token.parent.mkdir(parents=True)
    montaje.ruta_token.write_text("token-viejo")

    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    assert montaje.ruta_token.read_text() == "token-viejo"


# ---- las teclas -----------------------------------------------------------------------------------


def test_shift_insert_se_pulsa_en_orden_y_se_suelta_al_reves(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    assert montaje.notificaciones() == [(SHIFT, 1), (INSERT, 1), (INSERT, 0), (SHIFT, 0)]


def test_ctrl_shift_v_usa_la_v_minuscula(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((CTRL, SHIFT, V))

    assert montaje.notificaciones() == [
        (CTRL, 1),
        (SHIFT, 1),
        (0x76, 1),
        (0x76, 0),
        (SHIFT, 0),
        (CTRL, 0),
    ]


def test_cada_tecla_se_manda_por_notify_keyboard_keysym_con_su_firma(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((CTRL, V))

    for mensaje in montaje.conexion.llamadas_a("NotifyKeyboardKeysym"):
        assert mensaje.header.fields[HeaderFields.signature] == "oa{sv}iu"
        assert mensaje.body[0] == SESION and mensaje.body[1] == {}


def test_separa_pulsar_y_soltar_la_ultima_tecla_con_20_ms(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((CTRL, V))

    assert montaje.pausas == [0.02]


def test_una_combinacion_vacia_no_abre_nada(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion(())

    assert montaje.aperturas == 0


# ---- cierre y errores -----------------------------------------------------------------------------


def test_cierra_la_sesion_y_la_conexion_al_terminar(montaje: Montaje) -> None:
    montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    assert montaje.conexion.llamadas_a("Close")
    assert montaje.conexion.cerrada is True


@pytest.mark.parametrize("etapa", ["CreateSession", "SelectDevices", "Start"])
def test_un_codigo_de_respuesta_distinto_de_cero_es_denegado_y_no_se_escribe(
    tmp_path: Path, etapa: str
) -> None:
    montaje = Montaje(tmp_path, _guion(**{etapa: Guion(respuesta=(1, {}))}))

    with pytest.raises(FalloDeTeclado, match="denegó|canceló|rechaz"):
        montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    assert montaje.notificaciones() == []
    assert montaje.conexion.cerrada is True


def test_si_start_es_denegado_la_sesion_creada_se_cierra(tmp_path: Path) -> None:
    montaje = Montaje(tmp_path, _guion(Start=Guion(respuesta=(1, {}))))

    with pytest.raises(FalloDeTeclado):
        montaje.teclador.pulsar_combinacion((SHIFT, INSERT))

    assert montaje.conexion.llamadas_a("Close")


def test_si_falla_una_tecla_a_mitad_se_sueltan_las_pulsadas_y_se_cierra(tmp_path: Path) -> None:
    montaje = Montaje(
        tmp_path,
        _guion(NotifyKeyboardKeysym=[Guion(), Guion(), Guion(error="no se pudo")]),
    )

    with pytest.raises(FalloDeTeclado):
        montaje.teclador.pulsar_combinacion((CTRL, SHIFT, V))

    assert montaje.conexion.llamadas_a("Close")
    assert montaje.conexion.cerrada is True


def test_un_error_del_portal_se_informa_como_fallo_de_teclado(tmp_path: Path) -> None:
    montaje = Montaje(tmp_path, _guion(CreateSession=Guion(error="Session creation inhibited")))

    with pytest.raises(FalloDeTeclado, match="inhibited"):
        montaje.teclador.pulsar_combinacion((SHIFT, INSERT))


# ---- esperas -------------------------------------------------------------------------------------------


def test_espera_10_s_por_la_autorizacion_y_3_s_por_cada_tecla(tmp_path: Path) -> None:
    cliente = Mock(spec=ClientePortal)
    cliente.solicitar.side_effect = [
        Mock(resultados={"session_handle": ("s", SESION)}),
        Mock(resultados={}),
        Mock(resultados={}),
    ]
    teclador = TecladorPortal(
        abrir_cliente=lambda: cliente, ruta_token=tmp_path / "t", dormir=lambda _: None
    )

    teclador.pulsar_combinacion((CTRL, V))

    assert [c.kwargs.get("timeout_s") for c in cliente.solicitar.call_args_list] == [10.0] * 3
    notificaciones = [
        c for c in cliente.llamar.call_args_list if c.args[1] == "NotifyKeyboardKeysym"
    ]
    assert notificaciones and all(c.kwargs.get("timeout_s") == 3.0 for c in notificaciones)


def test_un_portal_que_no_responde_es_un_fallo_y_no_cuelga(tmp_path: Path) -> None:
    cliente = Mock(spec=ClientePortal)
    cliente.solicitar.side_effect = ErrorDePortal("Se agotó el tiempo de espera")
    teclador = TecladorPortal(
        abrir_cliente=lambda: cliente, ruta_token=tmp_path / "t", dormir=lambda _: None
    )

    with pytest.raises(FalloDeTeclado, match="tiempo"):
        teclador.pulsar_combinacion((CTRL, V))

    cliente.cerrar.assert_called_once()
