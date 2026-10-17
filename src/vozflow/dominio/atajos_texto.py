"""Atajos de texto (RF-020): una palabra clave que se expande a un texto más largo."""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from vozflow.dominio.claves import normalizar_clave, plano_alineado


@dataclass(frozen=True)
class AtajoTexto:
    disparador: str
    reemplazo: str
    id: int = 0


def expandir(texto: str, atajos: Sequence[AtajoTexto]) -> str:
    """Reemplaza cada disparador que aparezca como palabra o frase completa.

    No distingue mayúsculas ni acentos; gana el disparador más largo; el reemplazo se inserta
    tal cual y no se vuelve a examinar. Si el texto termina en el disparador y la puntuación
    automática le puso un punto final, ese punto no queda pegado al reemplazo.
    """
    por_clave = {normalizar_clave(a.disparador): a.reemplazo for a in atajos}
    por_clave.pop("", None)
    if not texto or not por_clave:
        return texto
    claves = sorted(por_clave, key=len, reverse=True)
    alternativas = "|".join(r"\s+".join(re.escape(p) for p in clave.split()) for clave in claves)
    patron = re.compile(rf"(?<!\w)(?:{alternativas})(?!\w)")
    plano = plano_alineado(texto)
    final_del_texto = len(texto.rstrip())
    partes: list[str] = []
    cursor = 0
    for coincidencia in patron.finditer(plano):
        inicio, fin = coincidencia.span()
        partes.append(texto[cursor:inicio])
        partes.append(por_clave[" ".join(coincidencia.group(0).split())])
        cursor = fin
        if fin + 1 == final_del_texto and texto[fin] == ".":
            cursor = fin + 1
    partes.append(texto[cursor:])
    return "".join(partes)
