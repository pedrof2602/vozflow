"""Línea de comandos de vozflow: ``python -m vozflow <orden>``."""

import argparse
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vozflow.aplicacion import Grabadora, dictar_una_vez
from vozflow.audio.captura import ErrorDeAudio
from vozflow.dominio.tuberia import OpcionesDeTuberia
from vozflow.medicion import FRASES_DE_PRUEBA, ejecutar_medicion
from vozflow.registro import configurar_registro
from vozflow.transcripcion.faster_whisper import MODELO_POR_DEFECTO
from vozflow.transcripcion.motor import ErrorDeTranscripcion, MotorDeTranscripcion

CODIGO_OK = 0
CODIGO_ERROR = 1
# El 2 lo usa argparse para los errores de uso.
CODIGO_SIN_VOZ = 3
CODIGO_INTERRUMPIDO = 130


@dataclass
class Dependencias:
    """Lo que toca el hardware o el disco; las pruebas lo reemplazan por dobles."""

    crear_grabadora: Callable[[], Grabadora]
    crear_motor: Callable[[str], MotorDeTranscripcion]
    esperar: Callable[[float], None]
    descargar_modelo: Callable[[str], str]
    entrada: Callable[[str], str] = input
    salida: Callable[[str], None] = print


def dependencias_reales() -> Dependencias:
    # Importaciones perezosas: cargar sounddevice y el motor es lento y necesita el sistema.
    from vozflow.audio.captura import Capturador
    from vozflow.transcripcion.faster_whisper import MotorFasterWhisper, descargar_modelo

    return Dependencias(
        crear_grabadora=Capturador,
        crear_motor=lambda modelo: MotorFasterWhisper(modelo=modelo),
        esperar=time.sleep,
        descargar_modelo=descargar_modelo,
    )


def _segundos_positivos(texto: str) -> float:
    try:
        valor = float(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"'{texto}' no es un número") from error
    if valor <= 0:
        raise argparse.ArgumentTypeError("debe ser mayor que cero")
    return valor


def _cantidad_de_frases(texto: str) -> int:
    try:
        valor = int(texto)
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"'{texto}' no es un número entero") from error
    if not 1 <= valor <= len(FRASES_DE_PRUEBA):
        raise argparse.ArgumentTypeError(f"debe estar entre 1 y {len(FRASES_DE_PRUEBA)}")
    return valor


def _dispositivo(texto: str) -> str | int:
    """Un número es el índice del dispositivo; otro texto, parte de su nombre."""
    return int(texto) if texto.isdigit() else texto


def _crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vozflow", description="Dictado por voz local.")
    ordenes = parser.add_subparsers(dest="orden", required=True, metavar="orden")

    dictar = ordenes.add_parser("dictar", help="graba unos segundos y muestra el texto limpio")
    dictar.add_argument("--segundos", type=_segundos_positivos, default=10.0)
    dictar.add_argument(
        "--dispositivo", type=_dispositivo, help="micrófono: índice o parte del nombre"
    )
    dictar.add_argument("--idioma", choices=["es", "en"], help="por defecto se detecta solo")
    dictar.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    dictar.add_argument(
        "--sin-comandos", action="store_true", help="no interpretar «coma», «punto»…"
    )
    dictar.add_argument("--sin-limpieza", action="store_true", help="no quitar muletillas")
    dictar.add_argument(
        "--sin-puntuacion", action="store_true", help="no tocar mayúsculas ni signos"
    )
    dictar.add_argument(
        "--detalle", action="store_true", help="mostrar el texto crudo y los tiempos"
    )

    medir = ordenes.add_parser(
        "medir", help="mide latencia, calidad y muletillas con tu voz (20 frases guiadas)"
    )
    medir.add_argument(
        "--cantidad",
        type=_cantidad_de_frases,
        default=len(FRASES_DE_PRUEBA),
        help=f"cuántas frases (de 1 a {len(FRASES_DE_PRUEBA)}); por defecto todas",
    )
    medir.add_argument(
        "--dispositivo", type=_dispositivo, help="micrófono: índice o parte del nombre"
    )
    medir.add_argument("--modelo", default=MODELO_POR_DEFECTO)

    descarga = ordenes.add_parser(
        "descargar-modelo", help="descarga el modelo de transcripción (única vez que usa internet)"
    )
    descarga.add_argument("--modelo", default=MODELO_POR_DEFECTO)
    return parser


