"""``python -m vozflow dictar``: graba, transcribe y muestra el texto ya limpio."""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pytest

from tests.dobles import MotorFalso
from vozflow.__main__ import (
    CODIGO_ERROR,
    CODIGO_OK,
    CODIGO_SIN_VOZ,
    Dependencias,
    main,
)
from vozflow.audio.captura import ErrorDeAudio
from vozflow.audio.senal import FRECUENCIA
from vozflow.transcripcion.motor import ErrorDeTranscripcion


def _voz(segundos: float) -> np.ndarray:
    t = np.arange(int(segundos * FRECUENCIA)) / FRECUENCIA
    return (6000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)


def _silencio(segundos: float) -> np.ndarray:
    return np.zeros(int(segundos * FRECUENCIA), dtype=np.int16)


@dataclass
class GrabadoraFalsa:
    """Reproduce un audio grabado a medida que pasa el tiempo (el reloj es ``avanzar``)."""

    audio: np.ndarray = field(default_factory=lambda: _voz(3.0))
    falla_al_iniciar: ErrorDeAudio | None = None
    eventos: list[str] = field(default_factory=list)
    dispositivo: str | int | None = None
    _segundos: float = 0.0

    def iniciar(self, dispositivo: str | int | None = None) -> None:
        self.eventos.append("iniciar")
        self.dispositivo = dispositivo
        if self.falla_al_iniciar is not None:
            raise self.falla_al_iniciar

    def avanzar(self, segundos: float) -> None:
        self._segundos += segundos

    def audio_acumulado(self) -> np.ndarray:
        return self.audio[: int(self._segundos * FRECUENCIA)]

    def detener_crudo(self) -> np.ndarray:
        self.eventos.append("detener")
        return self.audio


class MotorQueAvisa(MotorFalso):
    def __init__(self, eventos: list[str]) -> None:
        super().__init__()
        self._eventos = eventos

    def cargar(self) -> None:
        self._eventos.append("cargar")
        super().cargar()


def _dependencias(
    grabadora: GrabadoraFalsa,
    motor: MotorFalso,
    esperas: list[float] | None = None,
) -> Dependencias:
    def esperar(segundos: float) -> None:
        if esperas is not None:
            esperas.append(segundos)
        grabadora.avanzar(segundos)

    return Dependencias(
        crear_grabadora=lambda: grabadora,
        crear_motor=lambda modelo: motor,
        esperar=esperar,
        descargar_modelo=lambda modelo: f"/modelos/{modelo}",
    )


# ---- camino feliz ----------------------


def test_imprime_el_texto_procesado_por_la_tuberia(capsys: pytest.CaptureFixture[str]) -> None:
    motor = MotorFalso(texto="eh, o sea, tengo que, tengo que hacer el deploy del branch nuevo")

    codigo = main(["dictar", "--segundos", "3"], _dependencias(GrabadoraFalsa(), motor))

    salida = capsys.readouterr()
    assert codigo == CODIGO_OK
    assert salida.out == "Tengo que hacer el deploy del branch nuevo.\n"


def test_el_texto_va_a_la_salida_y_los_avisos_al_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(["dictar", "--segundos", "3"], _dependencias(GrabadoraFalsa(), MotorFalso("hola mundo")))

    salida = capsys.readouterr()
    assert salida.out == "Hola mundo.\n"
    assert "Grabando" in salida.err


def test_graba_exactamente_los_segundos_pedidos() -> None:
    esperas: list[float] = []

    main(
        ["dictar", "--segundos", "10"],
        _dependencias(GrabadoraFalsa(_voz(10.0)), MotorFalso(), esperas),
    )

    assert sum(esperas) == pytest.approx(10.0)
    assert max(esperas) <= 1.0  # revisa el audio cada segundo para transcribir por tramos


def test_carga_el_motor_antes_de_empezar_a_grabar() -> None:
    eventos: list[str] = []
    grabadora = GrabadoraFalsa(eventos=eventos)
    motor = MotorQueAvisa(eventos)

    main(["dictar", "--segundos", "2"], _dependencias(grabadora, motor))

    assert eventos[:2] == ["cargar", "iniciar"]
    assert eventos[-1] == "detener"


