"""Página del historial (RF-027): buscar, copiar, volver a insertar y borrar dictados."""

from collections.abc import Callable
from typing import Protocol

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from vozflow.dominio.historial import Dictado
from vozflow.insercion.puerto import Destino, Insertor
from vozflow.persistencia.historial import HistorialRepo
from vozflow.ui.ajustes.base import PaginaBase

_LIMITE = 200
_RESUMEN = 70


class _Portapapeles(Protocol):
    def copiar(self, texto: str, *, tambien_primaria: bool) -> None: ...


def _linea(dictado: Dictado) -> str:
    texto = " ".join(dictado.texto_final.split())
    if len(texto) > _RESUMEN:
        texto = texto[: _RESUMEN - 1] + "…"
    fecha = dictado.creado_en.astimezone().strftime("%d/%m %H:%M")
    estado = dictado.estado.replace("_", " ")
    marca = "" if dictado.estado == "insertado" else f"[{estado}] "
    return f"{fecha}  {marca}{texto}"


class PaginaHistorial(PaginaBase):
    def __init__(
        self,
        historial: HistorialRepo,
        portapapeles: _Portapapeles,
        insertor: Insertor,
        al_reinsertar: Callable[[Callable[[], None]], None],
        destino: Destino | None = None,
    ) -> None:
        super().__init__()
        self._historial = historial
        self._portapapeles = portapapeles
        self._insertor = insertor
        self._al_reinsertar = al_reinsertar
        self._destino = destino or Destino()
        self._ids: list[int] = []
        self.aviso_apagado = QLabel()
        self.campo_busqueda = QLineEdit()
        self.campo_busqueda.setPlaceholderText("Buscar en lo dictado…")
        self.campo_busqueda.returnPressed.connect(self.buscar)
        self.lista = QListWidget()
        self.lista.currentRowChanged.connect(self._al_elegir)
        self.vista = QPlainTextEdit()
        self.vista.setReadOnly(True)
        botones = QHBoxLayout()
        for texto, accion in (
            ("Copiar", self.copiar),
            ("Volver a insertar", self.reinsertar),
            ("Borrar", self.borrar),
            ("Borrar todo", self._confirmar_y_borrar_todo),
        ):
            boton = QPushButton(texto)
            boton.clicked.connect(lambda _=False, a=accion: a())
            botones.addWidget(boton)
        columna = QVBoxLayout(self)
        columna.addWidget(self.aviso_apagado)
        columna.addWidget(self.campo_busqueda)
        columna.addWidget(self.lista, 2)
        columna.addWidget(self.vista, 1)
        columna.addLayout(botones)
        columna.addWidget(self._etiqueta_mensaje)
        self.recargar()

    def recargar(self) -> None:
        self.aviso_apagado.setText(
            "" if self._historial.esta_activo()
            else "El historial está apagado: los dictados nuevos no se guardan."
        )  # fmt: skip
        self.buscar()

    def buscar(self) -> None:
        consulta = self.campo_busqueda.text().strip()
        dictados = (
            self._historial.buscar(consulta, _LIMITE)
            if consulta
            else self._historial.listar(_LIMITE)
        )
        self._mostrar(dictados)
        if consulta and not dictados:
            self.avisar("No hay ningún dictado que coincida con la búsqueda.")
        elif self.hay_error is False:
            self.avisar("")

    def copiar(self) -> None:
        id_ = self._elegido()
        if id_ is not None and self._historial.copiar(id_, self._portapapeles):
            self.avisar("Texto copiado al portapapeles.")

    def reinsertar(self) -> None:
        id_ = self._elegido()
        if id_ is None:
            return

        def insertar() -> None:
            resultado = self._historial.reinsertar(id_, self._insertor, self._destino)
            if resultado.insertado:
                self.buscar()
                self.avisar("Texto insertado de nuevo.")
            else:
                self.avisar(resultado.motivo or "No se pudo insertar el texto.", error=True)

        # Se inserta en la ventana que tenía el foco antes: quien llama oculta ésta y espera.
        self._al_reinsertar(insertar)

    def borrar(self) -> None:
        id_ = self._elegido()
        if id_ is not None:
            self._historial.borrar(id_)
            self.buscar()

    def borrar_todo(self) -> None:
        cantidad = self._historial.borrar_todo()
        self.buscar()
        self.avisar(f"Se borraron {cantidad} dictados.")

    # ---- internos ------------------------------------------------------------------------------

    def _confirmar_y_borrar_todo(self) -> None:
        respuesta = QMessageBox.question(
            self, "Borrar todo el historial", "¿Borrar todos los dictados guardados?"
        )
        if respuesta == QMessageBox.StandardButton.Yes:
            self.borrar_todo()

    def _mostrar(self, dictados: list[Dictado]) -> None:
        self._ids = [d.id for d in dictados]
        self._textos = {d.id: d.texto_final for d in dictados}
        self.lista.blockSignals(True)
        self.lista.clear()
        for d in dictados:
            self.lista.addItem(_linea(d))
        self.lista.blockSignals(False)
        self.vista.clear()

    def _elegido(self) -> int | None:
        fila = self.lista.currentRow()
        return self._ids[fila] if 0 <= fila < len(self._ids) else None

    def _al_elegir(self, fila: int) -> None:
        self.vista.setPlainText(
            self._textos.get(self._ids[fila], "") if 0 <= fila < len(self._ids) else ""
        )