def _avisar(mensaje: str) -> None:
    print(mensaje, file=sys.stderr)


def _orden_dictar(argumentos: argparse.Namespace, dependencias: Dependencias) -> int:
    opciones = OpcionesDeTuberia(
        quitar_muletillas=not argumentos.sin_limpieza,
        puntuacion_automatica=not argumentos.sin_puntuacion,
        comandos_de_voz=not argumentos.sin_comandos,
    )
    resultado = dictar_una_vez(
        grabadora=dependencias.crear_grabadora(),
        motor=dependencias.crear_motor(argumentos.modelo),
        segundos=argumentos.segundos,
        dispositivo=argumentos.dispositivo,
        idioma=argumentos.idioma,
        opciones=opciones,
        esperar=dependencias.esperar,
        al_empezar=lambda: _avisar(f"Grabando {argumentos.segundos:g} s… hablá ahora."),
    )
    transcripcion = resultado.transcripcion
    if argumentos.detalle:
        _avisar(f"Texto crudo: {transcripcion.texto!r}")
        _avisar(f"Idioma: {transcripcion.idioma or '—'} ({transcripcion.probabilidad_idioma:.0%})")
        _avisar(
            f"Grabado: {resultado.segundos_grabados:.1f} s · "
            f"espera tras terminar: {resultado.espera_tras_soltar_ms} ms"
        )
    if not transcripcion.texto:
        _avisar("No se detectó voz.")
        return CODIGO_SIN_VOZ
    if resultado.procesado.descartar:
        _avisar("Dictado descartado («borra eso»).")
        return CODIGO_OK
    if not resultado.procesado.texto:
        _avisar("El dictado quedó vacío tras quitar las muletillas.")
        return CODIGO_SIN_VOZ
    print(resultado.procesado.texto)
    return CODIGO_OK


def _orden_medir(argumentos: argparse.Namespace, dependencias: Dependencias) -> int:
    ejecutar_medicion(
        grabadora=dependencias.crear_grabadora(),
        motor=dependencias.crear_motor(argumentos.modelo),
        frases=FRASES_DE_PRUEBA[: argumentos.cantidad],
        dispositivo=argumentos.dispositivo,
        entrada=dependencias.entrada,
        salida=dependencias.salida,
    )
    return CODIGO_OK


def _orden_descargar_modelo(argumentos: argparse.Namespace, dependencias: Dependencias) -> int:
    _avisar(f"Descargando el modelo '{argumentos.modelo}' (puede tardar unos minutos)…")
    print(dependencias.descargar_modelo(argumentos.modelo))
    return CODIGO_OK


def main(argv: Sequence[str] | None = None, dependencias: Dependencias | None = None) -> int:
    """Ejecuta una orden y devuelve el código de salida."""
    if dependencias is None:
        configurar_registro(logging.WARNING)
        dependencias = dependencias_reales()
    argumentos = _crear_parser().parse_args(argv)
    try:
        if argumentos.orden == "dictar":
            return _orden_dictar(argumentos, dependencias)
        if argumentos.orden == "medir":
            return _orden_medir(argumentos, dependencias)
        return _orden_descargar_modelo(argumentos, dependencias)
    except (ErrorDeAudio, ErrorDeTranscripcion) as error:
        _avisar(f"Error: {error}")
        return CODIGO_ERROR
    except KeyboardInterrupt:
        _avisar("Interrumpido.")
        return CODIGO_INTERRUMPIDO


if __name__ == "__main__":
    raise SystemExit(main())
