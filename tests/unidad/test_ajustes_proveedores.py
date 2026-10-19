"""Página de proveedores de reescritura (RF-023 a RF-025)."""

import os
from collections.abc import Callable

from PySide6.QtWidgets import QLineEdit
from pytestqt.qtbot import QtBot

from tests.dobles import ReescritorFalso
from tests.unidad.test_gestion_de_proveedores import CLAVE, Claves
from vozflow.gestion_de_proveedores import GestionDeProveedores
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.proveedores import PaginaProveedores

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _en_el_acto(trabajo: Callable[[], str], al_terminar: Callable[[str, bool], None]) -> None:
    """Corre «en segundo plano» sin hilos, para que la prueba sea determinista."""
    from vozflow.gestion_de_proveedores import ErrorDeProveedor

    try:
        al_terminar(trabajo(), False)
    except ErrorDeProveedor as error:
        al_terminar(str(error), True)


def _pagina(qtbot: QtBot, reescritor: ReescritorFalso | None = None):  # type: ignore[no-untyped-def]
    claves = Claves()
    reescritor = reescritor or ReescritorFalso("Hola, mundo.")
    gestion = GestionDeProveedores(
        abrir_base(":memory:"),
        claves,
        lambda p, c: reescritor,
    )
    pagina = PaginaProveedores(gestion, en_segundo_plano=_en_el_acto)
    qtbot.addWidget(pagina)
    return pagina, gestion, claves


def _elegir(pagina: PaginaProveedores, id_: str) -> None:
    pagina.combo_proveedor.setCurrentIndex(pagina.combo_proveedor.findData(id_))


