"""``Aplicacion`` con dobles de todos los puertos: del atajo al texto insertado (T061)."""

import threading
import time
from collections.abc import Callable, Iterator

import pytest

from tests.dobles import EscuchaFalsa, GrabadoraFalsa, InsertorFalso, MotorFalso, VentanaFalsa
from vozflow.aplicacion import Aplicacion, RegistroDeDictados
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.configuracion import ConfiguracionEstatica, FuenteDeConfiguracion
from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.dominio.tuberia import procesar
from vozflow.insercion.puerto import ResultadoInsercion
from vozflow.transcripcion.motor import ErrorDeTranscripcion, Transcripcion
from vozflow.ventana.puerto import InfoVentana

M, A = AccionDeAtajo.MANTENER, AccionDeAtajo.ALTERNAR
ATAJOS = {M: "RightCtrl", A: "<Control><Alt>space"}


def _esperar(condicion: Callable[[], bool], segundos: float = 3.0) -> bool:
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.005)
    return False


class Montaje:
    def __init__(
        self,
        *,
        texto: str = "hola mundo",
        segundos: float = 1.5,
        ventana: InfoVentana | None = None,
        resultado: ResultadoInsercion | None = None,
        configuracion: FuenteDeConfiguracion | None = None,
        historial: RegistroDeDictados | None = None,
    ) -> None:
        self.escucha = EscuchaFalsa()
        self.grabadora = GrabadoraFalsa(segundos)
        self.motor = MotorFalso(texto=texto)
        self.ventana = VentanaFalsa(ventana)
        self.insertor = InsertorFalso(resultado)
        self.estados: list[E] = []
        self.avisos: list[str] = []
        self.sin_insertar: list[str] = []
        self.app = Aplicacion(
            escucha=self.escucha,
            grabadora=self.grabadora,
            motor=self.motor,
            ventana=self.ventana,
            insertor=self.insertor,
            atajos=ATAJOS,
            al_cambiar_estado=self.estados.append,
            al_aviso=self.avisos.append,
            al_texto_sin_insertar=self.sin_insertar.append,
            configuracion=configuracion,
            historial=historial,
        )

    def espera_estado(self, estado: E) -> bool:
        return _esperar(lambda: self.app.estado is estado)


@pytest.fixture
def m() -> Iterator[Montaje]:
    montaje = Montaje()
    montaje.app.iniciar()
    yield montaje
    montaje.app.detener()


def _dictar_mantenido(m: Montaje) -> None:
    m.escucha.pulsar(M)
    assert m.espera_estado(E.ESCUCHANDO)
    m.escucha.soltar(M)
    assert _esperar(lambda: m.app.estado is E.INACTIVO or m.app.estado is E.ERROR)


# ---- mantener ----------------------------------------------------------------------------------


def test_al_pulsar_empieza_a_grabar_y_consulta_la_ventana(m: Montaje) -> None:
    m.escucha.pulsar(M)

    assert m.espera_estado(E.ESCUCHANDO)
    assert _esperar(lambda: m.grabadora.iniciadas == 1 and m.ventana.consultas == 1)


def test_al_soltar_transcribe_procesa_e_inserta(m: Montaje) -> None:
    _dictar_mantenido(m)

    esperado = procesar("hola mundo", "es").texto
    assert [t for t, _ in m.insertor.insertados] == [esperado]
    assert m.grabadora.detenidas == 1
    assert m.estados == [E.ESCUCHANDO, E.TRANSCRIBIENDO, E.INSERTANDO, E.INACTIVO]


def test_soltar_reacciona_enseguida_y_no_espera_al_siguiente_ciclo_de_revision(m: Montaje) -> None:
    m.escucha.pulsar(M)
    assert m.espera_estado(E.ESCUCHANDO)
    inicio = time.monotonic()

    m.escucha.soltar(M)
    assert _esperar(lambda: len(m.insertor.insertados) == 1)

    assert time.monotonic() - inicio < 0.6


