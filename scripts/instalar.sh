#!/usr/bin/env bash
# Instala (o actualiza) vozflow en tu computadora: un solo comando, y se puede repetir.
#
#   ./scripts/instalar.sh
#   curl -fsSL https://raw.githubusercontent.com/pedrof2602/vozflow/main/scripts/instalar.sh | bash
#
# Códigos de salida: 0 listo · 1 error durante la instalación · 2 requisito que no se cumple
# (no se tocó nada) · 3 cancelaste.
#
# Para pruebas se puede cambiar el entorno con variables VOZFLOW_* (ver más abajo).

set -u

REPO="${VOZFLOW_REPO:-https://github.com/pedrof2602/vozflow.git}"
DESTINO="${VOZFLOW_DIRECTORIO:-$HOME/.local/share/vozflow-app}"
ENTRADA="${VOZFLOW_ENTRADA:-/dev/tty}"
OS_RELEASE="${VOZFLOW_OS_RELEASE:-/etc/os-release}"
UDEV_DIR="${VOZFLOW_UDEV_DIR:-/etc/udev/rules.d}"
MODULOS_DIR="${VOZFLOW_MODULOS_DIR:-/etc/modules-load.d}"
ESPACIO_MINIMO_MB=3000
MEMORIA_AVISO_MB=4096
USUARIO="${USER:-$(id -un)}"
# El nombre se arma dentro del bloque que corre con permisos de administrador: solo los
# caracteres que admite un nombre de usuario de Linux.
case "$USUARIO" in
    "" | *[!A-Za-z0-9._-]* | -*)
        printf '%s\n' "✗ El nombre de usuario («$USUARIO») tiene caracteres que no puedo usar con seguridad." >&2
        exit 1
        ;;
esac

decir() { printf '%s\n' "$*"; }

# ---- salidas ---------------------------------------------------------------------------------------

requisito_no_cumplido() {
    decir ""
    decir "✗ $1"
    shift
    for linea in "$@"; do decir "  $linea"; done
    decir ""
    decir "No cambié nada en tu computadora."
    exit 2
}

error_en_la_instalacion() {
    decir ""
    decir "✗ $1"
    shift
    for linea in "$@"; do decir "  $linea"; done
    exit 1
}

cancelar() {
    decir ""
    decir "Cancelado. No cambié nada."
    exit 3
}

# ---- preguntas ---------------------------------------------------------------------------------------
# preguntar "texto" S|N  -> 0 si la respuesta es sí. Con VOZFLOW_SIN_PREGUNTAS=1 se usa el valor
# por defecto sin preguntar.

preguntar() {
    local texto="$1" defecto="$2" opciones respuesta
    if [ "${VOZFLOW_SIN_PREGUNTAS:-}" = "1" ]; then
        [ "$defecto" = "S" ]
        return
    fi
    if [ "$defecto" = "S" ]; then opciones="[S/n]"; else opciones="[s/N]"; fi
    printf '%s %s ' "$texto" "$opciones"
    if [ -z "${ENTRADA_ABIERTA:-}" ]; then
        # Se abre una sola vez (el script puede venir por una tubería, así que no es la entrada).
        if ! { exec 3< "$ENTRADA"; } 2> /dev/null; then
            decir ""
            decir "No puedo preguntarte nada porque no hay una terminal."
            decir "Corré este comando desde una terminal."
            exit 3
        fi
        ENTRADA_ABIERTA=1
    fi
    if ! read -r respuesta <&3; then
        decir ""
        decir "No recibí tu respuesta."
        exit 3
    fi
    case "$respuesta" in
        "") [ "$defecto" = "S" ] ;;
        [sSyY]*) return 0 ;;
        *) return 1 ;;
    esac
}

# ---- comprobaciones (antes de cambiar nada) ----------------------------------------------------------

FAMILIA=""
NOMBRE_DEL_SISTEMA=""

detectar_el_sistema() {
    if [ ! -r "$OS_RELEASE" ]; then
        requisito_no_cumplido "No pude saber qué sistema tenés." \
            "vozflow todavía solo se instala en Linux con GNOME (probado en Fedora)."
    fi
    local datos id id_like
    datos="$(. "$OS_RELEASE" && printf '%s|%s|%s' "${ID:-}" "${ID_LIKE:-}" "${PRETTY_NAME:-${NAME:-Linux}}")"
    id="${datos%%|*}"
    datos="${datos#*|}"
    id_like="${datos%%|*}"
    NOMBRE_DEL_SISTEMA="${datos#*|}"
    case " $id $id_like " in
        *" fedora "* | *" rhel "*) FAMILIA="fedora" ;;
        *" debian "* | *" ubuntu "*) FAMILIA="debian" ;;
        *)
            requisito_no_cumplido "Tu sistema ($NOMBRE_DEL_SISTEMA) todavía no está soportado." \
                "vozflow funciona en Fedora y en sistemas parecidos a Debian o Ubuntu, con GNOME." \
                "Si querés ayudar a que funcione en el tuyo, avisanos en el repositorio."
            ;;
    esac
}

