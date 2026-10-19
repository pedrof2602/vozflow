"""Página de audio y motor de los ajustes (RF-005): micrófono, idioma, modelo, hilos, indicador."""

from collections.abc import Callable

from PySide6.QtWidgets import QComboBox, QFormLayout, QLineEdit, QPushButton, QSpinBox

from vozflow.audio.captura import Dispositivo, listar_dispositivos
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.ui.ajustes.base import PaginaBase
from vozflow.ui.componentes import Interruptor

_IDIOMAS = (("Automático", "automatico"), ("Español", "es"), ("Inglés", "en"))


class PaginaAudio(PaginaBase):
    def __init__(
        self,
        ajustes: AjustesRepo,
        listar_dispositivos: Callable[[], list[Dispositivo]] = listar_dispositivos,
    ) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._listar = listar_dispositivos
        self.combo_microfono = QComboBox()
        self.combo_idioma = QComboBox()
        for texto, valor in _IDIOMAS:
            self.combo_idioma.addItem(texto, valor)
        self.campo_modelo = QLineEdit()
        self.spin_hilos = QSpinBox()
        self.spin_hilos.setRange(1, 8)
        self.check_indicador = Interruptor("Mostrar el indicador al grabar")
        guardar = QPushButton("Guardar")
        guardar.setProperty("principal", True)
        guardar.clicked.connect(lambda _=False: self.guardar())
        formulario = QFormLayout(self)
        formulario.addRow("Micrófono", self.combo_microfono)
        formulario.addRow("Idioma", self.combo_idioma)
        formulario.addRow("Modelo de transcripción", self.campo_modelo)
        formulario.addRow("Hilos de cómputo", self.spin_hilos)
        formulario.addRow(self.check_indicador)
        formulario.addRow(guardar)
        formulario.addRow(self._etiqueta_mensaje)
        self.recargar()

    def recargar(self) -> None:
        guardado = str(self._ajustes.obtener("audio.dispositivo"))
        self.combo_microfono.clear()
        self.combo_microfono.addItem("Predeterminado del sistema", "")
        try:
            dispositivos = self._listar()
        except Exception:  # sin PortAudio o sin permisos: la página igual tiene que abrir
            dispositivos = []
        nombres = [d.nombre for d in dispositivos]
        for dispositivo in dispositivos:
            marca = " (predeterminado)" if dispositivo.es_predeterminado else ""
            self.combo_microfono.addItem(f"{dispositivo.nombre}{marca}", dispositivo.nombre)
        if guardado and guardado not in nombres:  # un micrófono que hoy no está enchufado
            self.combo_microfono.addItem(f"{guardado} (no conectado)", guardado)
        self.combo_microfono.setCurrentIndex(max(0, self.combo_microfono.findData(guardado)))
        self.combo_idioma.setCurrentIndex(
            self.combo_idioma.findData(self._ajustes.obtener("idioma.modo"))
        )
        self.campo_modelo.setText(str(self._ajustes.obtener("motor.modelo")))
        self.spin_hilos.setValue(int(self._ajustes.obtener("motor.hilos")))
        self.check_indicador.setChecked(bool(self._ajustes.obtener("interfaz.indicador")))

    def guardar(self) -> None:
        try:
            self._ajustes.establecer("motor.modelo", self.campo_modelo.text())
        except DatoInvalido:
            self.avisar("El modelo de transcripción no puede quedar vacío.", error=True)
            return
        self._ajustes.establecer("audio.dispositivo", self.combo_microfono.currentData() or "")
        self._ajustes.establecer("idioma.modo", self.combo_idioma.currentData())
        self._ajustes.establecer("motor.hilos", self.spin_hilos.value())
        self._ajustes.establecer("interfaz.indicador", self.check_indicador.isChecked())
        self.avisar(
            "Guardado. El indicador rige enseguida; el micrófono, el idioma, el modelo y los "
            "hilos rigen al reiniciar vozflow."
        )
