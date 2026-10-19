"""La ventana de ajustes (RF-029): reúne las páginas y vive en la bandeja."""

import os
from pathlib import Path

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QWidget
from pytestqt.qtbot import QtBot

from tests.dobles import ReescritorFalso
from tests.unidad.test_gestion_de_proveedores import Claves
from vozflow.audio.captura import Dispositivo
from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.insercion.puerto import Destino, ResultadoInsercion
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.ventana import ContextoDeAjustes, VentanaAjustes, crear_paginas
from vozflow.ui.estado import vista_de

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _ventana(qtbot: QtBot, ocultar_al_cerrar: bool = True) -> VentanaAjustes:
    paginas: dict[str, QWidget] = {
        "Uno": QLabel("uno"),
        "Dos": QLabel("dos"),
        "Tres": QLabel("tres"),
    }
    ventana = VentanaAjustes(paginas, ocultar_al_cerrar=ocultar_al_cerrar, espera_ms=0)
    qtbot.addWidget(ventana)
    return ventana


def test_cada_pagina_es_una_pestana_en_orden(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot)

    assert ventana.nombres_de_paginas() == ["Uno", "Dos", "Tres"]


def test_mostrar_pagina_elige_la_pestana_y_muestra_la_ventana(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot)

    ventana.mostrar_pagina("Tres")

    assert ventana.isVisible() and ventana.pagina_actual() == "Tres"


def test_una_pagina_que_no_existe_es_un_error(qtbot: QtBot) -> None:
    import pytest

    with pytest.raises(KeyError):
        _ventana(qtbot).mostrar_pagina("Inventada")


def test_muestra_el_estado_actual_aunque_no_haya_bandeja(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot)

    ventana.establecer_vista(vista_de(E.ESCUCHANDO))

    assert "Escuchando" in ventana.texto_de_estado()
    ventana.establecer_vista(vista_de(E.ERROR))
    assert "Error" in ventana.texto_de_estado()


def test_cerrar_la_ventana_la_oculta_y_el_programa_sigue(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot, ocultar_al_cerrar=True)
    ventana.show()

    evento = QCloseEvent()
    ventana.closeEvent(evento)

    assert not ventana.isVisible() and not evento.isAccepted()


def test_sin_bandeja_cerrar_solo_minimiza_para_no_perder_la_unica_puerta(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot, ocultar_al_cerrar=False)
    ventana.show()

    evento = QCloseEvent()
    ventana.closeEvent(evento)

    assert not evento.isAccepted() and ventana.isMinimized()


def test_salir_de_verdad_deja_que_se_cierre(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot)
    ventana.permitir_cierre()

    evento = QCloseEvent()
    ventana.closeEvent(evento)

    assert evento.isAccepted()


def test_para_reinsertar_se_oculta_espera_ejecuta_y_vuelve_a_mostrarse(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot)
    ventana.show()
    visto_durante: list[bool] = []

    ventana.sin_foco(lambda: visto_durante.append(ventana.isVisible()))

    qtbot.waitUntil(lambda: ventana.isVisible() and bool(visto_durante), timeout=2000)
    assert visto_durante == [False]


# ---- armado con todas las páginas ----------------------------------------------------------------------------


class Portapapeles:
    def copiar(self, texto: str, *, tambien_primaria: bool) -> None: ...


class Insertor:
    def insertar(self, texto: str, destino: Destino) -> ResultadoInsercion:
        return ResultadoInsercion.exito()


def _contexto(tmp_path: Path) -> ContextoDeAjustes:
    return ContextoDeAjustes(
        base=abrir_base(tmp_path / "v.db"),
        claves=Claves(),
        crear_reescritor=lambda p, c: ReescritorFalso(),
        aplicar_atajos=lambda atajos: None,
        portapapeles=Portapapeles(),
        insertor=Insertor(),
        listar_dispositivos=lambda: [Dispositivo(0, "Micrófono", 1, es_predeterminado=True)],
    )


def test_se_arman_todas_las_paginas_de_los_ajustes(qtbot: QtBot, tmp_path: Path) -> None:
    paginas = crear_paginas(_contexto(tmp_path), lambda accion: accion())

    assert list(paginas) == [
        "Teclas", "Audio", "Modos", "Vocabulario", "Reescritura", "Copia", "Historial"
    ]  # fmt: skip
    for pagina in paginas.values():
        qtbot.addWidget(pagina)


def test_la_ventana_completa_se_abre_con_cada_pagina(qtbot: QtBot, tmp_path: Path) -> None:
    ventana = VentanaAjustes(crear_paginas(_contexto(tmp_path), lambda accion: accion()))
    qtbot.addWidget(ventana)

    for nombre in ventana.nombres_de_paginas():
        ventana.mostrar_pagina(nombre)
        assert ventana.pagina_actual() == nombre


def test_las_paginas_se_conectan_entre_si_por_la_misma_base(qtbot: QtBot, tmp_path: Path) -> None:
    contexto = _contexto(tmp_path)
    paginas = crear_paginas(contexto, lambda accion: accion())
    for pagina in paginas.values():
        qtbot.addWidget(pagina)  # que Qt las cierre en orden y no al apagar el intérprete
    vocabulario = paginas["Vocabulario"]
    vocabulario.campo_palabra.setText("SQLAlchemy")  # type: ignore[attr-defined]
    vocabulario.agregar_palabra()  # type: ignore[attr-defined]

    copia = paginas["Copia"]
    destino = tmp_path / "c.json"
    copia._elegir = lambda modo: destino  # type: ignore[attr-defined]  # noqa: SLF001
    copia.exportar()  # type: ignore[attr-defined]

    assert "SQLAlchemy" in destino.read_text(encoding="utf-8")


