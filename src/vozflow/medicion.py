"""Medición con la voz real de Pedro: ``python -m vozflow medir``.

Recorre 20 frases (10 en español, 5 en inglés, 5 mezcladas, varias con «eh» y repeticiones a
propósito), guarda el audio fuera del repositorio y resume la latencia, la calidad y las
muletillas que quedaron, para decidir si se cumplen CE-002, CE-003 y CE-004.
"""

import json
import math
import re
import statistics
import threading
import wave
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import numpy as np
import numpy.typing as npt

from vozflow import rutas
from vozflow.aplicacion import Grabadora, dictar_hasta
from vozflow.audio.senal import FRECUENCIA
from vozflow.dominio.tuberia import OPCIONES_POR_DEFECTO, OpcionesDeTuberia
from vozflow.transcripcion.motor import MotorDeTranscripcion

LIMITE_DE_LATENCIA_MS = 5000
"""CE-002: el texto aparece en menos de 5 s tras soltar la tecla."""

MINIMO_SIN_CORRECCION = 0.90
"""CE-003: al menos el 90 % de las frases salen sin necesidad de corrección."""

Tipo = Literal["es", "en", "mixta"]


@dataclass(frozen=True)
class FraseDePrueba:
    numero: int
    tipo: Tipo
    idioma_esperado: str
    texto: str
    """Lo que Pedro debe decir, tal cual, incluidas las muletillas y los comandos de voz."""


def _f(numero: int, tipo: Tipo, texto: str) -> FraseDePrueba:
    return FraseDePrueba(numero, tipo, "en" if tipo == "en" else "es", texto)


FRASES_DE_PRUEBA: tuple[FraseDePrueba, ...] = (
    _f(1, "es", "Necesito que revises el informe antes de las cinco de la tarde."),
    _f(2, "es", "Eh, o sea, tengo que, tengo que hacer el merge del pull request."),
    _f(3, "es", "Mañana a las nueve tenemos la reunión con el equipo de ventas."),
    _f(
        4,
        "es",
        "Este, quería preguntarte si podés mandarme el informe, o sea, el de la semana pasada.",
    ),
    _f(5, "es", "La función devuelve una lista de clientes coma ordenada por apellido."),
    _f(6, "es", "Hola Marta coma cómo estás signo de interrogación"),
    _f(7, "es", "Tengo que ir al banco y después pasar por la farmacia, mmm, antes de volver."),
    _f(8, "es", "El servidor se cayó a las tres de la mañana y no sabemos por qué."),
    _f(9, "es", "Voy a revisar los logs, eh, voy a revisar los logs de producción."),
    _f(10, "es", "Primera línea nueva línea segunda línea nueva línea tercera línea"),
    _f(11, "en", "Please open the pull request and check that the tests are passing."),
    _f(12, "en", "Um, I think we should, you know, refactor the database module."),
    _f(13, "en", "The deployment failed because the environment variable was missing."),
    _f(14, "en", "I need to review the code, uh, I need to review the code before lunch."),
    _f(15, "en", "Can you send me the report by Friday question mark"),
    _f(
        16,
        "mixta",
        "Tengo que hacer el merge del branch y después correr los tests en el pipeline de CI.",
    ),
    _f(17, "mixta", "Eh, el endpoint devuelve un error quinientos cuando el payload está vacío."),
    _f(
        18, "mixta", "Necesito actualizar la dependency en el package punto json y hacer un rebase."
    ),
    _f(19, "mixta", "Subí el commit al repositorio, o sea, hice el push a main."),
    _f(
        20,
        "mixta",
        "El dashboard muestra los logs del servicio, pero el filtro por fecha no funciona.",
    ),
)

_MULETILLA_VISIBLE = re.compile(
    r"(?<!\w)(?:eh+m*|ehm+|em+|mm+h?|uh+|um+|o sea)(?!\w)", re.IGNORECASE
)


def contar_muletillas_visibles(texto: str) -> int:
    """Cuenta solo las muletillas inequívocas («eh», «mmm», «um», «o sea»).

    Es independiente de las reglas de limpieza a propósito: si usara las mismas, siempre daría 0.
    """
    return len(_MULETILLA_VISIBLE.findall(texto))


@dataclass(frozen=True)
class Medicion:
    numero: int
    tipo: str
    idioma_esperado: str
    frase: str
    idioma_detectado: str
    texto_crudo: str
    texto_final: str
    espera_ms: int
    """Lo que se esperó tras terminar de hablar hasta tener el texto."""
    segundos_grabados: float
    no_voz_probabilidad: float
    logprob_medio: float
    muletillas_restantes: int
    sin_correccion: bool | None
    """El juicio de Pedro; ``None`` si no lo dio."""


@dataclass(frozen=True)
class ResumenDeMediciones:
    cantidad: int
    fuente_de_energia: str
    latencia_min_ms: int
    latencia_mediana_ms: int
    latencia_p95_ms: int
    latencia_max_ms: int
    evaluadas: int
    sin_correccion: int
    porcentaje_sin_correccion: float | None
    muletillas_restantes: int
    aciertos_de_idioma: int
    no_voz_probabilidad_maxima: float
    logprob_medio: float
    cumple_ce002: bool | None
    cumple_ce003: bool | None
    cumple_ce004: bool | None