comprobar_el_escritorio() {
    case "${XDG_CURRENT_DESKTOP:-}" in
        *GNOME*) ;;
        *)
            requisito_no_cumplido "No encuentro el escritorio GNOME." \
                "vozflow necesita GNOME. Si lo tenés, abrí esta terminal dentro de tu sesión gráfica." \
                "Otros escritorios (KDE, Xfce, etc.) todavía no están soportados."
            ;;
    esac
    if [ "${XDG_SESSION_TYPE:-}" != "wayland" ]; then
        requisito_no_cumplido "Tu sesión no usa Wayland (usa «${XDG_SESSION_TYPE:-desconocida}»)." \
            "vozflow necesita Wayland. En la pantalla de ingreso elegí «GNOME» (no «GNOME en Xorg»)."
    fi
}

comprobar_el_espacio() {
    local libre
    libre="${VOZFLOW_ESPACIO_LIBRE_MB:-$(df -Pm "$HOME" 2>/dev/null | awk 'NR==2 {print $4}')}"
    libre="${libre:-0}"
    if [ "$libre" -lt "$ESPACIO_MINIMO_MB" ]; then
        requisito_no_cumplido "Hay poco espacio libre: ${libre} MB." \
            "vozflow necesita unos 3 GB (el programa y el modelo de voz)." \
            "Liberá espacio y volvé a correr este comando."
    fi
    ESPACIO_LIBRE_MB="$libre"
}

avisar_si_hay_poca_memoria() {
    local memoria
    memoria="${VOZFLOW_MEMORIA_MB:-$(awk '/MemTotal/ {print int($2 / 1024)}' /proc/meminfo 2>/dev/null)}"
    memoria="${memoria:-0}"
    if [ "$memoria" -lt "$MEMORIA_AVISO_MB" ]; then
        decir "! Tu computadora tiene poca memoria (${memoria} MB): vozflow puede andar lento."
    fi
}

# ---- lo que se instala con permisos de administrador ---------------------------------------------------

PAQUETES=""
ORDEN_DE_PAQUETES=""

elegir_los_paquetes() {
    if [ "$FAMILIA" = "fedora" ]; then
        PAQUETES="git wl-clipboard ydotool portaudio gnome-keyring python3-gobject at-spi2-core gcc kernel-headers"
        ORDEN_DE_PAQUETES="dnf install -y $PAQUETES"
    else
        PAQUETES="git curl wl-clipboard ydotool libportaudio2 gnome-keyring python3-gi gir1.2-atspi-2.0 build-essential linux-libc-dev"
        ORDEN_DE_PAQUETES="apt-get update && apt-get install -y $PAQUETES"
    fi
}

contar_lo_que_se_hara() {
    decir ""
    decir "Para dejar todo listo necesito permisos de administrador una sola vez. Voy a:"
    decir "  • Instalar estos programas: $PAQUETES"
    decir "  • Darle permiso a tu usuario para leer el teclado (grupo «input»)"
    decir "  • Dejar listo el teclado virtual, para pegar el texto donde estés escribiendo"
    decir ""
}

instalar_con_permisos() {
    local bloque
    bloque="set -e
$ORDEN_DE_PAQUETES
usermod -aG input \"$USUARIO\"
mkdir -p \"$UDEV_DIR\" \"$MODULOS_DIR\"
printf '%s\\n' 'KERNEL==\"uinput\", GROUP=\"input\", MODE=\"0660\"' > \"$UDEV_DIR/60-vozflow-uinput.rules\"
printf 'uinput\\n' > \"$MODULOS_DIR/vozflow-uinput.conf\"
modprobe uinput || true
udevadm control --reload-rules || true
udevadm trigger --name-match=uinput || true"
    if ! sudo bash -c "$bloque"; then
        error_en_la_instalacion "No pude instalar los programas necesarios." \
            "Revisá que tu contraseña esté bien y que tengas conexión a internet." \
            "Después volvé a correr este mismo comando: retoma desde acá."
    fi
}

grupo_input_ya_activo() {
    local grupos="${VOZFLOW_GRUPOS_ACTIVOS:-$(id -nG 2>/dev/null)}"
    case " $grupos " in *" input "*) return 0 ;; *) return 1 ;; esac
}

