"""Los permisos del sistema que vozflow necesita, explicados en palabras llanas (002, RP-011).

Una función pura sobre las ``Sondas`` del diagnóstico: devuelve, por permiso, si está bien, y si no,
para qué sirve y el paso exacto (con el comando para copiar). Lo usan el asistente de primer uso, el
diagnóstico y los mensajes de error. Los textos van en segunda persona, sin jerga fuera del comando.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from vozflow.diagnostico import Sondas

_PORTAL_ESCRITORIO_REMOTO = "org.freedesktop.portal.RemoteDesktop"


class Estado(StrEnum):
    BIEN = "bien"
    FALTA_REINICIAR_SESION = "falta_reiniciar_sesion"
    FALTA = "falta"
    NO_APLICA = "no_aplica"


@dataclass(frozen=True)
class Permiso:
    nombre: str
    titulo: str
    estado: Estado
    por_que: str
    paso: str = ""
    comando: str = ""
    """Lo que se puede copiar y pegar en una terminal; vacío si no hace falta ninguno."""


def _o[T](llamada: Callable[[], T], defecto: T) -> T:
    """Una sonda que falla cuenta como «no»: el diagnóstico nunca se cae."""
    try:
        return llamada()
    except Exception:
        return defecto


def _teclado(sondas: Sondas) -> Permiso:
    por_que = "Para saber qué tecla apretás para dictar, mientras la mantenés apretada."
    if _o(sondas.puede_leer_teclados, False):
        return Permiso("teclado", "Leer el teclado", Estado.BIEN, por_que)
    if _o(sondas.grupo_input_en_la_base, False) and not _o(sondas.grupo_input_activo, False):
        return Permiso(
            "teclado",
            "Leer el teclado",
            Estado.FALTA_REINICIAR_SESION,
            por_que,
            "Ya diste el permiso, pero falta una cosa: cerrá sesión y volvé a entrar para que "
            "se active. Mientras tanto podés dictar con la tecla de empezar y terminar.",
        )
    return Permiso(
        "teclado",
        "Leer el teclado",
        Estado.FALTA,
        por_que,
        "Copiá este comando en una terminal, escribí tu contraseña y después cerrá sesión y "
        "volvé a entrar.",
        "sudo usermod -aG input $USER",
    )


def _teclado_virtual(sondas: Sondas) -> Permiso:
    por_que = "Para pegar el texto en la ventana donde estás escribiendo."
    titulo = "Pegar el texto"
    if _o(sondas.puede_escribir_uinput, False):
        return Permiso("teclado_virtual", titulo, Estado.BIEN, por_que)
    if _o(lambda: sondas.version_de_portal(_PORTAL_ESCRITORIO_REMOTO), 0) > 0:
        return Permiso("teclado_virtual", titulo, Estado.BIEN, por_que)
    return Permiso(
        "teclado_virtual",
        titulo,
        Estado.FALTA,
        por_que,
        "Volvé a correr el instalador de vozflow: deja todo listo. Si ya lo hiciste, cerrá "
        "sesión y volvé a entrar.",
    )


def _portapapeles(sondas: Sondas) -> Permiso:
    titulo = "Copiar y pegar"
    por_que = "Para copiar el texto antes de pegarlo."
    if not _o(sondas.es_wayland, True):
        return Permiso("portapapeles", titulo, Estado.NO_APLICA, por_que)
    if _o(lambda: sondas.programa_instalado("wl-copy"), False):
        return Permiso("portapapeles", titulo, Estado.BIEN, por_que)
    gestor = _o(sondas.gestor_de_paquetes, "")
    comando = f"sudo {gestor} install wl-clipboard" if gestor else ""
    paso = (
        "Copiá este comando en una terminal y escribí tu contraseña."
        if comando
        else "Instalá el paquete wl-clipboard con el gestor de programas de tu sistema."
    )
    return Permiso("portapapeles", titulo, Estado.FALTA, por_que, paso, comando)


def _microfono(sondas: Sondas) -> Permiso:
    titulo = "Micrófono"
    por_que = "Para escucharte."
    if _o(sondas.microfonos, 0) > 0:
        return Permiso("microfono", titulo, Estado.BIEN, por_que)
    return Permiso(
        "microfono",
        titulo,
        Estado.FALTA,
        por_que,
        "Conectá un micrófono y elegilo en los ajustes de sonido de tu sistema.",
    )


def comprobar_permisos(sondas: Sondas) -> list[Permiso]:
    """El estado de cada permiso, en el orden en que conviene explicarlos."""
    return [_teclado(sondas), _teclado_virtual(sondas), _portapapeles(sondas), _microfono(sondas)]
