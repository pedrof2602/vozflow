"""Ícono de la bandeja y su menú (RF-028), con ``pytest-qt`` sin pantalla."""

import os

import pytest
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon
from pytestqt.qtbot import QtBot

from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.ui.bandeja import Bandeja
from vozflow.ui.estado import VistaDeEstado, vista_de

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class BandejaFalsa(QObject):
    """Lo que usa ``Bandeja`` de ``QSystemTrayIcon``, sin tocar el escritorio."""

    activated = Signal(QSystemTrayIcon.ActivationReason)

    def __init__(self) -> None:
        super().__init__()
        self.iconos: list[QIcon] = []
        self.textos: list[str] = []
        self.menu: QMenu | None = None
        self.visible = False

    def setIcon(self, icono: QIcon) -> None:
        self.iconos.append(icono)

    def setToolTip(self, texto: str) -> None:
        self.textos.append(texto)

    def setContextMenu(self, menu: QMenu) -> None:
        self.menu = menu

    def show(self) -> None:
        self.visible = True

    def hide(self) -> None:
        self.visible = False


class Registro:
    def __init__(self) -> None:
        self.llamadas: list[str] = []

    def abrir_ajustes(self) -> None:
        self.llamadas.append("ajustes")

    def abrir_historial(self) -> None:
        self.llamadas.append("historial")

    def pausar(self, pausado: bool) -> None:
        self.llamadas.append(f"pausar:{pausado}")

    def salir(self) -> None:
        self.llamadas.append("salir")


def _bandeja(registro: Registro, disponible: bool = True) -> tuple[Bandeja, BandejaFalsa]:
    falsa = BandejaFalsa()
    bandeja = Bandeja(
        al_abrir_ajustes=registro.abrir_ajustes,
        al_abrir_historial=registro.abrir_historial,
        al_pausar=registro.pausar,
        al_salir=registro.salir,
        crear_icono=lambda: falsa,
        disponible=lambda: disponible,
    )
    return bandeja, falsa


def _accion(bandeja: Bandeja, texto: str):  # type: ignore[no-untyped-def]
    return next(a for a in bandeja.menu.actions() if a.text() == texto)


def test_el_menu_tiene_abrir_ajustes_historial_pausar_y_salir(qtbot: QtBot) -> None:
    bandeja, _ = _bandeja(Registro())

    textos = [a.text() for a in bandeja.menu.actions() if not a.isSeparator()]

    assert textos == ["Abrir ajustes", "Historial", "Pausar", "Salir"]


def test_cada_opcion_del_menu_avisa(qtbot: QtBot) -> None:
    registro = Registro()
    bandeja, _ = _bandeja(registro)

    _accion(bandeja, "Abrir ajustes").trigger()
    _accion(bandeja, "Historial").trigger()
    _accion(bandeja, "Salir").trigger()

    assert registro.llamadas == ["ajustes", "historial", "salir"]


def test_pausar_y_reanudar(qtbot: QtBot) -> None:
    registro = Registro()
    bandeja, _ = _bandeja(registro)

    _accion(bandeja, "Pausar").trigger()
    assert "Reanudar" in [a.text() for a in bandeja.menu.actions()]
    _accion(bandeja, "Reanudar").trigger()

    assert registro.llamadas == ["pausar:True", "pausar:False"]
    assert bandeja.pausada is False


def test_un_clic_en_el_icono_abre_los_ajustes(qtbot: QtBot) -> None:
    registro = Registro()
    bandeja, falsa = _bandeja(registro)

    falsa.activated.emit(QSystemTrayIcon.ActivationReason.Trigger)

    assert registro.llamadas == ["ajustes"]


def test_el_icono_se_muestra_y_cambia_con_el_estado(qtbot: QtBot) -> None:
    bandeja, falsa = _bandeja(Registro())
    assert falsa.visible is True

    imagenes = []
    for estado in (E.INACTIVO, E.ESCUCHANDO, E.TRANSCRIBIENDO, E.ERROR):
        bandeja.establecer_estado(estado)
        imagenes.append(falsa.iconos[-1].pixmap(22, 22).toImage())

    assert len({bytes(i.constBits()) for i in imagenes}) == 4  # los cuatro se ven distintos
    assert "Error" in falsa.textos[-1]


def test_el_tooltip_dice_el_estado(qtbot: QtBot) -> None:
    bandeja, falsa = _bandeja(Registro())

    bandeja.establecer_estado(E.ESCUCHANDO)

    assert "Escuchando" in falsa.textos[-1]


def test_cuando_esta_pausada_el_icono_lo_aclara(qtbot: QtBot) -> None:
    bandeja, falsa = _bandeja(Registro())

    _accion(bandeja, "Pausar").trigger()

    assert "pausa" in falsa.textos[-1].lower()


def test_el_estado_se_publica_para_quien_lo_quiera_mostrar(qtbot: QtBot) -> None:
    bandeja, _ = _bandeja(Registro())

    with qtbot.waitSignal(bandeja.estado_cambiado) as senal:
        bandeja.establecer_estado(E.TRANSCRIBIENDO)

    vista = senal.args[0]
    assert isinstance(vista, VistaDeEstado) and vista == vista_de(E.TRANSCRIBIENDO)
    assert bandeja.vista_actual == vista_de(E.TRANSCRIBIENDO)


# ---- sin bandeja en el escritorio (GNOME sin la extensión) ------------------------------------------------


def test_sin_bandeja_no_hay_error_y_el_estado_igual_se_publica(qtbot: QtBot) -> None:
    creados: list[object] = []
    bandeja = Bandeja(
        al_abrir_ajustes=lambda: None,
        al_abrir_historial=lambda: None,
        al_pausar=lambda _: None,
        al_salir=lambda: None,
        crear_icono=lambda: creados.append(1),
        disponible=lambda: False,
    )

    with qtbot.waitSignal(bandeja.estado_cambiado):
        bandeja.establecer_estado(E.ESCUCHANDO)

    assert bandeja.disponible is False and creados == []


def test_sin_bandeja_el_menu_sigue_existiendo_para_la_ventana_principal(qtbot: QtBot) -> None:
    bandeja, _ = _bandeja(Registro(), disponible=False)

    assert [a.text() for a in bandeja.menu.actions() if not a.isSeparator()][0] == "Abrir ajustes"


def test_con_la_bandeja_disponible_se_avisa(qtbot: QtBot) -> None:
    bandeja, _ = _bandeja(Registro(), disponible=True)

    assert bandeja.disponible is True


def test_al_cerrar_se_oculta_el_icono(qtbot: QtBot) -> None:
    bandeja, falsa = _bandeja(Registro())

    bandeja.cerrar()

    assert falsa.visible is False


@pytest.mark.parametrize("estado", list(E))
def test_todos_los_estados_se_pueden_mostrar(qtbot: QtBot, estado: E) -> None:
    bandeja, _ = _bandeja(Registro())

    bandeja.establecer_estado(estado)

    assert bandeja.vista_actual == vista_de(estado)
