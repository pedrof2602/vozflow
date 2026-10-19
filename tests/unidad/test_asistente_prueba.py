"""Paso de prueba del asistente: dictar una frase y ver el texto ahí mismo, sin pegar (002)."""

import os
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from vozflow.audio.captura import ErrorDeAudio
from vozflow.mensajes import explicar
from vozflow.ui.asistente.prueba import PasoPrueba

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class ProbadorFalso:
    """Respuestas inmediatas y guiadas: cada método registra la llamada y contesta lo configurado."""

    def __init__(self, descargado: bool = True) -> None:
        self.descargado = descargado
        self.llamadas: list[str] = []
        self.texto = "hola, esto es una prueba"
        self.falla_al_preparar: str | None = None
        self.falla_al_descargar: str | None = None
        self.falla_al_empezar: Exception | None = None
        self.falla_al_terminar: str | None = None
        self.avances: list[tuple[int, int]] = [(0, 480), (480, 480)]
        self.preparar_ya = True  # contesta enseguida; si es falso, el listo queda pendiente
        self.pendiente: Callable[[], None] | None = None

    def modelo_descargado(self) -> bool:
        return self.descargado

    def descargar_modelo(
        self,
        al_avance: Callable[[int, int], None],
        al_listo: Callable[[], None],
        al_error: Callable[[str], None],
    ) -> None:
        self.llamadas.append("descargar")
        if self.falla_al_descargar:
            al_error(self.falla_al_descargar)
            return
        for hechos, total in self.avances:
            al_avance(hechos, total)
        self.descargado = True
        al_listo()

    def preparar(self, al_listo: Callable[[], None], al_error: Callable[[str], None]) -> None:
        self.llamadas.append("preparar")
        if self.falla_al_preparar:
            al_error(self.falla_al_preparar)
        elif self.preparar_ya:
            al_listo()
        else:
            self.pendiente = al_listo

    def empezar(self) -> None:
        self.llamadas.append("empezar")
        if self.falla_al_empezar is not None:
            raise self.falla_al_empezar

    def terminar(
        self, al_resultado: Callable[[str], None], al_error: Callable[[str], None]
    ) -> None:
        self.llamadas.append("terminar")
        if self.falla_al_terminar:
            al_error(self.falla_al_terminar)
        else:
            al_resultado(self.texto)

    def cancelar(self) -> None:
        self.llamadas.append("cancelar")


def _paso(qtbot: QtBot, probador: ProbadorFalso | None = None) -> tuple[PasoPrueba, ProbadorFalso]:
    probador = probador or ProbadorFalso()
    paso = PasoPrueba(probador)
    qtbot.addWidget(paso)
    paso.al_entrar()
    paso.show()
    return paso, probador


def _textos(paso: PasoPrueba) -> str:
    return " ".join(e.text() for e in paso.findChildren(QLabel))


def test_al_entrar_prepara_el_modelo_y_habilita_grabar(qtbot: QtBot) -> None:
    paso, probador = _paso(qtbot)

    assert probador.llamadas == ["preparar"]
    assert paso.boton_grabar.isEnabled() is True


def test_mientras_el_modelo_carga_dice_preparando_y_no_deja_grabar(qtbot: QtBot) -> None:
    probador = ProbadorFalso()
    probador.preparar_ya = False

    paso, _ = _paso(qtbot, probador)

    assert "preparando" in _textos(paso).lower() and paso.boton_grabar.isEnabled() is False
    assert probador.pendiente is not None
    probador.pendiente()
    assert paso.boton_grabar.isEnabled() is True


def test_grabar_y_terminar_muestra_el_texto_dentro_del_asistente(qtbot: QtBot) -> None:
    paso, probador = _paso(qtbot)

    paso.boton_grabar.click()
    assert paso.boton_grabar.text() == "Listo, terminé"
    paso.boton_grabar.click()

    assert probador.llamadas == ["preparar", "empezar", "terminar"]
    assert paso.texto() == "hola, esto es una prueba"
    assert paso.boton_grabar.text() == "Probar de nuevo"


def test_el_paso_no_tiene_forma_de_pegar_en_otra_ventana() -> None:
    import inspect

    parametros = inspect.signature(PasoPrueba.__init__).parameters

    assert list(parametros) == ["self", "probador"]  # sin insertor, ventana ni historial


