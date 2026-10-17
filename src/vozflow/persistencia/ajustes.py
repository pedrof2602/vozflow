"""Ajustes persistentes (``data-model.md``, «Ajustes»): pares clave-valor con tipo y validación.

Los valores se guardan como JSON en la tabla ``ajuste``. Una clave sin valor, o con un valor
que no se puede leer, vale lo que dice su defecto.
"""

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Any

from vozflow.atajos.evdev import parsear_atajo
from vozflow.atajos.gsettings import a_formato_gnome
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.transcripcion.faster_whisper import HILOS_POR_DEFECTO, MODELO_POR_DEFECTO

_IDIOMAS = ("automatico", "es", "en")
_HILOS_MINIMO, _HILOS_MAXIMO = 1, 8


def _texto(valor: Any) -> str:
    if not isinstance(valor, str):
        raise DatoInvalido("Tiene que ser un texto")
    return valor


def _texto_no_vacio(valor: Any) -> str:
    texto = _texto(valor).strip()
    if not texto:
        raise DatoInvalido("No puede estar vacío")
    return texto


def _booleano(valor: Any) -> bool:
    if not isinstance(valor, bool):
        raise DatoInvalido("Tiene que ser verdadero o falso")
    return valor


def _hilos(valor: Any) -> int:
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise DatoInvalido("Los hilos tienen que ser un número entero")
    if not _HILOS_MINIMO <= valor <= _HILOS_MAXIMO:
        raise DatoInvalido(f"Los hilos tienen que estar entre {_HILOS_MINIMO} y {_HILOS_MAXIMO}")
    return valor


def _idioma(valor: Any) -> str:
    if valor not in _IDIOMAS:
        raise DatoInvalido(f"El idioma tiene que ser uno de: {', '.join(_IDIOMAS)}")
    return str(valor)


def _mantener(valor: Any) -> str:
    texto = _texto_no_vacio(valor)
    try:
        parsear_atajo(texto)
    except ValueError as error:
        raise DatoInvalido(f"Atajo no válido: {error}") from error
    return texto


def _alternar(valor: Any) -> str:
    texto = _texto_no_vacio(valor)
    try:
        return a_formato_gnome(texto)
    except ValueError as error:
        raise DatoInvalido(f"Atajo no válido: {error}") from error


@dataclass(frozen=True)
class _Clave:
    defecto: Any
    validar: Callable[[Any], Any]


_CLAVES: dict[str, _Clave] = {
    "atajo.mantener": _Clave("RightCtrl", _mantener),
    "atajo.alternar": _Clave("<Control><Alt>space", _alternar),
    "audio.dispositivo": _Clave("", _texto),
    "idioma.modo": _Clave("automatico", _idioma),
    "motor.modelo": _Clave(MODELO_POR_DEFECTO, _texto_no_vacio),
    "motor.hilos": _Clave(HILOS_POR_DEFECTO, _hilos),
    "historial.activo": _Clave(True, _booleano),
    "reescritura.activa": _Clave(False, _booleano),
    "interfaz.indicador": _Clave(True, _booleano),
}


def _igual(a: str, b: str) -> bool:
    def forma(texto: str) -> str:
        try:
            return a_formato_gnome(texto).lower()
        except ValueError:
            return texto.strip().lower()

    return forma(a) == forma(b)


@dataclass(frozen=True)
class Ajustes:
    """Una foto de los ajustes, para quien arranca el servicio."""

    atajo_mantener: str
    atajo_alternar: str
    dispositivo: str | None
    idioma: str | None
    modelo: str
    hilos: int
    historial_activo: bool
    reescritura_activa: bool
    indicador: bool

    def atajos(self) -> dict[AccionDeAtajo, str]:
        return {
            AccionDeAtajo.MANTENER: self.atajo_mantener,
            AccionDeAtajo.ALTERNAR: self.atajo_alternar,
        }

    def con_atajos(self, mantener: str | None, alternar: str | None) -> Ajustes:
        """Cambia los atajos solo para esta ejecución (no toca la base)."""
        return replace(
            self,
            atajo_mantener=mantener or self.atajo_mantener,
            atajo_alternar=alternar or self.atajo_alternar,
        )


class AjustesRepo:
    def __init__(self, base: sqlite3.Connection) -> None:
        self._base = base

    def obtener(self, clave: str) -> Any:
        definicion = self._definicion(clave)
        fila = self._base.execute("SELECT valor FROM ajuste WHERE clave = ?", (clave,)).fetchone()
        if fila is None:
            return definicion.defecto
        try:
            return definicion.validar(json.loads(fila["valor"]))
        except ValueError, DatoInvalido:
            return definicion.defecto

    def establecer(self, clave: str, valor: Any) -> None:
        definicion = self._definicion(clave)
        limpio = definicion.validar(valor)
        otra = "atajo.alternar" if clave == "atajo.mantener" else "atajo.mantener"
        if clave.startswith("atajo.") and _igual(limpio, self.obtener(otra)):
            raise DatoInvalido("Los dos atajos tienen que ser teclas distintas")
        with self._base:
            self._base.execute(
                "INSERT INTO ajuste (clave, valor) VALUES (?, ?) "
                "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
                (clave, json.dumps(limpio)),
            )

    @staticmethod
    def defecto(clave: str) -> Any:
        return AjustesRepo._definicion(clave).defecto

    def validar_atajos(self, mantener: str, alternar: str) -> tuple[str, str]:
        """Comprueba los dos atajos juntos y los devuelve normalizados, sin guardar nada."""
        validos = (_mantener(mantener), _alternar(alternar))
        if _igual(*validos):
            raise DatoInvalido("Los dos atajos tienen que ser teclas distintas")
        return validos

    def establecer_atajos(self, mantener: str, alternar: str) -> None:
        """Cambia los dos atajos a la vez: o se guardan los dos o ninguno."""
        valido_mantener, valido_alternar = self.validar_atajos(mantener, alternar)
        with self._base:
            for clave, valor in (
                ("atajo.mantener", valido_mantener),
                ("atajo.alternar", valido_alternar),
            ):
                self._base.execute(
                    "INSERT INTO ajuste (clave, valor) VALUES (?, ?) "
                    "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
                    (clave, json.dumps(valor)),
                )

    def restablecer(self, clave: str) -> None:
        self._definicion(clave)
        with self._base:
            self._base.execute("DELETE FROM ajuste WHERE clave = ?", (clave,))

    def todos(self) -> dict[str, Any]:
        return {clave: self.obtener(clave) for clave in _CLAVES}

    def cargar(self) -> Ajustes:
        idioma = self.obtener("idioma.modo")
        return Ajustes(
            atajo_mantener=self.obtener("atajo.mantener"),
            atajo_alternar=self.obtener("atajo.alternar"),
            dispositivo=self.obtener("audio.dispositivo") or None,
            idioma=None if idioma == "automatico" else idioma,
            modelo=self.obtener("motor.modelo"),
            hilos=self.obtener("motor.hilos"),
            historial_activo=self.obtener("historial.activo"),
            reescritura_activa=self.obtener("reescritura.activa"),
            indicador=self.obtener("interfaz.indicador"),
        )

    @staticmethod
    def _definicion(clave: str) -> _Clave:
        try:
            return _CLAVES[clave]
        except KeyError:
            raise DatoInvalido(f"No existe la clave de ajuste «{clave}»") from None
