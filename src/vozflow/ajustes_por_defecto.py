"""Valores por defecto de la configuración.

La persistencia llega en el lote 3 y la edición desde la interfaz, en el lote 5. Los atajos
evitan F6, F7 y F8, que usa OpenWhispr si está instalado.
"""

from dataclasses import dataclass, replace

from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.transcripcion.faster_whisper import HILOS_POR_DEFECTO, MODELO_POR_DEFECTO


@dataclass(frozen=True)
class Ajustes:
    atajo_mantener: str = "RightCtrl"
    atajo_alternar: str = "<Control><Alt>space"
    modelo: str = MODELO_POR_DEFECTO
    hilos: int = HILOS_POR_DEFECTO

    def atajos(self) -> dict[AccionDeAtajo, str]:
        return {
            AccionDeAtajo.MANTENER: self.atajo_mantener,
            AccionDeAtajo.ALTERNAR: self.atajo_alternar,
        }

    def con_atajos(self, mantener: str | None, alternar: str | None) -> Ajustes:
        return replace(
            self,
            atajo_mantener=mantener or self.atajo_mantener,
            atajo_alternar=alternar or self.atajo_alternar,
        )
