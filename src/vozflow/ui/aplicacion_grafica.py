"""La interfaz completa: bandeja, indicador y ventana de ajustes, conectadas entre sí."""

from collections.abc import Callable
from typing import Protocol

from PySide6.QtCore import QObject, QTimer

from vozflow.dominio.dictado import EstadoDelDictado
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.ui.ajustes.ventana import ContextoDeAjustes, VentanaAjustes, crear_paginas
from vozflow.ui.asistente.ventana import VentanaAsistente, debe_abrirse
from vozflow.ui.bandeja import Bandeja
from vozflow.ui.indicador import Indicador
from vozflow.ui.puente import Puente

_INTERVALO_DE_NIVEL_MS = 50
_AVISO_VISIBLE_MS = 15000


class Controlador(Protocol):
    def pausar(self, pausado: bool) -> None: ...
    def salir(self) -> None: ...


class InterfazGrafica(QObject):
    def __init__(
        self,
        *,
        controlador: Controlador,
        ajustes: AjustesRepo,
        contexto: ContextoDeAjustes,
        nivel: Callable[[], float],
        destino_de_traduccion: Callable[[], str | None] = lambda: None,
        bandeja_disponible: Callable[[], bool] | None = None,
        intervalo_de_nivel_ms: int = _INTERVALO_DE_NIVEL_MS,
        asistente: VentanaAsistente | None = None,
    ) -> None:
        super().__init__()
        self.puente = Puente()
        self._controlador = controlador
        self._nivel = nivel
        self._destino_de_traduccion = destino_de_traduccion
        self._ajustes = ajustes
        self.asistente = asistente
        self.indicador = Indicador(activo=lambda: bool(ajustes.obtener("interfaz.indicador")))
        opciones = {} if bandeja_disponible is None else {"disponible": bandeja_disponible}
        self.bandeja = Bandeja(
            al_abrir_ajustes=lambda: self.mostrar_ajustes("Dictado"),
            al_abrir_historial=lambda: self.mostrar_ajustes("Historial"),
            al_pausar=controlador.pausar,
            al_salir=self.salir,
            **opciones,
        )
        self.ventana = VentanaAjustes(
            {}, ocultar_al_cerrar=self.bandeja.disponible
        )  # se llenan abajo: las páginas necesitan la ventana para reinsertar sin foco
        for nombre, pagina in crear_paginas(contexto, self.ventana.sin_foco).items():
            self.ventana.agregar_pagina(nombre, pagina)
        self._timer = QTimer(self.indicador)  # muere con el indicador, no queda girando suelto
        self._timer.setInterval(intervalo_de_nivel_ms)
        self._timer.timeout.connect(lambda: self.indicador.establecer_nivel(self._nivel()))
        self.bandeja.estado_cambiado.connect(self.ventana.establecer_vista)
        self.puente.estado.connect(self._al_cambiar_el_estado)
        self.puente.aviso.connect(self._al_avisar)
        self.puente.abrir_pagina.connect(self.mostrar_ajustes)

    def mostrar_ajustes(self, pagina: str = "Dictado") -> None:
        self.ventana.mostrar_pagina(pagina)

    def mostrar_al_arrancar(self) -> None:
        """La primera vez abre el asistente. Sin bandeja, la ventana de ajustes es la señal
        de que el programa corre (con el asistente abierto ya hay una ventana a la vista).
        """
        if self.asistente is not None and debe_abrirse(self._ajustes):
            self.asistente.abrir()
            return
        if not self.bandeja.disponible:
            self.mostrar_ajustes("Dictado")

    def cerrar(self) -> None:
        self._timer.stop()
        self.bandeja.cerrar()
        self.indicador.hide()
        self.ventana.permitir_cierre()
        self.ventana.close()
        if self.asistente is not None:
            self.asistente.hide()

    # ---- internos ------------------------------------------------------------------------------

    def _al_cambiar_el_estado(self, estado: EstadoDelDictado) -> None:
        self.bandeja.establecer_estado(estado)
        self.indicador.establecer_estado(estado, self._destino_de_traduccion())
        if estado is EstadoDelDictado.ESCUCHANDO:
            self._timer.start()
        else:
            self._timer.stop()

    def _al_avisar(self, texto: str) -> None:
        self.ventana.statusBar().showMessage(texto, _AVISO_VISIBLE_MS)
        self.bandeja.notificar(texto)

    def salir(self) -> None:
        # Sin esto la ventana ignoraría el cierre y Qt cancelaría el quit().
        self.ventana.permitir_cierre()
        self._controlador.salir()
