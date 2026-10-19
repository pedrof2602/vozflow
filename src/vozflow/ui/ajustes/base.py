"""Lo común de las páginas de ajustes: un aviso de éxito o de error."""

from PySide6.QtWidgets import QLabel, QWidget


class PaginaBase(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.mensaje = ""
        self.hay_error = False
        self._etiqueta_mensaje = QLabel()
        self._etiqueta_mensaje.setWordWrap(True)

    def avisar(self, texto: str, *, error: bool = False) -> None:
        self.mensaje, self.hay_error = texto, error
        self._etiqueta_mensaje.setText(texto)
        self._etiqueta_mensaje.setProperty("error", error)
        self._etiqueta_mensaje.setProperty("exito", not error)
        self._etiqueta_mensaje.style().unpolish(self._etiqueta_mensaje)
        self._etiqueta_mensaje.style().polish(self._etiqueta_mensaje)
