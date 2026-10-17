"""Reescritor con Anthropic (``POST /v1/messages``); la clave viaja en ``x-api-key``."""

import httpx

from vozflow.llm._http import publicar_json, texto_valido, tokens_maximos

URL = "https://api.anthropic.com/v1/messages"
VERSION_DE_LA_API = "2023-06-01"
_NOMBRE = "Anthropic"


class ReescritorAnthropic:
    def __init__(
        self, modelo: str, clave: str, transporte: httpx.BaseTransport | None = None
    ) -> None:
        if not clave.strip():
            raise ValueError("Falta la clave de acceso de Anthropic")
        self._modelo = modelo
        self._clave = clave.strip()
        self._transporte = transporte

    def __repr__(self) -> str:  # la clave nunca sale en un repr
        return f"ReescritorAnthropic(modelo={self._modelo!r})"

    def reescribir(self, texto: str, instruccion: str, tiempo_maximo_s: int) -> str:
        datos = publicar_json(
            URL,
            cabeceras={"x-api-key": self._clave, "anthropic-version": VERSION_DE_LA_API},
            cuerpo={
                "model": self._modelo,
                "max_tokens": tokens_maximos(texto),
                "system": instruccion,
                "messages": [{"role": "user", "content": texto}],
            },
            tiempo_maximo_s=tiempo_maximo_s,
            nombre=_NOMBRE,
            transporte=self._transporte,
        )
        bloques = datos.get("content") if isinstance(datos, dict) else None
        partes = [
            b["text"]
            for b in (bloques if isinstance(bloques, list) else [])
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
        ]
        motivo = datos.get("stop_reason") if isinstance(datos, dict) else None
        return texto_valido("".join(partes), _NOMBRE, cortado=motivo in ("max_tokens", "refusal"))
