"""Página de modos de los ajustes (RF-021): crear, editar y asignar aplicaciones."""

import os

from pytestqt.qtbot import QtBot

from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.modos_repo import ModosRepo
from vozflow.ui.ajustes.modos import PaginaModos

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _pagina(qtbot: QtBot):  # type: ignore[no-untyped-def]
    base = abrir_base(":memory:")
    modos, asignaciones = ModosRepo(base), AsignacionesRepo(base)
    pagina = PaginaModos(modos, asignaciones)
    qtbot.addWidget(pagina)
    return pagina, modos, asignaciones


def test_lista_los_modos_de_fabrica(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    nombres = [pagina.lista.item(i).text() for i in range(pagina.lista.count())]

    assert nombres == ["General", "Terminal", "Código", "Mensajería", "Documentos"]


def test_al_elegir_un_modo_muestra_sus_banderas(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    pagina.seleccionar("Terminal")

    assert pagina.campo_nombre.text() == "Terminal"
    assert pagina.combo_pegado.currentData() == "terminal"
    assert pagina.combo_salto.currentData() == "espacio"
    assert pagina.check_muletillas.isChecked() and pagina.check_puntuacion.isChecked()


def test_crea_un_modo_nuevo(qtbot: QtBot) -> None:
    pagina, modos, _ = _pagina(qtbot)

    pagina.nuevo()
    pagina.campo_nombre.setText("Reuniones")
    pagina.check_puntuacion.setChecked(False)
    pagina.campo_instruccion.setPlainText("Tono formal")
    pagina.guardar_modo()

    modo = modos.obtener("Reuniones")
    assert modo is not None and modo.puntuacion_automatica is False
    assert modo.instruccion == "Tono formal"
    assert "Reuniones" in [pagina.lista.item(i).text() for i in range(pagina.lista.count())]


def test_edita_un_modo_existente(qtbot: QtBot) -> None:
    pagina, modos, _ = _pagina(qtbot)
    pagina.seleccionar("Código")

    pagina.check_comandos.setChecked(False)
    pagina.combo_salto.setCurrentIndex(pagina.combo_salto.findData("espacio"))
    pagina.guardar_modo()

    codigo = modos.obtener("Código")
    assert codigo is not None and codigo.comandos_de_voz is False
    assert codigo.salto_de_linea == "espacio"


def test_un_nombre_repetido_se_rechaza_con_un_aviso(qtbot: QtBot) -> None:
    pagina, modos, _ = _pagina(qtbot)
    pagina.nuevo()
    pagina.campo_nombre.setText("terminal")

    pagina.guardar_modo()

    assert pagina.hay_error is True and "Terminal" in pagina.mensaje
    assert len(modos.listar()) == 5


def test_borra_un_modo_y_no_deja_borrar_el_general(qtbot: QtBot) -> None:
    pagina, modos, _ = _pagina(qtbot)
    pagina.seleccionar("Documentos")
    pagina.borrar_modo()
    assert modos.obtener("Documentos") is None

    pagina.seleccionar("General")
    pagina.borrar_modo()

    assert modos.obtener("General") is not None
    assert pagina.hay_error is True and "general" in pagina.mensaje.lower()


def test_el_boton_de_borrar_se_apaga_con_el_general(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    pagina.seleccionar("General")
    assert pagina.boton_borrar.isEnabled() is False
    pagina.seleccionar("Terminal")
    assert pagina.boton_borrar.isEnabled() is True


# ---- asignar aplicaciones ----------------------------------------------------------------------------------


def test_asigna_una_aplicacion_a_un_modo(qtbot: QtBot) -> None:
    pagina, _, asignaciones = _pagina(qtbot)

    pagina.asignar("ptyxis", "Terminal", es_terminal=False)

    (asignacion,) = asignaciones.listar()
    assert asignacion.aplicacion == "ptyxis" and asignacion.es_terminal is False
    assert pagina.tabla.rowCount() == 1


def test_marca_a_mano_una_aplicacion_como_terminal(qtbot: QtBot) -> None:
    pagina, _, asignaciones = _pagina(qtbot)

    pagina.asignar("vscodium", "General", es_terminal=True)

    asignacion = asignaciones.obtener("vscodium")
    assert asignacion is not None and asignacion.es_terminal is True


def test_la_tabla_muestra_aplicacion_modo_y_terminal(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)
    pagina.asignar("ptyxis", "Terminal", es_terminal=True)

    fila = [pagina.tabla.item(0, c).text() for c in range(3)]

    assert fila == ["ptyxis", "Terminal", "Sí"]


def test_quita_una_asignacion(qtbot: QtBot) -> None:
    pagina, _, asignaciones = _pagina(qtbot)
    pagina.asignar("ptyxis", "Terminal", es_terminal=False)

    pagina.quitar_asignacion("ptyxis")

    assert asignaciones.listar() == [] and pagina.tabla.rowCount() == 0


def test_asignar_sin_aplicacion_es_un_error(qtbot: QtBot) -> None:
    pagina, _, asignaciones = _pagina(qtbot)

    pagina.asignar("  ", "Terminal", es_terminal=False)

    assert pagina.hay_error is True and asignaciones.listar() == []


def test_al_borrar_un_modo_sus_aplicaciones_pasan_al_general_en_la_tabla(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)
    pagina.asignar("obsidian", "Documentos", es_terminal=False)

    pagina.seleccionar("Documentos")
    pagina.borrar_modo()

    assert pagina.tabla.item(0, 1).text() == "General"
