"""La ventana de ajustes (RF-029): barra lateral agrupada y una página por entrada."""

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.audio.captura import Dispositivo
from vozflow.dominio.dictado import EstadoDelDictado
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
from vozflow.ui.ajustes.apariencia import PaginaApariencia
from vozflow.ui.ajustes.audio import PaginaAudio
from vozflow.ui.ajustes.copia import PaginaCopia
from vozflow.ui.ajustes.historial import PaginaHistorial
from vozflow.ui.ajustes.modos import PaginaModos
from vozflow.ui.ajustes.proveedores import PaginaProveedores
from vozflow.ui.ajustes.teclas import PaginaTeclas
from vozflow.ui.ajustes.vocabulario import PaginaVocabulario
from vozflow.ui.estado import VistaDeEstado, vista_de
from vozflow.ui.iconos_de_linea import icono
from vozflow.ui.logo import logo
from vozflow.ui.tema import paleta_actual

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
    aplicar_tema: Callable[[str], None] = lambda modo: None


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
        "Apariencia": PaginaApariencia(ajustes, contexto.aplicar_tema),
    }


GRUPOS_POR_DEFECTO = {
    "Historial": "INICIO",
    "Modos": "TEXTO",
    "Vocabulario": "TEXTO",
    "Teclas": "DICTADO",
    "Audio": "DICTADO",
    "Reescritura": "INTELIGENCIA ARTIFICIAL",
    "Copia": "DATOS",
    "Apariencia": "APLICACIÓN",
}
ORDEN_DE_GRUPOS = ["INICIO", "TEXTO", "DICTADO", "INTELIGENCIA ARTIFICIAL", "DATOS", "APLICACIÓN"]
_ICONOS_POR_PAGINA = {
    "Historial": "historial",
    "Modos": "modos",
    "Vocabulario": "vocabulario",
    "Teclas": "teclas",
    "Audio": "audio",
    "Reescritura": "reescritura",
    "Copia": "copia",
    "Apariencia": "ajustes",
}
_DESCRIPCIONES_POR_DEFECTO = {
    "Historial": "Lo que dictaste, para buscarlo y volver a usarlo",
    "Modos": "Cómo se pule el texto según la aplicación",
    "Vocabulario": "Palabras propias y atajos de texto",
    "Teclas": "Con qué teclas se empieza y se termina de dictar",
    "Audio": "El micrófono que se escucha",
    "Reescritura": "Mejora y traducción con un modelo de lenguaje, solo si lo prendés",
    "Copia": "Exportar e importar tus datos",
    "Apariencia": "Tema claro, oscuro o el del sistema",
}


