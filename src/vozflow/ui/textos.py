"""Todos los textos de las opciones de los ajustes, en un solo lugar (002, RP-017).

Segunda persona rioplatense, una línea de ayuda por opción, sin jerga ni siglas sin explicar. La
clave es la del ajuste cuando la opción es un ajuste; si no, un nombre propio de la opción.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Texto:
    titulo: str
    ayuda: str


TEXTOS: dict[str, Texto] = {
    # ---- básicas ----
    "atajo.mantener": Texto(
        "Tecla para dictar",
        "Mantenela apretada mientras hablás y soltala cuando termines.",
    ),
    "audio.dispositivo": Texto(
        "Micrófono",
        "El que te escucha. Si dudás, dejá el predeterminado del sistema.",
    ),
    "idioma.modo": Texto(
        "Idioma que hablás",
        "«Automático» lo reconoce solo, aunque mezcles español e inglés.",
    ),
    "interfaz.indicador": Texto(
        "Mostrar el cartel al grabar",
        "Un cartelito en pantalla que te avisa que te está escuchando.",
    ),
    "interfaz.tema": Texto(
        "Tema",
        "Claro, oscuro, o el mismo de tu sistema, que cambia solo.",
    ),
    "autoinicio": Texto(
        "Arrancar con la sesión",
        "vozflow se abre sola en segundo plano cada vez que prendés tu computadora.",
    ),
    "asistente.repetir": Texto(
        "Repetir el asistente",
        "Volvé a recorrer la configuración inicial: micrófono, tecla y una prueba.",
    ),
    "historial.activo": Texto(
        "Guardar lo que dictás",
        "Se guarda solo el texto, nunca el audio. Apagalo si no querés historial.",
    ),
    # ---- avanzadas ----
    "atajo.alternar": Texto(
        "Tecla para empezar y terminar",
        "Apretala una vez para empezar a dictar y otra vez para terminar.",
    ),
    "atajo.mejorar": Texto(
        "Tecla para mejorar",
        "Mantenela apretada y hablá: el asistente de IA pule el texto antes de pegarlo.",
    ),
    "atajo.traducir": Texto(
        "Tecla para mejorar y traducir",
        "Mantenela apretada y hablá: el asistente de IA pule el texto y lo traduce.",
    ),
    "traduccion.idioma": Texto(
        "Traducir al idioma",
        "El idioma al que se traduce cuando usás la tecla de traducir.",
    ),
    "motor.modelo": Texto(
        "Modelo de voz",
        "Cuanto más grande, mejor entiende, pero más tarda. «small» es un buen equilibrio.",
    ),
    "motor.hilos": Texto(
        "Potencia de cálculo",
        "Cuántos núcleos del procesador usa para entenderte: más es más rápido, pero trabaja más.",
    ),
    "reescritura.activa": Texto(
        "Usar el asistente de IA",
        "Mejora o traduce tu texto con un servicio externo. Está apagado salvo que lo prendas.",
    ),
    "proveedor.modelo": Texto(
        "Modelo del asistente",
        "El nombre del modelo que va a usar el servicio de IA que elegiste.",
    ),
    "proveedor.tiempo": Texto(
        "Tiempo máximo de espera",
        "Si el servicio tarda más que esto, se pega tu texto sin mejorar.",
    ),
    "proveedor.direccion": Texto(
        "Dirección de Ollama",
        "Solo si usás Ollama, un programa para correr modelos en tu propia computadora.",
    ),
    "proveedor.clave": Texto(
        "Clave de acceso",
        "Se guarda de forma segura en el llavero de tu sistema, nunca en un archivo.",
    ),
    "modo.muletillas": Texto(
        "Quitar muletillas",
        "Saca los «eh», «mmm» y repeticiones al final de lo que dictaste.",
    ),
    "modo.puntuacion": Texto(
        "Puntuación y mayúsculas automáticas",
        "Agrega puntos, comas y mayúsculas por vos.",
    ),
    "modo.comandos": Texto(
        "Comandos de voz",
        "Decí «nueva línea» o «punto» y se escribe el signo, no la palabra.",
    ),
    "modo.estilo": Texto(
        "Estilo para el asistente de IA",
        "Una indicación como «formal y breve». Se usa con las teclas de mejorar.",
    ),
    "modo.pegado": Texto(
        "Cómo se pega",
        "«Automático» elige solo; cambialo si el texto sale mal en una aplicación.",
    ),
    "modo.saltos": Texto(
        "Saltos de línea",
        "Conservalos, o cambialos por espacios si la aplicación manda el mensaje con Intro.",
    ),
    "modo.terminal": Texto(
        "Marcar como terminal",
        "En una terminal el texto se pega con otra combinación de teclas.",
    ),
    "copia.exportar": Texto(
        "Guardar una copia de seguridad",
        "Guarda tu vocabulario, atajos y modos en un archivo. No incluye lo dictado.",
    ),
    "copia.importar": Texto(
        "Recuperar una copia de seguridad",
        "Carga un archivo guardado antes. Suma lo que falta y no borra lo que tenés.",
    ),
}


def texto_de(clave: str) -> Texto:
    try:
        return TEXTOS[clave]
    except KeyError:
        raise KeyError(f"No hay texto para la opción «{clave}»") from None


def ayuda_de(clave: str) -> str:
    return texto_de(clave).ayuda