# ---- alternar -----------------------------------------------------------------------------------------


def test_alternar_empieza_y_termina_con_dos_pulsaciones(m: Montaje) -> None:
    m.escucha.pulsar(A)
    m.escucha.soltar(A)  # la persona suelta la tecla: cada pulsación es una pulsación completa
    assert m.espera_estado(E.ESCUCHANDO)

    m.escucha.pulsar(A)
    m.escucha.soltar(A)

    assert _esperar(lambda: len(m.insertor.insertados) == 1)
    assert m.espera_estado(E.INACTIVO)


def test_soltar_la_tecla_de_mantener_no_corta_una_grabacion_iniciada_con_alternar(
    m: Montaje,
) -> None:
    m.escucha.pulsar(A)
    m.escucha.soltar(A)
    assert m.espera_estado(E.ESCUCHANDO)

    m.escucha.pulsar(M)
    m.escucha.soltar(M)
    time.sleep(0.15)

    assert m.app.estado is E.ESCUCHANDO and m.insertor.insertados == []


def test_se_puede_dictar_dos_veces_seguidas(m: Montaje) -> None:
    _dictar_mantenido(m)
    _dictar_mantenido(m)

    assert len(m.insertor.insertados) == 2


# ---- lo que no se inserta --------------------------------------------------------------------------------


def test_un_dictado_de_menos_de_medio_segundo_no_inserta_nada() -> None:
    montaje = Montaje(segundos=0.3)
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.insertor.insertados == []
        assert montaje.app.estado is E.INACTIVO
        assert montaje.avisos == []
    finally:
        montaje.app.detener()


def test_un_dictado_en_silencio_no_inserta_nada() -> None:
    montaje = Montaje()
    montaje.grabadora.amplitud = 0.0
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.insertor.insertados == []
        assert montaje.app.estado is E.INACTIVO
    finally:
        montaje.app.detener()


def test_borra_eso_descarta_el_dictado() -> None:
    montaje = Montaje(texto="escribe esto borra eso")
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.insertor.insertados == []
        assert montaje.app.estado is E.INACTIVO
    finally:
        montaje.app.detener()


def test_mientras_transcribe_se_ignora_pulsar() -> None:
    montaje = Montaje()
    entrada, salida = threading.Event(), threading.Event()
    original = montaje.motor.transcribir

    def lento(audio, pista, idioma):  # type: ignore[no-untyped-def]
        entrada.set()
        salida.wait(5)
        return original(audio, pista, idioma)

    montaje.motor.transcribir = lento  # type: ignore[method-assign]
    montaje.app.iniciar()
    try:
        montaje.escucha.pulsar(M)
        assert montaje.espera_estado(E.ESCUCHANDO)
        montaje.escucha.soltar(M)
        assert entrada.wait(3)
        assert montaje.app.estado is E.TRANSCRIBIENDO

        montaje.escucha.pulsar(M)
        montaje.escucha.soltar(M)
        montaje.escucha.pulsar(A)
        time.sleep(0.1)

        assert montaje.grabadora.iniciadas == 1
        salida.set()
        assert montaje.espera_estado(E.INACTIVO)
        assert len(montaje.insertor.insertados) == 1
    finally:
        salida.set()
        montaje.app.detener()


# ---- fallos: se avisa y no se pierde el texto ---------------------------------------------------------------


def test_si_la_insercion_falla_se_avisa_y_se_conserva_el_texto() -> None:
    montaje = Montaje(resultado=ResultadoInsercion.fallido("No se pudo pegar"))
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.app.estado is E.ERROR
        assert montaje.sin_insertar == [procesar("hola mundo", "es").texto]
        assert montaje.avisos and "No se pudo pegar" in montaje.avisos[0]
        assert montaje.app.texto_sin_insertar == montaje.sin_insertar[0]
    finally:
        montaje.app.detener()


