"""Escucha del modo «alternar» con un atajo de GNOME y el servicio D-Bus al que llama."""

from collections.abc import Callable, Mapping

from vozflow.atajos.gsettings import AtajoDeGnome, a_formato_gnome
from vozflow.atajos.puerto import AccionDeAtajo, AlEvento, Despachador, FaseDeAtajo
from vozflow.servicio_dbus import ServicioDBus

CrearServicio = Callable[[Callable[[], None]], ServicioDBus]


class EscuchaDeGnome:
    """Solo maneja ``alternar``: el atajo de GNOME no avisa al soltar la tecla."""

    def __init__(
        self,
        atajo: AtajoDeGnome | None = None,
        crear_servicio: CrearServicio = ServicioDBus,
    ) -> None:
        self._atajo = atajo or AtajoDeGnome()
        self._crear_servicio = crear_servicio
        self._servicio: ServicioDBus | None = None
        self._despachador: Despachador | None = None

    def iniciar(self, atajos: Mapping[AccionDeAtajo, str], al_evento: AlEvento) -> None:
        if self._servicio is not None:
            raise RuntimeError("La escucha ya está iniciada")
        if set(atajos) != {AccionDeAtajo.ALTERNAR}:
            raise ValueError("El atajo de GNOME solo sirve para la acción alternar")
        binding = a_formato_gnome(atajos[AccionDeAtajo.ALTERNAR])
        despachador = Despachador(al_evento)
        servicio = self._crear_servicio(lambda: self._alternar(despachador))
        # Primero el servicio, así otra instancia se detecta sin tocar gsettings y la tecla
        # nunca queda registrada sin nadie que la escuche.
        servicio.iniciar()
        try:
            self._atajo.registrar(binding)
        except BaseException:
            servicio.detener()
            raise
        self._servicio = servicio
        self._despachador = despachador

    def detener(self) -> None:
        if self._servicio is None:
            return
        servicio, self._servicio = self._servicio, None
        if self._despachador is not None:
            self._despachador.detener()
        servicio.detener()
        self._atajo.quitar()

    @staticmethod
    def _alternar(despachador: Despachador) -> None:
        # Cada llamada es una pulsación completa: se «suelta» enseguida para que la siguiente
        # no se tome por la repetición de una tecla apretada.
        despachador.emitir(AccionDeAtajo.ALTERNAR, FaseDeAtajo.PULSADO)
        despachador.emitir(AccionDeAtajo.ALTERNAR, FaseDeAtajo.SOLTADO)