def test_pasa_el_dispositivo_el_idioma_y_el_modelo() -> None:
    grabadora = GrabadoraFalsa()
    motor = MotorFalso()
    modelos: list[str] = []
    dependencias = _dependencias(grabadora, motor)

    def crear_motor(modelo: str) -> MotorFalso:
        modelos.append(modelo)
        return motor

    dependencias.crear_motor = crear_motor

    main(
        [
            "dictar",
            "--segundos",
            "2",
            "--dispositivo",
            "Micrófono USB",
            "--idioma",
            "en",
            "--modelo",
            "base",
        ],
        dependencias,
    )

    assert grabadora.dispositivo == "Micrófono USB"
    assert motor.llamadas[0].idioma == "en"
    assert modelos == ["base"]


def test_un_dispositivo_numerico_se_pasa_como_numero() -> None:
    grabadora = GrabadoraFalsa()

    main(
        ["dictar", "--segundos", "2", "--dispositivo", "12"], _dependencias(grabadora, MotorFalso())
    )

    assert grabadora.dispositivo == 12


def test_transcribe_los_tramos_cerrados_mientras_graba() -> None:
    audio = np.concatenate([_voz(2.0), _silencio(1.0), _voz(2.0)])
    motor = MotorFalso()

    main(["dictar", "--segundos", "5"], _dependencias(GrabadoraFalsa(audio), motor))

    assert len(motor.llamadas) == 2  # un tramo cerrado por el silencio, y el último


def test_las_banderas_apagan_pasos_de_la_tuberia(capsys: pytest.CaptureFixture[str]) -> None:
    motor = MotorFalso("eh hola mundo")

    main(
        ["dictar", "--segundos", "2", "--sin-limpieza", "--sin-puntuacion", "--sin-comandos"],
        _dependencias(GrabadoraFalsa(), motor),
    )

    assert capsys.readouterr().out == "eh hola mundo\n"


def test_detalle_muestra_el_texto_crudo_y_los_tiempos_en_el_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main(
        ["dictar", "--segundos", "2", "--detalle"],
        _dependencias(GrabadoraFalsa(), MotorFalso("eh hola")),
    )

    salida = capsys.readouterr()
    assert salida.out == "Hola\n"  # una sola palabra tras la limpieza: sin punto final
    assert "eh hola" in salida.err
    assert "idioma" in salida.err.lower()


# ---- errores ----------------------


def test_sin_microfono_sale_con_error_y_un_mensaje_claro(
    capsys: pytest.CaptureFixture[str],
) -> None:
    grabadora = GrabadoraFalsa(
        falla_al_iniciar=ErrorDeAudio("No se pudo abrir el micrófono: sin dispositivo")
    )

    codigo = main(["dictar", "--segundos", "2"], _dependencias(grabadora, MotorFalso()))

    salida = capsys.readouterr()
    assert codigo == CODIGO_ERROR
    assert "micrófono" in salida.err
    assert salida.out == ""


def test_modelo_sin_descargar_sale_con_error_y_dice_como_arreglarlo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class MotorSinModelo(MotorFalso):
        def cargar(self) -> None:
            raise ErrorDeTranscripcion("El modelo 'small' no está descargado. Descargalo con: ...")

    grabadora = GrabadoraFalsa()

    codigo = main(["dictar", "--segundos", "2"], _dependencias(grabadora, MotorSinModelo()))

    salida = capsys.readouterr()
    assert codigo == CODIGO_ERROR
    assert "descargado" in salida.err
    assert salida.out == ""
    assert "iniciar" not in grabadora.eventos  # ni siquiera empieza a grabar


