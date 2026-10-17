"""La base SQLite: esquema de la versión 1, migraciones y datos de fábrica (T069)."""

import sqlite3
from pathlib import Path

import pytest

from vozflow.persistencia.base import VERSION_DEL_ESQUEMA, EsquemaMasNuevo, abrir_base

TABLAS = {
    "dictado",
    "entrada_diccionario",
    "atajo_texto",
    "modo",
    "asignacion",
    "proveedor",
    "ajuste",
}


def _tablas(base: sqlite3.Connection) -> set[str]:
    filas = base.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {f[0] for f in filas}


def test_crea_el_esquema_de_la_version_1(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")

    assert VERSION_DEL_ESQUEMA == 1
    assert base.execute("PRAGMA user_version").fetchone()[0] == 1
    assert _tablas(base) >= TABLAS


def test_activa_las_claves_foraneas(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")

    assert base.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_crea_la_carpeta_si_no_existe(tmp_path: Path) -> None:
    ruta = tmp_path / "no" / "existe" / "vozflow.db"

    abrir_base(ruta)

    assert ruta.is_file()


def test_abrirla_dos_veces_no_duplica_nada(tmp_path: Path) -> None:
    ruta = tmp_path / "vozflow.db"
    primera = abrir_base(ruta)
    primera.close()

    segunda = abrir_base(ruta)

    assert segunda.execute("SELECT COUNT(*) FROM modo").fetchone()[0] == 5
    assert segunda.execute("PRAGMA user_version").fetchone()[0] == 1


def test_rechaza_una_base_de_una_version_mas_nueva(tmp_path: Path) -> None:
    ruta = tmp_path / "vozflow.db"
    nueva = sqlite3.connect(ruta)
    nueva.execute("PRAGMA user_version = 99")
    nueva.close()

    with pytest.raises(EsquemaMasNuevo, match="99"):
        abrir_base(ruta)


def test_no_modifica_una_base_que_rechaza(tmp_path: Path) -> None:
    ruta = tmp_path / "vozflow.db"
    nueva = sqlite3.connect(ruta)
    nueva.execute("PRAGMA user_version = 99")
    nueva.close()

    with pytest.raises(EsquemaMasNuevo):
        abrir_base(ruta)

    comprobar = sqlite3.connect(ruta)
    assert comprobar.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] == 0


def test_los_modos_de_fabrica_vienen_sembrados(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")

    filas = base.execute(
        "SELECT nombre, es_general, tipo_pegado, salto_de_linea FROM modo ORDER BY id"
    ).fetchall()

    assert [f["nombre"] for f in filas] == [
        "General",
        "Terminal",
        "Código",
        "Mensajería",
        "Documentos",
    ]
    assert [f["nombre"] for f in filas if f["es_general"]] == ["General"]
    terminal = next(f for f in filas if f["nombre"] == "Terminal")
    assert (terminal["tipo_pegado"], terminal["salto_de_linea"]) == ("terminal", "espacio")


def test_las_filas_se_leen_por_nombre_de_columna(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")

    fila = base.execute("SELECT nombre FROM modo WHERE es_general = 1").fetchone()

    assert fila["nombre"] == "General"


def test_la_base_en_memoria_tambien_sirve() -> None:
    base = abrir_base(":memory:")

    assert _tablas(base) >= TABLAS


def test_la_busqueda_de_texto_completo_esta_disponible(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")
    base.execute(
        "INSERT INTO dictado (creado_en, texto_crudo, texto_final, duracion_audio_ms, "
        "duracion_proceso_ms, estado) VALUES ('2026-10-17T10:00:00Z', 'x', 'Reunión de equipo', "
        "1000, 500, 'insertado')"
    )

    hallados = base.execute(
        "SELECT rowid FROM dictado_fts WHERE dictado_fts MATCH 'reunion'"
    ).fetchall()

    assert len(hallados) == 1  # sin distinguir acentos


def test_el_texto_borrado_sale_del_indice_de_busqueda(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")
    base.execute(
        "INSERT INTO dictado (creado_en, texto_crudo, texto_final, duracion_audio_ms, "
        "duracion_proceso_ms, estado) VALUES ('2026-10-17T10:00:00Z', 'x', 'secreto', 1, 1, "
        "'insertado')"
    )
    base.execute("DELETE FROM dictado")

    assert (
        base.execute(
            "SELECT COUNT(*) FROM dictado_fts WHERE dictado_fts MATCH 'secreto'"
        ).fetchone()[0]
        == 0
    )


# ---- reglas que protege el propio esquema ----------------------------------------------------------------


def test_no_se_puede_borrar_el_modo_general(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")

    with pytest.raises(sqlite3.DatabaseError, match="general"):
        base.execute("DELETE FROM modo WHERE es_general = 1")


def test_no_puede_haber_dos_modos_generales(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")

    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO modo (nombre, es_general) VALUES ('Otro', 1)")


def test_al_borrar_un_modo_sus_aplicaciones_pasan_al_general_y_el_historial_queda_sin_modo(
    tmp_path: Path,
) -> None:
    base = abrir_base(tmp_path / "vozflow.db")
    terminal = base.execute("SELECT id FROM modo WHERE nombre = 'Terminal'").fetchone()[0]
    general = base.execute("SELECT id FROM modo WHERE es_general = 1").fetchone()[0]
    base.execute(
        "INSERT INTO asignacion (aplicacion, modo_id, es_terminal) VALUES ('ptyxis', ?, 1)",
        (terminal,),
    )
    base.execute(
        "INSERT INTO dictado (creado_en, texto_crudo, texto_final, duracion_audio_ms, "
        "duracion_proceso_ms, modo_id, estado) VALUES ('2026-10-17T10:00:00Z', 'a', 'a', 1, 1, ?, "
        "'insertado')",
        (terminal,),
    )

    base.execute("DELETE FROM modo WHERE id = ?", (terminal,))

    asignacion = base.execute("SELECT modo_id, es_terminal FROM asignacion").fetchone()
    assert (asignacion["modo_id"], asignacion["es_terminal"]) == (general, 1)
    assert base.execute("SELECT modo_id FROM dictado").fetchone()[0] is None


@pytest.mark.parametrize(
    "sentencia",
    [
        "INSERT INTO modo (nombre, tipo_pegado) VALUES ('X', 'raro')",
        "INSERT INTO modo (nombre, salto_de_linea) VALUES ('X', 'raro')",
        "INSERT INTO modo (nombre) VALUES ('General')",
        "INSERT INTO entrada_diccionario (palabra, palabra_norm) VALUES ('', '')",
        "INSERT INTO entrada_diccionario (palabra, palabra_norm) VALUES ('{81}', 'x')",
        "INSERT INTO atajo_texto (disparador, disparador_norm, reemplazo) VALUES ('{101}', 'x', 'r')",
        "INSERT INTO atajo_texto (disparador, disparador_norm, reemplazo) VALUES ('a', 'a', '')",
        "INSERT INTO asignacion (aplicacion, modo_id) VALUES ('x', 9999)",
        "INSERT INTO dictado (creado_en, texto_crudo, texto_final, duracion_audio_ms, duracion_proceso_ms, estado) VALUES ('t', 'a', 'a', 0, 1, 'insertado')",
        "INSERT INTO dictado (creado_en, texto_crudo, texto_final, duracion_audio_ms, duracion_proceso_ms, estado) VALUES ('t', 'a', 'a', 1, 1, 'raro')",
        "INSERT INTO proveedor (id, tiempo_maximo_s) VALUES ('ollama', 2)",
        "INSERT INTO proveedor (id) VALUES ('otro')",
    ],
)
def test_el_esquema_rechaza_datos_invalidos(tmp_path: Path, sentencia: str) -> None:
    base = abrir_base(tmp_path / "vozflow.db")
    sentencia = sentencia.replace("{81}", "a" * 81).replace("{101}", "a" * 101)

    with pytest.raises(sqlite3.IntegrityError):
        base.execute(sentencia)


def test_solo_un_proveedor_puede_estar_activo(tmp_path: Path) -> None:
    base = abrir_base(tmp_path / "vozflow.db")
    base.execute("INSERT INTO proveedor (id, activo) VALUES ('ollama', 1)")

    with pytest.raises(sqlite3.IntegrityError):
        base.execute("INSERT INTO proveedor (id, activo) VALUES ('anthropic', 1)")
