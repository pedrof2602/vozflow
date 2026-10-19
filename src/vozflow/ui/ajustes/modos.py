"""Página de modos de los ajustes (RF-021): crear, editar y asignar aplicaciones."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.modos_repo import ModosRepo
from vozflow.ui.ajustes.base import PaginaBase
from vozflow.ui.componentes import Interruptor

_PEGADOS = (("Automático", "automatico"), ("Como terminal", "terminal"), ("Normal", "normal"))
_SALTOS = (("Conservar los saltos de línea", "conservar"), ("Una sola línea", "espacio"))


class PaginaModos(PaginaBase):
    def __init__(self, modos: ModosRepo, asignaciones: AsignacionesRepo) -> None:
        super().__init__()
        self._modos = modos
        self._asignaciones = asignaciones
        self._editando: int | None = None
        self.lista = QListWidget()
        self.lista.currentTextChanged.connect(self._al_elegir)
        self.campo_nombre = QLineEdit()
        self.check_muletillas = Interruptor("Quitar muletillas")
        self.check_puntuacion = Interruptor("Puntuación y mayúsculas automáticas")
        self.check_comandos = Interruptor("Comandos de voz")
        self.check_reescribir = Interruptor("Reescribir con el modelo de lenguaje")
        self.campo_instruccion = QPlainTextEdit()
        self.campo_instruccion.setPlaceholderText(
            "Indicación de estilo para la reescritura (opcional)"
        )
        self.combo_pegado = QComboBox()
        for texto, valor in _PEGADOS:
            self.combo_pegado.addItem(texto, valor)
        self.combo_salto = QComboBox()
        for texto, valor in _SALTOS:
            self.combo_salto.addItem(texto, valor)
        boton_nuevo = QPushButton("Nuevo")
        boton_nuevo.clicked.connect(lambda _=False: self.nuevo())
        boton_guardar = QPushButton("Guardar")
        boton_guardar.setProperty("principal", True)
        boton_guardar.clicked.connect(lambda _=False: self.guardar_modo())
        self.boton_borrar = QPushButton("Borrar")
        self.boton_borrar.clicked.connect(lambda _=False: self.borrar_modo())

        formulario = QFormLayout()
        formulario.addRow("Nombre", self.campo_nombre)
        formulario.addRow(self.check_muletillas)
        formulario.addRow(self.check_puntuacion)
        formulario.addRow(self.check_comandos)
        formulario.addRow(self.check_reescribir)
        formulario.addRow("Estilo", self.campo_instruccion)
        formulario.addRow("Pegado", self.combo_pegado)
        formulario.addRow("Saltos de línea", self.combo_salto)
        botones = QHBoxLayout()
        for boton in (boton_nuevo, boton_guardar, self.boton_borrar):
            botones.addWidget(boton)
        formulario.addRow(botones)

        self.tabla = QTableWidget(0, 3)
        self.tabla.setHorizontalHeaderLabels(["Aplicación", "Modo", "Es terminal"])
        self.campo_aplicacion = QLineEdit()
        self.campo_aplicacion.setPlaceholderText("Identificador de la aplicación, p. ej. ptyxis")
        self.combo_modo_de_aplicacion = QComboBox()
        self.check_terminal = Interruptor("Marcar como terminal")
        asignar = QPushButton("Asignar")
        asignar.clicked.connect(
            lambda _=False: self.asignar(
                self.campo_aplicacion.text(),
                self.combo_modo_de_aplicacion.currentText(),
                es_terminal=self.check_terminal.isChecked(),
            )
        )
        quitar = QPushButton("Quitar la seleccionada")
        quitar.clicked.connect(lambda _=False: self._quitar_la_elegida())

        columna = QVBoxLayout(self)
        arriba = QHBoxLayout()
        arriba.addWidget(self.lista, 1)
        contenedor = QVBoxLayout()
        contenedor.addLayout(formulario)
        arriba.addLayout(contenedor, 2)
        columna.addLayout(arriba)
        columna.addWidget(self.tabla)
        fila = QHBoxLayout()
        for widget in (
            self.campo_aplicacion,
            self.combo_modo_de_aplicacion,
            self.check_terminal,
            asignar,
            quitar,
        ):
            fila.addWidget(widget)
        columna.addLayout(fila)
        columna.addWidget(self._etiqueta_mensaje)
        self._recargar()
        self.seleccionar("General")

    # ---- modos --------------------------------------------------------------------------

    def seleccionar(self, nombre: str) -> None:
        modo = self._modos.obtener(nombre)
        if modo is None:
            return
        self._editando = modo.id
        self.campo_nombre.setText(modo.nombre)
        self.check_muletillas.setChecked(modo.quitar_muletillas)
        self.check_puntuacion.setChecked(modo.puntuacion_automatica)
        self.check_comandos.setChecked(modo.comandos_de_voz)
        self.check_reescribir.setChecked(modo.reescribir)
        self.campo_instruccion.setPlainText(modo.instruccion)
        self.combo_pegado.setCurrentIndex(self.combo_pegado.findData(modo.tipo_pegado))
        self.combo_salto.setCurrentIndex(self.combo_salto.findData(modo.salto_de_linea))
        self.boton_borrar.setEnabled(not modo.es_general)
        elegido = self.lista.findItems(modo.nombre, Qt.MatchFlag.MatchExactly)
        if elegido and self.lista.currentItem() is not elegido[0]:
            self.lista.blockSignals(True)
            self.lista.setCurrentItem(elegido[0])
            self.lista.blockSignals(False)

    def nuevo(self) -> None:
        self._editando = None
        self.campo_nombre.clear()
        for casilla in (self.check_muletillas, self.check_puntuacion, self.check_comandos):
            casilla.setChecked(True)
        self.check_reescribir.setChecked(False)
        self.campo_instruccion.clear()
        self.combo_pegado.setCurrentIndex(self.combo_pegado.findData("automatico"))
        self.combo_salto.setCurrentIndex(self.combo_salto.findData("conservar"))
        self.boton_borrar.setEnabled(False)
        self.campo_nombre.setFocus()

    def guardar_modo(self) -> None:
        datos = {
            "quitar_muletillas": self.check_muletillas.isChecked(),
            "puntuacion_automatica": self.check_puntuacion.isChecked(),
            "comandos_de_voz": self.check_comandos.isChecked(),
            "reescribir": self.check_reescribir.isChecked(),
            "instruccion": self.campo_instruccion.toPlainText(),
            "tipo_pegado": self.combo_pegado.currentData(),
            "salto_de_linea": self.combo_salto.currentData(),
        }
        try:
            if self._editando is None:
                modo = self._modos.crear(self.campo_nombre.text(), **datos)
            else:
                modo = self._modos.actualizar(
                    self._editando, nombre=self.campo_nombre.text(), **datos
                )
        except DatoInvalido as error:
            self.avisar(str(error), error=True)
            return
        self._recargar()
        self.seleccionar(modo.nombre)
        self.avisar(f"Se guardó el modo «{modo.nombre}».")

    def borrar_modo(self) -> None:
        if self._editando is None:
            return
        try:
            self._modos.borrar(self._editando)
        except DatoInvalido as error:
            self.avisar(str(error), error=True)
            return
        self._recargar()
        self.seleccionar("General")
        self.avisar("Modo borrado: sus aplicaciones pasaron al modo general.")

    # ---- asignaciones -------------------------------------------------------------------

    def asignar(self, aplicacion: str, modo: str, *, es_terminal: bool) -> None:
        destino = self._modos.obtener(modo)
        if destino is None:
            self.avisar(f"No existe el modo «{modo}».", error=True)
            return
        try:
            self._asignaciones.asignar(aplicacion, destino.id, es_terminal=es_terminal)
        except DatoInvalido as error:
            self.avisar(str(error), error=True)
            return
        self._recargar_tabla()
        self.avisar(f"«{aplicacion.strip().lower()}» usa el modo «{destino.nombre}».")

    def quitar_asignacion(self, aplicacion: str) -> None:
        self._asignaciones.quitar(aplicacion)
        self._recargar_tabla()

    def _quitar_la_elegida(self) -> None:
        celda = self.tabla.item(self.tabla.currentRow(), 0)
        if celda is not None:
            self.quitar_asignacion(celda.text())

    # ---- internos -----------------------------------------------------------------------

    def _recargar(self) -> None:
        self.lista.blockSignals(True)
        self.lista.clear()
        self.combo_modo_de_aplicacion.clear()
        for modo in self._modos.listar():
            self.lista.addItem(modo.nombre)
            self.combo_modo_de_aplicacion.addItem(modo.nombre)
        self.lista.blockSignals(False)
        self._recargar_tabla()

    def _recargar_tabla(self) -> None:
        nombres = {m.id: m.nombre for m in self._modos.listar()}
        filas = self._asignaciones.listar()
        self.tabla.setRowCount(len(filas))
        for i, a in enumerate(filas):
            self.tabla.setItem(i, 0, QTableWidgetItem(a.aplicacion))
            self.tabla.setItem(i, 1, QTableWidgetItem(nombres.get(a.modo_id, "?")))
            self.tabla.setItem(i, 2, QTableWidgetItem("Sí" if a.es_terminal else "No"))

    def _al_elegir(self, nombre: str) -> None:
        if nombre:
            self.seleccionar(nombre)
