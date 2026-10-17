"""Reescritor con un modelo local de Ollama (``POST /api/chat`` sin streaming)."""

import httpx

from vozflow.llm._http import publicar_json, texto_valido

DIRECCION_POR_DEFECTO = "http://127.0.0.1:11434"
_NOMBRE = "Ollama"


class ReescritorOllama:
    def __init__(
        self,
        modelo: str,
        direccion: str = DIRECCION_POR_DEFECTO,
        transporte: httpx.BaseTransport | None = None,
    ) -> None:
        self._modelo = modelo
        self._url = f"{direccion.rstrip('/')}/api/chat"
        self._transporte = transporte

    def __repr__(self) -> str:
        return f"ReescritorOllama(modelo={self._modelo!r})"

    def reescribir(self, texto: str, instruccion: str, tiempo_maximo_s: int) -> str:
        datos = publicar_json(
            self._url,
            cabeceras={},
            cuerpo={
                "model": self._modelo,
                "messages": [
                    {"role": "system", "content": instruccion},
                    {"role": "user", "content": texto},
                ],
                "stream": False,
                "think": False,  # sin razonamiento en voz alta: solo el texto
                "options": {"temperature": 0.2},
            },
            tiempo_maximo_s=tiempo_maximo_s,
            nombre=_NOMBRE,
            transporte=self._transporte,
        )
        mensaje = datos.get("message") if isinstance(datos, dict) else None
        contenido = mensaje.get("content") if isinstance(mensaje, dict) else None
        cortado = isinstance(datos, dict) and datos.get("done_reason") == "length"
        return texto_valido(contenido, _NOMBRE, cortado=cortado)
