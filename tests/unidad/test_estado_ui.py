"""Cómo se muestra cada estado del dictado (RF-028), sin importar Qt."""

import sys

import pytest

from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.ui.estado import VistaDeEstado, vista_de


def test_cada_estado_tiene_su_texto_icono_y_color() -> None:
    for estado in E:
        vista = vista_de(estado)

        assert isinstance(vista, VistaDeEstado)
        assert vista.texto.strip() and vista.icono and vista.color.startswith("#")
        assert len(vista.color) == 7


@pytest.mark.parametrize(
    ("estado", "icono", "texto"),
    [
        (E.INACTIVO, "inactivo", "Listo"),
        (E.ESCUCHANDO, "escuchando", "Escuchando"),
        (E.TRANSCRIBIENDO, "transcribiendo", "Transcribiendo"),
        (E.ERROR, "error", "Error"),
    ],
)
def test_los_cuatro_estados_de_la_spec(estado: E, icono: str, texto: str) -> None:
    vista = vista_de(estado)

    assert vista.icono == icono and texto in vista.texto


def test_insertar_se_muestra_como_trabajando_con_su_propio_texto() -> None:
    insertando, transcribiendo = vista_de(E.INSERTANDO), vista_de(E.TRANSCRIBIENDO)

    assert insertando.icono == transcribiendo.icono and insertando.color == transcribiendo.color
    assert "Insertando" in insertando.texto


def test_los_estados_se_distinguen_por_icono_y_no_solo_por_color() -> None:
    iconos = {vista_de(e).icono for e in (E.INACTIVO, E.ESCUCHANDO, E.TRANSCRIBIENDO, E.ERROR)}
    colores = {vista_de(e).color for e in (E.INACTIVO, E.ESCUCHANDO, E.TRANSCRIBIENDO, E.ERROR)}

    assert len(iconos) == 4 and len(colores) == 4


def test_importar_ui_estado_en_un_proceso_nuevo_no_carga_qt() -> None:
    import subprocess

    codigo = (
        "import sys; import vozflow.ui.estado; "
        "sys.exit(1 if any(m.startswith('PySide6') for m in sys.modules) else 0)"
    )
    assert subprocess.run([sys.executable, "-I", "-c", codigo], check=False).returncode == 0
