"""El tema visual de vozflow: el aspecto de OpenWhispr (``docs/diseno/referencia-openwhispr.md``).

Dos paletas, oscura y clara, con los mismos roles; la hoja de estilos de Qt se arma a partir de
una paleta. Sin Qt: se prueba el contraste y el contenido sin abrir ventanas.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from string import Template


@dataclass(frozen=True)
class Paleta:
    nombre: str
    fondo: str
    ventana: str
    superficie: str
    tarjeta: str
    superficie_3: str
    elevada: str
    campo: str
    borde: str
    borde_suave: str
    borde_hover: str
    foco: str
    texto: str
    texto_atenuado: str
    primario: str
    primario_hover: str
    texto_sobre_primario: str
    acento: str
    acento_texto: str
    enlace: str
    error: str
    exito: str
    aviso: str
    seleccion: str


OSCURA = Paleta(
    nombre="oscura",
    fondo="#191b1d",
    ventana="#121416",
    superficie="#202225",
    tarjeta="#24272a",
    superficie_3="#2b2e32",
    elevada="#32363b",
    campo="#121416",
    borde="#383b3e",
    borde_suave="#343539",
    borde_hover="#4a4d53",
    foco="#d0647c",
    texto="#e8e8e8",
    texto_atenuado="#9a9a9a",
    primario="#b64f67",
    primario_hover="#a74660",
    texto_sobre_primario="#ffffff",
    acento="#d0647c",
    acento_texto="#e8899d",
    enlace="#e8899d",
    error="#ff6b70",
    exito="#45ba50",
    aviso="#e99b2a",
    seleccion="#3a2229",
)

CLARA = Paleta(
    nombre="clara",
    fondo="#f4f4f5",
    ventana="#ebebed",
    superficie="#fafafa",
    tarjeta="#ffffff",
    superficie_3="#f0f0f1",
    elevada="#ffffff",
    campo="#ffffff",
    borde="#e3e3e3",
    borde_suave="#ececec",
    borde_hover="#cfcfd3",
    foco="#a63d55",
    texto="#111111",
    texto_atenuado="#656565",
    primario="#a63d55",
    primario_hover="#933449",
    texto_sobre_primario="#ffffff",
    acento="#a63d55",
    acento_texto="#9c2f48",
    enlace="#9c2f48",
    error="#c62828",
    exito="#1e7a34",
    aviso="#9a5b00",
    seleccion="#f8e5e9",
)


_actual = OSCURA


def paleta_actual() -> Paleta:
    """La paleta en uso: los componentes que se dibujan solos la consultan al pintarse."""
    return _actual


def establecer_paleta(paleta: Paleta) -> None:
    global _actual
    _actual = paleta


def paleta_del_sistema(esquema: str | None) -> Paleta:
    """``esquema`` es el del sistema (``dark`` o ``light``); sin dato claro, el oscuro de la guía."""
    return CLARA if (esquema or "").strip().lower() == "light" else OSCURA


# ---- contraste (WCAG 2.x) --------------------------------------------------------------------


def _luminancia(color: str) -> float:
    canales = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lineales = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in canales]
    return 0.2126 * lineales[0] + 0.7152 * lineales[1] + 0.0722 * lineales[2]


def contraste(a: str, b: str) -> float:
    """Relación de contraste entre dos colores ``#rrggbb`` (de 1 a 21)."""
    claro, oscuro = sorted((_luminancia(a), _luminancia(b)), reverse=True)
    return (claro + 0.05) / (oscuro + 0.05)


# ---- recursos y hoja de estilos ----------------------------------------------------------------

_FLECHA = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
    '<path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="{c}" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)
_TILDE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 12 12">'
    '<path d="M2.5 6.2 5 8.6l4.5-5" fill="none" stroke="{c}" stroke-width="1.8" '
    'stroke-linecap="round" stroke-linejoin="round"/></svg>'
)