def test_el_texto_se_muestra_tal_cual_y_no_como_html(qtbot: QtBot) -> None:
    probador = ProbadorFalso()
    probador.texto = "<b>hola</b> <img src=x>"

    paso, _ = _paso(qtbot, probador)
    paso.boton_grabar.click()
    paso.boton_grabar.click()

    assert paso.texto() == "<b>hola</b> <img src=x>"
    assert paso.etiqueta_resultado.textFormat() == Qt.TextFormat.PlainText


def test_si_no_se_entendio_nada_lo_dice_y_deja_probar_otra_vez(qtbot: QtBot) -> None:
    probador = ProbadorFalso()
    probador.texto = ""
    paso, _ = _paso(qtbot, probador)

    paso.boton_grabar.click()
    paso.boton_grabar.click()

    assert "no te escuché" in _textos(paso).lower()
    assert paso.boton_grabar.text() == "Probar de nuevo" and paso.boton_grabar.isEnabled()


def test_un_error_del_microfono_se_explica_en_palabras_llanas(qtbot: QtBot) -> None:
    probador = ProbadorFalso()
    probador.falla_al_empezar = ErrorDeAudio("detalle técnico", "microfono_ocupado")
    paso, _ = _paso(qtbot, probador)

    paso.boton_grabar.click()

    assert explicar("microfono_ocupado").que_paso in _textos(paso)
    assert "detalle técnico" not in _textos(paso)
    assert paso.boton_grabar.text() == "Grabar"


def test_un_error_al_entender_lo_dice_sin_tecnicismos(qtbot: QtBot) -> None:
    probador = ProbadorFalso()
    probador.falla_al_terminar = "traceback feo"
    paso, _ = _paso(qtbot, probador)

    paso.boton_grabar.click()
    paso.boton_grabar.click()

    assert explicar("generico").que_paso in _textos(paso)
    assert "traceback" not in _textos(paso)


def test_el_paso_siempre_deja_avanzar_aunque_la_prueba_no_salga(qtbot: QtBot) -> None:
    paso, _ = _paso(qtbot)

    assert paso.puede_avanzar() is True


def test_al_salir_en_medio_de_una_grabacion_la_cancela(qtbot: QtBot) -> None:
    paso, probador = _paso(qtbot)
    paso.boton_grabar.click()

    paso.al_salir()

    assert probador.llamadas[-1] == "cancelar"


def test_al_salir_sin_grabar_no_cancela_nada(qtbot: QtBot) -> None:
    paso, probador = _paso(qtbot)

    paso.al_salir()

    assert "cancelar" not in probador.llamadas


# ---- el modelo no está -----------------------------------------------------------------------------------------


def test_sin_modelo_ofrece_descargarlo_y_no_deja_grabar(qtbot: QtBot) -> None:
    paso, probador = _paso(qtbot, ProbadorFalso(descargado=False))

    assert explicar("modelo_faltante").que_paso in _textos(paso)
    assert paso.boton_descargar.isHidden() is False and paso.boton_grabar.isEnabled() is False
    assert probador.llamadas == []  # no se intenta cargar lo que no está


def test_descargar_muestra_la_barra_y_despues_prepara_el_modelo(qtbot: QtBot) -> None:
    paso, probador = _paso(qtbot, ProbadorFalso(descargado=False))

    paso.boton_descargar.click()

    assert "100 %" in paso.texto_de_progreso()
    assert probador.llamadas == ["descargar", "preparar"]
    assert paso.boton_grabar.isEnabled() is True and paso.boton_descargar.isHidden() is True


def test_si_la_descarga_falla_lo_explica_y_deja_reintentar(qtbot: QtBot) -> None:
    probador = ProbadorFalso(descargado=False)
    probador.falla_al_descargar = "sin conexión"
    paso, _ = _paso(qtbot, probador)

    paso.boton_descargar.click()

    assert "internet" in _textos(paso).lower()
    assert paso.boton_descargar.isHidden() is False and paso.boton_grabar.isEnabled() is False


def test_si_no_se_puede_preparar_el_modelo_deja_reintentar(qtbot: QtBot) -> None:
    probador = ProbadorFalso()
    probador.falla_al_preparar = "no cargó"
    paso, _ = _paso(qtbot, probador)

    assert explicar("generico").que_paso in _textos(paso)
    assert paso.boton_reintentar.isHidden() is False and paso.boton_grabar.isEnabled() is False

    probador.falla_al_preparar = None
    paso.boton_reintentar.click()

    assert paso.boton_grabar.isEnabled() is True


def test_el_titulo_y_la_ayuda_del_paso(qtbot: QtBot) -> None:
    paso, _ = _paso(qtbot)

    assert PasoPrueba.TITULO == "Probá tu voz"
    assert "frase" in _textos(paso).lower()
