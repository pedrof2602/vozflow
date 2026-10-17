"""Cómo se muestra cada estado del dictado (RF-028). Sin Qt: se prueba sin pantalla."""

from dataclasses import dataclass

from vozflow.dominio.dictado import EstadoDelDictado


@dataclass(frozen=True)
class VistaDeEstado:
    texto: str
    icono: str
    """Nombre de la forma que se dibuja; el estado no depende solo del color."""
    color: str


_INACTIVO = VistaDeEstado("Listo", "inactivo", "#8a8f98")
_ESCUCHANDO = VistaDeEstado("Escuchando…", "escuchando", "#e5484d")
_TRANSCRIBIENDO = VistaDeEstado("Transcribiendo…", "transcribiendo", "#f5a524")
_ERROR = VistaDeEstado("Error en el dictado", "error", "#7c3aed")

_VISTAS = {
    EstadoDelDictado.INACTIVO: _INACTIVO,
    EstadoDelDictado.ESCUCHANDO: _ESCUCHANDO,
    EstadoDelDictado.TRANSCRIBIENDO: _TRANSCRIBIENDO,
    EstadoDelDictado.INSERTANDO: VistaDeEstado(
        "Insertando…", _TRANSCRIBIENDO.icono, _TRANSCRIBIENDO.color
    ),
    EstadoDelDictado.ERROR: _ERROR,
}


def vista_de(estado: EstadoDelDictado) -> VistaDeEstado:
    return _VISTAS[estado]
