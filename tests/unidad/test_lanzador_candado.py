"""El candado de instancia única no se deja en una carpeta que comparten todos los usuarios."""

import os
import stat
from pathlib import Path

import pytest

from vozflow.ui.lanzador import _directorio_del_candado


def test_usa_la_carpeta_de_ejecucion_del_usuario_si_existe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    assert _directorio_del_candado() == tmp_path


def test_sin_esa_carpeta_usa_una_propia_del_usuario_y_privada(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))

    carpeta = _directorio_del_candado()

    assert carpeta != tmp_path
    assert carpeta.parent == tmp_path
    assert str(os.getuid()) in carpeta.name
    assert stat.S_IMODE(carpeta.stat().st_mode) == 0o700
