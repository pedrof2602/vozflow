"""Un dictado ya transcrito (RF-027). El audio nunca se guarda: solo el texto y los tiempos."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

EstadoDelHistorial = Literal["insertado", "no_insertado", "error"]
ESTADOS_DEL_HISTORIAL: tuple[str, ...] = ("insertado", "no_insertado", "error")


@dataclass(frozen=True)
class Dictado:
    id: int
    creado_en: datetime
    texto_crudo: str
    texto_final: str
    idioma: str
    duracion_audio_ms: int
    duracion_proceso_ms: int
    aplicacion: str
    modo_id: int | None
    reescrito: bool
    proveedor: str
    estado: EstadoDelHistorial
