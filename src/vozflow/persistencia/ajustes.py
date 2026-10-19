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


_IDIOMA_DE_TRADUCCION_MIN, _IDIOMA_DE_TRADUCCION_MAX = 2, 40


def _idioma_de_traduccion(valor: Any) -> str:
    texto = _texto(valor).strip()
    if not _IDIOMA_DE_TRADUCCION_MIN <= len(texto) <= _IDIOMA_DE_TRADUCCION_MAX:
        raise DatoInvalido(
            f"El idioma de destino tiene que tener entre {_IDIOMA_DE_TRADUCCION_MIN} y "
            f"{_IDIOMA_DE_TRADUCCION_MAX} caracteres"
        )
    if not texto.isprintable():
        raise DatoInvalido(
            "El idioma de destino no puede tener saltos de línea ni caracteres raros"
        )
    return texto


_TEMAS = ("auto", "claro", "oscuro")


def _tema(valor: Any) -> str:
    if valor not in _TEMAS:
        raise DatoInvalido("El tema debe ser «auto», «claro» u «oscuro»")
    return str(valor)


@dataclass(frozen=True)
class _Clave:
    defecto: Any
    validar: Callable[[Any], Any]


_CLAVES: dict[str, _Clave] = {
    "atajo.mantener": _Clave("RightCtrl", _mantener),
    "atajo.alternar": _Clave("<Control><Alt>space", _alternar),
    "atajo.traducir": _Clave("RightAlt", _mantener),  # mejorar y traducir
    "atajo.mejorar": _Clave("RightShift", _mantener),  # solo mejorar
    "traduccion.idioma": _Clave("inglés", _idioma_de_traduccion),
    "audio.dispositivo": _Clave("", _texto),
    "idioma.modo": _Clave("automatico", _idioma),
    "motor.modelo": _Clave(MODELO_POR_DEFECTO, _texto_no_vacio),
    "motor.hilos": _Clave(HILOS_POR_DEFECTO, _hilos),
    "historial.activo": _Clave(True, _booleano),
    "reescritura.activa": _Clave(False, _booleano),
    "interfaz.indicador": _Clave(True, _booleano),
    "interfaz.tema": _Clave("auto", _tema),
    # Si el asistente de primer uso ya se completó o se salteó (002, RP-013).
    "asistente.hecho": _Clave(False, _booleano),
}


_ATAJOS = ("atajo.mantener", "atajo.alternar", "atajo.traducir", "atajo.mejorar")


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
    atajo_traducir: str
    atajo_mejorar: str
    idioma_de_traduccion: str
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
            AccionDeAtajo.TRADUCIR: self.atajo_traducir,
            AccionDeAtajo.MEJORAR: self.atajo_mejorar,
        }

    def con_atajos(
        self,
        mantener: str | None,
        alternar: str | None,
        traducir: str | None = None,
        mejorar: str | None = None,
    ) -> Ajustes:
        """Cambia los atajos solo para esta ejecución (no toca la base)."""
        return replace(
            self,
            atajo_mantener=mantener or self.atajo_mantener,
            atajo_alternar=alternar or self.atajo_alternar,
            atajo_traducir=traducir or self.atajo_traducir,
            atajo_mejorar=mejorar or self.atajo_mejorar,
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
        if clave in _ATAJOS and any(
            _igual(limpio, self.obtener(otra)) for otra in _ATAJOS if otra != clave
        ):
            raise DatoInvalido("Los atajos tienen que ser teclas distintas")
        with self._base:
            self._base.execute(
                "INSERT INTO ajuste (clave, valor) VALUES (?, ?) "
                "ON CONFLICT (clave) DO UPDATE SET valor = excluded.valor",
                (clave, json.dumps(limpio)),
            )

    @staticmethod
    def defecto(clave: str) -> Any:
        return AjustesRepo._definicion(clave).defecto

    def validar_atajos(
        self,
        mantener: str,
        alternar: str,
        traducir: str | None = None,
        mejorar: str | None = None,
    ) -> tuple[str, str, str, str]:
        """Comprueba los cuatro atajos juntos y los devuelve normalizados, sin guardar nada.

        Si no se indica ``traducir`` o ``mejorar`` se usa el que ya estaba guardado.
        """
        validos = (
            _mantener(mantener),
            _alternar(alternar),
            _mantener(traducir if traducir is not None else self.obtener("atajo.traducir")),
            _mantener(mejorar if mejorar is not None else self.obtener("atajo.mejorar")),
        )
        pares = ((a, b) for a in range(4) for b in range(a + 1, 4))
        if any(_igual(validos[a], validos[b]) for a, b in pares):
            raise DatoInvalido("Los atajos tienen que ser teclas distintas")
        return validos

    def establecer_atajos(
        self,
        mantener: str,
        alternar: str,
        traducir: str | None = None,
        mejorar: str | None = None,
    ) -> None:
        """Cambia los atajos a la vez: o se guardan todos o ninguno."""
        valido_mantener, valido_alternar, valido_traducir, valido_mejorar = self.validar_atajos(
            mantener, alternar, traducir, mejorar
        )
        with self._base:
            for clave, valor in (
                ("atajo.mantener", valido_mantener),
                ("atajo.alternar", valido_alternar),
                ("atajo.traducir", valido_traducir),
                ("atajo.mejorar", valido_mejorar),
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
            atajo_traducir=self.obtener("atajo.traducir"),
            atajo_mejorar=self.obtener("atajo.mejorar"),
            idioma_de_traduccion=self.obtener("traduccion.idioma"),
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
