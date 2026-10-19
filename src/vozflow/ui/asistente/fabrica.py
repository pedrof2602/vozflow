"""Arma los pasos del asistente de primer uso (002, RP-007): solo los que hacen falta."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.audio.captura import Dispositivo
from vozflow.diagnostico import Sondas
from vozflow.permisos import comprobar_permisos
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.ui.asistente.arranque import PasoArranque
from vozflow.ui.asistente.base import PasoDelAsistente
from vozflow.ui.asistente.microfono import Medidor, PasoMicrofono
from vozflow.ui.asistente.permisos import PasoPermisos, hay_permisos_pendientes
from vozflow.ui.asistente.prueba import PasoPrueba, Probador
from vozflow.ui.asistente.tecla import PasoTecla


@dataclass
class ContextoDelAsistente:
    """Todo lo que los pasos necesitan de afuera."""

    ajustes: AjustesRepo
    aplicar_atajos: Callable[[Mapping[AccionDeAtajo, str]], None]
    listar_dispositivos: Callable[[], list[Dispositivo]]
    sondas: Sondas
    copiar: Callable[[str], None]
    teclas_del_teclado: Callable[[], set[int]]
    medidor: Medidor
    probador: Probador
    autoinicio_activo: Callable[[], bool]
    fijar_autoinicio: Callable[[bool], None]


def crear_pasos(contexto: ContextoDelAsistente) -> list[PasoDelAsistente]:
    """Los permisos, solo si falta alguno; después micrófono, tecla, prueba y arranque."""
    pasos: list[PasoDelAsistente] = []
    if hay_permisos_pendientes(comprobar_permisos(contexto.sondas)):
        pasos.append(PasoPermisos(lambda: comprobar_permisos(contexto.sondas), contexto.copiar))
    pasos += [
        PasoMicrofono(contexto.ajustes, contexto.listar_dispositivos, contexto.medidor),
        PasoTecla(contexto.ajustes, contexto.aplicar_atajos, contexto.teclas_del_teclado),
        PasoPrueba(contexto.probador),
        PasoArranque(contexto.autoinicio_activo, contexto.fijar_autoinicio),
    ]
    return pasos