# ---- uv y el proyecto -----------------------------------------------------------------------------------

asegurar_uv() {
    export PATH="$HOME/.local/bin:$PATH"
    if command -v uv > /dev/null 2>&1; then return 0; fi
    decir ""
    decir "Falta «uv», el programa que instala y maneja las piezas de vozflow."
    decir "Voy a bajar su instalador oficial de https://astral.sh/uv/install.sh y a ejecutarlo."
    if ! preguntar "¿Lo instalo?" S; then cancelar; fi
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        error_en_la_instalacion "No pude instalar uv." \
            "Revisá tu conexión a internet y volvé a correr este comando."
    fi
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv > /dev/null 2>&1 || error_en_la_instalacion "Instalé uv pero no lo encuentro." \
        "Cerrá y abrí la terminal, y volvé a correr este comando."
}

PROYECTO=""

buscar_o_bajar_el_proyecto() {
    local aqui
    aqui="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." 2> /dev/null && pwd)" || aqui=""
    if [ -n "$aqui" ] && [ -f "$aqui/pyproject.toml" ] && grep -q '^name = "vozflow"' "$aqui/pyproject.toml"; then
        PROYECTO="$aqui"
        if [ -d "$PROYECTO/.git" ]; then
            git -C "$PROYECTO" pull --ff-only > /dev/null 2>&1 || decir "! No pude actualizar el código (sigo con el que tenés)."
        fi
        return 0
    fi
    PROYECTO="$DESTINO"
    if [ -d "$DESTINO/.git" ]; then
        git -C "$DESTINO" pull --ff-only > /dev/null 2>&1 || decir "! No pude actualizar el código (sigo con el que tenés)."
    else
        mkdir -p "$(dirname "$DESTINO")"
        if ! git clone --quiet "$REPO" "$DESTINO"; then
            error_en_la_instalacion "No pude bajar vozflow." \
                "Revisá tu conexión a internet y volvé a correr este comando."
        fi
    fi
}

vozflow() {
    uv run --project "$PROYECTO" python -m vozflow "$@"
}

# ---- el programa ------------------------------------------------------------------------------------

principal() {
    decir "vozflow — instalación"
    decir ""
    decir "Compruebo tu computadora…"
    detectar_el_sistema
    decir "✓ Sistema: $NOMBRE_DEL_SISTEMA"
    comprobar_el_escritorio
    decir "✓ Escritorio GNOME con Wayland"
    comprobar_el_espacio
    decir "✓ Espacio libre: ${ESPACIO_LIBRE_MB} MB"
    avisar_si_hay_poca_memoria

    elegir_los_paquetes
    contar_lo_que_se_hara
    if ! preguntar "¿Seguimos?" S; then cancelar; fi
    instalar_con_permisos
    decir "✓ Programas y permisos listos"

    asegurar_uv
    buscar_o_bajar_el_proyecto
    decir "✓ Código en $PROYECTO"

    decir ""
    decir "Instalo las piezas de vozflow (puede tardar unos minutos)…"
    if ! (cd "$PROYECTO" && uv sync --locked); then
        error_en_la_instalacion "No pude instalar las piezas de vozflow." \
            "Revisá tu conexión a internet y volvé a correr este mismo comando."
    fi
    decir "✓ Piezas instaladas"

    decir ""
    decir "Bajo el modelo de voz (una sola vez, unos 480 MB)…"
    if ! vozflow descargar-modelo; then
        error_en_la_instalacion "No pude bajar el modelo de voz." \
            "Necesito internet esta única vez. Conectate y volvé a correr este mismo comando:" \
            "retoma lo que ya se bajó."
    fi
    decir "✓ Modelo de voz listo"

    vozflow entrada instalar > /dev/null 2>&1 || decir "! No pude ponerte vozflow en el menú de aplicaciones."
    decir "✓ vozflow está en tu menú de aplicaciones"

    decir ""
    if preguntar "¿Querés que vozflow arranque sola cuando prendés la computadora?" N; then
        vozflow autoinicio activar > /dev/null 2>&1 || decir "! No pude activar el arranque automático."
        decir "✓ vozflow arrancará con tu sesión"
    fi

    decir ""
    decir "¡Listo!"
    if ! grupo_input_ya_activo; then
        decir ""
        decir "Falta una cosa: cerrá sesión y volvé a entrar para que el teclado funcione."
        decir "(Mientras tanto vozflow anda con la tecla de empezar y terminar.)"
    fi
    decir ""
    decir "Abrí vozflow desde el menú de aplicaciones: buscá «vozflow»."
    exit 0
}

principal "$@"
