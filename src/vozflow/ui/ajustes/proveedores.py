"""Página de la reescritura con un modelo de lenguaje (RF-023 a RF-025). Viene apagada."""

import threading
from collections.abc import Callable

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
)

from vozflow.dominio.reescritura import TIEMPO_MAXIMO_S, TIEMPO_MINIMO_S
from vozflow.gestion_de_proveedores import ErrorDeProveedor, GestionDeProveedores
from vozflow.ui.ajustes.base import PaginaBase

EnSegundoPlano = Callable[[Callable[[], str], Callable[[str, bool], None]], None]
_NOMBRES = {"ollama": "Ollama (local)", "anthropic": "Anthropic", "openrouter": "OpenRouter"}
_IDIOMAS_SUGERIDOS = (
    "inglés", "español", "portugués", "francés", "alemán", "italiano", "japonés", "chino",
)  # fmt: skip


class _Puente(QObject):
    """Lleva el resultado de un hilo al hilo de la ventana."""

    terminado = Signal(str, bool)


def en_un_hilo(trabajo: Callable[[], str], al_terminar: Callable[[str, bool], None]) -> None:
    """Corre ``trabajo`` fuera de la ventana: probar la conexión puede tardar hasta un minuto."""
    puente = _Puente()
    puente.terminado.connect(al_terminar)

    def correr() -> None:
        try:
            puente.terminado.emit(trabajo(), False)
        except ErrorDeProveedor as error:
            puente.terminado.emit(str(error), True)

    hilo = threading.Thread(target=correr, daemon=True)
    hilo._puente = puente  # type: ignore[attr-defined]  # que no se libere antes de terminar
    hilo.start()


class PaginaProveedores(PaginaBase):
    def __init__(
        self, gestion: GestionDeProveedores, en_segundo_plano: EnSegundoPlano = en_un_hilo
    ) -> None:
        super().__init__()
        self._gestion = gestion
        self._en_segundo_plano = en_segundo_plano
        self.estado_general = QLabel()
        self.combo_proveedor = QComboBox()
        for id_, nombre in _NOMBRES.items():
            self.combo_proveedor.addItem(nombre, id_)
        self.campo_modelo = QLineEdit()
        self.spin_tiempo = QSpinBox()
        self.spin_tiempo.setRange(TIEMPO_MINIMO_S, TIEMPO_MAXIMO_S)
        self.spin_tiempo.setSuffix(" s")
        self.campo_direccion = QLineEdit()
        self.campo_clave = QLineEdit()
        self.campo_clave.setEchoMode(QLineEdit.EchoMode.Password)
        self.combo_idioma = QComboBox()
        self.combo_idioma.setEditable(True)
        self.combo_idioma.addItems(_IDIOMAS_SUGERIDOS)
        self.aclaracion_de_traduccion = QLabel(
            "La tecla de traducir usa este mismo servicio: con la reescritura apagada no envía "
            "nada y, si falla, no inserta texto sin traducir."
        )
        self.aclaracion_de_traduccion.setWordWrap(True)
        formulario = QFormLayout(self)
        formulario.addRow(self.estado_general)
        formulario.addRow("Proveedor", self.combo_proveedor)
        formulario.addRow("Modelo", self.campo_modelo)
        formulario.addRow("Tiempo máximo", self.spin_tiempo)
        formulario.addRow("Dirección (solo Ollama)", self.campo_direccion)
        formulario.addRow("Clave de acceso", self.campo_clave)
        formulario.addRow("Traducir al idioma", self.combo_idioma)
        formulario.addRow(self.aclaracion_de_traduccion)
        botones = QHBoxLayout()
        for texto, accion in (
            ("Guardar", self.guardar),
            ("Borrar la clave", self.borrar_clave),
            ("Probar", self.probar),
            ("Activar", self.activar),
            ("Apagar la reescritura", self.desactivar),
        ):
            boton = QPushButton(texto)
            boton.setProperty("principal", texto == "Guardar")
            boton.clicked.connect(lambda _=False, a=accion: a())
            botones.addWidget(boton)
        formulario.addRow(botones)
        formulario.addRow(self._etiqueta_mensaje)
        self.combo_proveedor.currentIndexChanged.connect(lambda _: self._mostrar())
        self._mostrar()

    @property
    def _id(self) -> str:
        return str(self.combo_proveedor.currentData())

    def guardar(self) -> None:
        try:
            self._gestion.configurar(
                self._id,
                modelo=self.campo_modelo.text(),
                tiempo_maximo_s=self.spin_tiempo.value(),
                direccion=self.campo_direccion.text() if self._id == "ollama" else None,
            )
            self._gestion.establecer_idioma_de_traduccion(self.combo_idioma.currentText())
            if self.campo_clave.text().strip() and self._id != "ollama":
                self._gestion.guardar_clave(self._id, self.campo_clave.text())
        except ErrorDeProveedor as error:
            self.avisar(str(error), error=True)
            return
        self.campo_clave.clear()  # la clave no queda a la vista
        self._mostrar()
        self.avisar("Guardado.")

    def borrar_clave(self) -> None:
        self._intentar(lambda: self._gestion.borrar_clave(self._id), "Clave borrada.")

    def activar(self) -> None:
        self._intentar(
            lambda: self._gestion.activar(self._id),
            f"Reescritura encendida con {_NOMBRES[self._id]}.",
        )

    def desactivar(self) -> None:
        self._intentar(self._gestion.desactivar, "Reescritura apagada.")

    def probar(self) -> None:
        self.avisar("Probando la conexión…")
        id_ = self._id
        self._en_segundo_plano(lambda: self._gestion.probar(id_), self._al_probar)

    # ---- internos ------------------------------------------------------------------------------

    def _al_probar(self, texto: str, error: bool) -> None:
        self.avisar(texto if error else f"Funciona. Respuesta de prueba: {texto}", error=error)

    def _intentar(self, accion: Callable[[], object], exito: str) -> None:
        try:
            accion()
        except ErrorDeProveedor as error:
            self.avisar(str(error), error=True)
            return
        self._mostrar()
        self.avisar(exito)

    def _mostrar(self) -> None:
        estado = next(e for e in self._gestion.estado() if e.proveedor.id == self._id)
        proveedor = estado.proveedor
        self.campo_modelo.setText(proveedor.modelo)
        self.spin_tiempo.setValue(proveedor.tiempo_maximo_s)
        self.campo_direccion.setText(proveedor.direccion)
        self.campo_direccion.setEnabled(proveedor.id == "ollama")
        self.campo_clave.setEnabled(estado.tiene_clave is not None)
        self.campo_clave.setPlaceholderText(
            "—" if estado.tiene_clave is None
            else "Hay una clave guardada (escribí otra para reemplazarla)" if estado.tiene_clave
            else "Pegá la clave de acceso"
        )  # fmt: skip
        self.combo_idioma.setCurrentText(self._gestion.idioma_de_traduccion())
        activo = self._gestion.proveedor_activo()
        if self._gestion.reescritura_encendida() and activo is not None:
            self.estado_general.setText(f"Reescritura encendida con {_NOMBRES[activo.id]}.")
        else:
            self.estado_general.setText(
                "La reescritura está apagada: nada sale de esta computadora."
            )
