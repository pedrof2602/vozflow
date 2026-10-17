"""Página de vocabulario (RF-019, RF-020): diccionario personal y atajos de texto."""

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.ui.ajustes.base import PaginaBase

_MAXIMO_DE_PALABRA, _MAXIMO_DE_DISPARADOR = 80, 100


class PaginaVocabulario(PaginaBase):
    def __init__(self, diccionario: DiccionarioRepo, atajos: AtajosTextoRepo) -> None:
        super().__init__()
        self._diccionario = diccionario
        self._atajos = atajos
        self._ids_de_palabras: list[int] = []
        self._ids_de_atajos: list[int] = []
        self.lista_palabras = QListWidget()
        self.campo_palabra = QLineEdit()
        self.campo_palabra.setMaxLength(_MAXIMO_DE_PALABRA)
        self.campo_palabra.setPlaceholderText("Palabra o nombre, tal como se escribe")
        self.campo_nota = QLineEdit()
        self.campo_nota.setPlaceholderText("Nota (opcional)")
        self.lista_atajos = QListWidget()
        self.campo_disparador = QLineEdit()
        self.campo_disparador.setMaxLength(_MAXIMO_DE_DISPARADOR)
        self.campo_disparador.setPlaceholderText("Lo que decís, p. ej. mi firma")
        self.campo_reemplazo = QPlainTextEdit()
        self.campo_reemplazo.setPlaceholderText(
            "El texto que se escribe (puede tener varias líneas)"
        )

        diccionario_caja = QGroupBox("Diccionario personal")
        formulario = QFormLayout(diccionario_caja)
        formulario.addRow(self.lista_palabras)
        formulario.addRow(self.campo_palabra)
        formulario.addRow(self.campo_nota)
        agregar = QPushButton("Agregar palabra")
        agregar.clicked.connect(lambda _=False: self.agregar_palabra())
        borrar = QPushButton("Borrar la seleccionada")
        borrar.clicked.connect(lambda _=False: self.borrar_palabra())
        formulario.addRow(agregar)
        formulario.addRow(borrar)

        atajos_caja = QGroupBox("Atajos de texto")
        formulario_atajos = QFormLayout(atajos_caja)
        formulario_atajos.addRow(self.lista_atajos)
        formulario_atajos.addRow(self.campo_disparador)
        formulario_atajos.addRow(self.campo_reemplazo)
        agregar_atajo = QPushButton("Agregar atajo")
        agregar_atajo.clicked.connect(lambda _=False: self.agregar_atajo())
        borrar_atajo = QPushButton("Borrar el seleccionado")
        borrar_atajo.clicked.connect(lambda _=False: self.borrar_atajo())
        formulario_atajos.addRow(agregar_atajo)
        formulario_atajos.addRow(borrar_atajo)

        columna = QVBoxLayout(self)
        columna.addWidget(diccionario_caja)
        columna.addWidget(atajos_caja)
        columna.addWidget(self._etiqueta_mensaje)
        self._recargar()

    # ---- diccionario --------------------------------------------------------------------

    def agregar_palabra(self) -> None:
        try:
            entrada = self._diccionario.agregar(self.campo_palabra.text(), self.campo_nota.text())
        except DatoInvalido as error:
            self.avisar(str(error), error=True)
            return
        self.campo_palabra.clear()
        self.campo_nota.clear()
        self._recargar()
        self.avisar(f"Se agregó «{entrada.palabra}».")

    def borrar_palabra(self) -> None:
        fila = self.lista_palabras.currentRow()
        if 0 <= fila < len(self._ids_de_palabras):
            self._diccionario.borrar(self._ids_de_palabras[fila])
            self._recargar()

    # ---- atajos de texto ----------------------------------------------------------------

    def agregar_atajo(self) -> None:
        try:
            atajo = self._atajos.agregar(
                self.campo_disparador.text(), self.campo_reemplazo.toPlainText()
            )
        except DatoInvalido as error:
            self.avisar(str(error), error=True)
            return
        self.campo_disparador.clear()
        self.campo_reemplazo.clear()
        self._recargar()
        self.avisar(f"Se agregó el atajo «{atajo.disparador}».")

    def borrar_atajo(self) -> None:
        fila = self.lista_atajos.currentRow()
        if 0 <= fila < len(self._ids_de_atajos):
            self._atajos.borrar(self._ids_de_atajos[fila])
            self._recargar()

    # ---- internos -----------------------------------------------------------------------

    def _recargar(self) -> None:
        palabras = self._diccionario.listar()
        self._ids_de_palabras = [e.id for e in palabras]
        self.lista_palabras.clear()
        for e in palabras:
            self.lista_palabras.addItem(f"{e.palabra} — {e.nota}" if e.nota else e.palabra)
        atajos = self._atajos.listar()
        self._ids_de_atajos = [a.id for a in atajos]
        self.lista_atajos.clear()
        for a in atajos:
            self.lista_atajos.addItem(f"{a.disparador} → {a.reemplazo.replace(chr(10), ' ⏎ ')}")
