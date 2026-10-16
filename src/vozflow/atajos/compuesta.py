"""Reparte cada acción a su técnica y pasa a la siguiente si una falla (cadena de respaldo)."""

import logging
from collections.abc import Callable, Mapping, Sequence

from vozflow.atajos.evdev import SinPermisoDeTeclado, SinTeclados
from vozflow.atajos.gsettings import ErrorDeGSettings
from vozflow.atajos.puerto import AccionDeAtajo, AlEvento, AtajoOcupado, EscuchaDeAtajos
from vozflow.dbus_portal import ErrorDePortal
from vozflow.servicio_dbus import InstanciaYaEnEjecucion

_registro = logging.getLogger(__name__)

FabricaDeEscucha = Callable[[], EscuchaDeAtajos]

# Fallos que justifican probar otra técnica. Un atajo mal escrito (ValueError) o una segunda
# instancia de vozflow (InstanciaYaEnEjecucion) no se arreglan cambiando de técnica.
_FALLOS_RECUPERABLES = (
    AtajoOcupado,
    SinPermisoDeTeclado,
    SinTeclados,
    ErrorDeGSettings,
    ErrorDePortal,
    OSError,
)


class NingunAdaptadorSirve(Exception):
    """Ninguna técnica pudo escuchar el atajo; el mensaje dice por qué falló cada una."""


class EscuchaCompuesta:
    def __init__(self, candidatas: Mapping[AccionDeAtajo, Sequence[FabricaDeEscucha]]) -> None:
        self.candidatas = {accion: list(fabricas) for accion, fabricas in candidatas.items()}
        self._activas: list[EscuchaDeAtajos] = []
        self._iniciada = False

    def iniciar(self, atajos: Mapping[AccionDeAtajo, str], al_evento: AlEvento) -> None:
        if self._iniciada:
            raise RuntimeError("La escucha ya está iniciada")
        activas: list[EscuchaDeAtajos] = []
        try:
            for accion, texto in atajos.items():
                activas.append(self._iniciar_accion(accion, texto, al_evento))
        except BaseException:
            for escucha in reversed(activas):
                _detener_sin_fallar(escucha)
            raise
        self._activas = activas
        self._iniciada = True

    def detener(self) -> None:
        activas, self._activas = self._activas, []
        self._iniciada = False
        for escucha in reversed(activas):
            _detener_sin_fallar(escucha)

    def _iniciar_accion(
        self, accion: AccionDeAtajo, texto: str, al_evento: AlEvento
    ) -> EscuchaDeAtajos:
        errores: list[tuple[str, Exception]] = []
        for fabrica in self.candidatas.get(accion, []):
            escucha = fabrica()
            nombre = type(escucha).__name__
            try:
                escucha.iniciar({accion: texto}, al_evento)
            except InstanciaYaEnEjecucion, ValueError:
                _detener_sin_fallar(escucha)
                raise
            except _FALLOS_RECUPERABLES as error:
                _registro.info("%s no sirvió para el atajo %s: %s", nombre, accion.value, error)
                errores.append((nombre, error))
                _detener_sin_fallar(escucha)
                continue
            return escucha
        ocupado = next((e for _, e in errores if isinstance(e, AtajoOcupado)), None)
        if ocupado is not None:
            raise ocupado
        motivos = "; ".join(f"{nombre}: {error}" for nombre, error in errores)
        raise NingunAdaptadorSirve(
            f"No se pudo escuchar el atajo «{accion.value}» con ninguna técnica"
            + (f" ({motivos})" if motivos else "")
        )


def _detener_sin_fallar(escucha: EscuchaDeAtajos) -> None:
    try:
        escucha.detener()
    except Exception:
        _registro.exception("Falló al detener una escucha de atajos")
