"""Atajo personalizado de GNOME para el modo «alternar» (línea base).

Se registra con ``gsettings`` como cualquier atajo personalizado de Configuración > Teclado; al
pulsarlo, GNOME ejecuta ``dbus-send`` y eso llama al servicio de vozflow (``servicio_dbus``).
Es lo que hace OpenWhispr en este mismo escritorio. Avisa al pulsar pero **no al soltar**, por eso
sirve para alternar y no para mantener-para-hablar (eso lo resuelve ``evdev``).

Se registra al iniciar y se retira al detenerse, para no dejar una tecla apuntando a un servicio
apagado.
"""

import ast
import contextlib
import re
import subprocess
from collections.abc import Callable, Iterator, Sequence

from vozflow.atajos.evdev import parsear_atajo
from vozflow.atajos.puerto import AtajoOcupado

Ejecutor = Callable[[Sequence[str]], str]

ESQUEMA_DE_LA_LISTA = "org.gnome.settings-daemon.plugins.media-keys"
_ESQUEMA_DE_ENTRADA = "org.gnome.settings-daemon.plugins.media-keys.custom-keybinding"
RAIZ = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"
RUTA_PROPIA = f"{RAIZ}/vozflow/"
COMANDO = (
    "dbus-send --session --type=method_call --dest=com.vozflow.App "
    "/com/vozflow/App com.vozflow.App.Toggle"
)
_ESQUEMAS_CON_ATAJOS = (
    "org.gnome.desktop.wm.keybindings",
    "org.gnome.shell.keybindings",
    "org.gnome.settings-daemon.plugins.media-keys",
    "org.gnome.mutter.keybindings",
    "org.gnome.mutter.wayland.keybindings",
)

_NOMBRE_DE_MODIFICADOR = {"ctrl": "Control", "alt": "Alt", "shift": "Shift", "super": "Super"}
_ALIAS_DE_GNOME = {
    "primary": "ctrl",
    "control": "ctrl",
    "ctrl": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "super": "super",
    "meta": "super",
}
_NOMBRE_DE_TECLA = {
    "space": "space",
    "espacio": "space",
    "scrolllock": "Scroll_Lock",
    "esc": "Escape",
    "escape": "Escape",
    "return": "Return",
    "enter": "Return",
    "backspace": "BackSpace",
    "grave": "grave",
    "backtick": "grave",
}


class ErrorDeGSettings(Exception):
    """No se pudo usar ``gsettings``; el mensaje se puede mostrar tal cual."""


def ejecutar_gsettings(argumentos: Sequence[str]) -> str:
    resultado = subprocess.run(
        ["gsettings", *argumentos], capture_output=True, text=True, timeout=5, check=True
    )
    return resultado.stdout


def a_formato_gnome(texto: str) -> str:
    """``Ctrl+Alt+Space`` → ``<Control><Alt>space``: el formato de los atajos de GNOME."""
    combinacion = parsear_atajo(texto)  # valida el nombre y rechaza lo que no existe
    if combinacion.solo_modificador:
        raise ValueError(
            f"El atajo {texto!r} es un modificador solo: no sirve como atajo de GNOME "
            "(se maneja leyendo el teclado)"
        )
    nombres = [t.lower() for t in re.split(r"[+<>\s]+", texto.strip()) if t]
    *modificadores, principal = nombres
    prefijo = "".join(f"<{_NOMBRE_DE_MODIFICADOR[_ALIAS_DE_GNOME[m]]}>" for m in modificadores)
    if principal in _NOMBRE_DE_TECLA:
        tecla = _NOMBRE_DE_TECLA[principal]
    elif re.fullmatch(r"f\d{1,2}", principal):
        tecla = principal.upper()
    elif len(principal) == 1:
        tecla = principal
    else:
        tecla = principal.capitalize()
    return prefijo + tecla


def _normalizar(atajo: str) -> tuple[frozenset[str], str]:
    """Una tecla de GNOME sin importar el orden de los modificadores ni las mayúsculas."""
    modificadores = {
        _ALIAS_DE_GNOME.get(m.lower(), m.lower()) for m in re.findall(r"<(\w+)>", atajo)
    }
    return frozenset(modificadores), atajo.rsplit(">", 1)[-1].lower()


