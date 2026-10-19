#!/usr/bin/env bash
# Quita vozflow de tu computadora. Retira lo que puso la instalación y PREGUNTA antes de borrar
# nada que no se pueda recuperar (tus datos, el modelo de voz, tus claves y los permisos).
#
#   ./scripts/desinstalar.sh
#
# Códigos de salida: 0 listo · 1 error · 3 cancelaste.

set -u

DESTINO="${VOZFLOW_DIRECTORIO:-$HOME/.local/share/vozflow-app}"
ENTRADA="${VOZFLOW_ENTRADA:-/dev/tty}"
UDEV_DIR="${VOZFLOW_UDEV_DIR:-/etc/udev/rules.d}"
MODULOS_DIR="${VOZFLOW_MODULOS_DIR:-/etc/modules-load.d}"
DATOS="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
MODELOS="${HF_HOME:-$HOME/.cache/huggingface}/hub"
USUARIO="${USER:-$(id -un)}"
MARCA_DE_ENTRADA="X-Vozflow-Generado=true"
MARCA_DEL_ICONO="Generado por vozflow"

decir() { printf '%s\n' "$*"; }

cancelar() {
    decir ""
    decir "Cancelado. No cambié nada."
    exit 3
}

# preguntar "texto" S|N -> 0 si la respuesta es sí. Con VOZFLOW_SIN_PREGUNTAS=1 se usa el valor
# por defecto: lo irreversible nunca se acepta solo.
preguntar() {
    local texto="$1" defecto="$2" opciones respuesta
    if [ "${VOZFLOW_SIN_PREGUNTAS:-}" = "1" ]; then
        [ "$defecto" = "S" ]
        return
    fi
    if [ "$defecto" = "S" ]; then opciones="[S/n]"; else opciones="[s/N]"; fi
    printf '%s %s ' "$texto" "$opciones"
    if [ -z "${ENTRADA_ABIERTA:-}" ]; then
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

# Borra un archivo solo si lo generó vozflow (lleva su marca). Devuelve 0 si lo borró.
retirar_si_es_nuestro() {
    local archivo="$1" marca="$2"
    if [ -f "$archivo" ] && grep -q "$marca" "$archivo" 2> /dev/null; then
        rm -f "$archivo"
        return 0
    fi
    return 1
}

PROYECTO=""

buscar_el_proyecto() {
    local aqui
    aqui="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." 2> /dev/null && pwd)" || aqui=""
    if [ -n "$aqui" ] && [ -f "$aqui/pyproject.toml" ] && grep -q '^name = "vozflow"' "$aqui/pyproject.toml"; then
        PROYECTO="$aqui"
    elif [ -f "$DESTINO/pyproject.toml" ]; then
        PROYECTO="$DESTINO"
    fi
}

principal() {
    decir "vozflow — desinstalación"
    decir ""
    decir "Voy a sacar vozflow del menú de aplicaciones y del arranque."
    decir "Después te pregunto por lo demás, una cosa por vez: no borro nada tuyo sin preguntarte."
    decir ""
    if ! preguntar "¿Seguimos?" S; then cancelar; fi
    export PATH="$HOME/.local/bin:$PATH"
    buscar_el_proyecto

    local quito=0
    retirar_si_es_nuestro "$DATOS/applications/vozflow.desktop" "$MARCA_DE_ENTRADA" && quito=1
    retirar_si_es_nuestro "$DATOS/icons/hicolor/scalable/apps/vozflow.svg" "$MARCA_DEL_ICONO" && quito=1
    retirar_si_es_nuestro "$CONFIG/autostart/vozflow.desktop" "$MARCA_DE_ENTRADA" && quito=1
    if [ "$quito" = 1 ]; then
        decir "✓ Retiré vozflow del menú de aplicaciones y del arranque"
    else
        decir "✓ vozflow ya estaba retirado del menú y del arranque"
    fi

    decir ""
    if preguntar "¿Borro tus datos (el historial de lo que dictaste, tu vocabulario y tus atajos)?" N; then
        rm -rf "${DATOS:?}/vozflow"
        decir "✓ Borré tus datos"
    fi

    if preguntar "¿Borro el modelo de voz que se bajó (unos 480 MB)? Otras aplicaciones lo podrían usar." N; then
        rm -rf "$MODELOS"/models--Systran--faster-whisper-*
        decir "✓ Borré el modelo de voz"
    fi

    if preguntar "¿Borro las claves de los servicios de IA que guardaste en tu llavero?" N; then
        if [ -n "$PROYECTO" ] && command -v uv > /dev/null 2>&1; then
            for proveedor in ollama anthropic openrouter; do
                uv run --project "$PROYECTO" python -m vozflow proveedor borrar-clave "$proveedor" > /dev/null 2>&1
            done
            decir "✓ Borré tus claves"
        else
            decir "! No encuentro vozflow para borrar las claves. Borralas a mano desde «Contraseñas y claves»."
        fi
    fi

    if preguntar "¿Quito también los permisos del teclado (los que dio el instalador)? Otras aplicaciones los podrían usar." N; then
        local bloque="rm -f \"$UDEV_DIR/60-vozflow-uinput.rules\" \"$MODULOS_DIR/vozflow-uinput.conf\"
udevadm control --reload-rules || true
gpasswd -d \"$USUARIO\" input || true"
        if sudo bash -c "$bloque"; then
            decir "✓ Quité los permisos del teclado"
        else
            decir "! No pude quitar los permisos del teclado."
        fi
    fi

    if [ -n "$PROYECTO" ]; then
        if [ "$PROYECTO" = "$DESTINO" ]; then
            if preguntar "¿Borro también la carpeta donde está el programa ($PROYECTO)?" N; then
                rm -rf "${PROYECTO:?}"
                decir "✓ Borré la carpeta del programa"
            fi
        else
            decir "La carpeta del programa ($PROYECTO) es tu copia del código: la dejo donde está."
        fi
    fi

    decir ""
    decir "Listo. Dejé tus datos (historial y vocabulario), el modelo de voz y los permisos"
    decir "que no me pediste borrar. Si querés, volvé a instalar vozflow cuando quieras."
    exit 0
}

principal "$@"
