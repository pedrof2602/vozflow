"""Página «Dictado» de los ajustes (002, RP-015, RP-017 a RP-019): lo básico, simple y explicado."""

import os
from collections.abc import Mapping

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from vozflow.atajos.puerto import AccionDeAtajo, AtajoOcupado
from vozflow.audio.captura import Dispositivo
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.dictado import PaginaDictado
from vozflow.ui.textos import ayuda_de, texto_de

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DISPOSITIVOS = [
    Dispositivo(0, "Micrófono interno", 2, es_predeterminado=True),
    Dispositivo(3, "Auriculares USB", 1, es_predeterminado=False),
]


class Aplicador:
    def __init__(self) -> None:
        self.recibidos: list[dict[AccionDeAtajo, str]] = []
        self.error: Exception | None = None

    def __call__(self, atajos: Mapping[AccionDeAtajo, str]) -> None:
        if self.error is not None:
            raise self.error
        self.recibidos.append(dict(atajos))


def _pagina(qtbot: QtBot, dispositivos: list[Dispositivo] | None = None):  # type: ignore[no-untyped-def]
    ajustes = AjustesRepo(abrir_base(":memory:"))
    aplicador = Aplicador()
    lista = DISPOSITIVOS if dispositivos is None else dispositivos
    pagina = PaginaDictado(ajustes, aplicador, lambda: lista)
    qtbot.addWidget(pagina)
    pagina.show()
    return pagina, ajustes, aplicador


def _textos(pagina: PaginaDictado) -> list[str]:
    return [e.text() for e in pagina.findChildren(QLabel)]


# ---- lo que muestra ---------------------------------------------------------------------------------------------


