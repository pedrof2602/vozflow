"""Migración 2 de la base: el motivo del fallo de un dictado (RP-021)."""

import sqlite3
from pathlib import Path

import pytest

from vozflow.persistencia.base import _ESQUEMA_1, EsquemaMasNuevo, abrir_base


def _base_de_la_version_1(ruta: Path) -> None:
    """Una base real como la de una instalación anterior, con un dictado ya guardado."""
    conexion = sqlite3.connect(ruta)
    conexion.executescript(f"BEGIN;\n{_ESQUEMA_1}\nPRAGMA user_version = 1;\nCOMMIT;")
    conexion.execute(
        "INSERT INTO dictado (creado_en, texto_crudo, texto_final, duracion_audio_ms,"
        " duracion_proceso_ms, estado) VALUES ('2026-10-17T21:00:00Z', 'hola', 'Hola.', 900, 400,"
        " 'no_insertado')"
    )
    conexion.commit()
    conexion.close()


def test_una_base_de_la_version_1_migra_a_la_2(tmp_path: Path) -> None:
    ruta = tmp_path / "v.db"
    _base_de_la_version_1(ruta)

    base = abrir_base(ruta)

    assert base.execute("PRAGMA user_version").fetchone()[0] == 2


def test_los_dictados_viejos_quedan_con_el_motivo_vacio(tmp_path: Path) -> None:
    ruta = tmp_path / "v.db"
    _base_de_la_version_1(ruta)

    base = abrir_base(ruta)

    fila = base.execute("SELECT texto_final, motivo FROM dictado").fetchone()
    assert (fila["texto_final"], fila["motivo"]) == ("Hola.", "")


def test_una_base_nueva_ya_tiene_la_columna_motivo(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "n.db")

    columnas = [f["name"] for f in base.execute("PRAGMA table_info(dictado)")]

    assert "motivo" in columnas


def test_el_motivo_no_puede_ser_nulo(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "n.db")

    with pytest.raises(sqlite3.IntegrityError):
        base.execute(
            "INSERT INTO dictado (creado_en, texto_crudo, texto_final, duracion_audio_ms,"
            " duracion_proceso_ms, estado, motivo) VALUES ('x', 'a', 'b', 1, 0, 'insertado', NULL)"
        )


def test_migrar_dos_veces_no_rompe_nada(tmp_path: Path) -> None:
    ruta = tmp_path / "v.db"
    _base_de_la_version_1(ruta)
    abrir_base(ruta).close()

    base = abrir_base(ruta)

    assert base.execute("SELECT count(*) FROM dictado").fetchone()[0] == 1


def test_una_base_de_una_version_mayor_se_sigue_rechazando(tmp_path: Path) -> None:
    ruta = tmp_path / "f.db"
    conexion = sqlite3.connect(ruta)
    conexion.execute("PRAGMA user_version = 99")
    conexion.commit()
    conexion.close()

    with pytest.raises(EsquemaMasNuevo, match="actualizá vozflow"):
        abrir_base(ruta)
