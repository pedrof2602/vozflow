"""Diagnóstico del escritorio: qué hay disponible para los atajos y la inserción de texto."""

import glob
import importlib.metadata
import os
import platform
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

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
    grupo_input_en_la_base: Callable[[], bool] = lambda: True
    """El usuario figura en el grupo ``input`` (aunque la sesión actual todavía no lo tenga)."""
    grupo_input_activo: Callable[[], bool] = lambda: True
    """El proceso en marcha ya tiene el grupo ``input`` (hace falta una sesión nueva si no)."""
    gestor_de_paquetes: Callable[[], str] = lambda: ""
    """``dnf``, ``apt`` o vacío si no se conoce."""
    microfonos: Callable[[], int] = lambda: 1
    es_wayland: Callable[[], bool] = lambda: True


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

    def grupo_input_en_la_base() -> bool:
        import getpass
        import grp

        try:
            grupo = grp.getgrnam("input")
        except KeyError:
            return False
        return getpass.getuser() in grupo.gr_mem or os.getgid() == grupo.gr_gid

    def grupo_input_activo() -> bool:
        import grp

        try:
            return grp.getgrnam("input").gr_gid in os.getgroups()
        except KeyError:
            return False

    def gestor_de_paquetes() -> str:
        return next((g for g in ("dnf", "apt") if shutil.which(g)), "")

    def microfonos() -> int:
        from vozflow.audio.captura import listar_dispositivos

        return len(listar_dispositivos())

    return Sondas(
        grupo_input_en_la_base=grupo_input_en_la_base,
        grupo_input_activo=grupo_input_activo,
        gestor_de_paquetes=gestor_de_paquetes,
        microfonos=microfonos,
        es_wayland=lambda: os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland",
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


# ---- diagnóstico copiable para un reporte (002, RP-024) ----------------------------------------


@dataclass(frozen=True)
class DatosCopiables:
    """Solo lo que es seguro pegar en un reporte público: versiones y si algo funciona.

    A propósito no hay campos para texto dictado, ventanas, claves ni nombres de dispositivos.
    """

    version_de_vozflow: str
    version_de_python: str
    sistema: str
    gnome: str
    sesion: str
    puede_leer_teclados: bool
    puede_escribir_uinput: bool
    tiene_portapapeles: bool
    microfonos: int
    modelo: str | None
    historial_activo: bool
    reescritura_activa: bool


class EntornoCopiable(Protocol):
    """Lo que toca el sistema; las pruebas lo reemplazan."""

    def os_release(self) -> str: ...
    def gnome(self) -> str: ...
    def sesion(self) -> str: ...
    def nombres_de_microfonos(self) -> list[str]: ...
    def modelo_instalado(self) -> str | None: ...
    def historial_activo(self) -> bool: ...
    def reescritura_activa(self) -> bool: ...
    def puede_leer_teclados(self) -> bool: ...
    def puede_escribir_uinput(self) -> bool: ...
    def tiene_portapapeles(self) -> bool: ...


_DESCONOCIDO = "desconocido"


def _o(valor: Callable[[], Any], defecto: Any) -> Any:
    try:
        return valor()
    except Exception:
        return defecto


def _nombre_del_sistema(os_release: str) -> str:
    for linea in os_release.splitlines():
        if linea.startswith("PRETTY_NAME="):
            return linea.split("=", 1)[1].strip().strip('"') or _DESCONOCIDO
    return _DESCONOCIDO


def reunir_datos_copiables(entorno: EntornoCopiable) -> DatosCopiables:
    """Junta los datos; lo que no se pueda leer queda como «desconocido», nunca falla."""
    return DatosCopiables(
        version_de_vozflow=_o(lambda: importlib.metadata.version("vozflow"), _DESCONOCIDO),
        version_de_python=platform.python_version(),
        sistema=_nombre_del_sistema(_o(entorno.os_release, "")),
        gnome=_o(entorno.gnome, _DESCONOCIDO) or _DESCONOCIDO,
        sesion=_o(entorno.sesion, _DESCONOCIDO) or _DESCONOCIDO,
        puede_leer_teclados=bool(_o(entorno.puede_leer_teclados, False)),
        puede_escribir_uinput=bool(_o(entorno.puede_escribir_uinput, False)),
        tiene_portapapeles=bool(_o(entorno.tiene_portapapeles, False)),
        microfonos=len(
            _o(entorno.nombres_de_microfonos, [])
        ),  # solo la cantidad, nunca los nombres
        modelo=_o(entorno.modelo_instalado, None),
        historial_activo=bool(_o(entorno.historial_activo, False)),
        reescritura_activa=bool(_o(entorno.reescritura_activa, False)),
    )


def _estado(ok: bool) -> str:
    return "bien" if ok else "falta"


def _microfonos(cantidad: int) -> str:
    if cantidad == 0:
        return "ninguno"
    return f"{cantidad} dispositivo" + ("" if cantidad == 1 else "s")


def _anonimizar(texto: str, hogar: str, usuario: str) -> str:
    if hogar:
        texto = texto.replace(hogar, "~")
    if len(usuario) >= 3:
        texto = re.sub(rf"\b{re.escape(usuario)}\b", "usuario", texto, flags=re.IGNORECASE)
    return texto


def formatear_copiable(datos: DatosCopiables, hogar: str = "", usuario: str = "") -> str:
    """El Markdown de ``contracts/diagnostico.md``, con el hogar y el usuario ocultos."""
    texto = "\n".join(
        [
            f"**vozflow** {datos.version_de_vozflow} · **Python** {datos.version_de_python} · "
            f"**Sistema** {datos.sistema} · **GNOME** {datos.gnome} · **Sesión** {datos.sesion}",
            "",
            "| Permiso | Estado |",
            "|---|---|",
            f"| Leer el teclado | {_estado(datos.puede_leer_teclados)} |",
            f"| Teclado virtual | {_estado(datos.puede_escribir_uinput)} |",
            f"| Copiar y pegar | {_estado(datos.tiene_portapapeles)} |",
            f"| Micrófono | {_microfonos(datos.microfonos)} |",
            "",
            "Modelo de voz: "
            + (f"instalado ({datos.modelo})" if datos.modelo else "sin descargar")
            + " · Historial: "
            + ("activado" if datos.historial_activo else "apagado")
            + " · Reescritura: "
            + ("activada" if datos.reescritura_activa else "apagada"),
            "",
        ]
    )
    return _anonimizar(texto, hogar, usuario)


class EntornoReal:
    """El entorno de verdad: sondas del escritorio y los ajustes guardados."""

    def __init__(self, sondas: Sondas, ajustes: Any) -> None:
        self._sondas = sondas
        self._ajustes = ajustes

    def os_release(self) -> str:
        with open("/etc/os-release", encoding="utf-8") as archivo:
            return archivo.read()

    def gnome(self) -> str:
        import subprocess

        salida = subprocess.run(
            ["gnome-shell", "--version"], capture_output=True, text=True, timeout=3, check=True
        ).stdout
        encontrado = re.search(r"\d+(?:\.\d+)*", salida)
        return encontrado.group(0) if encontrado else _DESCONOCIDO

    def sesion(self) -> str:
        return os.environ.get("XDG_SESSION_TYPE", "")

    def nombres_de_microfonos(self) -> list[str]:
        from vozflow.audio.captura import listar_dispositivos

        return [d.nombre for d in listar_dispositivos()]

    def modelo_instalado(self) -> str | None:
        from vozflow.transcripcion.faster_whisper import modelo_disponible

        nombre = str(self._ajustes.obtener("motor.modelo"))
        return nombre if modelo_disponible(nombre) else None

    def historial_activo(self) -> bool:
        return bool(self._ajustes.obtener("historial.activo"))

    def reescritura_activa(self) -> bool:
        return bool(self._ajustes.obtener("reescritura.activa"))

    def puede_leer_teclados(self) -> bool:
        return self._sondas.puede_leer_teclados()

    def puede_escribir_uinput(self) -> bool:
        return self._sondas.puede_escribir_uinput()

    def tiene_portapapeles(self) -> bool:
        return self._sondas.programa_instalado("wl-copy")