def percentil(valores: Sequence[int], q: float) -> int:
    """Percentil por rango más cercano (el valor de la posición ``ceil(q * n)``)."""
    ordenados = sorted(valores)
    rango = max(1, math.ceil(q * len(ordenados)))
    return ordenados[rango - 1]


def resumir_mediciones(
    mediciones: Sequence[Medicion], fuente_de_energia: str
) -> ResumenDeMediciones:
    cantidad = len(mediciones)
    esperas = [m.espera_ms for m in mediciones]
    juicios = [m.sin_correccion for m in mediciones if m.sin_correccion is not None]
    sin_correccion = sum(1 for j in juicios if j)
    muletillas = sum(m.muletillas_restantes for m in mediciones)
    p95 = percentil(esperas, 0.95) if esperas else 0
    return ResumenDeMediciones(
        cantidad=cantidad,
        fuente_de_energia=fuente_de_energia,
        latencia_min_ms=min(esperas, default=0),
        latencia_mediana_ms=round(statistics.median(esperas)) if esperas else 0,
        latencia_p95_ms=p95,
        latencia_max_ms=max(esperas, default=0),
        evaluadas=len(juicios),
        sin_correccion=sin_correccion,
        porcentaje_sin_correccion=100.0 * sin_correccion / len(juicios) if juicios else None,
        muletillas_restantes=muletillas,
        aciertos_de_idioma=sum(1 for m in mediciones if m.idioma_detectado == m.idioma_esperado),
        no_voz_probabilidad_maxima=max((m.no_voz_probabilidad for m in mediciones), default=0.0),
        logprob_medio=statistics.fmean(m.logprob_medio for m in mediciones) if mediciones else 0.0,
        cumple_ce002=p95 < LIMITE_DE_LATENCIA_MS if cantidad else None,
        cumple_ce003=(
            sin_correccion / cantidad >= MINIMO_SIN_CORRECCION
            if cantidad and len(juicios) == cantidad
            else None
        ),
        cumple_ce004=muletillas == 0 if cantidad else None,
    )


def _veredicto(cumple: bool | None) -> str:
    return {True: "cumple", False: "NO cumple", None: "sin veredicto"}[cumple]


def formatear_resumen(resumen: ResumenDeMediciones) -> str:
    porcentaje = (
        f"{resumen.porcentaje_sin_correccion:.0f} %"
        if resumen.porcentaje_sin_correccion is not None
        else "sin datos"
    )
    lineas = [
        "# Medición con voz real",
        "",
        f"- Frases medidas: {resumen.cantidad}",
        f"- Fuente de energía: {resumen.fuente_de_energia}",
        f"- Idioma detectado correctamente: {resumen.aciertos_de_idioma} de {resumen.cantidad}",
        "",
        "## CE-002: espera tras terminar de hablar (meta: p95 menor que 5 s)"
        f" — {_veredicto(resumen.cumple_ce002)}",
        "",
        "| mínimo | mediana | p95 | máximo |",
        "|---|---|---|---|",
        f"| {resumen.latencia_min_ms} ms | {resumen.latencia_mediana_ms} ms "
        f"| {resumen.latencia_p95_ms} ms | {resumen.latencia_max_ms} ms |",
        "",
        "## CE-003: frases sin necesidad de corrección (meta: al menos 90 %)"
        f" — {_veredicto(resumen.cumple_ce003)}",
        "",
        f"{resumen.sin_correccion} de {resumen.evaluadas} evaluadas ({porcentaje}).",
        "",
        "## CE-004: muletillas que quedaron en el texto final (meta: ninguna)"
        f" — {_veredicto(resumen.cumple_ce004)}",
        "",
        f"{resumen.muletillas_restantes} muletillas restantes.",
        "",
        "## Confianza del motor (para decidir un filtro de ruido)",
        "",
        f"- Mayor probabilidad de «no es voz» vista: {resumen.no_voz_probabilidad_maxima:.2f}",
        f"- Confianza media (logprob): {resumen.logprob_medio:.2f}",
        "",
    ]
    return "\n".join(lineas)


def leer_fuente_de_energia(raiz: Path = Path("/sys/class/power_supply")) -> str:
    """``corriente``, ``batería`` o ``desconocida``, según lo que informa el sistema."""
    if not raiz.is_dir():
        return "desconocida"

    def leer(carpeta: Path, archivo: str) -> str:
        try:
            return (carpeta / archivo).read_text().strip()
        except OSError:
            return ""

    fuentes = [d for d in raiz.iterdir() if d.is_dir()]
    if any(leer(d, "type") == "Mains" and leer(d, "online") == "1" for d in fuentes):
        return "corriente"
    estados = [leer(d, "status") for d in fuentes if leer(d, "type") == "Battery"]
    if "Discharging" in estados:
        return "batería"
    if estados or any(leer(d, "type") == "Mains" for d in fuentes):
        return "corriente"
    return "desconocida"


