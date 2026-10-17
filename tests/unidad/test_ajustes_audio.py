"""Página de audio y motor de los ajustes (RF-005): micrófono, idioma, modelo, hilos, indicador."""

import os

from pytestqt.qtbot import QtBot

from vozflow.audio.captura import Dispositivo
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.audio import PaginaAudio

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DISPOSITIVOS = [
    Dispositivo(0, "Micrófono interno", 2, es_predeterminado=True),
    Dispositivo(3, "Auriculares USB", 1, es_predeterminado=False),
]


def _pagina(qtbot: QtBot, dispositivos: list[Dispositivo] | None = None):  # type: ignore[no-untyped-def]
    ajustes = AjustesRepo(abrir_base(":memory:"))
    lista = DISPOSITIVOS if dispositivos is None else dispositivos
    pagina = PaginaAudio(ajustes, listar_dispositivos=lambda: lista)
    qtbot.addWidget(pagina)
    return pagina, ajustes


def test_ofrece_el_predeterminado_y_cada_microfono(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    nombres = [pagina.combo_microfono.itemText(i) for i in range(pagina.combo_microfono.count())]

    assert nombres[0].startswith("Predeterminado")
    assert "Micrófono interno" in nombres[1] and "Auriculares USB" in nombres[2]


def test_arranca_con_los_valores_por_defecto(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    assert pagina.combo_microfono.currentIndex() == 0
    assert pagina.combo_idioma.currentData() == "automatico"
    assert pagina.campo_modelo.text() == "small"
    assert pagina.spin_hilos.value() == 4
    assert pagina.check_indicador.isChecked() is True


def test_guarda_todo_lo_elegido(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina(qtbot)
    pagina.combo_microfono.setCurrentIndex(2)
    pagina.combo_idioma.setCurrentIndex(pagina.combo_idioma.findData("en"))
    pagina.campo_modelo.setText("medium")
    pagina.spin_hilos.setValue(6)
    pagina.check_indicador.setChecked(False)

    pagina.guardar()

    assert ajustes.obtener("audio.dispositivo") == "Auriculares USB"
    assert ajustes.obtener("idioma.modo") == "en"
    assert ajustes.obtener("motor.modelo") == "medium"
    assert ajustes.obtener("motor.hilos") == 6
    assert ajustes.obtener("interfaz.indicador") is False
    assert pagina.hay_error is False


def test_elegir_el_predeterminado_guarda_vacio(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina(qtbot)
    ajustes.establecer("audio.dispositivo", "Auriculares USB")
    pagina.recargar()

    pagina.combo_microfono.setCurrentIndex(0)
    pagina.guardar()

    assert ajustes.obtener("audio.dispositivo") == ""


def test_muestra_lo_ya_guardado(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("audio.dispositivo", "Auriculares USB")
    ajustes.establecer("idioma.modo", "es")
    ajustes.establecer("motor.hilos", 2)
    pagina = PaginaAudio(ajustes, listar_dispositivos=lambda: DISPOSITIVOS)
    qtbot.addWidget(pagina)

    assert pagina.combo_microfono.currentText().startswith("Auriculares")
    assert pagina.combo_idioma.currentData() == "es" and pagina.spin_hilos.value() == 2


def test_los_hilos_van_de_1_a_8(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    assert (pagina.spin_hilos.minimum(), pagina.spin_hilos.maximum()) == (1, 8)


def test_un_modelo_vacio_se_rechaza_y_no_cambia_nada(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina(qtbot)
    pagina.campo_modelo.setText("  ")
    pagina.spin_hilos.setValue(7)

    pagina.guardar()

    assert pagina.hay_error is True and "modelo" in pagina.mensaje.lower()
    assert ajustes.obtener("motor.hilos") == 4


def test_un_microfono_guardado_que_ya_no_esta_se_conserva_en_la_lista(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("audio.dispositivo", "Micrófono desenchufado")
    pagina = PaginaAudio(ajustes, listar_dispositivos=lambda: DISPOSITIVOS)
    qtbot.addWidget(pagina)

    assert "desenchufado" in pagina.combo_microfono.currentText()


def test_sin_microfonos_igual_funciona_con_el_predeterminado(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot, dispositivos=[])

    assert pagina.combo_microfono.count() == 1


def test_si_no_se_puede_listar_los_microfonos_no_se_cae(qtbot: QtBot) -> None:
    def falla() -> list[Dispositivo]:
        raise OSError("sin PortAudio")

    pagina = PaginaAudio(AjustesRepo(abrir_base(":memory:")), listar_dispositivos=falla)
    qtbot.addWidget(pagina)

    assert pagina.combo_microfono.count() == 1


def test_avisa_que_el_micro_el_idioma_y_el_modelo_rigen_al_reiniciar(qtbot: QtBot) -> None:
    pagina, _ = _pagina(qtbot)

    pagina.guardar()

    assert "reinici" in pagina.mensaje.lower()
