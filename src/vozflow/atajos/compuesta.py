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
        # Las acciones que comparten la misma lista de técnicas (mantener y traducir leen el mismo
        # teclado) arrancan juntas con una sola escucha.
        grupos: dict[tuple[FabricaDeEscucha, ...], dict[AccionDeAtajo, str]] = {}
        for accion, texto in atajos.items():
            grupos.setdefault(tuple(self.candidatas.get(accion, [])), {})[accion] = texto
        activas: list[EscuchaDeAtajos] = []
        try:
            for fabricas, acciones in grupos.items():
                activas.append(self._iniciar_grupo(fabricas, acciones, al_evento))
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

    def _iniciar_grupo(
        self,
        fabricas: tuple[FabricaDeEscucha, ...],
        acciones: Mapping[AccionDeAtajo, str],
        al_evento: AlEvento,
    ) -> EscuchaDeAtajos:
        nombre_del_grupo = " y ".join(a.value for a in acciones)
        errores: list[tuple[str, Exception]] = []
        for fabrica in fabricas:
            escucha = fabrica()
            nombre = type(escucha).__name__
            try:
                escucha.iniciar(acciones, al_evento)
            except InstanciaYaEnEjecucion, ValueError:
                _detener_sin_fallar(escucha)
                raise
            except _FALLOS_RECUPERABLES as error:
                _registro.info("%s no sirvió para %s: %s", nombre, nombre_del_grupo, error)
                errores.append((nombre, error))
                _detener_sin_fallar(escucha)
                continue
            return escucha
        ocupado = next((e for _, e in errores if isinstance(e, AtajoOcupado)), None)
        if ocupado is not None:
            raise ocupado
        motivos = "; ".join(f"{nombre}: {error}" for nombre, error in errores)
        raise NingunAdaptadorSirve(
            f"No se pudo escuchar el atajo «{nombre_del_grupo}» con ninguna técnica"
            + (f" ({motivos})" if motivos else "")
        )


def _detener_sin_fallar(escucha: EscuchaDeAtajos) -> None:
    try:
        escucha.detener()
    except Exception:
        _registro.exception("Falló al detener una escucha de atajos")
