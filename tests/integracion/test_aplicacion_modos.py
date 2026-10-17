"""Los modos por aplicación, el diccionario y los atajos de texto, con la base real (T083)."""

from tests.integracion.test_aplicacion import Montaje, _dictar_mantenido
from vozflow.configuracion import ConfiguracionDeBase
from vozflow.insercion.puerto import AtajoDePegado
from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.modos_repo import ModosRepo
from vozflow.ventana.puerto import InfoVentana

DICTADO = "primera línea nueva línea segunda línea"


class Entorno:
    def __init__(self, aplicacion: str | None, texto: str = DICTADO) -> None:
        self.base = abrir_base(":memory:")
        self.modos = ModosRepo(self.base)
        self.asignaciones = AsignacionesRepo(self.base)
        self.diccionario = DiccionarioRepo(self.base)
        self.atajos = AtajosTextoRepo(self.base)
        ventana = InfoVentana(aplicacion, "titulo", 7) if aplicacion else None
        self.montaje = Montaje(
            texto=texto, ventana=ventana, configuracion=ConfiguracionDeBase(self.base)
        )

    def dictar(self) -> tuple[str, AtajoDePegado, str]:
        _dictar_mantenido(self.montaje)
        texto, destino = self.montaje.insertor.insertados[-1]
        return texto, destino.atajo, destino.salto_de_linea


def _arrancar(entorno: Entorno) -> Entorno:
    entorno.montaje.app.iniciar()
    return entorno


def test_la_aplicacion_asignada_a_terminal_sale_en_una_linea_y_con_ctrl_shift_v() -> None:
    entorno = _arrancar(Entorno("ptyxis"))
    try:
        terminal = entorno.modos.obtener("Terminal")
        assert terminal is not None
        entorno.asignaciones.asignar("ptyxis", terminal.id)

        texto, atajo, salto = entorno.dictar()

        assert "\n" not in texto and "línea segunda" in texto
        assert (atajo, salto) == (AtajoDePegado.CTRL_SHIFT_V, "espacio")
    finally:
        entorno.montaje.app.detener()


def test_una_aplicacion_sin_asignacion_usa_el_modo_general() -> None:
    entorno = _arrancar(Entorno("obsidian"))
    try:
        texto, atajo, salto = entorno.dictar()

        assert "\n" in texto
        assert (atajo, salto) == (AtajoDePegado.SHIFT_INSERT, "conservar")
    finally:
        entorno.montaje.app.detener()


def test_una_terminal_conocida_sin_asignar_tambien_sale_en_una_linea() -> None:
    entorno = _arrancar(Entorno("ptyxis"))
    try:
        texto, atajo, _ = entorno.dictar()

        assert "\n" not in texto and atajo is AtajoDePegado.CTRL_SHIFT_V
    finally:
        entorno.montaje.app.detener()


def test_las_banderas_del_modo_cambian_el_texto() -> None:
    entorno = _arrancar(Entorno("code", texto="hola mundo"))
    try:
        general, _, _ = entorno.dictar()
        codigo = entorno.modos.obtener("Código")
        assert codigo is not None
        entorno.asignaciones.asignar("code", codigo.id)

        en_codigo, _, _ = entorno.dictar()

        assert general == "Hola mundo."
        assert en_codigo == "hola mundo"  # el modo Código no puntúa ni capitaliza solo
    finally:
        entorno.montaje.app.detener()


def test_un_cambio_de_asignacion_rige_en_el_siguiente_dictado_sin_reiniciar() -> None:
    entorno = _arrancar(Entorno("obsidian"))
    try:
        antes, _, _ = entorno.dictar()
        terminal = entorno.modos.obtener("Terminal")
        assert terminal is not None
        entorno.asignaciones.asignar("obsidian", terminal.id)

        despues, _, _ = entorno.dictar()

        assert "\n" in antes and "\n" not in despues
    finally:
        entorno.montaje.app.detener()


def test_los_atajos_de_texto_de_la_base_se_expanden() -> None:
    entorno = _arrancar(Entorno("obsidian", texto="gracias coma mi firma"))
    try:
        entorno.atajos.agregar("mi firma", "Pedro Freimeyer")

        texto, _, _ = entorno.dictar()

        assert texto == "Gracias, Pedro Freimeyer"
    finally:
        entorno.montaje.app.detener()


def test_un_atajo_de_texto_de_varias_lineas_en_una_terminal_sale_en_una_sola() -> None:
    entorno = _arrancar(Entorno("ptyxis", texto="mi firma"))
    try:
        entorno.atajos.agregar("mi firma", "Saludos,\nPedro")

        texto, _, _ = entorno.dictar()

        assert texto == "Saludos, Pedro"
    finally:
        entorno.montaje.app.detener()


def test_el_diccionario_de_la_base_llega_al_motor() -> None:
    entorno = _arrancar(Entorno("obsidian"))
    try:
        entorno.diccionario.agregar("SQLAlchemy")
        entorno.diccionario.agregar("FastAPI")

        entorno.dictar()

        assert entorno.montaje.motor.llamadas[0].pista == "SQLAlchemy, FastAPI"
    finally:
        entorno.montaje.app.detener()


def test_sin_saber_la_ventana_se_usa_el_modo_general() -> None:
    entorno = _arrancar(Entorno(None))
    try:
        texto, atajo, salto = entorno.dictar()

        assert "\n" in texto and (atajo, salto) == (AtajoDePegado.SHIFT_INSERT, "conservar")
    finally:
        entorno.montaje.app.detener()
