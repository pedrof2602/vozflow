"""Página «General» de los ajustes (002, RP-015): tema, arrancar con la sesión y el asistente.

Reúne las antiguas páginas «Apariencia» y «Sistema». Todo se guarda al cambiar.
"""

from collections.abc import Callable

from PySide6.QtWidgets import QPushButton, QVBoxLayout

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.ui.ajustes.base import PaginaBase
from vozflow.ui.componentes import Chips, FilaDeAjuste, Interruptor
from vozflow.ui.textos import ayuda_de, texto_de

_TEMAS = (
    ("Automático (como el sistema)", "auto"),
    ("Claro", "claro"),
    ("Oscuro", "oscuro"),
)


class PaginaGeneral(PaginaBase):
    CLAVES = ("interfaz.tema",)

    def __init__(
        self,
        ajustes: AjustesRepo,
        aplicar_tema: Callable[[str], None],
        autoinicio_activo: Callable[[], bool],
        fijar_autoinicio: Callable[[bool], None],
        repetir_asistente: Callable[[], None] = lambda: None,
    ) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._aplicar_tema = aplicar_tema
        self._fijar_autoinicio = fijar_autoinicio

        self.selector_tema = Chips()
        for texto, modo in _TEMAS:
            self.selector_tema.addItem(texto, modo)
        self._mostrar_tema()
        self.selector_tema.currentIndexChanged.connect(lambda _: self._tema_elegido())

        self.interruptor_autoinicio = Interruptor()
        self.interruptor_autoinicio.setChecked(autoinicio_activo())
        self.interruptor_autoinicio.toggled.connect(self._autoinicio_cambiado)

        self.boton_asistente = QPushButton("Abrir el asistente")
        self.boton_asistente.clicked.connect(lambda _=False: repetir_asistente())

        self.filas = {
            "interfaz.tema": FilaDeAjuste(
                texto_de("interfaz.tema").titulo,
                ayuda_de("interfaz.tema"),
                self.selector_tema,
                restablecer=self._restablecer_tema,
                es_el_original=lambda: (
                    self._ajustes.obtener("interfaz.tema") == self._ajustes.defecto("interfaz.tema")
                ),
            ),
            "autoinicio": FilaDeAjuste(
                texto_de("autoinicio").titulo, ayuda_de("autoinicio"), self.interruptor_autoinicio
            ),
            "asistente.repetir": FilaDeAjuste(
                texto_de("asistente.repetir").titulo,
                ayuda_de("asistente.repetir"),
                self.boton_asistente,
            ),
        }
        columna = QVBoxLayout(self)
        for fila in self.filas.values():
            columna.addWidget(fila)
        columna.addWidget(self._etiqueta_mensaje)
        columna.addStretch()

    # ---- tema ----

    def _mostrar_tema(self) -> None:
        self.selector_tema.blockSignals(True)
        self.selector_tema.setCurrentIndex(
            max(0, self.selector_tema.findData(self._ajustes.obtener("interfaz.tema")))
        )
        self.selector_tema.blockSignals(False)

    def _tema_elegido(self) -> None:
        modo = str(self.selector_tema.currentData())
        self._ajustes.establecer("interfaz.tema", modo)
        self._aplicar_tema(modo)
        self.filas["interfaz.tema"].refrescar()

    def _restablecer_tema(self) -> None:
        self._ajustes.restablecer("interfaz.tema")
        self._mostrar_tema()
        self._aplicar_tema(str(self._ajustes.obtener("interfaz.tema")))

    # ---- arrancar con la sesión ----

    def _autoinicio_cambiado(self, activo: bool) -> None:
        try:
            self._fijar_autoinicio(activo)
        except (OSError, ValueError) as error:  # FileExistsError es un OSError
            self.interruptor_autoinicio.blockSignals(True)
            self.interruptor_autoinicio.setChecked(not activo)
            self.interruptor_autoinicio.blockSignals(False)
            self.avisar(str(error), error=True)
            return
        self.avisar(
            "vozflow arrancará en segundo plano con la sesión."
            if activo
            else "vozflow ya no arranca con la sesión."
        )
