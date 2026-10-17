"""Diagnóstico del escritorio: qué hay disponible para los atajos y la inserción de texto."""

import glob
import os
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass

_PORTALES = {
    "GlobalShortcuts": "org.freedesktop.portal.GlobalShortcuts",
    "RemoteDesktop": "org.freedesktop.portal.RemoteDesktop",
    "Clipboard": "org.freedesktop.portal.Clipboard",
}
_PROGRAMAS = ("wl-copy", "wl-paste", "ydotool", "gsettings", "dbus-send")


@dataclass(frozen=True)
class Comprobacion:
    nombre: str
    ok: bool
    detalle: str


@dataclass(frozen=True)
class Sondas:
    """Lo que toca el escritorio; las pruebas lo reemplazan por funciones simples."""

    version_de_portal: Callable[[str], int]
    puede_leer_teclados: Callable[[], bool]
    puede_escribir_uinput: Callable[[], bool]
    ydotoold_corre: Callable[[], bool]
    programa_instalado: Callable[[str], bool]
    consultar_ventana: Callable[[], tuple[bool, int]]
    """``(identificó una ventana, milisegundos que tardó)``."""


def sondas_reales() -> Sondas:
    from vozflow.dbus_portal import ClientePortal
    from vozflow.insercion.ydotool import socket_de_ydotool
    from vozflow.ventana.atspi import VentanaActivaAtspi

    def version_de_portal(interfaz: str) -> int:
        cliente = ClientePortal.abrir()
        try:
            return cliente.version_de(interfaz)
        finally:
            cliente.cerrar()

    def consultar_ventana() -> tuple[bool, int]:
        inicio = time.perf_counter()
        ventana = VentanaActivaAtspi().consultar()
        return ventana is not None, round((time.perf_counter() - inicio) * 1000)

    return Sondas(
        version_de_portal=version_de_portal,
        puede_leer_teclados=lambda: any(
            os.access(ruta, os.R_OK) for ruta in glob.glob("/dev/input/event*")
        ),
        puede_escribir_uinput=lambda: os.access("/dev/uinput", os.W_OK),
        ydotoold_corre=lambda: socket_de_ydotool().exists(),
        programa_instalado=lambda nombre: shutil.which(nombre) is not None,
        consultar_ventana=consultar_ventana,
    )


def ejecutar_diagnostico(sondas: Sondas) -> list[Comprobacion]:
    resultado = [_portal(nombre, interfaz, sondas) for nombre, interfaz in _PORTALES.items()]
    resultado += [
        Comprobacion(
            "Lectura de /dev/input",
            sondas.puede_leer_teclados(),
            "se puede leer el teclado (mantener-para-hablar)"
            if sondas.puede_leer_teclados()
            else "sin permiso: agregá tu usuario al grupo input y volvé a iniciar sesión",
        ),
        Comprobacion(
            "Escritura en /dev/uinput",
            sondas.puede_escribir_uinput(),
            "se puede crear un teclado virtual"
            if sondas.puede_escribir_uinput()
            else "sin permiso para /dev/uinput (lo necesita ydotoold)",
        ),
        Comprobacion(
            "ydotoold",
            sondas.ydotoold_corre(),
            "el servicio de ydotool está corriendo"
            if sondas.ydotoold_corre()
            else "no está corriendo; vozflow usará el portal RemoteDesktop",
        ),
    ]
    resultado += [
        Comprobacion(
            f"Programa {programa}",
            sondas.programa_instalado(programa),
            "instalado" if sondas.programa_instalado(programa) else "falta instalarlo",
        )
        for programa in _PROGRAMAS
    ]
    resultado.append(_ventana(sondas))
    return resultado


def _portal(nombre: str, interfaz: str, sondas: Sondas) -> Comprobacion:
    titulo = f"Portal {nombre}"
    try:
        version = sondas.version_de_portal(interfaz)
    except Exception as error:
        return Comprobacion(titulo, False, f"no se pudo consultar: {error}")
    if version <= 0:
        return Comprobacion(titulo, False, "el escritorio no lo ofrece")
    return Comprobacion(titulo, True, f"disponible, versión {version}")


def _ventana(sondas: Sondas) -> Comprobacion:
    nombre = "Ventana activa (AT-SPI)"
    try:
        identificada, milisegundos = sondas.consultar_ventana()
    except Exception as error:
        return Comprobacion(nombre, False, f"falló: {type(error).__name__}")
    if identificada:
        return Comprobacion(nombre, True, f"contestó en {milisegundos} ms")
    return Comprobacion(
        nombre, True, f"contestó en {milisegundos} ms pero no identificó ninguna ventana"
    )


def formatear(resultado: list[Comprobacion]) -> str:
    return "\n".join(f"{'✓' if c.ok else '✗'} {c.nombre}: {c.detalle}" for c in resultado)