# ---- barra lateral agrupada (lote 7) -----------------------------------------------------------------------


def _con_grupos(qtbot: QtBot) -> VentanaAjustes:
    paginas: dict[str, QWidget] = {
        "Uno": QLabel("uno"),
        "Dos": QLabel("dos"),
        "Tres": QLabel("tres"),
        "Cuatro": QLabel("cuatro"),
    }
    ventana = VentanaAjustes(
        paginas,
        grupos={"Cuatro": "Primero", "Uno": "Segundo", "Dos": "Segundo", "Tres": "Tercero"},
        orden_de_grupos=["Primero", "Segundo", "Tercero"],
        espera_ms=0,
    )
    qtbot.addWidget(ventana)
    return ventana


def test_la_barra_lateral_ordena_las_paginas_por_grupo(qtbot: QtBot) -> None:
    ventana = _con_grupos(qtbot)

    assert ventana.nombres_de_paginas() == ["Cuatro", "Uno", "Dos", "Tres"]


def test_la_barra_lateral_muestra_la_etiqueta_de_cada_grupo(qtbot: QtBot) -> None:
    ventana = _con_grupos(qtbot)

    assert ventana.etiquetas_de_grupo() == ["Primero", "Segundo", "Tercero"]


def test_hay_un_boton_de_navegacion_por_pagina(qtbot: QtBot) -> None:
    ventana = _con_grupos(qtbot)

    assert [b.text().strip() for b in ventana.botones_de_navegacion()] == [
        "Cuatro", "Uno", "Dos", "Tres",
    ]  # fmt: skip


def test_hacer_clic_en_un_boton_muestra_su_pagina(qtbot: QtBot) -> None:
    ventana = _con_grupos(qtbot)
    ventana.show()

    ventana.botones_de_navegacion()[2].click()

    assert ventana.pagina_actual() == "Dos"
    assert ventana.widget_de_pagina("Dos").isVisible()
    assert not ventana.widget_de_pagina("Uno").isVisible()


def test_solo_un_boton_esta_marcado_a_la_vez(qtbot: QtBot) -> None:
    ventana = _con_grupos(qtbot)

    ventana.mostrar_pagina("Tres")

    marcados = [b.isChecked() for b in ventana.botones_de_navegacion()]
    assert marcados.count(True) == 1 and marcados[3] is True


def test_el_encabezado_muestra_el_nombre_de_la_pagina(qtbot: QtBot) -> None:
    ventana = _con_grupos(qtbot)

    ventana.mostrar_pagina("Dos")

    assert ventana.titulo_de_pagina() == "Dos"


def test_una_pagina_se_puede_describir_en_el_encabezado(qtbot: QtBot) -> None:
    ventana = VentanaAjustes(
        {"Uno": QLabel("uno")}, descripciones={"Uno": "Una descripción"}, espera_ms=0
    )
    qtbot.addWidget(ventana)

    assert ventana.descripcion_de_pagina() == "Una descripción"


def test_arranca_en_la_primera_pagina_de_la_barra(qtbot: QtBot) -> None:
    ventana = _con_grupos(qtbot)

    assert ventana.pagina_actual() == "Cuatro"


def test_el_estado_lleva_un_punto_del_color_del_estado(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot)

    ventana.establecer_vista(vista_de(E.ESCUCHANDO))

    assert vista_de(E.ESCUCHANDO).color in ventana.color_de_estado()


def test_las_paginas_largas_se_pueden_desplazar(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QScrollArea

    ventana = _con_grupos(qtbot)

    pagina = ventana.widget_de_pagina("Uno")

    area = pagina.parent()
    while area is not None and not isinstance(area, QScrollArea):
        area = area.parent()
    assert isinstance(area, QScrollArea)


def test_agregar_una_pagina_despues_la_suma_a_la_barra(qtbot: QtBot) -> None:
    ventana = _ventana(qtbot)

    ventana.agregar_pagina("Nueva", QLabel("n"), grupo="Otro")

    assert "Nueva" in ventana.nombres_de_paginas()
    assert "Otro" in ventana.etiquetas_de_grupo()


def test_las_paginas_reales_quedan_agrupadas_como_en_la_guia(qtbot: QtBot, tmp_path: Path) -> None:
    ventana = VentanaAjustes(crear_paginas(_contexto(tmp_path), lambda accion: accion()))
    qtbot.addWidget(ventana)

    assert ventana.nombres_de_paginas() == [
        "Historial", "Modos", "Vocabulario", "Teclas", "Audio", "Reescritura", "Copia",
    ]  # fmt: skip
    assert ventana.etiquetas_de_grupo() == [
        "INICIO", "TEXTO", "DICTADO", "INTELIGENCIA ARTIFICIAL", "DATOS",
    ]  # fmt: skip
    assert all(not b.icon().isNull() for b in ventana.botones_de_navegacion())
