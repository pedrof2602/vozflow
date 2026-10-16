"""Comprobación C: ¿AT-SPI identifica la ventana activa en tus cuatro aplicaciones?

    uv run python -m tests.manual.comprobacion_ventana

Tenés 6 segundos por aplicación para darle el foco (abrila antes). Pasa si las cuatro se
identifican en menos de 500 ms. Plan B si Chrome, Teams u Obsidian no aparecen: marcar la
aplicación a mano como terminal en los ajustes.
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Any

from tests.manual._comun import cuenta_regresiva, guardar  # noqa: E402

AYUDANTE = Path(__file__).resolve().parents[2] / "src/vozflow/ventana/ayudante_atspi.py"
APLICACIONES = [
    ("Ptyxis (terminal)", ("ptyxis",)),
    ("Google Chrome", ("chrom",)),
    ("Portal for Teams", ("teams", "portal")),
    ("Obsidian", ("obsidian",)),
]
LIMITE_MS = 500


def consultar() -> tuple[dict[str, Any] | None, float]:
    inicio = time.perf_counter()
    salida = subprocess.run(
        ["/usr/bin/python3", "-I", str(AYUDANTE)], capture_output=True, text=True, timeout=10
    )
    milisegundos = (time.perf_counter() - inicio) * 1000
    return (
        json.loads(salida.stdout) if salida.returncode == 0 and salida.stdout.strip() else None
    ), milisegundos


def main() -> int:
    resultados = []
    for nombre, esperados in APLICACIONES:
        cuenta_regresiva(6, f"\nDale el foco a «{nombre}»…")
        ventana, ms = consultar()
        detectada = (ventana or {}).get("aplicacion", "")
        acierta = any(e in str(detectada) for e in esperados)
        a_tiempo = ms < LIMITE_MS
        print(
            f"  detectada: {detectada or '— nada —'} | {ms:.0f} ms | "
            f"{'OK' if acierta and a_tiempo else 'FALLA'}"
            f"{'' if a_tiempo else ' (más de 500 ms)'}"
        )
        resultados.append(
            {
                "aplicacion": nombre,
                "detectada": detectada,
                "ms": round(ms),
                "acierta": acierta,
                "a_tiempo": a_tiempo,
            }
        )
    pasa = all(r["acierta"] and r["a_tiempo"] for r in resultados)
    print(
        "\nRESULTADO:",
        "PASA" if pasa else "FALLA (plan B: marcar la aplicación a mano como terminal)",
    )
    destino = guardar("comprobacion-c", {"resultados": resultados, "pasa": pasa})
    print("Resultado guardado en", destino)
    return 0 if pasa else 1


if __name__ == "__main__":
    raise SystemExit(main())
