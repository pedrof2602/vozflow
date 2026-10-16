"""Medición con voz real de CE-002, CE-003 y CE-004 (``python -m vozflow medir``)."""

import json
import wave
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from tests.dobles import MotorFalso
from vozflow.audio.senal import FRECUENCIA
from vozflow.medicion import (
    FRASES_DE_PRUEBA,
    FraseDePrueba,
    Medicion,
    contar_muletillas_visibles,
    ejecutar_medicion,
    escribir_wav,
    formatear_resumen,
    leer_fuente_de_energia,
    percentil,
    resumir_mediciones,
)

# ---- las 20 frases ----------------------


def test_son_20_frases_numeradas_con_la_proporcion_de_la_spec() -> None:
    assert [f.numero for f in FRASES_DE_PRUEBA] == list(range(1, 21))
    tipos = [f.tipo for f in FRASES_DE_PRUEBA]
    assert (tipos.count("es"), tipos.count("en"), tipos.count("mixta")) == (10, 5, 5)


def test_cada_frase_declara_el_idioma_que_se_espera_detectar() -> None:
    for frase in FRASES_DE_PRUEBA:
        assert frase.idioma_esperado == ("en" if frase.tipo == "en" else "es")


def test_varias_frases_traen_muletillas_o_repeticiones_para_poner_a_prueba_la_limpieza() -> None:
    con_muletillas = [f for f in FRASES_DE_PRUEBA if contar_muletillas_visibles(f.texto) > 0]

    assert len(con_muletillas) >= 8


def test_ninguna_frase_esta_repetida() -> None:
    textos = [f.texto for f in FRASES_DE_PRUEBA]
    assert len(set(textos)) == len(textos)


# ---- percentiles y resumen ----------------------


def test_percentil_por_rango_mas_cercano() -> None:
    valores = list(range(1, 21))

    assert percentil(valores, 0.95) == 19
    assert percentil(valores, 1.0) == 20
    assert percentil([7], 0.95) == 7
    assert percentil([5, 1, 3], 0.5) == 3


def _medicion(
    numero: int,
    espera_ms: int = 3000,
    sin_correccion: bool | None = True,
    muletillas: int = 0,
    esperado: str = "es",
    detectado: str = "es",
) -> Medicion:
    return Medicion(
        numero=numero,
        tipo="es",
        idioma_esperado=esperado,
        frase="x",
        idioma_detectado=detectado,
        texto_crudo="x",
        texto_final="x",
        espera_ms=espera_ms,
        segundos_grabados=4.0,
        no_voz_probabilidad=0.1,
        logprob_medio=-0.3,
        muletillas_restantes=muletillas,
        sin_correccion=sin_correccion,
    )


def _veinte(**cambios: object) -> list[Medicion]:
    return [_medicion(n, **cambios) for n in range(1, 21)]  # type: ignore[arg-type]


def test_resumen_de_latencias() -> None:
    mediciones = [_medicion(n, espera_ms=n * 100) for n in range(1, 21)]

    resumen = resumir_mediciones(mediciones, "corriente")

    assert resumen.latencia_min_ms == 100
    assert resumen.latencia_mediana_ms == 1050
    assert resumen.latencia_p95_ms == 1900
    assert resumen.latencia_max_ms == 2000
    assert resumen.fuente_de_energia == "corriente"


def test_porcentaje_sin_correccion_y_veredictos_cuando_todo_va_bien() -> None:
    resumen = resumir_mediciones(_veinte(), "corriente")

    assert resumen.porcentaje_sin_correccion == pytest.approx(100.0)
    assert resumen.cumple_ce002 is True
    assert resumen.cumple_ce003 is True
    assert resumen.cumple_ce004 is True


def test_ce003_pide_al_menos_18_de_20() -> None:
    justo = [_medicion(n, sin_correccion=n > 2) for n in range(1, 21)]  # 18 de 20
    corto = [_medicion(n, sin_correccion=n > 3) for n in range(1, 21)]  # 17 de 20

    assert resumir_mediciones(justo, "corriente").cumple_ce003 is True
    assert resumir_mediciones(corto, "corriente").cumple_ce003 is False


def test_ce002_falla_si_el_p95_llega_a_5_segundos() -> None:
    lentas = [_medicion(n, espera_ms=5000 if n >= 19 else 3000) for n in range(1, 21)]

    resumen = resumir_mediciones(lentas, "bateria")

    assert resumen.latencia_p95_ms == 5000
    assert resumen.cumple_ce002 is False


