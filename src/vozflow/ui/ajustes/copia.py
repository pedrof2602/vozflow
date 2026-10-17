"""Página de la copia de seguridad (RF-022): exportar e importar, y qué entrada falló."""

from collections.abc import Callable
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from vozflow.dominio.copia import CopiaInvalida
from vozflow.persistencia.copia_repo import CopiaRepo
from vozflow.ui.ajustes.base import PaginaBase


def elegir_con_dialogo(modo: str) -> Path | None:
    if modo == "exportar":
        ruta, _ = QFileDialog.getSaveFileName(
            None, "Guardar la copia", "vozflow-copia.json", "Copia de vozflow (*.json)"
        )
    else:
        ruta, _ = QFileDialog.getOpenFileName(
            None, "Elegir la copia", "", "Copia de vozflow (*.json)"
        )
    return Path(ruta) if ruta else None


class PaginaCopia(PaginaBase):
    def __init__(
        self,
        copia: CopiaRepo,
        elegir_archivo: Callable[[str], Path | None] = elegir_con_dialogo,
    ) -> None:
        super().__init__()
        self._copia = copia
        self._elegir = elegir_archivo
        self.aclaracion = QLabel(
            "La copia guarda el diccionario, los atajos de texto, los modos y las asignaciones de "
            "aplicación. No incluye el historial ni las claves de acceso."
        )
        self.aclaracion.setWordWrap(True)
        exportar = QPushButton("Exportar…")
        exportar.clicked.connect(lambda _=False: self.exportar())
        importar = QPushButton("Importar…")
        importar.clicked.connect(lambda _=False: self.importar())
        botones = QHBoxLayout()
        botones.addWidget(exportar)
        botones.addWidget(importar)
        columna = QVBoxLayout(self)
        columna.addWidget(self.aclaracion)
        columna.addLayout(botones)
        columna.addWidget(self._etiqueta_mensaje)
        columna.addStretch()

    def exportar(self) -> None:
        destino = self._elegir("exportar")
        if destino is None:
            return
        try:
            self._copia.exportar_a(destino)
        except OSError as error:
            self.avisar(f"No se pudo escribir {destino}: {error.strerror}", error=True)
            return
        self.avisar(f"Copia guardada en {destino}.")

    def importar(self) -> None:
        origen = self._elegir("importar")
        if origen is None:
            return
        try:
            resumen = self._copia.importar_de(origen)
        except CopiaInvalida as error:
            self.avisar(f"No se importó nada. {error}", error=True)
            return
        self.avisar(
            f"Se importó: {resumen.diccionario} palabras, {resumen.atajos_de_texto} atajos de "
            f"texto, {resumen.modos} modos y {resumen.asignaciones} asignaciones."
        )