def _como_valor(texto: str) -> object:
    texto = texto.strip()
    if texto.startswith("@"):
        texto = texto.split(" ", 1)[1]
    return ast.literal_eval(texto)


def leer_lista(ejecutar: Ejecutor) -> list[str]:
    valor = _como_valor(ejecutar(["get", ESQUEMA_DE_LA_LISTA, "custom-keybindings"]))
    return [str(ruta) for ruta in valor] if isinstance(valor, list) else []


class AtajoDeGnome:
    def __init__(self, ejecutar: Ejecutor = ejecutar_gsettings) -> None:
        self._ejecutar = ejecutar

    def registrar(self, binding: str) -> None:
        """Crea el atajo ``vozflow``. Lanza ``AtajoOcupado`` si la tecla ya la usa otra función."""
        with _traducir_errores():
            conflicto = self._buscar_conflicto(binding)
            if conflicto is not None:
                raise AtajoOcupado(f"{binding} ya lo usa {conflicto}")
            esquema = f"{_ESQUEMA_DE_ENTRADA}:{RUTA_PROPIA}"
            for clave, valor in (("name", "vozflow"), ("command", COMANDO), ("binding", binding)):
                self._ejecutar(["set", esquema, clave, valor])
            lista = leer_lista(self._ejecutar)
            if RUTA_PROPIA not in lista:
                self._ejecutar(
                    ["set", ESQUEMA_DE_LA_LISTA, "custom-keybindings", repr([*lista, RUTA_PROPIA])]
                )

    def quitar(self) -> None:
        """Borra solo el atajo de vozflow. Es inofensivo si no estaba."""
        with _traducir_errores():
            lista = leer_lista(self._ejecutar)
            if RUTA_PROPIA in lista:
                restantes = [ruta for ruta in lista if ruta != RUTA_PROPIA]
                self._ejecutar(["set", ESQUEMA_DE_LA_LISTA, "custom-keybindings", repr(restantes)])
            self._ejecutar(["reset-recursively", f"{_ESQUEMA_DE_ENTRADA}:{RUTA_PROPIA}"])

    # ---- internos -----------------------------------------------------------------------------

    def _buscar_conflicto(self, binding: str) -> str | None:
        buscado = _normalizar(binding)
        for ruta in leer_lista(self._ejecutar):
            if ruta == RUTA_PROPIA:
                continue
            esquema = f"{_ESQUEMA_DE_ENTRADA}:{ruta}"
            actual = _como_valor(self._ejecutar(["get", esquema, "binding"]))
            if isinstance(actual, str) and actual and _normalizar(actual) == buscado:
                nombre = _como_valor(self._ejecutar(["get", esquema, "name"]))
                return f"el atajo personalizado «{nombre or ruta}»"
        for esquema in _ESQUEMAS_CON_ATAJOS:
            try:
                salida = self._ejecutar(["list-recursively", esquema])
            except subprocess.CalledProcessError:
                continue  # el esquema no existe en esta versión de GNOME
            for linea in salida.splitlines():
                partes = linea.split(" ", 2)
                if len(partes) < 3:
                    continue
                try:
                    valor = _como_valor(partes[2])
                except ValueError, SyntaxError:
                    continue
                candidatos = valor if isinstance(valor, list) else [valor]
                if any(isinstance(c, str) and c and _normalizar(c) == buscado for c in candidatos):
                    return f"la función «{partes[1]}» de GNOME"
        return None


@contextlib.contextmanager
def _traducir_errores() -> Iterator[None]:
    """Convierte los fallos de ``gsettings`` en ``ErrorDeGSettings`` con un mensaje claro."""
    try:
        yield
    except FileNotFoundError as error:
        raise ErrorDeGSettings("No se encontró el comando gsettings") from error
    except subprocess.CalledProcessError as error:
        detalle = (error.stderr or "").strip() or f"código {error.returncode}"
        raise ErrorDeGSettings(f"gsettings falló: {detalle}") from error
