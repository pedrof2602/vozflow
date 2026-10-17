"""Reescritor con OpenRouter (formato compatible con OpenAI); la clave va como ``Bearer``."""

import httpx

from vozflow.llm._http import publicar_json, texto_valido, tokens_maximos

URL = "https://openrouter.ai/api/v1/chat/completions"
_NOMBRE = "OpenRouter"


class ReescritorOpenRouter:
    def __init__(
        self, modelo: str, clave: str, transporte: httpx.BaseTransport | None = None
    ) -> None:
        if not clave.strip():
            raise ValueError("Falta la clave de acceso de OpenRouter")
        self._modelo = modelo
        self._clave = clave.strip()
        self._transporte = transporte

    def __repr__(self) -> str:  # la clave nunca sale en un repr
        return f"ReescritorOpenRouter(modelo={self._modelo!r})"

    def reescribir(self, texto: str, instruccion: str, tiempo_maximo_s: int) -> str:
        datos = publicar_json(
            URL,
            cabeceras={"Authorization": f"Bearer {self._clave}", "X-OpenRouter-Title": "vozflow"},
            cuerpo={
                "model": self._modelo,
                "max_tokens": tokens_maximos(texto),
                "messages": [
                    {"role": "system", "content": instruccion},
                    {"role": "user", "content": texto},
                ],
            },
            tiempo_maximo_s=tiempo_maximo_s,
            nombre=_NOMBRE,
            transporte=self._transporte,
        )
        elecciones = datos.get("choices") if isinstance(datos, dict) else None
        primera = elecciones[0] if isinstance(elecciones, list) and elecciones else None
        mensaje = primera.get("message") if isinstance(primera, dict) else None
        contenido = mensaje.get("content") if isinstance(mensaje, dict) else None
        motivo = primera.get("finish_reason") if isinstance(primera, dict) else None
        return texto_valido(contenido, _NOMBRE, cortado=motivo in ("length", "content_filter"))
