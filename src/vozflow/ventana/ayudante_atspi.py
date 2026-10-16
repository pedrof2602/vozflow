"""Ayudante que dice cuál es la ventana activa, consultando AT-SPI.

Corre con el Python del sistema (``/usr/bin/python3 -I``) porque necesita ``gi``, que no está en el
entorno de uv. No importa nada de vozflow. Imprime una línea de JSON: ``{"aplicacion": ...,
"titulo": ..., "pid": ...}``, o ``null`` si no hay ventana activa. El título puede traer datos
personales: quien lo reciba no debe registrarlo.
"""

import json

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi  # noqa: E402


def ventana_activa() -> dict[str, object] | None:
    escritorio = Atspi.get_desktop(0)
    for i in range(escritorio.get_child_count()):
        aplicacion = escritorio.get_child_at_index(i)
        if aplicacion is None:
            continue
        for j in range(aplicacion.get_child_count()):
            try:
                ventana = aplicacion.get_child_at_index(j)
                if ventana is None or not ventana.get_state_set().contains(Atspi.StateType.ACTIVE):
                    continue
                return {
                    "aplicacion": (aplicacion.get_name() or "").lower(),
                    "titulo": ventana.get_name() or "",
                    "pid": aplicacion.get_process_id(),
                }
            except Exception:  # una ventana que desaparece mientras se consulta
                continue
    return None


if __name__ == "__main__":
    print(json.dumps(ventana_activa(), ensure_ascii=False))
