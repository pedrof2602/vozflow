"""Inserta el texto copiándolo y pegándolo con una tecla; restaura el portapapeles (RF-018)."""

import logging
import time
from collections.abc import Callable, Sequence

from vozflow.dominio.pegado import decidir_estrategia
from vozflow.insercion.portapapeles import Portapapeles, PortapapelesNoLegible
from vozflow.insercion.puerto import Destino, FalloDeTeclado, ResultadoInsercion, Teclador

# Tiempo para que la aplicación lea el portapapeles antes de devolverlo a como estaba.
_ESPERA_ANTES_DE_RESTAURAR_S = 0.15

_registro = logging.getLogger(__name__)


class InsertorPorTeclas:
    """Prueba cada teclador en orden hasta que uno logre pegar. Nunca lanza ni manda Enter."""

    def __init__(
        self,
        portapapeles: Portapapeles,
        tecladores: Sequence[Teclador],
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self._portapapeles = portapapeles
        self.tecladores = list(tecladores)
        self._dormir = dormir

    def insertar(self, texto: str, destino: Destino) -> ResultadoInsercion:
        if not texto:
            return ResultadoInsercion.exito()
        estrategia = decidir_estrategia(texto, destino)
        previo = self._leer_previo()
        try:
            self._portapapeles.copiar(
                estrategia.texto, tambien_primaria=estrategia.copiar_a_primaria
            )
        except OSError as error:
            # El texto puede haber quedado a medias en el portapapeles: se devuelve el anterior.
            self._restaurar(previo)
            return ResultadoInsercion.fallido(f"No se pudo copiar el texto: {error}")
        try:
            return self._pegar(estrategia.teclas)
        finally:
            self._dormir(_ESPERA_ANTES_DE_RESTAURAR_S)
            self._restaurar(previo)

    # ---- internos -------------------------------------------------------------------------------

    def _pegar(self, teclas: Sequence[int]) -> ResultadoInsercion:
        motivos: list[str] = []
        for teclador in self.tecladores:
            try:
                teclador.pulsar_combinacion(teclas)
            except FalloDeTeclado as error:
                motivos.append(str(error))
            except Exception as error:  # un teclador roto no debe tumbar el dictado
                _registro.exception("Falló un teclador de forma inesperada")
                motivos.append(f"Error inesperado ({type(error).__name__})")
            else:
                return ResultadoInsercion.exito()
        if not motivos:
            return ResultadoInsercion.fallido("No hay ninguna forma de pegar configurada")
        return ResultadoInsercion.fallido("No se pudo pegar: " + "; ".join(motivos))

    def _leer_previo(self) -> str | None:
        try:
            return self._portapapeles.leer()
        except PortapapelesNoLegible:
            return None

    def _restaurar(self, previo: str | None) -> None:
        if previo is None:
            return  # no se pudo leer: no se inventa nada
        try:
            if previo == "":
                self._portapapeles.limpiar()
            else:
                self._portapapeles.copiar(previo, tambien_primaria=False)
        except OSError:
            _registro.warning("No se pudo restaurar el portapapeles")
