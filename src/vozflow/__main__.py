"""Línea de comandos de vozflow: ``python -m vozflow <orden>``."""

import argparse
import getpass
import logging
import signal
import sqlite3
import sys
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from vozflow import cli
from vozflow.aplicacion import Aplicacion, Grabadora, dictar_una_vez
from vozflow.atajos.compuesta import NingunAdaptadorSirve
from vozflow.atajos.evdev import SinPermisoDeTeclado, SinTeclados
from vozflow.atajos.gsettings import ErrorDeGSettings
from vozflow.atajos.puerto import AtajoOcupado, EscuchaDeAtajos
from vozflow.audio.captura import ErrorDeAudio
from vozflow.configuracion import ConfiguracionDeBase
from vozflow.diagnostico import Comprobacion, ejecutar_diagnostico, formatear, sondas_reales
from vozflow.dominio.copia import CopiaInvalida
from vozflow.dominio.dictado import EstadoDelDictado
from vozflow.dominio.tuberia import OpcionesDeTuberia
from vozflow.insercion.puerto import Insertor
from vozflow.medicion import FRASES_DE_PRUEBA, ejecutar_medicion
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.claves import Claves, LlaveroNoDisponible
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.historial import HistorialRepo
from vozflow.reescritura import FabricaDeReescritor, ReescrituraDeBase, crear_reescritor
from vozflow.registro import configurar_registro
from vozflow.servicio_dbus import InstanciaYaEnEjecucion
from vozflow.transcripcion.faster_whisper import MODELO_POR_DEFECTO
from vozflow.transcripcion.motor import ErrorDeTranscripcion, MotorDeTranscripcion
from vozflow.ventana.puerto import VentanaActiva

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
    abrir_base: Callable[[], sqlite3.Connection] = abrir_base
    leer_clave: Callable[[str], str] = getpass.getpass
    claves: Callable[[], cli.AlmacenDeClaves] = Claves
    crear_reescritor: FabricaDeReescritor = crear_reescritor
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


@dataclass
class DependenciasDelServicio:
    """Lo que toca el escritorio en el servicio; las pruebas lo reemplazan por dobles."""

    crear_escucha: Callable[[], EscuchaDeAtajos]
    crear_ventana: Callable[[], VentanaActiva]
    crear_insertor: Callable[[], Insertor]
    crear_motor: Callable[[str, int], MotorDeTranscripcion]
    """Recibe el modelo y la cantidad de hilos de los ajustes."""
    esperar_cierre: Callable[[], None]


def _esperar_senal() -> None:
    """Bloquea hasta Ctrl+C o ``SIGTERM`` (un apagado normal, no un error)."""
    cierre = threading.Event()
    for senal in (signal.SIGINT, signal.SIGTERM):
        signal.signal(senal, lambda *_: cierre.set())
    cierre.wait()


