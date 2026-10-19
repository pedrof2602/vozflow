"""Nada se perdió en el rediseño: toda capacidad de ajuste se alcanza desde alguna página (002).

RP-016: lo técnico queda en «Avanzado» «sin haber perdido ninguna capacidad».
"""

import os
from pathlib import Path

from pytestqt.qtbot import QtBot

from tests.unidad.test_ventana_ajustes import _contexto
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.ajustes.ventana import VentanaAjustes, crear_paginas

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BASICAS = ["Dictado", "Vocabulario", "Historial", "General"]
AVANZADAS = [
    "Otras teclas",
    "Modos",
    "Modelo y rendimiento",
    "Asistente de IA",
    "Copia de seguridad",
]


def _paginas(qtbot: QtBot, tmp_path: Path):  # type: ignore[no-untyped-def]
    paginas = crear_paginas(_contexto(tmp_path), lambda accion: accion())
    for pagina in paginas.values():
        qtbot.addWidget(pagina)
    return paginas


def test_toda_clave_de_ajuste_se_edita_desde_alguna_pagina(qtbot: QtBot, tmp_path: Path) -> None:
    paginas = _paginas(qtbot, tmp_path)
    editadas = {c for p in paginas.values() for c in getattr(p, "CLAVES", ())}

    claves = set(AjustesRepo(abrir_base(":memory:")).todos())

    # «asistente.hecho» lo maneja el asistente de primer uso, no una opción de la ventana.
    assert claves - {"asistente.hecho"} <= editadas


def test_ninguna_pagina_declara_una_clave_que_no_existe(qtbot: QtBot, tmp_path: Path) -> None:
    paginas = _paginas(qtbot, tmp_path)
    editadas = {c for p in paginas.values() for c in getattr(p, "CLAVES", ())}

    assert editadas <= set(AjustesRepo(abrir_base(":memory:")).todos())


def test_las_paginas_estan_repartidas_entre_basicas_y_avanzadas(
    qtbot: QtBot, tmp_path: Path
) -> None:
    paginas = _paginas(qtbot, tmp_path)

    assert list(paginas) == BASICAS + AVANZADAS


def test_lo_tecnico_vive_solo_en_avanzado(qtbot: QtBot, tmp_path: Path) -> None:
    paginas = _paginas(qtbot, tmp_path)
    claves_basicas = {c for n in BASICAS for c in getattr(paginas[n], "CLAVES", ())}

    tecnicas = {"motor.modelo", "motor.hilos", "atajo.alternar", "atajo.traducir",
                "traduccion.idioma", "reescritura.activa"}  # fmt: skip
    assert claves_basicas.isdisjoint(tecnicas)


def test_las_capacidades_que_no_son_ajustes_siguen_en_avanzado(
    qtbot: QtBot, tmp_path: Path
) -> None:
    ventana = VentanaAjustes(crear_paginas(_contexto(tmp_path), lambda accion: accion()))
    qtbot.addWidget(ventana)

    for nombre in ("Modos", "Copia de seguridad", "Asistente de IA"):
        assert nombre in ventana.nombres_de_paginas()


def test_el_asistente_de_ia_edita_el_interruptor_y_el_idioma_de_traduccion(
    qtbot: QtBot, tmp_path: Path
) -> None:
    paginas = _paginas(qtbot, tmp_path)

    assert set(paginas["Asistente de IA"].CLAVES) == {"reescritura.activa", "traduccion.idioma"}
