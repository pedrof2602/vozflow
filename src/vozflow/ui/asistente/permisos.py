"""Paso de permisos del asistente (002, RP-011): lo que falta, para qué sirve y el paso exacto."""

import logging
from collections.abc import Callable

from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from vozflow.permisos import Estado, Permiso
from vozflow.ui.asistente.base import PasoDelAsistente

_registro = logging.getLogger(__name__)
_PENDIENTES = (Estado.FALTA, Estado.FALTA_REINICIAR_SESION)


def hay_permisos_pendientes(permisos: list[Permiso]) -> bool:
    """El paso solo se muestra si hay algo para resolver: quien está bien no lo ve."""
    return any(p.estado in _PENDIENTES for p in permisos)


class PasoPermisos(PasoDelAsistente):
    TITULO = "Permisos"

    def __init__(
        self, comprobar: Callable[[], list[Permiso]], copiar: Callable[[str], None]
    ) -> None:
        super().__init__()
        self._comprobar = comprobar
        self._copiar = copiar
        self._comando = ""
        self.boton_copiar_comando = QPushButton("Copiar el comando")
        self.boton_copiar_comando.clicked.connect(lambda _=False: self._copiar(self._comando))
        self.boton_ya_lo_hice = QPushButton("Ya lo hice")
        self.boton_ya_lo_hice.clicked.connect(lambda _=False: self._revisar(avisar=True))
        self._contenido = QWidget()
        self._columna_del_contenido = QVBoxLayout(self._contenido)
        self._columna_del_contenido.setContentsMargins(0, 0, 0, 0)
        columna = QVBoxLayout(self)
        introduccion = QLabel(
            "Para que vozflow funcione, tu computadora tiene que dejarla hacer algunas cosas."
        )
        introduccion.setWordWrap(True)
        introduccion.setObjectName("descripcion")
        columna.addWidget(introduccion)
        columna.addWidget(self._contenido)
        columna.addWidget(self.boton_copiar_comando)
        columna.addWidget(self.boton_ya_lo_hice)
        columna.addStretch()

    def comando_visible(self) -> str:
        return self._comando

    def puede_avanzar(self) -> bool:
        return True  # nunca se traba a nadie: puede seguir y resolverlo después

    def al_entrar(self) -> None:
        self._revisar(avisar=False)

    # ---- internos ----

    def _revisar(self, *, avisar: bool) -> None:
        try:
            permisos = self._comprobar()
        except Exception:
            _registro.exception("No se pudieron comprobar los permisos")
            self._mostrar_texto("No pude comprobar los permisos. Probá de nuevo en un momento.")
            return
        pendientes = [p for p in permisos if p.estado in _PENDIENTES]
        self._limpiar()
        if not pendientes:
            self._mostrar_texto("¡Todo en orden! Ya podés seguir.")
            self.boton_ya_lo_hice.hide()
            self.boton_copiar_comando.hide()
            self._comando = ""
            if avisar:
                self.cambio.emit()
            return
        self.boton_ya_lo_hice.show()
        for permiso in pendientes:
            self._agregar(permiso)
        self._comando = next((p.comando for p in pendientes if p.comando), "")
        self.boton_copiar_comando.setVisible(bool(self._comando))
        if avisar:
            self.cambio.emit()

    def _limpiar(self) -> None:
        while (item := self._columna_del_contenido.takeAt(0)) is not None:
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _mostrar_texto(self, texto: str) -> None:
        self._limpiar()
        etiqueta = QLabel(texto)
        etiqueta.setWordWrap(True)
        self._columna_del_contenido.addWidget(etiqueta)

    def _agregar(self, permiso: Permiso) -> None:
        titulo = QLabel(permiso.titulo)
        titulo.setObjectName("seccion")
        por_que = QLabel(permiso.por_que)
        por_que.setObjectName("descripcion")
        por_que.setWordWrap(True)
        paso = QLabel(permiso.paso)
        paso.setWordWrap(True)
        for etiqueta in (titulo, por_que, paso):
            self._columna_del_contenido.addWidget(etiqueta)
        if permiso.comando:
            comando = QLabel(permiso.comando)
            comando.setObjectName("comando")
            comando.setTextInteractionFlags(comando.textInteractionFlags().TextSelectableByMouse)
            self._columna_del_contenido.addWidget(comando)