def test_muestra_que_la_reescritura_esta_apagada_por_defecto(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert "apagada" in pagina.estado_general.text().lower()


def test_ofrece_los_tres_proveedores(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    ids = [pagina.combo_proveedor.itemData(i) for i in range(pagina.combo_proveedor.count())]

    assert ids == ["ollama", "anthropic", "openrouter"]


def test_la_direccion_es_solo_de_ollama_y_la_clave_solo_de_los_externos(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    _elegir(pagina, "ollama")
    assert pagina.campo_direccion.isEnabled() and not pagina.campo_clave.isEnabled()
    _elegir(pagina, "anthropic")
    assert not pagina.campo_direccion.isEnabled() and pagina.campo_clave.isEnabled()


def test_el_campo_de_la_clave_es_oculto(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert pagina.campo_clave.echoMode() == QLineEdit.EchoMode.Password


def test_guardar_graba_modelo_tiempo_y_clave_y_vacia_el_campo_de_la_clave(qtbot: QtBot) -> None:
    pagina, gestion, claves = _pagina(qtbot)
    _elegir(pagina, "anthropic")
    pagina.campo_modelo.setText("claude-haiku-5-5")
    pagina.spin_tiempo.setValue(25)
    pagina.campo_clave.setText(CLAVE)

    pagina.guardar()

    anthropic = next(e for e in gestion.estado() if e.proveedor.id == "anthropic")
    assert (anthropic.proveedor.modelo, anthropic.proveedor.tiempo_maximo_s) == (
        "claude-haiku-5-5",
        25,
    )
    assert claves.guardadas == {"anthropic": CLAVE}
    assert pagina.campo_clave.text() == ""  # la clave no queda a la vista
    assert CLAVE not in pagina.mensaje and CLAVE not in pagina.estado_general.text()


def test_guardar_sin_tocar_la_clave_no_la_pisa(qtbot: QtBot) -> None:
    pagina, _, claves = _pagina(qtbot)
    claves.guardar("anthropic", CLAVE)
    _elegir(pagina, "anthropic")
    pagina.campo_modelo.setText("m")

    pagina.guardar()

    assert claves.guardadas == {"anthropic": CLAVE}


def test_dice_si_hay_clave_guardada_sin_mostrarla(qtbot: QtBot) -> None:
    pagina, _, claves = _pagina(qtbot)
    claves.guardar("anthropic", CLAVE)

    _elegir(pagina, "anthropic")

    assert "guardada" in pagina.campo_clave.placeholderText().lower()
    assert CLAVE not in pagina.campo_clave.placeholderText()


def test_activar_enciende_la_reescritura_y_lo_muestra(qtbot: QtBot) -> None:
    pagina, gestion, claves = _pagina(qtbot)
    claves.guardar("anthropic", CLAVE)
    _elegir(pagina, "anthropic")
    pagina.campo_modelo.setText("m")
    pagina.guardar()

    pagina.activar()

    assert gestion.reescritura_encendida() is True
    assert "encendida" in pagina.estado_general.text().lower()
    assert "anthropic" in pagina.estado_general.text().lower()


def test_activar_sin_modelo_o_sin_clave_explica_que_falta(qtbot: QtBot) -> None:
    pagina, gestion, _ = _pagina(qtbot)
    _elegir(pagina, "anthropic")

    pagina.activar()
    assert pagina.hay_error is True and "modelo" in pagina.mensaje

    pagina.campo_modelo.setText("m")
    pagina.guardar()
    pagina.activar()
    assert pagina.hay_error is True and "clave" in pagina.mensaje
    assert gestion.reescritura_encendida() is False


def test_desactivar_apaga_la_reescritura(qtbot: QtBot) -> None:
    pagina, gestion, _ = _pagina(qtbot)
    _elegir(pagina, "ollama")
    pagina.campo_modelo.setText("llama3.2")
    pagina.guardar()
    pagina.activar()

    pagina.desactivar()

    assert gestion.reescritura_encendida() is False
    assert "apagada" in pagina.estado_general.text().lower()


def test_probar_muestra_el_resultado(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)
    _elegir(pagina, "ollama")
    pagina.campo_modelo.setText("llama3.2")
    pagina.guardar()

    pagina.probar()

    assert pagina.hay_error is False and "Hola, mundo." in pagina.mensaje


def test_probar_con_un_fallo_muestra_el_motivo_y_nunca_la_clave(qtbot: QtBot) -> None:
    pagina, _, claves = _pagina(
        qtbot, ReescritorFalso(fallo="Anthropic rechazó la clave de acceso")
    )
    claves.guardar("anthropic", CLAVE)
    _elegir(pagina, "anthropic")
    pagina.campo_modelo.setText("m")
    pagina.guardar()

    pagina.probar()

    assert pagina.hay_error is True and "rechazó la clave" in pagina.mensaje
    assert CLAVE not in pagina.mensaje


def test_un_tiempo_fuera_de_rango_no_se_puede_poner(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert (pagina.spin_tiempo.minimum(), pagina.spin_tiempo.maximum()) == (3, 60)


def test_borrar_la_clave(qtbot: QtBot) -> None:
    pagina, _, claves = _pagina(qtbot)
    claves.guardar("anthropic", CLAVE)
    _elegir(pagina, "anthropic")

    pagina.borrar_clave()

    assert claves.guardadas == {}


def test_una_direccion_invalida_de_ollama_se_rechaza(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)
    _elegir(pagina, "ollama")
    pagina.campo_direccion.setText("localhost:11434")

    pagina.guardar()

    assert pagina.hay_error is True and "dirección" in pagina.mensaje


# ---- idioma de destino de la traducción (lote 6) ---------------------------------------------------------


def test_muestra_el_idioma_de_destino_y_ofrece_sugerencias(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    sugerencias = [pagina.combo_idioma.itemText(i) for i in range(pagina.combo_idioma.count())]

    assert pagina.combo_idioma.currentText() == "inglés"
    assert {"inglés", "español", "portugués", "francés", "alemán", "italiano"} <= set(sugerencias)
    assert pagina.combo_idioma.isEditable()  # se puede escribir cualquier otro


def test_guardar_graba_el_idioma_escrito_a_mano(qtbot: QtBot) -> None:
    pagina, gestion, _ = _pagina(qtbot)
    pagina.combo_idioma.setCurrentText("japonés")

    pagina.guardar()

    assert gestion.idioma_de_traduccion() == "japonés"


def test_un_idioma_vacio_se_rechaza_con_un_aviso(qtbot: QtBot) -> None:
    pagina, gestion, _ = _pagina(qtbot)
    pagina.combo_idioma.setCurrentText("  ")

    pagina.guardar()

    assert pagina.hay_error is True and "idioma" in pagina.mensaje.lower()
    assert gestion.idioma_de_traduccion() == "inglés"


def test_explica_que_la_traduccion_usa_el_mismo_servicio(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    assert "tecla de traducir" in pagina.aclaracion_de_traduccion.text().lower()


# ---- presentación como función opcional y privacidad (002, RP-020) --------------------------------------------


def test_la_pagina_dice_que_es_opcional_y_viene_apagada(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    texto = pagina.aviso_de_privacidad.text().lower()

    assert "opcional" in texto and "apagado" in texto


def test_la_pagina_dice_que_sale_del_equipo_y_que_el_audio_nunca(qtbot: QtBot) -> None:
    pagina, _, _ = _pagina(qtbot)

    texto = pagina.aviso_de_privacidad.text().lower()

    assert "texto" in texto and "audio nunca" in texto


def test_las_etiquetas_usan_los_textos_llanos(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QLabel

    from vozflow.ui.textos import texto_de

    pagina, _, _ = _pagina(qtbot)
    etiquetas = [e.text() for e in pagina.findChildren(QLabel)]

    for clave in ("proveedor.modelo", "proveedor.tiempo", "proveedor.direccion", "proveedor.clave"):
        assert texto_de(clave).titulo in etiquetas


def test_cada_campo_lleva_su_ayuda_como_pista(qtbot: QtBot) -> None:
    from vozflow.ui.textos import ayuda_de

    pagina, _, _ = _pagina(qtbot)

    assert pagina.campo_modelo.toolTip() == ayuda_de("proveedor.modelo")
    assert pagina.spin_tiempo.toolTip() == ayuda_de("proveedor.tiempo")
    assert pagina.campo_direccion.toolTip() == ayuda_de("proveedor.direccion")
    assert pagina.campo_clave.toolTip() == ayuda_de("proveedor.clave")
    assert pagina.combo_idioma.toolTip() == ayuda_de("traduccion.idioma")


def test_la_pagina_declara_sus_claves_para_el_inventario() -> None:
    assert set(PaginaProveedores.CLAVES) == {"reescritura.activa", "traduccion.idioma"}