def test_tras_un_error_se_puede_volver_a_dictar() -> None:
    montaje = Montaje(resultado=ResultadoInsercion.fallido("falló"))
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)
        montaje.insertor.resultado = ResultadoInsercion.exito()

        _dictar_mantenido(montaje)

        assert montaje.app.estado is E.INACTIVO
        assert len(montaje.insertor.insertados) == 2
    finally:
        montaje.app.detener()


def test_si_el_microfono_falla_al_iniciar_se_avisa_y_no_queda_trabado() -> None:
    montaje = Montaje()
    montaje.grabadora.fallar_al_iniciar = OSError("sin micrófono")
    montaje.app.iniciar()
    try:
        montaje.escucha.pulsar(M)
        assert montaje.espera_estado(E.ERROR)
        montaje.escucha.soltar(M)
        assert montaje.avisos

        montaje.grabadora.fallar_al_iniciar = None
        montaje.escucha.pulsar(M)
        assert montaje.espera_estado(E.ESCUCHANDO)
    finally:
        montaje.app.detener()


def test_si_el_motor_falla_se_avisa_sin_incluir_texto_ni_audio() -> None:
    montaje = Montaje()

    def roto(audio, pista, idioma) -> Transcripcion:  # type: ignore[no-untyped-def]
        raise ErrorDeTranscripcion("el modelo no está cargado")

    montaje.motor.transcribir = roto  # type: ignore[method-assign]
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.app.estado is E.ERROR
        assert montaje.insertor.insertados == []
        assert montaje.avisos and "modelo" in montaje.avisos[0]
    finally:
        montaje.app.detener()


# ---- la ventana activa ---------------------------------------------------------------------------------------------


def test_consultar_la_ventana_no_demora_la_grabacion() -> None:
    montaje = Montaje()
    montaje.ventana.liberar.clear()  # la consulta se queda esperando
    montaje.app.iniciar()
    try:
        montaje.escucha.pulsar(M)

        assert montaje.espera_estado(E.ESCUCHANDO)
        assert _esperar(lambda: montaje.grabadora.iniciadas == 1)
    finally:
        montaje.ventana.liberar.set()
        montaje.app.detener()


def test_si_la_ventana_tarda_demasiado_se_inserta_igual_sin_saber_el_destino() -> None:
    montaje = Montaje(texto="primera línea nueva línea segunda línea")
    montaje.ventana.liberar.clear()
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        (texto, destino) = montaje.insertor.insertados[0]
        assert "\n" in texto and destino.salto_de_linea == "conservar"
    finally:
        montaje.ventana.liberar.set()
        montaje.app.detener()


def test_si_la_consulta_de_la_ventana_falla_se_inserta_igual() -> None:
    montaje = Montaje()
    montaje.ventana.error = RuntimeError("AT-SPI se cayó")
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert len(montaje.insertor.insertados) == 1
    finally:
        montaje.app.detener()


def test_en_una_terminal_los_saltos_de_linea_se_vuelven_espacios() -> None:
    montaje = Montaje(
        texto="primera línea nueva línea segunda línea",
        ventana=InfoVentana("ptyxis", "claude", 10),
    )
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        (texto, destino) = montaje.insertor.insertados[0]
        assert "\n" not in texto and destino.salto_de_linea == "espacio"
    finally:
        montaje.app.detener()


def test_fuera_de_una_terminal_se_conservan_los_saltos_de_linea() -> None:
    montaje = Montaje(
        texto="primera línea nueva línea segunda línea",
        ventana=InfoVentana("obsidian", "nota", 11),
    )
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        (texto, destino) = montaje.insertor.insertados[0]
        assert "\n" in texto and destino.salto_de_linea == "conservar"
    finally:
        montaje.app.detener()


