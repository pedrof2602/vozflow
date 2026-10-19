"""Catálogo de mensajes llanos: un código estable → qué pasó y qué hacer (RP-022).

El historial guarda solo el código (``persistencia/base.py``, migración 2); el texto se puede
mejorar sin migrar. Segunda persona rioplatense, una idea por frase, sin jerga: un comando que la
persona deba copiar va entre comillas invertidas.
"""

from dataclasses import dataclass

GENERICO = "generico"


@dataclass(frozen=True)
class Explicacion:
    que_paso: str
    que_hacer: str


_CATALOGO = {
    "pegado_fallo": Explicacion(
        "No pude pegar el texto en la ventana donde estabas.",
        "Tu texto está a salvo acá abajo: tocá «Copiar» y pegalo con Ctrl+V.",
    ),
    "sin_portapapeles": Explicacion(
        "No pude copiar el texto para pegarlo.",
        "Instalá `wl-clipboard` (el instalador lo hace) y volvé a intentar.",
    ),
    "sin_permiso_teclado": Explicacion(
        "No tengo permiso para leer tu teclado.",
        "Seguí los pasos de «Permisos» en el asistente y cerrá sesión una vez.",
    ),
    "microfono_ocupado": Explicacion(
        "Otra aplicación está usando el micrófono.",
        "Cerrala o elegí otro micrófono en Ajustes → Dictado.",
    ),
    "sin_microfono": Explicacion(
        "No encuentro ningún micrófono.",
        "Conectá uno y elegilo en Ajustes → Dictado.",
    ),
    "modelo_faltante": Explicacion(
        "Falta el modelo de voz.",
        "Tocá «Descargar»: se hace una sola vez y necesita internet.",
    ),
    "ia_sin_respuesta": Explicacion(
        "El asistente de IA no respondió.",
        "Revisá tu internet; tu texto sin mejorar quedó a salvo en el historial.",
    ),
    "ia_clave_invalida": Explicacion(
        "El servicio de IA rechazó tu clave.",
        "Pegá la clave de nuevo en Ajustes → Avanzado → Asistente de IA.",
    ),
    "traduccion_fallo": Explicacion(
        "No pude traducir, así que no pegué nada.",
        "Probá de nuevo: tu texto quedó en el historial.",
    ),
    GENERICO: Explicacion(
        "No se pudo completar el dictado.",
        "Tu texto está en el historial. Si se repite, copiá el diagnóstico y avisanos.",
    ),
}

CODIGOS = tuple(_CATALOGO)


def explicar(codigo: str) -> Explicacion:
    """La explicación de un código; uno desconocido (o vacío) da la genérica, nunca falla."""
    return _CATALOGO.get(codigo, _CATALOGO[GENERICO])