def test_ce004_falla_con_una_sola_muletilla_restante() -> None:
    mediciones = [_medicion(n, muletillas=1 if n == 7 else 0) for n in range(1, 21)]

    resumen = resumir_mediciones(mediciones, "corriente")

    assert resumen.muletillas_restantes == 1
    assert resumen.cumple_ce004 is False


def test_si_faltan_evaluaciones_de_pedro_ce003_queda_sin_veredicto() -> None:
    mediciones = [_medicion(n, sin_correccion=None if n > 10 else True) for n in range(1, 21)]

    resumen = resumir_mediciones(mediciones, "corriente")

    assert resumen.evaluadas == 10
    assert resumen.cumple_ce003 is None


def test_aciertos_de_idioma() -> None:
    mediciones = [_medicion(n, detectado="es" if n != 3 else "en") for n in range(1, 21)]

    assert resumir_mediciones(mediciones, "corriente").aciertos_de_idioma == 19


def test_un_resumen_sin_mediciones_no_falla() -> None:
    resumen = resumir_mediciones([], "desconocida")

    assert resumen.cantidad == 0
    assert resumen.latencia_mediana_ms == 0
    assert resumen.cumple_ce002 is None


def test_el_resumen_en_texto_nombra_los_criterios_y_la_fuente_de_energia() -> None:
    texto = formatear_resumen(resumir_mediciones(_veinte(), "batería"))

    for esperado in ("CE-002", "CE-003", "CE-004", "batería", "p95", "100"):
        assert esperado in texto


# ---- muletillas visibles ----------------------


@pytest.mark.parametrize(
    ("texto", "cantidad"),
    [
        ("eh hola", 1),
        ("Hola, o sea, eh", 2),
        ("um, I think, uh, so", 2),
        ("mmm no sé", 1),
        ("EH", 1),
        ("este archivo es nuevo", 0),
        ("el umbral es alto", 0),
        ("bueno, vamos", 0),
        ("", 0),
    ],
)
def test_cuenta_solo_las_muletillas_inequivocas(texto: str, cantidad: int) -> None:
    assert contar_muletillas_visibles(texto) == cantidad


# ---- fuente de energía ----------------------


def _fuente(raiz: Path, nombre: str, **archivos: str) -> None:
    carpeta = raiz / nombre
    carpeta.mkdir()
    for archivo, contenido in archivos.items():
        (carpeta / archivo).write_text(contenido + "\n")


def test_con_el_cargador_conectado_es_corriente(tmp_path: Path) -> None:
    _fuente(tmp_path, "AC", type="Mains", online="1")
    _fuente(tmp_path, "BAT0", type="Battery", status="Charging")

    assert leer_fuente_de_energia(tmp_path) == "corriente"


def test_con_el_cargador_desconectado_es_bateria(tmp_path: Path) -> None:
    _fuente(tmp_path, "AC", type="Mains", online="0")
    _fuente(tmp_path, "BAT0", type="Battery", status="Discharging")

    assert leer_fuente_de_energia(tmp_path) == "batería"


def test_sin_datos_es_desconocida(tmp_path: Path) -> None:
    assert leer_fuente_de_energia(tmp_path) == "desconocida"
    assert leer_fuente_de_energia(tmp_path / "no-existe") == "desconocida"


def test_un_equipo_de_escritorio_sin_bateria_es_corriente(tmp_path: Path) -> None:
    _fuente(tmp_path, "AC", type="Mains", online="1")

    assert leer_fuente_de_energia(tmp_path) == "corriente"


# ---- guardar audio ----------------------


def test_escribir_wav_guarda_16_khz_mono_de_16_bits_y_con_permisos_privados(
    tmp_path: Path,
) -> None:
    audio = (np.sin(np.arange(FRECUENCIA) / 10) * 8000).astype(np.int16)
    destino = tmp_path / "frase.wav"

    escribir_wav(destino, audio)

    with wave.open(str(destino)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, FRECUENCIA)
        leido = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16)
    np.testing.assert_array_equal(leido, audio)
    assert destino.stat().st_mode & 0o077 == 0


# ---- el recorrido interactivo ----------------------


