"""Lo común de los reescritores por HTTP: enviar el pedido y traducir cualquier falla.

Los mensajes de error son fijos y se arman acá: nunca incluyen el cuerpo de la respuesta (un
servidor podría repetir la clave o el texto) y se lanzan fuera del ``except`` para que no
arrastren la excepción original, cuyo texto no controlamos.
"""

from typing import Any

import httpx

from vozflow.llm.puerto import ReescrituraFallida

_MINIMO_DE_TOKENS = 256
_MAXIMO_DE_TOKENS = 8192


def tokens_maximos(texto: str) -> int:
    """Un tope generoso: la reescritura rara vez es más larga que el original."""
    return max(_MINIMO_DE_TOKENS, min(_MAXIMO_DE_TOKENS, len(texto)))


def _explicar_codigo(codigo: int, nombre: str) -> str:
    if codigo in (401, 403):
        return f"{nombre} rechazó la clave de acceso"
    if codigo == 402:
        return f"{nombre} indica que no hay crédito suficiente"
    if codigo == 404:
        return f"{nombre} no encontró el modelo o la dirección configurados"
    if codigo == 429:
        return f"{nombre} limitó los pedidos (demasiadas solicitudes); probá más tarde"
    if codigo >= 500:
        return f"{nombre} tuvo un error (código {codigo})"
    return f"{nombre} rechazó el pedido (código {codigo})"


def publicar_json(
    url: str,
    *,
    cabeceras: dict[str, str],
    cuerpo: dict[str, Any],
    tiempo_maximo_s: int,
    nombre: str,
    transporte: httpx.BaseTransport | None,
) -> Any:
    """``POST`` con JSON; devuelve el JSON de la respuesta o lanza ``ReescrituraFallida``."""
    fallo: str | None = None
    datos: Any = None
    try:
        with httpx.Client(transport=transporte, timeout=httpx.Timeout(tiempo_maximo_s)) as cliente:
            respuesta = cliente.post(url, headers=cabeceras, json=cuerpo)
    except httpx.TimeoutException:
        fallo = f"{nombre} no respondió a tiempo"
    except httpx.HTTPError:
        fallo = f"No se pudo conectar con {nombre}"
    else:
        if respuesta.status_code != 200:
            fallo = _explicar_codigo(respuesta.status_code, nombre)
        else:
            try:
                datos = respuesta.json()
            except ValueError:
                fallo = f"{nombre} devolvió una respuesta que no se entiende"
    if fallo is not None:
        raise ReescrituraFallida(fallo)
    return datos


def texto_valido(texto: object, nombre: str, *, cortado: bool = False) -> str:
    """El texto reescrito, o ``ReescrituraFallida`` si falta, quedó vacío o vino cortado."""
    fallo: str | None = None
    if cortado:
        fallo = f"{nombre} cortó la respuesta antes de terminar"
    elif not isinstance(texto, str) or not texto.strip():
        fallo = f"{nombre} devolvió una respuesta vacía"
    if fallo is not None:
        raise ReescrituraFallida(fallo)
    assert isinstance(texto, str)
    return texto.strip()
