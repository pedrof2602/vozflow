"""Paso de la tecla del asistente (002, RP-009).

Muestra la tecla para dictar, deja cambiarla y no permite quedarse con una que el teclado de la
persona no tiene: en ese caso propone otra.
"""

from collections.abc import Callable, Mapping

from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from vozflow.atajos.disponibilidad import atajo_disponible, proponer_tecla
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.ui.ajustes.teclas import (
    ERRORES_DE_LA_ESCUCHA,
    CampoDeAtajo,
    cambiar_tecla_para_dictar,
)
from vozflow.ui.asistente.base import PasoDelAsistente
from vozflow.ui.componentes import FilaDeTeclas, teclas_de


class PasoTecla(PasoDelAsistente):
    TITULO = "Tu tecla para dictar"

    def __init__(
        self,
        ajustes: AjustesRepo,
        aplicar_atajos: Callable[[Mapping[AccionDeAtajo, str]], None],
        teclas_del_teclado: Callable[[], set[int]],
    ) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._aplicar_atajos = aplicar_atajos
        self._teclas_del_teclado = teclas_del_teclado
        self._propuesta = ""
        self.hay_error = False
        self.teclas = FilaDeTeclas()
        self.campo_tecla = CampoDeAtajo(permitir_modificador_solo=True)
        self.campo_tecla.hide()
        self.campo_tecla.setPlaceholderText("Apretá la tecla nueva…")
        self.campo_tecla.atajo_cambiado.connect(self._tecla_elegida)
        self.boton_cambiar = QPushButton("Cambiar")
        self.boton_cambiar.clicked.connect(lambda _=False: self._empezar_a_elegir())
        self.boton_propuesta = QPushButton()
        self.boton_propuesta.hide()
        self.boton_propuesta.clicked.connect(lambda _=False: self._usar_la_propuesta())
        self.aviso = QLabel()
        self.aviso.setWordWrap(True)
        ayuda = QLabel(
            "Mantenela apretada mientras hablás y soltala cuando termines: el texto aparece donde "
            "estés escribiendo."
        )
        ayuda.setWordWrap(True)
        fila = QHBoxLayout()
        fila.addWidget(self.teclas)
        fila.addWidget(self.boton_cambiar)
        columna = QVBoxLayout(self)
        columna.addWidget(ayuda)
        columna.addLayout(fila)
        columna.addWidget(self.campo_tecla)
        columna.addWidget(self.aviso)
        columna.addWidget(self.boton_propuesta)
        columna.addStretch()

    # ---- el paso ----

    def puede_avanzar(self) -> bool:
        return atajo_disponible(self._actual(), self._teclas_del_teclado())

    def al_entrar(self) -> None:
        self.aviso.clear()
        self._mostrar()

    # ---- internos ----

    def _actual(self) -> str:
        return str(self._ajustes.obtener("atajo.mantener"))

    def _mostrar(self) -> None:
        actual = self._actual()
        self.teclas.establecer(actual)
        teclas = self._teclas_del_teclado()
        if atajo_disponible(actual, teclas):
            self.boton_propuesta.hide()
            self._propuesta = ""
            return
        self._avisar_que_no_existe(actual, teclas)

    def _avisar_que_no_existe(self, atajo: str, teclas: set[int]) -> None:
        nombre = " + ".join(teclas_de(atajo)) or atajo
        otras = [str(self._ajustes.obtener(c)) for c in ("atajo.alternar", "atajo.traducir")]
        propuesta = proponer_tecla(teclas, excluir=otras)
        self.aviso.setText(f"Tu teclado no tiene la tecla «{nombre}», así que no podrías usarla.")
        self._propuesta = propuesta or ""
        if propuesta:
            self.boton_propuesta.setText("Usar " + " + ".join(teclas_de(propuesta)))
            self.boton_propuesta.show()
        else:
            self.boton_propuesta.hide()
            self.aviso.setText(self.aviso.text() + " Apretá «Cambiar» y elegí otra.")

    def _empezar_a_elegir(self) -> None:
        self.campo_tecla.show()
        self.campo_tecla.setFocus()

    def _tecla_elegida(self, atajo: str) -> None:
        self.campo_tecla.hide()
        teclas = self._teclas_del_teclado()
        if not atajo_disponible(atajo, teclas):
            self._avisar_que_no_existe(atajo, teclas)
            return
        self._aplicar(atajo)

    def _usar_la_propuesta(self) -> None:
        if self._propuesta:
            self._aplicar(self._propuesta)

    def _aplicar(self, atajo: str) -> None:
        try:
            cambiar_tecla_para_dictar(self._ajustes, self._aplicar_atajos, atajo)
        except (DatoInvalido, *ERRORES_DE_LA_ESCUCHA) as error:
            self.hay_error = True
            self.aviso.setText(str(error))
            self._mostrar_sin_pisar_el_aviso()
            return
        self.hay_error = False
        self.aviso.setText("Listo, ya funciona.")
        self._mostrar_sin_pisar_el_aviso()
        self.cambio.emit()

    def _mostrar_sin_pisar_el_aviso(self) -> None:
        aviso = self.aviso.text()
        self._mostrar()
        if not self.boton_propuesta.isVisibleTo(self):
            self.aviso.setText(aviso)