def preparar_recursos(paleta: Paleta, directorio: Path) -> dict[str, str]:
    """Escribe los dibujos que la hoja de estilos referencia por ruta (Qt no tiñe imágenes)."""
    directorio.mkdir(parents=True, exist_ok=True)
    archivos = {
        "flecha": (_FLECHA, paleta.texto_atenuado),
        "tilde": (_TILDE, paleta.texto_sobre_primario),
    }
    rutas: dict[str, str] = {}
    for nombre, (plantilla, color) in archivos.items():
        ruta = directorio / f"{nombre}-{paleta.nombre}.svg"
        ruta.write_text(plantilla.format(c=color), encoding="utf-8")
        rutas[nombre] = str(ruta)
    return rutas


_HOJA = Template(
    """
* { font-family: "$fuente"; font-size: 13px; }
QWidget { background: transparent; color: $texto; }
QMainWindow, QDialog, QWidget#ventana { background: $fondo; }
QToolTip { background: $elevada; color: $texto; border: 1px solid $borde; border-radius: 6px; padding: 4px 8px; }

QLabel#titulo { font-size: 20px; font-weight: 600; }
QLabel#seccion { font-size: 15px; font-weight: 600; }
QLabel#descripcion, QLabel#subtitulo { color: $texto_atenuado; }
QLabel#grupo { color: $texto_atenuado; font-size: 11px; font-weight: 600; padding: 10px 10px 4px 10px; }
QLabel#comando { font-family: monospace; background: $campo; border: 1px solid $borde; border-radius: 6px; padding: 6px 8px; }
QLabel[error="true"] { color: $error; }
QLabel[exito="true"] { color: $exito; }
QLabel[enlace="true"] { color: $enlace; }

QFrame#tarjeta { background: $tarjeta; border: 1px solid $borde_suave; border-radius: 10px; }
QFrame#panel { background: $tarjeta; border: 1px solid $borde_suave; border-radius: 12px; }
QFrame#lateral { background: $ventana; border: none; }
QFrame#separador { background: $borde_suave; border: none; max-height: 1px; min-height: 1px; }

QPushButton { background: $superficie_3; color: $texto; border: 1px solid $borde; border-radius: 8px; padding: 6px 14px; }
QPushButton:hover { background: $elevada; border-color: $borde_hover; }
QPushButton:pressed { background: $superficie; }
QPushButton:focus { border: 1px solid $foco; }
QPushButton:disabled { background: $superficie; color: $texto_atenuado; border-color: $borde_suave; }
QPushButton[principal="true"] { background: $primario; color: $texto_sobre_primario; border: 1px solid $primario; border-radius: 15px; padding: 6px 18px; font-weight: 600; }
QPushButton[principal="true"]:hover { background: $primario_hover; border-color: $primario_hover; }
QPushButton[principal="true"]:disabled { background: $superficie_3; color: $texto_atenuado; border-color: $borde_suave; }
QPushButton[peligro="true"] { color: $error; }
QPushButton[enlace="true"] { background: transparent; border: none; color: $acento_texto; padding: 2px 6px; }
QPushButton[enlace="true"]:hover { background: transparent; text-decoration: underline; }
QPushButton[grupo="true"] { background: transparent; border: none; border-radius: 8px; padding: 7px 10px; text-align: left; color: $texto_atenuado; font-size: 11px; font-weight: 600; }
QPushButton[grupo="true"]:hover { background: $superficie_3; }
QPushButton[chip="true"] { border: 1px solid $borde; border-radius: 12px; padding: 4px 12px; background: $superficie; }
QPushButton[chip="true"]:hover { border: 1px solid $borde_hover; border-radius: 12px; background: $superficie_3; }
QPushButton[chip="true"]:checked { background: $seleccion; color: $acento_texto; border: 1px solid $acento; border-radius: 12px; }
QPushButton[chip="true"]:focus { border: 1px solid $borde_hover; border-radius: 12px; }
QPushButton[chip="true"]:checked:focus { border: 1px solid $acento; border-radius: 12px; }
QPushButton[nav="true"] { background: transparent; border: none; border-radius: 8px; padding: 7px 10px; text-align: left; }
QPushButton[nav="true"]:hover { background: $superficie_3; }
QPushButton[nav="true"]:checked { background: $seleccion; color: $acento_texto; }

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox { background: $campo; color: $texto; border: 1px solid $borde; border-radius: 8px; padding: 5px 8px; selection-background-color: $primario; selection-color: $texto_sobre_primario; }
QLineEdit:hover, QPlainTextEdit:hover, QSpinBox:hover, QComboBox:hover { border-color: $borde_hover; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus { border: 1px solid $foco; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: $texto_atenuado; background: $superficie; }
QLineEdit[readOnly="true"] { background: $superficie; }
QComboBox { padding-right: 24px; }
QComboBox::drop-down { border: none; width: 22px; }
$flecha
QComboBox QAbstractItemView { background: $tarjeta; color: $texto; border: 1px solid $borde; border-radius: 8px; selection-background-color: $seleccion; selection-color: $acento_texto; outline: 0; padding: 3px; }
QSpinBox::up-button, QSpinBox::down-button { width: 0; border: none; }

QListWidget, QTableWidget { background: $tarjeta; border: 1px solid $borde_suave; border-radius: 10px; outline: 0; padding: 4px; }
QListWidget::item { padding: 7px 10px; border-radius: 7px; }
QListWidget::item:hover { background: $superficie_3; }
QListWidget::item:selected { background: $seleccion; color: $acento_texto; }
QTableWidget { gridline-color: $borde_suave; }
QTableWidget::item { padding: 6px 8px; }
QTableWidget::item:selected { background: $seleccion; color: $acento_texto; }
QHeaderView::section { background: transparent; color: $texto_atenuado; border: none; border-bottom: 1px solid $borde_suave; padding: 6px 8px; font-weight: 600; }

QGroupBox { background: $tarjeta; border: 1px solid $borde_suave; border-radius: 10px; margin-top: 0; padding: 30px 12px 10px 12px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; left: 14px; top: 8px; color: $texto; background: transparent; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid $borde_hover; border-radius: 4px; background: $campo; }
QCheckBox::indicator:checked { background: $primario; border-color: $primario; }
$tilde
QCheckBox::indicator:disabled { background: $superficie; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: $borde_hover; border-radius: 3px; min-height: 28px; }
QScrollBar::handle:vertical:hover { background: $texto_atenuado; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: $borde_hover; border-radius: 3px; min-width: 28px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { background: none; border: none; width: 0; height: 0; }

QStatusBar { background: $ventana; color: $texto_atenuado; border-top: 1px solid $borde_suave; }
QMenu { background: $tarjeta; color: $texto; border: 1px solid $borde; border-radius: 10px; padding: 5px; }
QMenu::item { padding: 6px 22px 6px 14px; border-radius: 6px; }
QMenu::item:selected { background: $seleccion; color: $acento_texto; }
QMenu::separator { height: 1px; background: $borde_suave; margin: 5px 8px; }
QMessageBox { background: $tarjeta; }
"""
)


def hoja_de_estilos(paleta: Paleta, fuente: str, recursos: Mapping[str, str] | None = None) -> str:
    """La hoja de estilos de Qt para ``paleta``; ``recursos`` trae las de ``preparar_recursos``."""
    recursos = recursos or {}
    flecha = tilde = ""
    if "flecha" in recursos:
        flecha = (
            'QComboBox::down-arrow { image: url("' + recursos["flecha"] + '");'
            " width: 12px; height: 12px; }"
        )
    if "tilde" in recursos:
        tilde = 'QCheckBox::indicator:checked { image: url("' + recursos["tilde"] + '"); }'
    valores = {**vars(paleta), "fuente": fuente, "flecha": flecha, "tilde": tilde}
    return _HOJA.substitute(valores).strip() + "\n"
