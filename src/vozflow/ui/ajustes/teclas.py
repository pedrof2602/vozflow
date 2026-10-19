"""Captura de teclas y la página «Otras teclas» de los ajustes (RF-003, RF-029, 002)."""

from collections.abc import Callable, Mapping

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence
from PySide6.QtWidgets import QLineEdit, QPushButton, QVBoxLayout, QWidget

from vozflow.atajos.compuesta import NingunAdaptadorSirve
from vozflow.atajos.evdev import SinPermisoDeTeclado, SinTeclados
from vozflow.atajos.gsettings import ErrorDeGSettings
from vozflow.atajos.puerto import AccionDeAtajo, AtajoOcupado
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.servicio_dbus import InstanciaYaEnEjecucion
from vozflow.ui.ajustes.base import PaginaBase
from vozflow.ui.componentes import FilaDeAjuste, FilaDeTeclas
from vozflow.ui.textos import ayuda_de, texto_de

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
    atajo_mostrado = Signal(str)

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
        self.atajo_mostrado.emit(valor)

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


ERRORES_DE_LA_ESCUCHA = (
    AtajoOcupado,
    NingunAdaptadorSirve,
    InstanciaYaEnEjecucion,
    ErrorDeGSettings,
    SinPermisoDeTeclado,
    SinTeclados,
    RuntimeError,
    ValueError,
)


class PaginaTeclas(PaginaBase):
    """«Otras teclas» (Avanzado): empezar y terminar, y dictar y traducir.

    La tecla para dictar está en «Dictado»; aquí se validan juntas las tres, así que nunca se pisan.
    """

    CLAVES = ("atajo.alternar", "atajo.traducir")

    def __init__(
        self,
        ajustes: AjustesRepo,
        aplicar_en_vivo: Callable[[Mapping[AccionDeAtajo, str]], None],
    ) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._aplicar_en_vivo = aplicar_en_vivo
        self.campo_alternar = CampoDeAtajo(permitir_modificador_solo=False)
        self.campo_traducir = CampoDeAtajo(permitir_modificador_solo=True)
        self._teclas = {"alternar": FilaDeTeclas(), "traducir": FilaDeTeclas()}
        self.campo_alternar.atajo_mostrado.connect(self._teclas["alternar"].establecer)
        self.campo_traducir.atajo_mostrado.connect(self._teclas["traducir"].establecer)
        aplicar = QPushButton("Aplicar")
        aplicar.setProperty("principal", True)
        aplicar.clicked.connect(lambda _=False: self.aplicar())
        self.filas = {
            "atajo.alternar": self._fila("atajo.alternar", self.campo_alternar, "alternar"),
            "atajo.traducir": self._fila("atajo.traducir", self.campo_traducir, "traducir"),
        }
        columna = QVBoxLayout(self)
        for fila in self.filas.values():
            columna.addWidget(fila)
        columna.addWidget(aplicar)
        columna.addWidget(self._etiqueta_mensaje)
        columna.addStretch()
        self._mostrar_actuales()

    def _fila(self, clave: str, campo: CampoDeAtajo, cual: str) -> FilaDeAjuste:
        control = QWidget()
        caja = QVBoxLayout(control)
        caja.setContentsMargins(0, 0, 0, 0)
        caja.addWidget(self._teclas[cual])
        caja.addWidget(campo)
        return FilaDeAjuste(
            texto_de(clave).titulo,
            ayuda_de(clave),
            control,
            restablecer=lambda: self._restablecer(clave),
            es_el_original=lambda: self._ajustes.obtener(clave) == self._ajustes.defecto(clave),
        )

    def teclas_mostradas(self, cual: str) -> list[str]:
        return self._teclas[cual].textos()

    def aplicar(self) -> None:
        """Valida, prueba las teclas nuevas en la escucha en vivo y recién entonces las guarda."""
        try:
            nuevos = self._ajustes.validar_atajos(
                self._ajustes.obtener("atajo.mantener"),
                self.campo_alternar.atajo,
                self.campo_traducir.atajo,
            )
            if nuevos == self._actuales():
                self.avisar("No hay cambios que aplicar.")
                return
            mantener, alternar, traducir = nuevos
            self._aplicar_en_vivo(
                {
                    AccionDeAtajo.MANTENER: mantener,
                    AccionDeAtajo.ALTERNAR: alternar,
                    AccionDeAtajo.TRADUCIR: traducir,
                }
            )
            self._ajustes.establecer_atajos(mantener, alternar, traducir)
        except (DatoInvalido, *ERRORES_DE_LA_ESCUCHA) as error:
            self.avisar(str(error), error=True)
            return
        self._mostrar_actuales()
        self.avisar("Listo: las teclas ya funcionan, sin reiniciar.")

    def _restablecer(self, clave: str) -> None:
        campo = self.campo_alternar if clave == "atajo.alternar" else self.campo_traducir
        campo.atajo = str(self._ajustes.defecto(clave))
        self.aplicar()

    def _actuales(self) -> tuple[str, str, str]:
        return (
            self._ajustes.obtener("atajo.mantener"),
            self._ajustes.obtener("atajo.alternar"),
            self._ajustes.obtener("atajo.traducir"),
        )

    def _mostrar_actuales(self) -> None:
        _, alternar, traducir = self._actuales()
        self.campo_alternar.atajo = alternar
        self.campo_traducir.atajo = traducir
        for fila in getattr(self, "filas", {}).values():
            fila.refrescar()
