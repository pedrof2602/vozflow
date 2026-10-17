"""``ydotool key``: solo atajos de teclado ya conocidos, nunca ``ydotool type``."""

import subprocess
from pathlib import Path

import pytest

from vozflow.insercion.puerto import FalloDeTeclado
from vozflow.insercion.ydotool import TecladorYdotool, socket_de_ydotool

CTRL, SHIFT, INSERT, V = 0xFFE3, 0xFFE1, 0xFF63, 0x76


class Ejecutor:
    def __init__(self, codigo: int = 0, error: Exception | None = None) -> None:
        self.llamadas: list[tuple[list[str], dict[str, str]]] = []
        self._codigo = codigo
        self._error = error

    def __call__(
        self, comando: list[str], entorno: dict[str, str], timeout_s: float
    ) -> subprocess.CompletedProcess[str]:
        self.llamadas.append((comando, entorno))
        if self._error is not None:
            raise self._error
        return subprocess.CompletedProcess(comando, self._codigo, "", "fallo de ydotool")


@pytest.fixture
def socket(tmp_path: Path) -> Path:
    ruta = tmp_path / ".ydotool_socket"
    ruta.touch()
    return ruta


@pytest.mark.parametrize(
    ("teclas", "esperado"),
    [
        ((SHIFT, INSERT), ["42:1", "110:1", "110:0", "42:0"]),
        ((CTRL, V), ["29:1", "47:1", "47:0", "29:0"]),
        ((CTRL, SHIFT, V), ["29:1", "42:1", "47:1", "47:0", "42:0", "29:0"]),
    ],
)
def test_arma_los_codigos_de_tecla_de_cada_atajo(
    socket: Path, teclas: tuple[int, ...], esperado: list[str]
) -> None:
    ejecutor = Ejecutor()

    TecladorYdotool(socket=socket, ejecutar=ejecutor).pulsar_combinacion(teclas)

    assert ejecutor.llamadas[0][0] == ["ydotool", "key", *esperado]


def test_usa_el_socket_de_ydotoold_del_usuario(socket: Path) -> None:
    ejecutor = Ejecutor()

    TecladorYdotool(socket=socket, ejecutar=ejecutor).pulsar_combinacion((SHIFT, INSERT))

    assert ejecutor.llamadas[0][1]["YDOTOOL_SOCKET"] == str(socket)


def test_el_socket_por_defecto_esta_en_el_directorio_de_ejecucion_del_usuario(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("YDOTOOL_SOCKET", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")

    assert socket_de_ydotool() == Path("/run/user/1000/.ydotool_socket")


def test_respeta_la_variable_ydotool_socket_si_esta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YDOTOOL_SOCKET", "/otro/socket")

    assert socket_de_ydotool() == Path("/otro/socket")


def test_sin_el_socket_el_fallo_dice_que_falta_ydotoold(tmp_path: Path) -> None:
    ejecutor = Ejecutor()
    teclador = TecladorYdotool(socket=tmp_path / "no-existe", ejecutar=ejecutor)

    with pytest.raises(FalloDeTeclado, match="ydotoold"):
        teclador.pulsar_combinacion((SHIFT, INSERT))

    assert ejecutor.llamadas == []


def test_una_tecla_que_no_conoce_se_rechaza_sin_ejecutar_nada(socket: Path) -> None:
    ejecutor = Ejecutor()

    with pytest.raises(FalloDeTeclado, match="atajo"):
        TecladorYdotool(socket=socket, ejecutar=ejecutor).pulsar_combinacion((0xF1,))  # «ñ»

    assert ejecutor.llamadas == []


def test_nunca_usa_ydotool_type(socket: Path) -> None:
    ejecutor = Ejecutor()

    TecladorYdotool(socket=socket, ejecutar=ejecutor).pulsar_combinacion((CTRL, V))

    assert "type" not in ejecutor.llamadas[0][0]


def test_un_codigo_de_salida_distinto_de_cero_es_un_fallo(socket: Path) -> None:
    with pytest.raises(FalloDeTeclado, match="ydotool"):
        TecladorYdotool(socket=socket, ejecutar=Ejecutor(codigo=1)).pulsar_combinacion((CTRL, V))


@pytest.mark.parametrize(
    "error", [FileNotFoundError("ydotool"), subprocess.TimeoutExpired("ydotool", 3)]
)
def test_si_no_esta_instalado_o_tarda_demasiado_es_un_fallo(socket: Path, error: Exception) -> None:
    with pytest.raises(FalloDeTeclado, match="ydotool"):
        TecladorYdotool(socket=socket, ejecutar=Ejecutor(error=error)).pulsar_combinacion((CTRL, V))


def test_una_combinacion_vacia_no_ejecuta_nada(socket: Path) -> None:
    ejecutor = Ejecutor()

    TecladorYdotool(socket=socket, ejecutar=ejecutor).pulsar_combinacion(())

    assert ejecutor.llamadas == []
