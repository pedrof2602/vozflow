"""Página «Dictado» de los ajustes (002, RP-015): lo básico, sin botón «Guardar».

Tecla para dictar, micrófono, idioma y cartel de grabación. Cada cambio se guarda al instante y cada
opción lleva su ayuda y, si se movió, un «Restablecer». Lo técnico vive en «Avanzado».
"""

from collections.abc import Callable, Mapping

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.audio.captura import Dispositivo, listar_dispositivos
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.ui.ajustes.base import PaginaBase
from vozflow.ui.ajustes.teclas import (
    ERRORES_DE_LA_ESCUCHA,
    CampoDeAtajo,
    cambiar_tecla_para_dictar,
)
from vozflow.ui.componentes import FilaDeAjuste, FilaDeTeclas, Interruptor
from vozflow.ui.microfonos import llenar_combo_de_microfonos
from vozflow.ui.textos import ayuda_de, texto_de

_IDIOMAS = (("Automático", "automatico"), ("Español", "es"), ("Inglés", "en"))
_REGE_AL_REINICIAR = "Listo. Se usa la próxima vez que abras vozflow."
_REGE_YA = "Listo, ya funciona."


class PaginaDictado(PaginaBase):
    CLAVES = ("atajo.mantener", "audio.dispositivo", "idioma.modo", "interfaz.indicador")

    def __init__(
        self,
        ajustes: AjustesRepo,
        aplicar_atajos: Callable[[Mapping[AccionDeAtajo, str]], None],
        listar: Callable[[], list[Dispositivo]] = listar_dispositivos,
    ) -> None:
        super().__init__()
        self._ajustes = ajustes
        self._aplicar_atajos = aplicar_atajos
        self._listar = listar
        self.combo_microfono = QComboBox()
        self.combo_idioma = QComboBox()
        for texto, valor in _IDIOMAS:
            self.combo_idioma.addItem(texto, valor)
        self.interruptor_indicador = Interruptor()
        self.teclas = FilaDeTeclas()
        self.campo_tecla = CampoDeAtajo(permitir_modificador_solo=True)
        self.campo_tecla.hide()
        self.campo_tecla.setPlaceholderText("Apretá la tecla nueva…")
        self.campo_tecla.atajo_cambiado.connect(self._tecla_elegida)
        self.boton_cambiar = QPushButton("Cambiar")
        self.boton_cambiar.clicked.connect(lambda _=False: self._empezar_a_elegir())

        caja_tecla = QWidget()
        columna_tecla = QVBoxLayout(caja_tecla)
        columna_tecla.setContentsMargins(0, 0, 0, 0)
        fila_tecla = QHBoxLayout()
        fila_tecla.addWidget(self.teclas)
        fila_tecla.addWidget(self.boton_cambiar)
        columna_tecla.addLayout(fila_tecla)
        columna_tecla.addWidget(self.campo_tecla)

        self.filas: dict[str, FilaDeAjuste] = {
            "atajo.mantener": self._fila("atajo.mantener", caja_tecla),
            "audio.dispositivo": self._fila("audio.dispositivo", self.combo_microfono),
            "idioma.modo": self._fila("idioma.modo", self.combo_idioma),
            "interfaz.indicador": self._fila("interfaz.indicador", self.interruptor_indicador),
        }
        columna = QVBoxLayout(self)
        for fila in self.filas.values():
            columna.addWidget(fila)
        columna.addWidget(self._etiqueta_mensaje)
        columna.addStretch()
        self.recargar()
        self.combo_microfono.currentIndexChanged.connect(lambda _: self._guardar_microfono())
        self.combo_idioma.currentIndexChanged.connect(lambda _: self._guardar_idioma())
        self.interruptor_indicador.toggled.connect(self._guardar_indicador)

    # ---- armado ----

    def _fila(self, clave: str, control: QWidget) -> FilaDeAjuste:
        return FilaDeAjuste(
            texto_de(clave).titulo,
            ayuda_de(clave),
            control,
            restablecer=lambda: self._restablecer(clave),
            es_el_original=lambda: self._ajustes.obtener(clave) == self._ajustes.defecto(clave),
        )

    def recargar(self) -> None:
        """Muestra lo guardado, sin volver a guardar nada."""
        controles = (self.combo_microfono, self.combo_idioma, self.interruptor_indicador)
        for control in controles:
            control.blockSignals(True)
        guardado = str(self._ajustes.obtener("audio.dispositivo"))
        llenar_combo_de_microfonos(self.combo_microfono, guardado, self._listar)
        self.combo_idioma.setCurrentIndex(
            self.combo_idioma.findData(self._ajustes.obtener("idioma.modo"))
        )
        self.interruptor_indicador.setChecked(bool(self._ajustes.obtener("interfaz.indicador")))
        for control in controles:
            control.blockSignals(False)
        self.teclas.establecer(str(self._ajustes.obtener("atajo.mantener")))
        self._refrescar_filas()

    def _refrescar_filas(self) -> None:
        for fila in getattr(self, "filas", {}).values():
            fila.refrescar()

    # ---- guardar al cambiar ----

    def _guardar_microfono(self) -> None:
        self._ajustes.establecer("audio.dispositivo", self.combo_microfono.currentData() or "")
        self._despues_de_guardar(_REGE_AL_REINICIAR)

    def _guardar_idioma(self) -> None:
        self._ajustes.establecer("idioma.modo", self.combo_idioma.currentData())
        self._despues_de_guardar(_REGE_AL_REINICIAR)

    def _guardar_indicador(self, activo: bool) -> None:
        self._ajustes.establecer("interfaz.indicador", activo)
        self._despues_de_guardar(_REGE_YA)

    def _despues_de_guardar(self, mensaje: str) -> None:
        self._refrescar_filas()
        self.avisar(mensaje)

    # ---- la tecla para dictar ----

    def _empezar_a_elegir(self) -> None:
        self.campo_tecla.show()
        self.campo_tecla.setFocus()

    def _tecla_elegida(self, atajo: str) -> None:
        self.campo_tecla.hide()
        self._cambiar_tecla(atajo)

    def _cambiar_tecla(self, atajo: str) -> bool:
        """Prueba la tecla nueva en la escucha en vivo y recién entonces la guarda."""
        try:
            cambiar_tecla_para_dictar(self._ajustes, self._aplicar_atajos, atajo)
        except (DatoInvalido, *ERRORES_DE_LA_ESCUCHA) as error:
            self.avisar(str(error), error=True)
            self.recargar()
            return False
        self.recargar()
        self.avisar(_REGE_YA)
        return True

    # ---- restablecer ----

    def _restablecer(self, clave: str) -> None:
        if clave == "atajo.mantener":
            self._cambiar_tecla(str(self._ajustes.defecto(clave)))
            return
        self._ajustes.restablecer(clave)
        self.recargar()
        self.avisar(_REGE_YA if clave == "interfaz.indicador" else _REGE_AL_REINICIAR)
