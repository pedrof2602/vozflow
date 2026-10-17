"""``wl-copy`` / ``wl-paste``: copiar a las dos selecciones y leer sin colgarse."""

import subprocess

import pytest

from vozflow.insercion.portapapeles import PortapapelesNoLegible, PortapapelesWayland


class Ejecutor:
    def __init__(self, respuestas: list[subprocess.CompletedProcess[str] | Exception]) -> None:
        self.llamadas: list[tuple[list[str], str | None, float, bool]] = []
        self._respuestas = respuestas

    def __call__(
        self, comando: list[str], entrada: str | None, timeout_s: float, capturar: bool
    ) -> subprocess.CompletedProcess[str]:
        self.llamadas.append((comando, entrada, timeout_s, capturar))
        respuesta = self._respuestas.pop(0) if self._respuestas else _ok()
        if isinstance(respuesta, Exception):
            raise respuesta
        return respuesta


def _ok(salida: str = "", codigo: int = 0, error: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], codigo, salida, error)


def test_copia_al_portapapeles_y_a_la_seleccion_primaria() -> None:
    ejecutor = Ejecutor([])

    PortapapelesWayland(ejecutor).copiar("hola ñandú", tambien_primaria=True)

    comandos = [(c[0], c[1:], e) for c, e, _, _ in ejecutor.llamadas]
    assert comandos == [("wl-copy", [], "hola ñandú"), ("wl-copy", ["--primary"], "hola ñandú")]


def test_sin_primaria_solo_copia_al_portapapeles() -> None:
    ejecutor = Ejecutor([])

    PortapapelesWayland(ejecutor).copiar("hola", tambien_primaria=False)

    assert [c for c, *_ in ejecutor.llamadas] == [["wl-copy"]]


def test_wl_copy_se_ejecuta_sin_capturar_la_salida() -> None:
    # wl-copy deja un proceso sirviendo la selección: capturar su salida lo dejaría esperando.
    ejecutor = Ejecutor([])

    PortapapelesWayland(ejecutor).copiar("hola", tambien_primaria=True)

    assert all(capturar is False for *_, capturar in ejecutor.llamadas)


def test_el_texto_viaja_por_la_entrada_y_no_por_la_linea_de_comandos() -> None:
    ejecutor = Ejecutor([])

    PortapapelesWayland(ejecutor).copiar("-secreto --version", tambien_primaria=False)

    assert "-secreto --version" not in ejecutor.llamadas[0][0]


def test_leer_usa_wl_paste_con_un_tope_de_200_ms() -> None:
    ejecutor = Ejecutor([_ok("contenido previo")])

    leido = PortapapelesWayland(ejecutor).leer()

    comando, entrada, tiempo, capturar = ejecutor.llamadas[0]
    assert leido == "contenido previo"
    assert comando[0] == "wl-paste" and "--no-newline" in comando
    assert entrada is None and tiempo == 0.2 and capturar is True


def test_un_portapapeles_vacio_se_lee_como_texto_vacio() -> None:
    ejecutor = Ejecutor([_ok(codigo=1, error="Nothing is copied")])

    assert PortapapelesWayland(ejecutor).leer() == ""


@pytest.mark.parametrize(
    "respuesta",
    [
        subprocess.TimeoutExpired("wl-paste", 0.2),
        _ok(codigo=1, error="Clipboard content is not available as requested type"),
        FileNotFoundError("wl-paste"),
    ],
)
def test_si_no_se_puede_leer_se_avisa_sin_colgarse(
    respuesta: subprocess.CompletedProcess[str] | Exception,
) -> None:
    with pytest.raises(PortapapelesNoLegible):
        PortapapelesWayland(Ejecutor([respuesta])).leer()


def test_limpiar_usa_wl_copy_clear() -> None:
    ejecutor = Ejecutor([])

    PortapapelesWayland(ejecutor).limpiar()

    assert [c for c, *_ in ejecutor.llamadas] == [
        ["wl-copy", "--clear"],
        ["wl-copy", "--primary", "--clear"],
    ]


def test_si_wl_copy_falla_se_informa() -> None:
    ejecutor = Ejecutor([_ok(codigo=1, error="no hay compositor")])

    with pytest.raises(OSError, match="wl-copy"):
        PortapapelesWayland(ejecutor).copiar("hola", tambien_primaria=False)
