"""El indicador flotante de grabación (RF-028): no roba el foco ni estorba al ratón."""

import os

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.ui.indicador import Indicador

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _indicador(qtbot: QtBot, activo: bool = True, duracion_error_ms: int = 60) -> Indicador:
    indicador = Indicador(activo=lambda: activo, duracion_error_ms=duracion_error_ms)
    qtbot.addWidget(indicador)
    return indicador


# ---- que no robe el foco -------------------------------------------------------------------------------


def test_es_una_ventana_sin_bordes_siempre_arriba(qtbot: QtBot) -> None:
    banderas = _indicador(qtbot).windowFlags()

    assert banderas & Qt.WindowType.FramelessWindowHint
    assert banderas & Qt.WindowType.WindowStaysOnTopHint
    assert banderas & Qt.WindowType.Tool  # no aparece en la lista de ventanas


def test_no_acepta_el_foco(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    assert indicador.windowFlags() & Qt.WindowType.WindowDoesNotAcceptFocus
    assert indicador.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert indicador.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_deja_pasar_los_clics(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    assert indicador.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert indicador.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)


def test_al_mostrarse_no_se_activa(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO)

    assert indicador.isVisible() and not indicador.isActiveWindow()


# ---- cuándo aparece ---------------------------------------------------------------------------------------


def test_empieza_oculto(qtbot: QtBot) -> None:
    assert not _indicador(qtbot).isVisible()


def test_aparece_al_escuchar_y_se_oculta_al_volver_a_inactivo(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO)
    assert indicador.isVisible()

    indicador.establecer_estado(E.INACTIVO)
    assert not indicador.isVisible()


@pytest.mark.parametrize("estado", [E.TRANSCRIBIENDO, E.INSERTANDO])
def test_sigue_visible_mientras_trabaja(qtbot: QtBot, estado: E) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)

    indicador.establecer_estado(estado)

    assert indicador.isVisible()


def test_muestra_el_texto_del_estado(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO)
    assert "Escuchando" in indicador.texto

    indicador.establecer_estado(E.TRANSCRIBIENDO)
    assert "Transcribiendo" in indicador.texto


def test_un_error_se_muestra_un_momento_y_se_oculta_solo(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot, duracion_error_ms=60)
    indicador.establecer_estado(E.ESCUCHANDO)

    indicador.establecer_estado(E.ERROR)
    assert indicador.isVisible() and "Error" in indicador.texto

    qtbot.waitUntil(lambda: not indicador.isVisible(), timeout=2000)


def test_si_tras_un_error_empieza_otro_dictado_no_se_oculta_de_golpe(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot, duracion_error_ms=60)
    indicador.establecer_estado(E.ERROR)

    indicador.establecer_estado(E.ESCUCHANDO)
    qtbot.wait(150)

    assert indicador.isVisible()


# ---- el ajuste interfaz.indicador ----------------------------------------------------------------------------


def test_con_el_ajuste_apagado_nunca_aparece(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot, activo=False)

    for estado in (E.ESCUCHANDO, E.TRANSCRIBIENDO, E.ERROR):
        indicador.establecer_estado(estado)
        assert not indicador.isVisible()


def test_el_ajuste_se_lee_cada_vez_y_rige_sin_reiniciar(qtbot: QtBot) -> None:
    encendido = [False]
    indicador = Indicador(activo=lambda: encendido[0])
    qtbot.addWidget(indicador)

    indicador.establecer_estado(E.ESCUCHANDO)
    assert not indicador.isVisible()
    indicador.establecer_estado(E.INACTIVO)
    encendido[0] = True
    indicador.establecer_estado(E.ESCUCHANDO)

    assert indicador.isVisible()


# ---- el nivel de audio ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(("entrada", "esperado"), [(0.4, 0.4), (-1.0, 0.0), (7.0, 1.0), (0.0, 0.0)])
def test_el_nivel_se_acota_entre_0_y_1(qtbot: QtBot, entrada: float, esperado: float) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_nivel(entrada)

    assert indicador.nivel == pytest.approx(esperado)


def test_al_volver_a_escuchar_el_nivel_arranca_en_cero(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_nivel(0.9)

    indicador.establecer_estado(E.ESCUCHANDO)

    assert indicador.nivel == 0.0


def test_se_dibuja_sin_errores_con_cualquier_nivel(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)

    for nivel in (0.0, 0.5, 1.0):
        indicador.establecer_nivel(nivel)
        indicador.grab()  # fuerza un repintado


def test_se_ubica_en_la_pantalla_abajo_y_al_centro(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO)

    pantalla = indicador.screen().availableGeometry()
    assert pantalla.contains(indicador.geometry().center())
    assert indicador.geometry().center().y() > pantalla.center().y()


# ---- traducir (lote 6) -----------------------------------------------------------------------------------


def test_al_traducir_el_indicador_dice_el_idioma_de_destino(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO, "inglés")

    assert (
        "Escuchando" in indicador.texto and "inglés" in indicador.texto and "→" in indicador.texto
    )


def test_sin_traducir_el_texto_no_cambia(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO)

    assert "→" not in indicador.texto


def test_mientras_transcribe_una_traduccion_sigue_mostrando_el_destino(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.TRANSCRIBIENDO, "francés")

    assert "francés" in indicador.texto
