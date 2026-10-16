"""Comprobación B: ¿el portal RemoteDesktop escribe ñ y tildes, y recuerda el permiso?

    uv run python -m tests.manual.comprobacion_escritorio_remoto              # prueba real
    uv run python -m tests.manual.comprobacion_escritorio_remoto --prueba-en-seco

Escribe en la ventana que tenga el foco: abrí antes un EDITOR DE TEXTO VACÍO (no una terminal).
Pasa si salen «cañón, árbol, pingüino ¿sí?», en la segunda ejecución no pide autorización y el
portapapeles no se toca. Anotá si GNOME mostró un indicador en la barra superior mientras la
sesión estuvo abierta (decide si la sesión se mantiene abierta o se abre por dictado).
Plan B si falla: ``ydotool key`` para los atajos de pegado más el portapapeles de Qt.
"""

import argparse
import time

from tests.manual._comun import cuenta_regresiva, guardar, preguntar  # noqa: E402
from vozflow import rutas  # noqa: E402
from vozflow.dbus_portal import ClientePortal, nuevo_token, valor  # noqa: E402
from vozflow.insercion.teclas import a_keysym  # noqa: E402

RD = "org.freedesktop.portal.RemoteDesktop"
SESION = "org.freedesktop.portal.Session"
TECLADO = 1
PERSISTIR_HASTA_REVOCAR = 2
TEXTO_CORTO = "cañón, árbol, pingüino ¿sí?"
TEXTO_LARGO = ("Velocidad de escritura 123 ñandú. " * 15)[:500]


def escribir(cliente: ClientePortal, sesion: str, texto: str) -> float:
    """Escribe ``texto`` pulsando y soltando cada tecla. Devuelve los segundos que tardó."""
    inicio = time.perf_counter()
    for caracter in texto:
        keysym = a_keysym(caracter)
        for estado in (1, 0):
            cliente.llamar(RD, "NotifyKeyboardKeysym", "oa{sv}iu", (sesion, {}, keysym, estado))
    return time.perf_counter() - inicio


def main() -> int:
    analizador = argparse.ArgumentParser(description=__doc__)
    analizador.add_argument("--prueba-en-seco", action="store_true")
    argumentos = analizador.parse_args()

    ruta_token = rutas.ruta_token_portal()
    token_guardado = ruta_token.read_text().strip() if ruta_token.is_file() else None
    print(f"Token de restauración guardado: {'sí' if token_guardado else 'no (primera vez)'}")

    cliente = ClientePortal.abrir()
    cliente.registrar_aplicacion()
    print(f"Portal RemoteDesktop, versión {cliente.version_de(RD)}")
    sesion = valor(
        cliente.solicitar(
            RD,
            "CreateSession",
            "a{sv}",
            lambda t: ({"handle_token": ("s", t), "session_handle_token": ("s", nuevo_token())},),
        ).resultados,
        "session_handle",
    )

    def opciones(t: str) -> tuple[object, ...]:
        extra = {"restore_token": ("s", token_guardado)} if token_guardado else {}
        return (
            sesion,
            {
                "handle_token": ("s", t),
                "types": ("u", TECLADO),
                "persist_mode": ("u", PERSISTIR_HASTA_REVOCAR),
                **extra,
            },
        )

    cliente.solicitar(RD, "SelectDevices", "oa{sv}", opciones)
    print("SelectDevices: OK")
    if argumentos.prueba_en_seco:
        cliente.llamar(SESION, "Close", "", (), ruta=sesion)
        print("Prueba en seco terminada: el cableado funciona (no se abrió ningún diálogo).")
        return 0

    print("\nGNOME puede mostrar ahora un diálogo de autorización: aceptalo.")
    inicio = time.perf_counter()
    inicio_sesion = cliente.solicitar(
        RD,
        "Start",
        "osa{sv}",
        lambda t: (sesion, "", {"handle_token": ("s", t)}),
        timeout_s=180,
    )
    tardo = time.perf_counter() - inicio
    hubo_dialogo = tardo >= 1.0
    nuevo_token_guardado = valor(inicio_sesion.resultados, "restore_token")
    print(f"Start tardó {tardo:.1f} s ({'con diálogo' if hubo_dialogo else 'sin diálogo'})")
    if nuevo_token_guardado:
        rutas.asegurar(ruta_token.parent)
        ruta_token.write_text(nuevo_token_guardado)
        ruta_token.chmod(0o600)
        print("Token de restauración guardado para la próxima vez.")

    cuenta_regresiva(5, "Poné el cursor en un editor de texto VACÍO. Voy a escribir en 5 segundos…")
    escribir(cliente, sesion, TEXTO_CORTO + " ")
    segundos_largo = escribir(cliente, sesion, TEXTO_LARGO)
    velocidad = len(TEXTO_LARGO) / segundos_largo
    print(f"\n500 caracteres en {segundos_largo:.1f} s ({velocidad:.0f} caracteres por segundo)")

    print("\nMirá la barra superior de GNOME durante estos 8 segundos (la sesión sigue abierta)…")
    time.sleep(8)
    cliente.llamar(SESION, "Close", "", (), ruta=sesion)
    print("Sesión cerrada.\n")

    salieron_bien = preguntar(f"¿Salió bien «{TEXTO_CORTO}» (ñ, tildes, diéresis y ¿)?")
    hubo_indicador = preguntar(
        "¿Viste un indicador en la barra superior mientras la sesión estaba abierta?"
    )
    pasa = salieron_bien
    print("RESULTADO:", "PASA" if pasa else "FALLA (plan B: ydotool key + portapapeles de Qt)")
    destino = guardar(
        "comprobacion-b",
        {
            "primera_vez": token_guardado is None,
            "start_tardo_s": round(tardo, 2),
            "hubo_dialogo": hubo_dialogo,
            "caracteres_por_segundo": round(velocidad),
            "salieron_bien_enie_y_tildes": salieron_bien,
            "hubo_indicador_en_la_barra": hubo_indicador,
            "pasa": pasa,
        },
    )
    print("Resultado guardado en", destino)
    return 0 if pasa else 1


if __name__ == "__main__":
    raise SystemExit(main())
