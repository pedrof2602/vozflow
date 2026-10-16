"""Comprobación A: ¿el portal GlobalShortcuts avisa al pulsar *y* al soltar?

    uv run python -m tests.manual.comprobacion_atajos              # con la prueba real
    uv run python -m tests.manual.comprobacion_atajos --prueba-en-seco

Pasa si llegan ``Activated`` y ``Deactivated`` y la diferencia coincide con lo que mantuviste la
tecla. Anotá además si GNOME vuelve a pedir confirmación en una segunda ejecución.
Plan B si falla: mantener-para-hablar con ``evdev`` (la línea base ya lo contempla).
"""

import argparse
import time
from typing import Any

from tests.manual._comun import guardar  # noqa: E402
from vozflow.dbus_portal import ClientePortal, nuevo_token, valor  # noqa: E402

GS = "org.freedesktop.portal.GlobalShortcuts"
SESION = "org.freedesktop.portal.Session"


def emparejar(eventos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Une cada ``Activated`` con el ``Deactivated`` que le sigue."""
    pares: list[dict[str, Any]] = []
    abierto: dict[str, Any] | None = None
    for evento in eventos:
        if evento["miembro"] == "Activated":
            abierto = evento
        elif evento["miembro"] == "Deactivated" and abierto is not None:
            pares.append(
                {
                    "atajo": evento["atajo"],
                    "mantenida_portal_ms": evento["marca_portal"] - abierto["marca_portal"],
                    "mantenida_local_ms": round((evento["t_local"] - abierto["t_local"]) * 1000),
                }
            )
            abierto = None
    return pares


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--atajo", default="CTRL+ALT+d", help="atajo que se propone a GNOME")
    analizador.add_argument("--segundos", type=int, default=40)
    analizador.add_argument("--prueba-en-seco", action="store_true")
    argumentos = analizador.parse_args()

    cliente = ClientePortal.abrir()
    cliente.registrar_aplicacion()
    print(f"Portal GlobalShortcuts, versión {cliente.version_de(GS)}")
    sesion = cliente.solicitar(
        GS,
        "CreateSession",
        "a{sv}",
        lambda t: ({"handle_token": ("s", t), "session_handle_token": ("s", nuevo_token())},),
    )
    ruta_sesion = valor(sesion.resultados, "session_handle")
    print("Sesión creada:", ruta_sesion)
    if argumentos.prueba_en_seco:
        cliente.llamar(SESION, "Close", "", (), ruta=ruta_sesion)
        print("Prueba en seco terminada: el cableado funciona (no se enlazó ningún atajo).")
        return 0

    eventos: list[dict[str, Any]] = []
    with cliente.escuchar(GS, ["Activated", "Deactivated"]) as senales:
        print("\nGNOME puede mostrar ahora un diálogo para confirmar el atajo: aceptalo.")
        inicio = time.perf_counter()
        enlace = cliente.solicitar(
            GS,
            "BindShortcuts",
            "oa(sa{sv})sa{sv}",
            lambda t: (
                ruta_sesion,
                [
                    (
                        "vozflow-mantener",
                        {
                            "description": ("s", "Mantener para hablar (comprobación de vozflow)"),
                            "preferred_trigger": ("s", argumentos.atajo),
                        },
                    )
                ],
                "",
                {"handle_token": ("s", t)},
            ),
            timeout_s=180,
        )
        tardo = time.perf_counter() - inicio
        enlazados = valor(enlace.resultados, "shortcuts", [])
        print(f"Atajos enlazados: {[a[0] for a in enlazados]}")
        print(
            f"BindShortcuts tardó {tardo:.1f} s ({'sin diálogo' if tardo < 1.0 else 'con diálogo'})"
        )
        print(
            f"\nMantené el atajo ~2 s y soltalo. Repetilo 3 veces. Tenés {argumentos.segundos} s."
        )
        t0 = time.perf_counter()
        fin = t0 + argumentos.segundos
        while time.perf_counter() < fin:
            senal = senales.recibir(timeout_s=0.5)
            if senal is None:
                continue
            evento = {
                "miembro": senal.miembro,
                "atajo": senal.cuerpo[1],
                "marca_portal": int(senal.cuerpo[2]),
                "t_local": time.perf_counter() - t0,
            }
            eventos.append(evento)
            print(f"  {evento['t_local']:6.2f} s  {senal.miembro}  ({senal.cuerpo[1]})")
    cliente.llamar(SESION, "Close", "", (), ruta=ruta_sesion)

    pares = emparejar(eventos)
    pasa = bool(pares)
    print(f"\nPares Activated→Deactivated: {len(pares)}")
    for par in pares:
        print(
            f"  mantenida {par['mantenida_local_ms']} ms (portal: {par['mantenida_portal_ms']} ms)"
        )
    print("RESULTADO:", "PASA" if pasa else "FALLA (plan B: evdev para mantener-para-hablar)")
    destino = guardar(
        "comprobacion-a",
        {
            "atajo_propuesto": argumentos.atajo,
            "bind_tardo_s": round(tardo, 2),
            "hubo_dialogo": tardo >= 1.0,
            "eventos": eventos,
            "pares": pares,
            "pasa": pasa,
        },
    )
    print("Resultado guardado en", destino)
    return 0 if pasa else 1


if __name__ == "__main__":
    raise SystemExit(main())
