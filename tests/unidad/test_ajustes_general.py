"""Página «General» de los ajustes (002, RP-015): tema, arrancar con la sesión, repetir el asistente.

Reúne y reemplaza lo que verificaban las páginas «Apariencia» y «Sistema».
"""

import os

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.general import PaginaGeneral
from vozflow.ui.textos import ayuda_de, texto_de

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class Autoinicio:
    def __init__(self, activo: bool = False, falla: Exception | None = None) -> None:
        self.activo = activo
        self.falla = falla
        self.llamadas: list[bool] = []

    def leer(self) -> bool:
        return self.activo

    def fijar(self, valor: bool) -> None:
        self.llamadas.append(valor)
        if self.falla is not None:
            raise self.falla
        self.activo = valor


def _pagina(  # type: ignore[no-untyped-def]
    qtbot: QtBot, autoinicio: Autoinicio | None = None, guardado: str | None = None
):
    ajustes = AjustesRepo(abrir_base(":memory:"))
    if guardado is not None:
        ajustes.establecer("interfaz.tema", guardado)
    temas: list[str] = []
    asistentes: list[int] = []
    arranque = autoinicio or Autoinicio()
    pagina = PaginaGeneral(
        ajustes, temas.append, arranque.leer, arranque.fijar, lambda: asistentes.append(1)
    )
    qtbot.addWidget(pagina)
    pagina.show()
    return pagina, ajustes, temas, arranque, asistentes


# ---- tema (lo que verificaba «Apariencia») ---------------------------------------------------------------------


def test_ofrece_automatico_claro_y_oscuro(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    opciones = [pagina.selector_tema.itemText(i) for i in range(pagina.selector_tema.count())]

    assert opciones == ["Automático (como el sistema)", "Claro", "Oscuro"]
    assert [pagina.selector_tema.itemData(i) for i in range(3)] == ["auto", "claro", "oscuro"]


def test_el_tema_arranca_en_automatico(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    assert pagina.selector_tema.currentData() == "auto"


def test_muestra_el_tema_guardado(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot, guardado="oscuro")

    assert pagina.selector_tema.currentData() == "oscuro"


def test_elegir_un_tema_lo_guarda_y_lo_aplica_en_el_momento(qtbot: QtBot) -> None:
    pagina, ajustes, temas, *_ = _pagina(qtbot)

    pagina.selector_tema.setCurrentIndex(1)

    assert ajustes.obtener("interfaz.tema") == "claro" and temas == ["claro"]


def test_volver_a_automatico_tambien_se_guarda(qtbot: QtBot) -> None:
    pagina, ajustes, temas, *_ = _pagina(qtbot)
    pagina.selector_tema.setCurrentIndex(2)

    pagina.selector_tema.setCurrentIndex(0)

    assert ajustes.obtener("interfaz.tema") == "auto" and temas == ["oscuro", "auto"]


def test_mostrar_el_tema_guardado_no_lo_vuelve_a_aplicar(qtbot: QtBot) -> None:
    _, _, temas, *_ = _pagina(qtbot, guardado="claro")

    assert temas == []


# ---- arrancar con la sesión (lo que verificaba «Sistema») ------------------------------------------------------


def test_el_interruptor_refleja_si_el_arranque_esta_activo(qtbot: QtBot) -> None:
    assert _pagina(qtbot, Autoinicio(True))[0].interruptor_autoinicio.isChecked() is True
    assert _pagina(qtbot, Autoinicio(False))[0].interruptor_autoinicio.isChecked() is False


def test_un_clic_activa_el_arranque_en_segundo_plano(qtbot: QtBot) -> None:
    pagina, _, _, arranque, _ = _pagina(qtbot, Autoinicio(False))

    QTest.mouseClick(pagina.interruptor_autoinicio, Qt.MouseButton.LeftButton)

    assert arranque.activo is True and arranque.llamadas == [True]
    assert pagina.hay_error is False and "arrancará" in pagina.mensaje


def test_otro_clic_lo_desactiva(qtbot: QtBot) -> None:
    pagina, _, _, arranque, _ = _pagina(qtbot, Autoinicio(True))

    QTest.mouseClick(pagina.interruptor_autoinicio, Qt.MouseButton.LeftButton)

    assert arranque.activo is False and arranque.llamadas == [False]
    assert "ya no arranca" in pagina.mensaje


def test_si_no_se_puede_el_interruptor_vuelve_atras_y_explica(qtbot: QtBot) -> None:
    arranque = Autoinicio(False, falla=FileExistsError("ya existe un archivo que no es de vozflow"))
    pagina, *_ = _pagina(qtbot, arranque)

    QTest.mouseClick(pagina.interruptor_autoinicio, Qt.MouseButton.LeftButton)

    assert pagina.interruptor_autoinicio.isChecked() is False
    assert pagina.hay_error is True and "ya existe" in pagina.mensaje


def test_el_error_al_volver_atras_no_dispara_otro_cambio(qtbot: QtBot) -> None:
    arranque = Autoinicio(False, falla=OSError("sin permiso"))
    pagina, *_ = _pagina(qtbot, arranque)

    QTest.mouseClick(pagina.interruptor_autoinicio, Qt.MouseButton.LeftButton)

    assert arranque.llamadas == [True]


# ---- ayuda, restablecer y el asistente --------------------------------------------------------------------------


def test_cada_opcion_lleva_su_titulo_y_su_ayuda(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)
    textos = [e.text() for e in pagina.findChildren(QLabel)]

    for clave in ("interfaz.tema", "autoinicio", "asistente.repetir"):
        assert texto_de(clave).titulo in textos and ayuda_de(clave) in textos


def test_la_ayuda_del_arranque_explica_que_es_en_segundo_plano() -> None:
    assert "segundo plano" in ayuda_de("autoinicio")


def test_con_el_tema_de_fabrica_no_hay_restablecer(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    boton = pagina.filas["interfaz.tema"].boton_restablecer
    assert boton is not None and boton.isHidden() is True


def test_restablecer_el_tema_vuelve_a_automatico_y_lo_aplica(qtbot: QtBot) -> None:
    pagina, ajustes, temas, *_ = _pagina(qtbot)
    pagina.selector_tema.setCurrentIndex(1)
    boton = pagina.filas["interfaz.tema"].boton_restablecer
    assert boton is not None and boton.isHidden() is False

    boton.click()

    assert ajustes.obtener("interfaz.tema") == "auto" and temas[-1] == "auto"
    assert pagina.selector_tema.currentData() == "auto" and boton.isHidden() is True


def test_el_arranque_con_la_sesion_no_tiene_restablecer(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    assert pagina.filas["autoinicio"].boton_restablecer is None


def test_el_boton_del_asistente_lo_abre(qtbot: QtBot) -> None:
    pagina, _, _, _, asistentes = _pagina(qtbot)

    pagina.boton_asistente.click()

    assert asistentes == [1]


def test_estan_las_claves_para_el_inventario() -> None:
    assert PaginaGeneral.CLAVES == ("interfaz.tema",)