class VentanaAjustes(QMainWindow):
    """Barra lateral agrupada a la izquierda y la página elegida a la derecha."""

    def __init__(
        self,
        paginas: Mapping[str, QWidget],
        ocultar_al_cerrar: bool = True,
        espera_ms: int = _ESPERA_PARA_SOLTAR_EL_FOCO_MS,
        grupos: Mapping[str, str] | None = None,
        orden_de_grupos: Sequence[str] | None = None,
        descripciones: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("vozflow — Ajustes")
        self.setWindowIcon(logo())
        self.resize(960, 640)
        self._ocultar_al_cerrar = ocultar_al_cerrar
        self._espera_ms = espera_ms
        self._cierre_permitido = False
        self._grupos = dict(GRUPOS_POR_DEFECTO if grupos is None else grupos)
        self._orden_de_grupos = list(
            ORDEN_DE_GRUPOS if orden_de_grupos is None else orden_de_grupos
        )
        self._descripciones = dict(
            _DESCRIPCIONES_POR_DEFECTO if descripciones is None else descripciones
        )
        self._paginas: dict[str, QWidget] = {}
        self._indices: dict[str, int] = {}
        self._botones: dict[str, QPushButton] = {}
        self._actual = ""

        raiz = QWidget()
        raiz.setObjectName("ventana")
        fila = QHBoxLayout(raiz)
        fila.setContentsMargins(0, 0, 0, 0)
        fila.setSpacing(0)
        self._lateral = QFrame()
        self._lateral.setObjectName("lateral")
        self._lateral.setFixedWidth(210)
        self._columna = QVBoxLayout(self._lateral)
        self._columna.setContentsMargins(10, 14, 10, 14)
        self._columna.setSpacing(2)
        marca = QLabel("vozflow")
        marca.setObjectName("seccion")
        marca.setContentsMargins(10, 0, 0, 8)
        self._columna.addWidget(marca)
        self._lugar_de_botones = QVBoxLayout()
        self._lugar_de_botones.setSpacing(2)
        self._columna.addLayout(self._lugar_de_botones)
        self._columna.addStretch()
        fila.addWidget(self._lateral)

        derecha = QVBoxLayout()
        derecha.setContentsMargins(28, 22, 28, 16)
        derecha.setSpacing(12)
        self._titulo = QLabel("")
        self._titulo.setObjectName("titulo")
        self._descripcion = QLabel("")
        self._descripcion.setObjectName("descripcion")
        self._descripcion.setWordWrap(True)
        derecha.addWidget(self._titulo)
        derecha.addWidget(self._descripcion)
        self._pila = QStackedWidget()
        derecha.addWidget(self._pila, 1)
        fila.addLayout(derecha, 1)
        self.setCentralWidget(raiz)

        self._estado = QLabel("Listo")
        self._punto = QLabel("●")
        self.statusBar().addPermanentWidget(self._punto)
        self.statusBar().addPermanentWidget(self._estado)
        self._grupo_de_botones = QButtonGroup(self)
        self._grupo_de_botones.setExclusive(True)

        for nombre, pagina in paginas.items():
            self._registrar(nombre, pagina)
        self._reconstruir_barra()
        if self._orden:
            self._elegir(self._orden[0])
        self.establecer_vista(vista_de(EstadoDelDictado.INACTIVO))

    # ---- armado de la barra ----

    def _registrar(self, nombre: str, pagina: QWidget) -> None:
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        area.setWidget(pagina)
        self._paginas[nombre] = pagina
        self._indices[nombre] = self._pila.addWidget(area)

    def _reconstruir_barra(self) -> None:
        while (item := self._lugar_de_botones.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
        self._botones.clear()
        self._etiquetas: list[QLabel] = []
        por_grupo: dict[str, list[str]] = {}
        for nombre in self._paginas:
            por_grupo.setdefault(self._grupos.get(nombre, ""), []).append(nombre)
        etiquetas = [g for g in self._orden_de_grupos if g in por_grupo]
        etiquetas += [g for g in por_grupo if g and g not in etiquetas]
        sin_grupo = por_grupo.get("", [])
        self._orden = []
        for grupo in ([""] if sin_grupo else []) + etiquetas:
            if grupo:
                etiqueta = QLabel(grupo)
                etiqueta.setObjectName("grupo")
                self._etiquetas.append(etiqueta)
                self._lugar_de_botones.addWidget(etiqueta)
            for nombre in por_grupo[grupo]:
                self._lugar_de_botones.addWidget(self._crear_boton(nombre))
                self._orden.append(nombre)

    def _crear_boton(self, nombre: str) -> QPushButton:
        boton = QPushButton(nombre)
        boton.setProperty("nav", True)
        boton.setCheckable(True)
        boton.setCursor(Qt.CursorShape.PointingHandCursor)
        icono_de_linea = _ICONOS_POR_PAGINA.get(nombre, "ajustes")
        boton.setIcon(icono(icono_de_linea, paleta_actual().texto_atenuado, 18))
        boton.clicked.connect(lambda _=False, n=nombre: self._elegir(n))
        self._grupo_de_botones.addButton(boton)
        self._botones[nombre] = boton
        return boton

    def _elegir(self, nombre: str) -> None:
        self._actual = nombre
        self._pila.setCurrentIndex(self._indices[nombre])
        self._botones[nombre].setChecked(True)
        self._titulo.setText(nombre)
        self._descripcion.setText(self._descripciones.get(nombre, ""))
        self._descripcion.setVisible(bool(self._descripciones.get(nombre)))

    # ---- interfaz pública ----

    def agregar_pagina(self, nombre: str, pagina: QWidget, grupo: str = "") -> None:
        self._registrar(nombre, pagina)
        if grupo:
            self._grupos[nombre] = grupo
        actual = self._actual
        self._reconstruir_barra()
        if actual:
            self._elegir(actual)

    def actualizar_iconos(self) -> None:
        """Vuelve a teñir los íconos de la barra con la paleta en uso."""
        for nombre, boton in self._botones.items():
            boton.setIcon(
                icono(_ICONOS_POR_PAGINA.get(nombre, "ajustes"), paleta_actual().texto_atenuado, 18)
            )

    def nombres_de_paginas(self) -> list[str]:
        return list(self._orden)

    def etiquetas_de_grupo(self) -> list[str]:
        return [e.text() for e in self._etiquetas]

    def botones_de_navegacion(self) -> list[QPushButton]:
        return [self._botones[n] for n in self._orden]

    def widget_de_pagina(self, nombre: str) -> QWidget:
        return self._paginas[nombre]

    def titulo_de_pagina(self) -> str:
        return self._titulo.text()

    def descripcion_de_pagina(self) -> str:
        return self._descripcion.text()

    def pagina_actual(self) -> str:
        return self._actual

    def mostrar_pagina(self, nombre: str) -> None:
        self._elegir(nombre)
        self.show()
        self.raise_()
        self.activateWindow()

    def establecer_vista(self, vista: VistaDeEstado) -> None:
        self._estado.setText(vista.texto)
        self._punto.setStyleSheet(f"color: {vista.color}; background: transparent;")

    def color_de_estado(self) -> str:
        return self._punto.styleSheet()

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
