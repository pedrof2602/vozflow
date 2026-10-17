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
