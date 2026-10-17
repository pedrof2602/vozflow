"""Página de teclas de los ajustes (RF-003, RF-029): capturar, avisar si choca y aplicar en vivo."""

from collections.abc import Callable, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from vozflow.atajos.compuesta import NingunAdaptadorSirve
from vozflow.atajos.evdev import SinPermisoDeTeclado, SinTeclados
from vozflow.atajos.gsettings import ErrorDeGSettings
from vozflow.atajos.puerto import AccionDeAtajo, AtajoOcupado
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.servicio_dbus import InstanciaYaEnEjecucion

_DESFASE_XCB = 8  # el servidor gráfico suma 8 al código de tecla de Linux
_MODIFICADORES_POR_LADO = {  # código de Linux → nombre con lado
    29: "LeftCtrl",
    97: "RightCtrl",
    42: "LeftShift",
    54: "RightShift",
    56: "LeftAlt",
    100: "RightAlt",
    125: "LeftMeta",
    126: "RightMeta",
}
_TECLAS_DE_MODIFICADOR = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_AltGr,
    Qt.Key.Key_Meta,
    Qt.Key.Key_Super_L,
    Qt.Key.Key_Super_R,
}
_SIN_MODIFICADOR_PERMITIDAS = {Qt.Key.Key_Pause, Qt.Key.Key_ScrollLock, Qt.Key.Key_Insert}


def nombre_de_modificador(codigo_nativo: int) -> str | None:
    """``RightCtrl`` a partir del código de tecla del servidor gráfico; ``None`` si no lo es."""
    return _MODIFICADORES_POR_LADO.get(codigo_nativo - _DESFASE_XCB)


def _es_de_funcion(tecla: Qt.Key) -> bool:
    return Qt.Key.Key_F1 <= tecla <= Qt.Key.Key_F24


class CampoDeAtajo(QLineEdit):
    """Un campo que no se escribe: se aprieta la combinación y la captura."""

    atajo_cambiado = Signal(str)

    def __init__(self, permitir_modificador_solo: bool) -> None:
        super().__init__()
        self._permitir_modificador_solo = permitir_modificador_solo
        self._atajo = ""
        self._modificador_pendiente: str | None = None
        self.setReadOnly(True)
        self.setPlaceholderText("Apretá la combinación…")

    @property
    def atajo(self) -> str:
        return self._atajo

    @atajo.setter
    def atajo(self, valor: str) -> None:
        self._atajo = valor
        self.setText(valor)

    def keyPressEvent(self, evento: QKeyEvent) -> None:  # noqa: N802 (nombre de Qt)
        tecla = Qt.Key(evento.key())
        if tecla == Qt.Key.Key_Escape:
            return
        if tecla in _TECLAS_DE_MODIFICADOR:
            self._modificador_pendiente = nombre_de_modificador(evento.nativeScanCode())
            return
        self._modificador_pendiente = None  # hubo otra tecla: ya no es un modificador solo
        modificadores = [
            nombre
            for bandera, nombre in (
                (Qt.KeyboardModifier.ControlModifier, "Ctrl"),
                (Qt.KeyboardModifier.AltModifier, "Alt"),
                (Qt.KeyboardModifier.ShiftModifier, "Shift"),
                (Qt.KeyboardModifier.MetaModifier, "Super"),
            )
            if evento.modifiers() & bandera
        ]
        if not modificadores and not (
            _es_de_funcion(tecla) or tecla in _SIN_MODIFICADOR_PERMITIDAS
        ):
            return  # una letra suelta se escribiría en todos lados: hace falta un modificador
        self._capturar("+".join([*modificadores, QKeySequence(tecla).toString()]))

    def keyReleaseEvent(self, evento: QKeyEvent) -> None:  # noqa: N802 (nombre de Qt)
        if (
            Qt.Key(evento.key()) in _TECLAS_DE_MODIFICADOR
            and self._modificador_pendiente is not None
            and self._permitir_modificador_solo
        ):
            self._capturar(self._modificador_pendiente)
        self._modificador_pendiente = None

    def _capturar(self, valor: str) -> None:
        self.atajo = valor
        self.atajo_cambiado.emit(valor)


_ERRORES_DE_LA_ESCUCHA = (
    AtajoOcupado,
    NingunAdaptadorSirve,
    InstanciaYaEnEjecucion,
    ErrorDeGSettings,
    SinPermisoDeTeclado,
    SinTeclados,
    RuntimeError,
    ValueError,
)


class PaginaTeclas(QWidget):
    def __init__(
        self,
        ajustes: AjustesRepo,
        aplicar_en_vivo: Callable[[Mapping[AccionDeAtajo, str]], None],
    ) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._aplicar_en_vivo = aplicar_en_vivo
        self.mensaje = ""
        self.hay_error = False
        self.campo_mantener = CampoDeAtajo(permitir_modificador_solo=True)
        self.campo_alternar = CampoDeAtajo(permitir_modificador_solo=False)
        self._etiqueta = QLabel()
        self._etiqueta.setWordWrap(True)
        aplicar = QPushButton("Aplicar")
        aplicar.clicked.connect(lambda _=False: self.aplicar())
        restablecer = QPushButton("Restablecer")
        restablecer.clicked.connect(lambda _=False: self.restablecer())
        formulario = QFormLayout(self)
        formulario.addRow("Mantener para hablar", self.campo_mantener)
        formulario.addRow("Pulsar para empezar y terminar", self.campo_alternar)
        botones = QHBoxLayout()
        botones.addWidget(aplicar)
        botones.addWidget(restablecer)
        formulario.addRow(botones)
        formulario.addRow(self._etiqueta)
        self._mostrar_actuales()

    def aplicar(self) -> None:
        """Valida, prueba las teclas nuevas en la escucha en vivo y recién entonces las guarda."""
        try:
            mantener, alternar = self._ajustes.validar_atajos(
                self.campo_mantener.atajo, self.campo_alternar.atajo
            )
            actuales = (
                self._ajustes.obtener("atajo.mantener"),
                self._ajustes.obtener("atajo.alternar"),
            )
            if (mantener, alternar) == actuales:
                self._avisar("No hay cambios que aplicar.", error=False)
                return
            self._aplicar_en_vivo(
                {AccionDeAtajo.MANTENER: mantener, AccionDeAtajo.ALTERNAR: alternar}
            )
            self._ajustes.establecer_atajos(mantener, alternar)
        except (DatoInvalido, *_ERRORES_DE_LA_ESCUCHA) as error:
            self._avisar(str(error), error=True)
            return
        self._mostrar_actuales()
        self._avisar("Los atajos se aplicaron: ya funcionan, sin reiniciar.", error=False)

    def restablecer(self) -> None:
        self.campo_mantener.atajo = self._ajustes.defecto("atajo.mantener")
        self.campo_alternar.atajo = self._ajustes.defecto("atajo.alternar")
        self.aplicar()

    def _mostrar_actuales(self) -> None:
        self.campo_mantener.atajo = self._ajustes.obtener("atajo.mantener")
        self.campo_alternar.atajo = self._ajustes.obtener("atajo.alternar")

    def _avisar(self, texto: str, *, error: bool) -> None:
        self.mensaje, self.hay_error = texto, error
        self._etiqueta.setText(texto)
        self._etiqueta.setStyleSheet("color: #b42318;" if error else "")