def servicio_real() -> DependenciasDelServicio:
    from vozflow.atajos import crear_escucha
    from vozflow.insercion import crear_insertor
    from vozflow.transcripcion.faster_whisper import MotorFasterWhisper
    from vozflow.ventana.atspi import VentanaActivaAtspi

    return DependenciasDelServicio(
        crear_escucha=crear_escucha,
        crear_ventana=VentanaActivaAtspi,
        crear_insertor=crear_insertor,
        crear_motor=lambda modelo, hilos: MotorFasterWhisper(modelo=modelo, hilos=hilos),
        esperar_cierre=_esperar_senal,
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
    parser = argparse.ArgumentParser(
        prog="vozflow",
        description="Dictado por voz local. Sin orden, arranca el servicio que escucha los atajos.",
    )
    parser.add_argument(
        "--sin-interfaz", action="store_true", help="sin ventanas ni bandeja (por ahora, siempre)"
    )
    parser.add_argument("--mantener", help="tecla para mantener y hablar (por defecto RightCtrl)")
    parser.add_argument(
        "--alternar", help="atajo para empezar y terminar (por defecto <Control><Alt>space)"
    )
    parser.add_argument("--modelo", help="modelo de transcripción (por defecto, el de los ajustes)")
    parser.add_argument(
        "--dispositivo", type=_dispositivo, help="micrófono: índice o parte del nombre"
    )
    ordenes = parser.add_subparsers(dest="orden", required=False, metavar="orden")

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

    cli.registrar(ordenes)

    ordenes.add_parser(
        "diagnostico", help="revisa qué tiene este escritorio para atajos e inserción de texto"
    )
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


def _hacer_diagnostico() -> list[Comprobacion]:
    return ejecutar_diagnostico(sondas_reales())


def _orden_de_datos(argumentos: argparse.Namespace, dependencias: Dependencias) -> int:
    base = dependencias.abrir_base()
    try:
        contexto = cli.Contexto(
            base=base,
            salida=dependencias.salida,
            leer_clave=dependencias.leer_clave,
            claves=dependencias.claves(),
            crear_reescritor=dependencias.crear_reescritor,
        )
        return cli.ejecutar(argumentos, contexto)
    finally:
        base.close()


def _orden_diagnostico() -> int:
    print(formatear(_hacer_diagnostico()))
    return CODIGO_OK


_TEXTO_DEL_ESTADO = {
    EstadoDelDictado.INACTIVO: "Listo.",
    EstadoDelDictado.ESCUCHANDO: "Escuchando…",
    EstadoDelDictado.TRANSCRIBIENDO: "Transcribiendo…",
    EstadoDelDictado.INSERTANDO: "Insertando…",
    EstadoDelDictado.ERROR: "El dictado falló.",
}


def _orden_servicio(
    argumentos: argparse.Namespace, dependencias: Dependencias, servicio: DependenciasDelServicio
) -> int:
    base = dependencias.abrir_base()
    try:
        repo = AjustesRepo(base)
        ajustes = repo.cargar().con_atajos(argumentos.mantener, argumentos.alternar)
        aplicacion = Aplicacion(
            escucha=servicio.crear_escucha(),
            grabadora=dependencias.crear_grabadora(),
            motor=servicio.crear_motor(argumentos.modelo or ajustes.modelo, ajustes.hilos),
            ventana=servicio.crear_ventana(),
            insertor=servicio.crear_insertor(),
            atajos=ajustes.atajos(),
            idioma=ajustes.idioma,
            dispositivo=argumentos.dispositivo or ajustes.dispositivo,
            configuracion=ConfiguracionDeBase(base),
            historial=HistorialRepo(base, activo=lambda: bool(repo.obtener("historial.activo"))),
            reescritura=ReescrituraDeBase(
                base, dependencias.claves(), dependencias.crear_reescritor
            ),
            al_cambiar_estado=lambda estado: _avisar(_TEXTO_DEL_ESTADO[estado]),
            al_aviso=lambda mensaje: _avisar(f"Aviso: {mensaje}"),
            # Lo dictado se muestra solo si no se pudo insertar, para que no se pierda.
            al_texto_sin_insertar=lambda texto: _avisar(f"Texto sin insertar: {texto}"),
        )
        try:
            _avisar("Cargando el modelo…")
            aplicacion.iniciar()
            _avisar(
                f"vozflow listo. Mantené {ajustes.atajo_mantener} para dictar, o pulsá "
                f"{ajustes.atajo_alternar} para empezar y terminar. Ctrl+C para salir."
            )
            servicio.esperar_cierre()
        except KeyboardInterrupt:
            pass  # Ctrl+C es la forma normal de apagarlo
        finally:
            aplicacion.detener()
    finally:
        base.close()
    _avisar("vozflow se apagó.")
    return CODIGO_OK


def main(
    argv: Sequence[str] | None = None,
    dependencias: Dependencias | None = None,
    servicio: DependenciasDelServicio | None = None,
) -> int:
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
        if argumentos.orden == "descargar-modelo":
            return _orden_descargar_modelo(argumentos, dependencias)
        if argumentos.orden == "diagnostico":
            return _orden_diagnostico()
        if argumentos.orden in cli.ORDENES_DE_DATOS:
            return _orden_de_datos(argumentos, dependencias)
        return _orden_servicio(argumentos, dependencias, servicio or servicio_real())
    except (
        cli.ErrorDeComando,
        LlaveroNoDisponible,
        DatoInvalido,
        CopiaInvalida,
        ErrorDeAudio,
        ErrorDeTranscripcion,
        AtajoOcupado,
        InstanciaYaEnEjecucion,
        NingunAdaptadorSirve,
        ErrorDeGSettings,
        SinPermisoDeTeclado,
        SinTeclados,
    ) as error:
        _avisar(f"Error: {error}")
        return CODIGO_ERROR
    except KeyboardInterrupt:
        _avisar("Interrumpido.")
        return CODIGO_INTERRUMPIDO


if __name__ == "__main__":
    raise SystemExit(main())