def test_un_error_del_motor_a_mitad_de_la_grabacion_detiene_el_microfono(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class MotorQueFalla(MotorFalso):
        def transcribir(self, audio, pista, idioma):  # type: ignore[no-untyped-def]
            raise ErrorDeTranscripcion("falló la transcripción")

    grabadora = GrabadoraFalsa()

    codigo = main(["dictar", "--segundos", "2"], _dependencias(grabadora, MotorQueFalla()))

    assert codigo == CODIGO_ERROR
    assert "falló" in capsys.readouterr().err
    assert "detener" in grabadora.eventos  # el micrófono no queda abierto


def test_sin_voz_avisa_y_no_imprime_nada(capsys: pytest.CaptureFixture[str]) -> None:
    motor = MotorFalso()

    codigo = main(
        ["dictar", "--segundos", "2"], _dependencias(GrabadoraFalsa(_silencio(3.0)), motor)
    )

    salida = capsys.readouterr()
    assert codigo == CODIGO_SIN_VOZ
    assert salida.out == ""
    assert "No se detectó voz" in salida.err
    assert motor.llamadas == []


def test_dictar_con_cero_segundos_o_negativos_se_rechaza() -> None:
    for segundos in ("0", "-3"):
        with pytest.raises(SystemExit) as salida:
            main(["dictar", "--segundos", segundos], _dependencias(GrabadoraFalsa(), MotorFalso()))
        assert salida.value.code == 2


def test_sin_subcomando_muestra_la_ayuda() -> None:
    with pytest.raises(SystemExit) as salida:
        main([], _dependencias(GrabadoraFalsa(), MotorFalso()))

    assert salida.value.code == 2


# ---- descargar-modelo ----------------------


def test_descargar_modelo_muestra_donde_quedo(capsys: pytest.CaptureFixture[str]) -> None:
    codigo = main(["descargar-modelo"], _dependencias(GrabadoraFalsa(), MotorFalso()))

    assert codigo == CODIGO_OK
    assert "/modelos/small" in capsys.readouterr().out


def test_descargar_modelo_informa_si_falla(capsys: pytest.CaptureFixture[str]) -> None:
    dependencias = _dependencias(GrabadoraFalsa(), MotorFalso())

    def sin_red(modelo: str) -> str:
        raise ErrorDeTranscripcion("No se pudo descargar el modelo: sin conexión")

    dependencias.descargar_modelo = sin_red

    codigo = main(["descargar-modelo", "--modelo", "base"], dependencias)

    assert codigo == CODIGO_ERROR
    assert "sin conexión" in capsys.readouterr().err


# ---- medir -------------------------------------------------------------------------------


class _Respuestas:
    def __init__(self, respuestas: list[str]) -> None:
        self._respuestas = iter(respuestas)
        self.preguntas: list[str] = []

    def __call__(self, pregunta: str) -> str:
        self.preguntas.append(pregunta)
        return next(self._respuestas)


def _dependencias_de_medicion(
    grabadora: GrabadoraFalsa, motor: MotorFalso, respuestas: _Respuestas, salida: list[str]
) -> Dependencias:
    dependencias = _dependencias(grabadora, motor)
    dependencias.entrada = respuestas
    dependencias.salida = salida.append
    return dependencias


def test_medir_recorre_las_frases_pedidas_y_guarda_todo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    salida: list[str] = []
    respuestas = _Respuestas(["", "", "s", "", "", "s"])

    codigo = main(
        ["medir", "--cantidad", "2"],
        _dependencias_de_medicion(GrabadoraFalsa(), MotorFalso("hola mundo"), respuestas, salida),
    )

    assert codigo == CODIGO_OK
    assert any("Frase 2/2" in linea for linea in salida)
    assert any("CE-002" in linea for linea in salida)
    carpetas = list((tmp_path / "vozflow" / "pruebas").glob("medicion-*"))
    assert len(carpetas) == 1
    assert (carpetas[0] / "frase-02.wav").is_file()


@pytest.mark.parametrize("cantidad", ["0", "21", "-1"])
def test_medir_rechaza_una_cantidad_fuera_de_rango(cantidad: str) -> None:
    with pytest.raises(SystemExit) as salida:
        main(
            ["medir", "--cantidad", cantidad],
            _dependencias_de_medicion(GrabadoraFalsa(), MotorFalso(), _Respuestas([]), []),
        )
    assert salida.value.code == 2


def test_medir_carga_el_modelo_antes_de_hacer_la_primera_pregunta(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))

    class MotorSinModelo(MotorFalso):
        def cargar(self) -> None:
            raise ErrorDeTranscripcion("El modelo 'small' no está descargado. Descargalo con: ...")

    respuestas = _Respuestas([])

    codigo = main(
        ["medir", "--cantidad", "1"],
        _dependencias_de_medicion(GrabadoraFalsa(), MotorSinModelo(), respuestas, []),
    )

    assert codigo == CODIGO_ERROR
    assert respuestas.preguntas == []  # no se le pidió a Pedro que leyera nada
    assert "descargado" in capsys.readouterr().err


def test_medir_sin_microfono_sale_con_error(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    grabadora = GrabadoraFalsa(falla_al_iniciar=ErrorDeAudio("No se pudo abrir el micrófono"))

    codigo = main(
        ["medir", "--cantidad", "1"],
        _dependencias_de_medicion(grabadora, MotorFalso(), _Respuestas(["", ""]), []),
    )

    assert codigo == CODIGO_ERROR
    assert "micrófono" in capsys.readouterr().err
