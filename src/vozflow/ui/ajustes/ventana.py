"""La ventana de ajustes (RF-029): una pestaña por página, y vive en la bandeja."""

import sqlite3
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QTabWidget, QWidget

from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.audio.captura import Dispositivo
from vozflow.gestion_de_proveedores import AlmacenDeClaves, GestionDeProveedores
from vozflow.insercion.puerto import Insertor
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.copia_repo import CopiaRepo
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.historial import HistorialRepo
from vozflow.persistencia.modos_repo import ModosRepo
from vozflow.reescritura import FabricaDeReescritor
from vozflow.ui.ajustes.audio import PaginaAudio
from vozflow.ui.ajustes.copia import PaginaCopia
from vozflow.ui.ajustes.historial import PaginaHistorial
from vozflow.ui.ajustes.modos import PaginaModos
from vozflow.ui.ajustes.proveedores import PaginaProveedores
from vozflow.ui.ajustes.teclas import PaginaTeclas
from vozflow.ui.ajustes.vocabulario import PaginaVocabulario
from vozflow.ui.estado import VistaDeEstado

_ESPERA_PARA_SOLTAR_EL_FOCO_MS = 400


class _Portapapeles(Protocol):
    def copiar(self, texto: str, *, tambien_primaria: bool) -> None: ...


@dataclass
class ContextoDeAjustes:
    """Todo lo que las páginas necesitan de afuera."""

    base: sqlite3.Connection
    claves: AlmacenDeClaves
    crear_reescritor: FabricaDeReescritor
    aplicar_atajos: Callable[[Mapping[AccionDeAtajo, str]], None]
    portapapeles: _Portapapeles
    insertor: Insertor
    listar_dispositivos: Callable[[], list[Dispositivo]]


def crear_paginas(
    contexto: ContextoDeAjustes, al_reinsertar: Callable[[Callable[[], None]], None]
) -> dict[str, QWidget]:
    base = contexto.base
    ajustes = AjustesRepo(base)
    modos = ModosRepo(base)
    return {
        "Teclas": PaginaTeclas(ajustes, contexto.aplicar_atajos),
        "Audio": PaginaAudio(ajustes, contexto.listar_dispositivos),
        "Modos": PaginaModos(modos, AsignacionesRepo(base)),
        "Vocabulario": PaginaVocabulario(DiccionarioRepo(base), AtajosTextoRepo(base)),
        "Reescritura": PaginaProveedores(
            GestionDeProveedores(base, contexto.claves, contexto.crear_reescritor)
        ),
        "Copia": PaginaCopia(CopiaRepo(base)),
        "Historial": PaginaHistorial(
            HistorialRepo(base, activo=lambda: bool(ajustes.obtener("historial.activo"))),
            contexto.portapapeles,
            contexto.insertor,
            al_reinsertar,
        ),
    }


class VentanaAjustes(QMainWindow):
    def __init__(
        self,
        paginas: Mapping[str, QWidget],
        ocultar_al_cerrar: bool = True,
        espera_ms: int = _ESPERA_PARA_SOLTAR_EL_FOCO_MS,
    ) -> None:
        super().__init__()
        self.setWindowTitle("vozflow — Ajustes")
        self.resize(760, 560)
        self._ocultar_al_cerrar = ocultar_al_cerrar
        self._espera_ms = espera_ms
        self._cierre_permitido = False
        self._pestanas = QTabWidget()
        self._indices: dict[str, int] = {}
        for nombre, pagina in paginas.items():
            self._indices[nombre] = self._pestanas.addTab(pagina, nombre)
        self.setCentralWidget(self._pestanas)
        self._estado = QLabel("Listo")
        self.statusBar().addPermanentWidget(self._estado)

    def agregar_pagina(self, nombre: str, pagina: QWidget) -> None:
        self._indices[nombre] = self._pestanas.addTab(pagina, nombre)

    def nombres_de_paginas(self) -> list[str]:
        return list(self._indices)

    def pagina_actual(self) -> str:
        indice = self._pestanas.currentIndex()
        return next(nombre for nombre, i in self._indices.items() if i == indice)

    def mostrar_pagina(self, nombre: str) -> None:
        self._pestanas.setCurrentIndex(self._indices[nombre])
        self.show()
        self.raise_()
        self.activateWindow()

    def establecer_vista(self, vista: VistaDeEstado) -> None:
        self._estado.setText(vista.texto)

    def texto_de_estado(self) -> str:
        return self._estado.text()

    def permitir_cierre(self) -> None:
        self._cierre_permitido = True

    def sin_foco(self, accion: Callable[[], None]) -> None:
        """Oculta la ventana, espera a que el foco vuelva a la aplicación anterior y ejecuta."""
        estaba_visible = self.isVisible()
        self.hide()

        def ejecutar() -> None:
            try:
                accion()
            finally:
                if estaba_visible:
                    self.show()

        QTimer.singleShot(self._espera_ms, ejecutar)

    def closeEvent(self, evento: QCloseEvent) -> None:  # noqa: N802 (nombre de Qt)
        if self._cierre_permitido:
            evento.accept()
            return
        evento.ignore()
        if self._ocultar_al_cerrar:
            self.hide()
        else:
            self.showMinimized()  # sin bandeja, esta ventana es la única puerta al programa
