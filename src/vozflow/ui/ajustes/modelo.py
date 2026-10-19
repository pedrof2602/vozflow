"""Página «Modelo y rendimiento» (Avanzado, 002, RP-016): modelo de voz y potencia de cálculo.

Lo técnico que quedó de la antigua página de audio; el micrófono, el idioma y el cartel viven en
«Dictado». Aquí sí hay «Guardar»: el modelo es un texto que hay que validar.
"""

from PySide6.QtWidgets import QLineEdit, QPushButton, QSpinBox, QVBoxLayout

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.ui.ajustes.base import PaginaBase
from vozflow.ui.componentes import FilaDeAjuste
from vozflow.ui.textos import ayuda_de, texto_de


class PaginaModelo(PaginaBase):
    CLAVES = ("motor.modelo", "motor.hilos")

    def __init__(self, ajustes: AjustesRepo) -> None:
        super().__init__()
        self._ajustes = ajustes
        self.campo_modelo = QLineEdit()
        self.spin_hilos = QSpinBox()
        self.spin_hilos.setRange(1, 8)
        guardar = QPushButton("Guardar")
        guardar.setProperty("principal", True)
        guardar.clicked.connect(lambda _=False: self.guardar())
        self.filas = {
            "motor.modelo": self._fila("motor.modelo", self.campo_modelo),
            "motor.hilos": self._fila("motor.hilos", self.spin_hilos),
        }
        columna = QVBoxLayout(self)
        for fila in self.filas.values():
            columna.addWidget(fila)
        columna.addWidget(guardar)
        columna.addWidget(self._etiqueta_mensaje)
        columna.addStretch()
        self.recargar()

    def _fila(self, clave: str, control: QLineEdit | QSpinBox) -> FilaDeAjuste:
        return FilaDeAjuste(
            texto_de(clave).titulo,
            ayuda_de(clave),
            control,
            restablecer=lambda: self._restablecer(clave),
            es_el_original=lambda: self._ajustes.obtener(clave) == self._ajustes.defecto(clave),
        )

    def recargar(self) -> None:
        self.campo_modelo.setText(str(self._ajustes.obtener("motor.modelo")))
        self.spin_hilos.setValue(int(self._ajustes.obtener("motor.hilos")))
        for fila in getattr(self, "filas", {}).values():
            fila.refrescar()

    def guardar(self) -> None:
        try:
            self._ajustes.establecer("motor.modelo", self.campo_modelo.text())
        except DatoInvalido:
            self.avisar("El modelo de voz no puede quedar vacío.", error=True)
            return
        self._ajustes.establecer("motor.hilos", self.spin_hilos.value())
        for fila in self.filas.values():
            fila.refrescar()
        self.avisar("Guardado. Rige al reiniciar vozflow.")

    def _restablecer(self, clave: str) -> None:
        self._ajustes.restablecer(clave)
        self.recargar()
        self.avisar("Restablecido. Rige al reiniciar vozflow.")