def escribir_wav(destino: Path, audio: npt.NDArray[np.int16]) -> None:
    """Guarda el audio como WAV de 16 kHz, mono y 16 bits, legible solo por el usuario."""
    with wave.open(str(destino), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(FRECUENCIA)
        wav.writeframes(audio.tobytes())
    destino.chmod(0o600)


def _preguntar_si_salio_bien(entrada: Callable[[str], str]) -> bool | None:
    """Devuelve el juicio de Pedro, o ``None`` si pide repetir la frase."""
    while True:
        respuesta = entrada("  ¿Salió sin necesidad de corrección? [s = sí, n = no, r = repetir] ")
        respuesta = respuesta.strip().lower()
        if respuesta in ("s", "si", "sí"):
            return True
        if respuesta in ("n", "no"):
            return False
        if respuesta in ("r", "repetir"):
            return None


def _grabar_una_frase(
    frase: FraseDePrueba,
    total: int,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    opciones: OpcionesDeTuberia,
    dispositivo: str | int | None,
    entrada: Callable[[str], str],
    salida: Callable[[str], None],
) -> tuple[Medicion, npt.NDArray[np.int16]] | None:
    salida(f"\nFrase {frase.numero}/{total} ({frase.tipo})")
    salida(f"  Decí: «{frase.texto}»")
    entrada("  Enter para EMPEZAR a grabar… ")
    parar = threading.Event()

    def esperar_enter() -> None:
        entrada("  Grabando. Enter para TERMINAR… ")
        parar.set()

    def esperar_o_parar(segundos: float) -> None:
        parar.wait(segundos)  # vuelve enseguida cuando Pedro presiona Enter

    threading.Thread(target=esperar_enter, daemon=True).start()
    resultado = dictar_hasta(
        grabadora=grabadora,
        motor=motor,
        seguir=lambda: not parar.is_set(),
        esperar=esperar_o_parar,
        dispositivo=dispositivo,
        opciones=opciones,
    )
    transcripcion = resultado.transcripcion
    salida(f"  Crudo:  {transcripcion.texto!r}")
    salida(f"  Final:  {resultado.procesado.texto!r}")
    salida(f"  Espera tras terminar: {resultado.espera_tras_soltar_ms} ms")
    if not transcripcion.texto:
        salida("  No se detectó voz en esta frase.")
    juicio = _preguntar_si_salio_bien(entrada)
    if juicio is None:
        return None
    medicion = Medicion(
        numero=frase.numero,
        tipo=frase.tipo,
        idioma_esperado=frase.idioma_esperado,
        frase=frase.texto,
        idioma_detectado=transcripcion.idioma,
        texto_crudo=transcripcion.texto,
        texto_final=resultado.procesado.texto,
        espera_ms=resultado.espera_tras_soltar_ms,
        segundos_grabados=round(resultado.segundos_grabados, 2),
        no_voz_probabilidad=round(transcripcion.no_voz_probabilidad, 3),
        logprob_medio=round(transcripcion.logprob_medio, 3),
        muletillas_restantes=contar_muletillas_visibles(resultado.procesado.texto),
        sin_correccion=juicio,
    )
    return medicion, resultado.audio


def ejecutar_medicion(
    *,
    grabadora: Grabadora,
    motor: MotorDeTranscripcion,
    frases: Sequence[FraseDePrueba] = FRASES_DE_PRUEBA,
    opciones: OpcionesDeTuberia = OPCIONES_POR_DEFECTO,
    dispositivo: str | int | None = None,
    entrada: Callable[[str], str] = input,
    salida: Callable[[str], None] = print,
    carpeta: Path | None = None,
) -> tuple[list[Medicion], Path]:
    """Recorre las frases con Pedro, guarda audio y resultados, y devuelve ambos."""
    # Antes de pedirle nada a Pedro: si falta el modelo se sabe enseguida, y el tiempo de carga
    # no entra en la espera de la primera frase.
    motor.cargar()
    if carpeta is None:
        carpeta = rutas.directorio_pruebas() / datetime.now().strftime("medicion-%Y%m%d-%H%M%S")
    rutas.asegurar(carpeta)
    mediciones: list[Medicion] = []
    for frase in frases:
        resultado = None
        while resultado is None:
            resultado = _grabar_una_frase(
                frase, len(frases), grabadora, motor, opciones, dispositivo, entrada, salida
            )
        medicion, audio = resultado
        escribir_wav(carpeta / f"frase-{frase.numero:02d}.wav", audio)
        mediciones.append(medicion)

    resumen = resumir_mediciones(mediciones, leer_fuente_de_energia())
    texto = formatear_resumen(resumen)
    (carpeta / "resumen.md").write_text(texto, encoding="utf-8")
    (carpeta / "resultados.json").write_text(
        json.dumps(
            {
                "fecha": datetime.now().isoformat(timespec="seconds"),
                "mediciones": [asdict(m) for m in mediciones],
                "resumen": asdict(resumen),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    salida("\n" + texto)
    salida(f"Audio y resultados guardados en {carpeta} (fuera del repositorio).")
    return mediciones, carpeta