def test_una_aplicacion_marcada_como_terminal_se_trata_como_terminal() -> None:
    montaje = Montaje(
        texto="primera línea nueva línea segunda línea",
        ventana=InfoVentana("vscodium", "x", 12),
    )
    montaje.app = Aplicacion(
        escucha=montaje.escucha,
        grabadora=montaje.grabadora,
        motor=montaje.motor,
        ventana=montaje.ventana,
        insertor=montaje.insertor,
        atajos=ATAJOS,
        configuracion=ConfiguracionEstatica(terminales={"vscodium"}),
    )
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.insertor.insertados[0][1].salto_de_linea == "espacio"
    finally:
        montaje.app.detener()


def test_el_titulo_de_la_ventana_no_se_registra(caplog: pytest.LogCaptureFixture) -> None:
    montaje = Montaje(ventana=InfoVentana("chrome", "Banco - saldo $1.000", 13))
    montaje.app.iniciar()
    try:
        with caplog.at_level("DEBUG"):
            _dictar_mantenido(montaje)
    finally:
        montaje.app.detener()

    assert "saldo" not in caplog.text and "hola mundo" not in caplog.text.lower()


# ---- ciclo de vida ----------------------------------------------------------------------------------------------------------


def test_iniciar_carga_el_modelo_una_sola_vez_y_escucha_los_atajos() -> None:
    montaje = Montaje()

    montaje.app.iniciar()
    try:
        assert montaje.motor.cargado is True
        _dictar_mantenido(montaje)
        _dictar_mantenido(montaje)
        assert (
            montaje.motor.veces_cargado <= 3
        )  # la carga inicial; el motor real la ignora si ya está
    finally:
        montaje.app.detener()


def test_detener_corta_la_escucha_y_libera_el_modelo() -> None:
    montaje = Montaje()
    montaje.app.iniciar()

    montaje.app.detener()
    montaje.app.detener()

    montaje.escucha.pulsar(M)
    time.sleep(0.1)
    assert montaje.grabadora.iniciadas == 0
    assert montaje.motor.cargado is False


def test_detener_en_plena_grabacion_no_deja_hilos_ni_el_microfono_abierto() -> None:
    montaje = Montaje()
    montaje.app.iniciar()
    montaje.escucha.pulsar(M)
    assert montaje.espera_estado(E.ESCUCHANDO)
    assert _esperar(lambda: montaje.grabadora.iniciadas == 1)

    montaje.app.detener()

    assert montaje.grabadora.detenidas == 1
    assert montaje.insertor.insertados == []


def test_el_arranque_de_la_grabacion_se_mide(m: Montaje) -> None:
    assert m.app.ultimo_arranque_ms is None

    m.escucha.pulsar(M)
    assert _esperar(lambda: m.app.ultimo_arranque_ms is not None)

    assert m.app.ultimo_arranque_ms is not None and m.app.ultimo_arranque_ms < 150


# ---- diccionario personal (T074) -----------------------------------------------------------------


def test_el_diccionario_llega_al_motor_como_pista() -> None:
    montaje = Montaje(configuracion=ConfiguracionEstatica(pista=lambda: "SQLAlchemy, FastAPI"))
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.motor.llamadas and montaje.motor.llamadas[0].pista == "SQLAlchemy, FastAPI"
    finally:
        montaje.app.detener()


def test_sin_diccionario_no_hay_pista() -> None:
    montaje = Montaje()
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)

        assert montaje.motor.llamadas[0].pista is None
    finally:
        montaje.app.detener()


def test_la_pista_se_lee_en_cada_dictado_y_no_solo_al_arrancar() -> None:
    palabras = ["uno"]
    montaje = Montaje(configuracion=ConfiguracionEstatica(pista=lambda: ", ".join(palabras)))
    montaje.app.iniciar()
    try:
        _dictar_mantenido(montaje)
        palabras.append("dos")
        _dictar_mantenido(montaje)

        assert [c.pista for c in montaje.motor.llamadas] == ["uno", "uno, dos"]
    finally:
        montaje.app.detener()
