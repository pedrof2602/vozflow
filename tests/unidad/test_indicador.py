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


# ---- píldora con barras de onda (lote 7) ---------------------------------------------------------------------


def test_es_una_pildora_con_las_esquinas_del_todo_redondas(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    assert indicador.radio_de_esquina() == indicador.height() / 2


def test_las_barras_empiezan_en_reposo(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)

    barras = indicador.barras()

    assert len(barras) == 9 and all(b <= 0.15 for b in barras)


def test_las_barras_siguen_el_nivel_de_la_voz(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)

    indicador.establecer_nivel(1.0)

    assert max(indicador.barras()) > 0.8


def test_las_barras_se_desplazan_con_el_tiempo(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)
    indicador.establecer_nivel(1.0)
    alta = indicador.barras().index(max(indicador.barras()))

    indicador.establecer_nivel(0.0)

    assert (
        indicador.barras()[alta] <= 0.15
        or indicador.barras().index(max(indicador.barras())) != alta
    )


def test_las_barras_vuelven_a_reposo_al_empezar_otro_dictado(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)
    indicador.establecer_nivel(1.0)

    indicador.establecer_estado(E.TRANSCRIBIENDO)
    indicador.establecer_estado(E.ESCUCHANDO)

    assert all(b <= 0.15 for b in indicador.barras())


def test_las_barras_siempre_quedan_entre_0_y_1(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)

    for nivel in (-3.0, 0.4, 7.0, 0.0):
        indicador.establecer_nivel(nivel)

    assert all(0.0 <= b <= 1.0 for b in indicador.barras())


def test_la_pildora_oscura_se_dibuja_con_texto_legible(qtbot: QtBot) -> None:
    from vozflow.ui.tema import contraste

    indicador = _indicador(qtbot)

    assert contraste(indicador.color_de_fondo(), indicador.color_de_texto()) >= 4.5


def test_en_la_pildora_se_ven_las_barras_en_el_color_del_estado(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO)
    indicador.establecer_nivel(1.0)
    indicador.show()

    imagen = indicador.grab().toImage()
    colores = {
        imagen.pixelColor(x, y).name()
        for x in range(imagen.width())
        for y in range(imagen.height())
    }

    assert indicador.color_del_estado() in colores


# ---- «· IA» al mejorar (003, RT-008) ---------------------------------------------------------------------------


def test_al_mejorar_el_indicador_avisa_que_usa_la_ia(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO, mejorando=True)

    assert indicador.texto == "Escuchando… · IA"


def test_sin_mejorar_el_texto_no_cambia(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO, mejorando=False)

    assert indicador.texto == "Escuchando…"


def test_al_traducir_manda_el_idioma_y_no_se_repite_la_ia(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)

    indicador.establecer_estado(E.ESCUCHANDO, "inglés", mejorando=True)

    assert indicador.texto == "Escuchando… → inglés"


def test_mientras_transcribe_una_mejora_sigue_diciendo_ia(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO, mejorando=True)

    indicador.establecer_estado(E.TRANSCRIBIENDO, mejorando=True)

    assert indicador.texto.endswith("· IA")


def test_en_inactivo_se_oculta_aunque_se_estuviera_mejorando(qtbot: QtBot) -> None:
    indicador = _indicador(qtbot)
    indicador.establecer_estado(E.ESCUCHANDO, mejorando=True)

    indicador.establecer_estado(E.INACTIVO, mejorando=True)

    assert not indicador.isVisible()
