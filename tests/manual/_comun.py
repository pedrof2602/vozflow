"""Ayudas compartidas por los guiones de comprobación a mano (no son pruebas de pytest)."""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from vozflow import rutas


def guardar(nombre: str, datos: dict[str, Any]) -> Path:
    """Guarda el resultado fuera del repositorio, para pegarlo en docs/validacion."""
    carpeta = rutas.asegurar(rutas.directorio_pruebas())
    destino = carpeta / f"{nombre}.json"
    datos = {"fecha": datetime.now().isoformat(timespec="seconds"), **datos}
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    destino.chmod(0o600)
    return destino


def cuenta_regresiva(segundos: int, mensaje: str) -> None:
    print(mensaje)
    for restante in range(segundos, 0, -1):
        print(f"  {restante}…", end="\r", flush=True)
        time.sleep(1)
    print("  ya       ")


def preguntar(texto: str) -> bool:
    while True:
        respuesta = input(f"{texto} [s/n] ").strip().lower()
        if respuesta in ("s", "si", "sí"):
            return True
        if respuesta in ("n", "no"):
            return False
