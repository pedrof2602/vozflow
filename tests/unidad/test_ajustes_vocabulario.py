"""Página de vocabulario (RF-019, RF-020): diccionario y atajos de texto."""

import os

from pytestqt.qtbot import QtBot

from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.ui.ajustes.vocabulario import PaginaVocabulario

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _pagina(qtbot: QtBot):  # type: ignore[no-untyped-def]
    base = abrir_base(":memory:")
    diccionario, atajos = DiccionarioRepo(base), AtajosTextoRepo(base)
    pagina = PaginaVocabulario(diccionario, atajos)
    qtbot.addWidget(pagina)
    return pagina, diccionario, atajos


def test_agrega_una_palabra_con_nota(qtbot: QtBot) -> None:
    pagina, diccionario, _ = _pagina(qtbot)
    pagina.campo_palabra.setText("SQLAlchemy")
    pagina.campo_nota.setText("ORM")

    pagina.agregar_palabra()

    assert [(e.palabra, e.nota) for e in diccionario.listar()] == [("SQLAlchemy", "ORM")]
    assert pagina.lista_palabras.count() == 1
    assert pagina.campo_palabra.text() == ""  # queda listo para la siguiente


def test_una_palabra_repetida_o_vacia_se_rechaza_con_la_misma_regla_del_modelo(
    qtbot: QtBot,
) -> None:
    pagina, diccionario, _ = _pagina(qtbot)
    pagina.campo_palabra.setText("SQLAlchemy")
    pagina.agregar_palabra()

    pagina.campo_palabra.setText("sqlalchemy")
    pagina.agregar_palabra()
    assert pagina.hay_error is True and "ya está" in pagina.mensaje

    pagina.campo_palabra.setText("  ")
    pagina.agregar_palabra()
    assert pagina.hay_error is True and "obligatoria" in pagina.mensaje
    assert len(diccionario.listar()) == 1


def test_el_campo_de_palabra_limita_los_80_caracteres(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert pagina.campo_palabra.maxLength() == 80


def test_borra_la_palabra_elegida(qtbot: QtBot) -> None:
    pagina, diccionario, _ = _pagina(qtbot)
    for palabra in ("uno", "dos"):
        pagina.campo_palabra.setText(palabra)
        pagina.agregar_palabra()

    pagina.lista_palabras.setCurrentRow(0)
    pagina.borrar_palabra()

    assert [e.palabra for e in diccionario.listar()] == ["dos"]
    assert pagina.lista_palabras.count() == 1


def test_borrar_sin_elegir_no_hace_nada(qtbot: QtBot) -> None:
    pagina, diccionario, _ = _pagina(qtbot)
    pagina.campo_palabra.setText("uno")
    pagina.agregar_palabra()
    pagina.lista_palabras.setCurrentRow(-1)

    pagina.borrar_palabra()

    assert len(diccionario.listar()) == 1


def test_agrega_un_atajo_de_texto_de_varias_lineas(qtbot: QtBot) -> None:
    pagina, _, atajos = _pagina(qtbot)
    pagina.campo_disparador.setText("mi firma")
    pagina.campo_reemplazo.setPlainText("Saludos,\nPedro")

    pagina.agregar_atajo()

    (atajo,) = atajos.listar()
    assert atajo.reemplazo == "Saludos,\nPedro"
    assert pagina.lista_atajos.count() == 1
    assert pagina.campo_reemplazo.toPlainText() == ""


def test_la_lista_de_atajos_muestra_el_reemplazo_en_una_linea(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)
    pagina.campo_disparador.setText("mi firma")
    pagina.campo_reemplazo.setPlainText("Saludos,\nPedro")
    pagina.agregar_atajo()

    texto = pagina.lista_atajos.item(0).text()

    assert "\n" not in texto and "mi firma" in texto and "Saludos," in texto


def test_un_atajo_sin_disparador_o_sin_reemplazo_se_rechaza(qtbot: QtBot) -> None:
    pagina, _, atajos = _pagina(qtbot)
    pagina.campo_disparador.setText("")
    pagina.campo_reemplazo.setPlainText("algo")
    pagina.agregar_atajo()
    assert "disparador" in pagina.mensaje

    pagina.campo_disparador.setText("ask")
    pagina.campo_reemplazo.setPlainText("   ")
    pagina.agregar_atajo()

    assert "reemplazo" in pagina.mensaje and pagina.hay_error is True
    assert atajos.listar() == []


def test_un_disparador_repetido_se_rechaza(qtbot: QtBot) -> None:
    pagina, _, atajos = _pagina(qtbot)
    pagina.campo_disparador.setText("ask")
    pagina.campo_reemplazo.setPlainText("pedido")
    pagina.agregar_atajo()

    pagina.campo_disparador.setText("ASK")
    pagina.campo_reemplazo.setPlainText("otro")
    pagina.agregar_atajo()

    assert pagina.hay_error is True and len(atajos.listar()) == 1


def test_el_disparador_limita_los_100_caracteres(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert pagina.campo_disparador.maxLength() == 100


def test_borra_el_atajo_elegido(qtbot: QtBot) -> None:
    pagina, _, atajos = _pagina(qtbot)
    pagina.campo_disparador.setText("ask")
    pagina.campo_reemplazo.setPlainText("pedido")
    pagina.agregar_atajo()

    pagina.lista_atajos.setCurrentRow(0)
    pagina.borrar_atajo()

    assert atajos.listar() == [] and pagina.lista_atajos.count() == 0


def test_muestra_lo_que_ya_estaba_guardado(qtbot: QtBot) -> None:
    base = abrir_base(":memory:")
    DiccionarioRepo(base).agregar("FastAPI")
    AtajosTextoRepo(base).agregar("ask", "pedido")
    pagina = PaginaVocabulario(DiccionarioRepo(base), AtajosTextoRepo(base))
    qtbot.addWidget(pagina)

    assert pagina.lista_palabras.count() == 1 and pagina.lista_atajos.count() == 1


def test_los_botones_no_se_estiran_a_todo_el_ancho(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QPushButton

    pagina, _, _ = _pagina(qtbot)
    pagina.resize(800, 700)
    pagina.show()

    botones = pagina.findChildren(QPushButton)

    assert botones and all(b.width() < pagina.width() / 2 for b in botones)
