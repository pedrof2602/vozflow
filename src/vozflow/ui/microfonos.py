"""La lista de micrófonos que se ofrece en un combo (los ajustes y el asistente la comparten)."""

from collections.abc import Callable

from PySide6.QtWidgets import QComboBox

from vozflow.audio.captura import Dispositivo


def llenar_combo_de_microfonos(
    combo: QComboBox, guardado: str, listar: Callable[[], list[Dispositivo]]
) -> int:
    """Llena ``combo`` con el predeterminado y cada micrófono; devuelve cuántos micrófonos hay.

    Un micrófono guardado que hoy no está enchufado se conserva, marcado como no conectado, para
    que abrir la página no cambie lo elegido en silencio.
    """
    combo.clear()
    combo.addItem("Predeterminado del sistema", "")
    try:
        dispositivos = listar()
    except Exception:  # sin sonido o sin permisos: la pantalla igual tiene que abrir
        dispositivos = []
    nombres = [d.nombre for d in dispositivos]
    for dispositivo in dispositivos:
        marca = " (predeterminado)" if dispositivo.es_predeterminado else ""
        combo.addItem(f"{dispositivo.nombre}{marca}", dispositivo.nombre)
    if guardado and guardado not in nombres:
        combo.addItem(f"{guardado} (no conectado)", guardado)
    combo.setCurrentIndex(max(0, combo.findData(guardado)))
    return len(dispositivos)