def test_una_base_nueva_muestra_los_valores_por_defecto(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert pagina.teclas.textos() == ["Ctrl der."]
    assert pagina.combo_microfono.currentData() == ""
    assert pagina.combo_idioma.currentData() == "automatico"
    assert pagina.interruptor_indicador.isChecked() is True


def test_cada_opcion_lleva_su_titulo_y_su_ayuda_en_lenguaje_llano(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)
    textos = _textos(pagina)

    for clave in ("atajo.mantener", "audio.dispositivo", "idioma.modo", "interfaz.indicador"):
        assert texto_de(clave).titulo in textos
        assert ayuda_de(clave) in textos


def test_ofrece_el_predeterminado_y_cada_microfono(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    nombres = [pagina.combo_microfono.itemText(i) for i in range(pagina.combo_microfono.count())]

    assert nombres[0].startswith("Predeterminado")
    assert "Micrófono interno" in nombres[1] and "Auriculares USB" in nombres[2]


def test_un_microfono_guardado_que_hoy_no_esta_se_ve_como_no_conectado(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("audio.dispositivo", "Micrófono viejo")
    pagina = PaginaDictado(ajustes, Aplicador(), lambda: DISPOSITIVOS)
    qtbot.addWidget(pagina)

    assert "no conectado" in pagina.combo_microfono.currentText()


def test_sin_microfonos_la_pagina_igual_abre(qtbot: QtBot) -> None:
    def falla() -> list[Dispositivo]:
        raise OSError("sin audio")

    ajustes = AjustesRepo(abrir_base(":memory:"))
    pagina = PaginaDictado(ajustes, Aplicador(), falla)
    qtbot.addWidget(pagina)

    assert pagina.combo_microfono.count() == 1


def test_muestra_la_tecla_guardada_con_teclas_dibujadas(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("atajo.mantener", "F9")
    pagina = PaginaDictado(ajustes, Aplicador(), lambda: [])
    qtbot.addWidget(pagina)

    assert pagina.teclas.textos() == ["F9"]


# ---- se guarda al cambiar, sin botón «Guardar» ------------------------------------------------------------


def test_elegir_un_microfono_lo_guarda_enseguida(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)

    pagina.combo_microfono.setCurrentIndex(2)

    assert ajustes.obtener("audio.dispositivo") == "Auriculares USB"
    assert pagina.hay_error is False and "próxima vez" in pagina.mensaje


def test_elegir_el_idioma_lo_guarda_enseguida(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)

    pagina.combo_idioma.setCurrentIndex(pagina.combo_idioma.findData("en"))

    assert ajustes.obtener("idioma.modo") == "en"


def test_el_cartel_se_prende_y_se_apaga_enseguida(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)

    pagina.interruptor_indicador.setChecked(False)

    assert ajustes.obtener("interfaz.indicador") is False
    assert "ya funciona" in pagina.mensaje.lower()


def test_la_pagina_no_tiene_boton_guardar(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QPushButton

    pagina, _, _ = _pagina(qtbot)

    assert "Guardar" not in [b.text() for b in pagina.findChildren(QPushButton)]


def test_mostrar_los_valores_guardados_no_los_vuelve_a_guardar(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)

    pagina.recargar()

    assert ajustes.todos()["audio.dispositivo"] == "" and pagina.mensaje == ""


# ---- la tecla para dictar --------------------------------------------------------------------------------------


def test_cambiar_muestra_el_campo_de_captura_y_le_da_el_foco(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)
    assert pagina.campo_tecla.isHidden() is True

    pagina.boton_cambiar.click()

    assert pagina.campo_tecla.isHidden() is False
    assert "Apretá" in pagina.campo_tecla.placeholderText()


def test_apretar_una_tecla_nueva_la_aplica_en_vivo_y_la_guarda(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    pagina.boton_cambiar.click()

    QTest.keyClick(pagina.campo_tecla, Qt.Key.Key_F9)

    assert ajustes.obtener("atajo.mantener") == "F9"
    assert aplicador.recibidos[-1][AccionDeAtajo.MANTENER] == "F9"
    assert aplicador.recibidos[-1][AccionDeAtajo.ALTERNAR] == "<Control><Alt>space"
    assert pagina.teclas.textos() == ["F9"]
    assert pagina.campo_tecla.isHidden() is True
    assert pagina.hay_error is False


def test_si_la_tecla_choca_con_otra_funcion_avisa_y_vuelve_a_la_anterior(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    aplicador.error = AtajoOcupado("la usa GNOME")
    pagina.boton_cambiar.click()

    QTest.keyClick(pagina.campo_tecla, Qt.Key.Key_F9)

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert pagina.hay_error is True and pagina.teclas.textos() == ["Ctrl der."]


def test_una_tecla_igual_a_otra_funcion_se_rechaza(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)
    ajustes.establecer("atajo.traducir", "F9")
    pagina.boton_cambiar.click()

    QTest.keyClick(pagina.campo_tecla, Qt.Key.Key_F9)

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert pagina.hay_error is True and "distintas" in pagina.mensaje


# ---- restablecer por opción -----------------------------------------------------------------------------------


def _restablecer_de(pagina: PaginaDictado, clave: str):  # type: ignore[no-untyped-def]
    return pagina.filas[clave].boton_restablecer


def test_con_los_valores_de_fabrica_no_hay_ningun_restablecer(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert all(
        fila.boton_restablecer is not None and fila.boton_restablecer.isHidden()
        for fila in pagina.filas.values()
    )


def test_cada_opcion_tiene_su_fila_con_restablecer(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert set(pagina.filas) == {
        "atajo.mantener", "audio.dispositivo", "idioma.modo", "interfaz.indicador",
    }  # fmt: skip


def test_restablecer_el_microfono_vuelve_al_predeterminado(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)
    pagina.combo_microfono.setCurrentIndex(2)
    assert _restablecer_de(pagina, "audio.dispositivo").isHidden() is False

    _restablecer_de(pagina, "audio.dispositivo").click()

    assert ajustes.obtener("audio.dispositivo") == ""
    assert pagina.combo_microfono.currentData() == ""
    assert _restablecer_de(pagina, "audio.dispositivo").isHidden() is True


def test_restablecer_el_idioma_y_el_cartel(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)
    pagina.combo_idioma.setCurrentIndex(pagina.combo_idioma.findData("es"))
    pagina.interruptor_indicador.setChecked(False)

    _restablecer_de(pagina, "idioma.modo").click()
    _restablecer_de(pagina, "interfaz.indicador").click()

    assert ajustes.obtener("idioma.modo") == "automatico"
    assert ajustes.obtener("interfaz.indicador") is True
    assert pagina.interruptor_indicador.isChecked() is True


def test_restablecer_la_tecla_la_aplica_en_vivo(qtbot: QtBot) -> None:
    pagina, ajustes, aplicador = _pagina(qtbot)
    pagina.boton_cambiar.click()
    QTest.keyClick(pagina.campo_tecla, Qt.Key.Key_F9)
    assert _restablecer_de(pagina, "atajo.mantener").isHidden() is False

    _restablecer_de(pagina, "atajo.mantener").click()

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert aplicador.recibidos[-1][AccionDeAtajo.MANTENER] == "RightCtrl"
    assert pagina.teclas.textos() == ["Ctrl der."]


def test_esta_la_clave_de_cada_opcion_para_el_inventario(qtbot: QtBot) -> None:
    assert set(PaginaDictado.CLAVES) == {
        "atajo.mantener", "audio.dispositivo", "idioma.modo", "interfaz.indicador",
    }  # fmt: skip


# ---- lo que verificaba la antigua página de audio (migrado) ------------------------------------------------


def test_elegir_el_predeterminado_guarda_vacio(qtbot: QtBot) -> None:
    pagina, ajustes, _ = _pagina(qtbot)
    pagina.combo_microfono.setCurrentIndex(2)

    pagina.combo_microfono.setCurrentIndex(0)

    assert ajustes.obtener("audio.dispositivo") == ""


def test_muestra_lo_ya_guardado_de_microfono_e_idioma(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("audio.dispositivo", "Auriculares USB")
    ajustes.establecer("idioma.modo", "es")
    ajustes.establecer("interfaz.indicador", False)
    pagina = PaginaDictado(ajustes, Aplicador(), lambda: DISPOSITIVOS)
    qtbot.addWidget(pagina)

    assert pagina.combo_microfono.currentText().startswith("Auriculares")
    assert pagina.combo_idioma.currentData() == "es"
    assert pagina.interruptor_indicador.isChecked() is False


def test_cambiar_el_microfono_avisa_que_rige_la_proxima_vez(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    pagina.combo_microfono.setCurrentIndex(1)

    assert "próxima vez" in pagina.mensaje.lower()