class GrabadoraDeMedicion:
    """Cada frase «graba» 3 s de voz; los eventos permiten ver el orden de las llamadas."""

    def __init__(self) -> None:
        t = np.arange(3 * FRECUENCIA) / FRECUENCIA
        self.audio = (6000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
        self.grabaciones = 0

    def iniciar(self, dispositivo: str | int | None = None) -> None:
        self.grabaciones += 1

    def audio_acumulado(self) -> np.ndarray:
        return self.audio

    def detener_crudo(self) -> np.ndarray:
        return self.audio


class Entrada:
    """Responde en orden a las preguntas de la medición y guarda lo que se le mostró."""

    def __init__(self, respuestas: list[str]) -> None:
        self._respuestas: Iterator[str] = iter(respuestas)
        self.preguntas: list[str] = []

    def __call__(self, pregunta: str) -> str:
        self.preguntas.append(pregunta)
        return next(self._respuestas)


FRASES_CORTAS = (
    FraseDePrueba(1, "es", "es", "Eh, necesito el informe."),
    FraseDePrueba(2, "en", "en", "Please send the report."),
)


@pytest.fixture
def datos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    return tmp_path / "datos"


def test_recorre_las_frases_guarda_audio_y_resultados_y_resume(datos: Path) -> None:
    # Por frase: Enter para empezar, Enter para terminar y s/n de «sin corrección».
    entrada = Entrada(["", "", "s", "", "", "n"])
    salida: list[str] = []

    mediciones, carpeta = ejecutar_medicion(
        grabadora=GrabadoraDeMedicion(),
        motor=MotorFalso(texto="eh necesito el informe", idioma="es"),
        frases=FRASES_CORTAS,
        entrada=entrada,
        salida=salida.append,
    )

    assert [m.numero for m in mediciones] == [1, 2]
    assert [m.sin_correccion for m in mediciones] == [True, False]
    assert mediciones[0].texto_crudo == "eh necesito el informe"
    assert mediciones[0].texto_final == "Necesito el informe."
    assert mediciones[0].muletillas_restantes == 0
    assert carpeta.parent == datos / "vozflow" / "pruebas"
    assert (carpeta / "frase-01.wav").is_file() and (carpeta / "frase-02.wav").is_file()
    guardado = json.loads((carpeta / "resultados.json").read_text())
    assert len(guardado["mediciones"]) == 2
    assert guardado["resumen"]["cantidad"] == 2
    resumen = (carpeta / "resumen.md").read_text()
    assert "CE-002" in resumen
    assert any("Eh, necesito el informe." in linea for linea in salida)


def test_repetir_una_frase_vuelve_a_grabarla_y_se_queda_con_el_ultimo_intento(
    datos: Path,
) -> None:
    grabadora = GrabadoraDeMedicion()
    entrada = Entrada(["", "", "r", "", "", "s"])  # la primera vez pide repetir

    mediciones, _ = ejecutar_medicion(
        grabadora=grabadora,
        motor=MotorFalso(),
        frases=FRASES_CORTAS[:1],
        entrada=entrada,
        salida=lambda _: None,
    )

    assert grabadora.grabaciones == 2
    assert len(mediciones) == 1
    assert mediciones[0].sin_correccion is True


def test_una_respuesta_invalida_se_vuelve_a_preguntar(datos: Path) -> None:
    entrada = Entrada(["", "", "tal vez", "s"])

    mediciones, _ = ejecutar_medicion(
        grabadora=GrabadoraDeMedicion(),
        motor=MotorFalso(),
        frases=FRASES_CORTAS[:1],
        entrada=entrada,
        salida=lambda _: None,
    )

    assert mediciones[0].sin_correccion is True
    assert len(entrada.preguntas) == 4


def test_una_frase_sin_voz_se_avisa_y_se_puede_repetir(datos: Path) -> None:
    class Silenciosa(GrabadoraDeMedicion):
        def __init__(self) -> None:
            super().__init__()
            self.audio = np.zeros(3 * FRECUENCIA, dtype=np.int16)

    salida: list[str] = []
    entrada = Entrada(["", "", "n"])

    mediciones, _ = ejecutar_medicion(
        grabadora=Silenciosa(),
        motor=MotorFalso(),
        frases=FRASES_CORTAS[:1],
        entrada=entrada,
        salida=salida.append,
    )

    assert mediciones[0].texto_crudo == ""
    assert any("voz" in linea.lower() for linea in salida)
