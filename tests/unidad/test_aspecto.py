"""El aspecto aplicado a toda la aplicación: tema y fuente, siguiendo al sistema."""

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication, QLabel
from pytestqt.qtbot import QtBot

from vozflow.ui.aspecto import Aspecto, esquema_del_sistema
from vozflow.ui.tema import CLARA, OSCURA, paleta_actual

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def _app() -> QApplication:
    app = QApplication.instance() or QApplication([])
    assert isinstance(app, QApplication)
    return app


def test_aplicar_oscuro_fija_la_paleta_y_la_hoja(tmp_path: Path) -> None:
    app = _app()
    aspecto = Aspecto(app, tmp_path)

    aspecto.aplicar("dark")

    assert aspecto.paleta is OSCURA and paleta_actual() is OSCURA
    assert OSCURA.fondo in app.styleSheet()


def test_aplicar_claro_cambia_todo(tmp_path: Path) -> None:
    app = _app()
    aspecto = Aspecto(app, tmp_path)
    aspecto.aplicar("dark")

    aspecto.aplicar("light")

    assert aspecto.paleta is CLARA and paleta_actual() is CLARA
    assert CLARA.fondo in app.styleSheet() and OSCURA.fondo not in app.styleSheet()


def test_la_hoja_usa_la_fuente_elegida(tmp_path: Path) -> None:
    app = _app()
    aspecto = Aspecto(app, tmp_path)

    aspecto.aplicar("dark")

    assert f'font-family: "{aspecto.fuente}"' in app.styleSheet()


def test_el_logo_queda_como_icono_de_la_aplicacion(tmp_path: Path) -> None:
    app = _app()

    Aspecto(app, tmp_path).aplicar("dark")

    assert not app.windowIcon().isNull()


def test_avisa_a_quienes_dependen_del_tema_cuando_cambia(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path)
    avisos: list[str] = []
    aspecto.al_cambiar(lambda paleta: avisos.append(paleta.nombre))

    aspecto.aplicar("dark")
    aspecto.aplicar("light")

    assert avisos == ["oscura", "clara"]


def test_los_recursos_del_tema_se_escriben_en_el_directorio(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path / "recursos")

    aspecto.aplicar("light")

    assert sorted(p.name for p in (tmp_path / "recursos").iterdir()) == [
        "flecha-clara.svg",
        "tilde-clara.svg",
    ]


def test_sin_dato_del_sistema_se_usa_el_oscuro(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path)

    aspecto.aplicar(None)

    assert aspecto.paleta is OSCURA


def test_el_esquema_del_sistema_es_un_texto_conocido() -> None:
    assert esquema_del_sistema(_app()) in ("dark", "light", None)


def test_seguir_al_sistema_reaplica_cuando_el_sistema_cambia(tmp_path: Path, qtbot: QtBot) -> None:
    app = _app()
    aspecto = Aspecto(app, tmp_path)
    aspecto.aplicar("dark")

    aspecto.seguir_al_sistema(lambda: "light")
    app.styleHints().colorSchemeChanged.emit(app.styleHints().colorScheme())

    assert aspecto.paleta is CLARA


def test_un_widget_nuevo_toma_el_tema(tmp_path: Path, qtbot: QtBot) -> None:
    app = _app()
    Aspecto(app, tmp_path).aplicar("dark")
    etiqueta = QLabel("hola")
    qtbot.addWidget(etiqueta)
    etiqueta.show()

    assert etiqueta.font().family() != "" and etiqueta.palette() is not None


# ---- modo claro, oscuro o automático ----------------------------------------------------------------------------


def test_en_automatico_manda_el_sistema(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path)
    aspecto.establecer_modo("auto")

    aspecto.aplicar("light")
    assert aspecto.paleta is CLARA
    aspecto.aplicar("dark")
    assert aspecto.paleta is OSCURA


def test_el_modo_claro_ignora_al_sistema(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path)
    aspecto.establecer_modo("claro")

    aspecto.aplicar("dark")

    assert aspecto.paleta is CLARA


def test_el_modo_oscuro_ignora_al_sistema(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path)
    aspecto.establecer_modo("oscuro")

    aspecto.aplicar("light")

    assert aspecto.paleta is OSCURA


def test_cambiar_de_modo_se_aplica_en_el_momento(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path)
    aspecto.seguir_al_sistema(lambda: "dark")
    aspecto.establecer_modo("auto")
    assert aspecto.paleta is OSCURA

    aspecto.establecer_modo("claro")

    assert aspecto.paleta is CLARA


def test_volver_a_automatico_retoma_el_color_del_sistema(tmp_path: Path) -> None:
    aspecto = Aspecto(_app(), tmp_path)
    aspecto.seguir_al_sistema(lambda: "dark")
    aspecto.establecer_modo("claro")

    aspecto.establecer_modo("auto")

    assert aspecto.paleta is OSCURA


def test_un_cambio_del_sistema_no_pisa_un_modo_fijo(tmp_path: Path) -> None:
    app = _app()
    aspecto = Aspecto(app, tmp_path)
    aspecto.establecer_modo("oscuro")
    aspecto.seguir_al_sistema(lambda: "light")

    app.styleHints().colorSchemeChanged.emit(app.styleHints().colorScheme())

    assert aspecto.paleta is OSCURA


def test_un_modo_desconocido_es_un_error(tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="modo"):
        Aspecto(_app(), tmp_path).establecer_modo("sepia")
