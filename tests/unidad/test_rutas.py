from pathlib import Path

import pytest

from vozflow import rutas


def test_usa_las_variables_xdg_si_estan_definidas(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    assert rutas.directorio_datos() == tmp_path / "datos" / "vozflow"
    assert rutas.directorio_cache() == tmp_path / "cache" / "vozflow"
    assert rutas.directorio_config() == tmp_path / "config" / "vozflow"


def test_usa_los_valores_por_defecto_del_home_sin_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for variable in ("XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_CONFIG_HOME"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    assert rutas.directorio_datos() == tmp_path / ".local" / "share" / "vozflow"
    assert rutas.directorio_cache() == tmp_path / ".cache" / "vozflow"
    assert rutas.directorio_config() == tmp_path / ".config" / "vozflow"


def test_ignora_una_variable_xdg_vacia_o_relativa(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # La especificación XDG manda ignorar valores vacíos o no absolutos.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", "")
    monkeypatch.setenv("XDG_CACHE_HOME", "relativa/cache")

    assert rutas.directorio_datos() == tmp_path / ".local" / "share" / "vozflow"
    assert rutas.directorio_cache() == tmp_path / ".cache" / "vozflow"


def test_rutas_derivadas_cuelgan_de_su_directorio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "datos"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))

    datos = tmp_path / "datos" / "vozflow"
    assert rutas.ruta_base_de_datos() == datos / "vozflow.db"
    assert rutas.directorio_pruebas() == datos / "pruebas"
    assert rutas.ruta_token_portal() == tmp_path / "config" / "vozflow" / "portal-token"


def test_asegurar_crea_el_directorio_con_permisos_privados(tmp_path: Path) -> None:
    destino = tmp_path / "a" / "b"

    resultado = rutas.asegurar(destino)

    assert resultado == destino
    assert destino.is_dir()
    assert destino.stat().st_mode & 0o077 == 0
