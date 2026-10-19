"""La base SQLite local (``data-model.md``): esquema versionado y migraciones al abrirla.

Solo la biblioteca estándar. El esquema lleva su versión en ``PRAGMA user_version``; abrir una
base de una versión más nueva que la conocida se rechaza sin tocarla.
"""

import sqlite3
from pathlib import Path

from vozflow import rutas

_ESQUEMA_1 = """
CREATE TABLE modo (
    id INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE CHECK (length(nombre) BETWEEN 1 AND 60),
    es_general INTEGER NOT NULL DEFAULT 0 CHECK (es_general IN (0, 1)),
    quitar_muletillas INTEGER NOT NULL DEFAULT 1 CHECK (quitar_muletillas IN (0, 1)),
    puntuacion_automatica INTEGER NOT NULL DEFAULT 1 CHECK (puntuacion_automatica IN (0, 1)),
    comandos_de_voz INTEGER NOT NULL DEFAULT 1 CHECK (comandos_de_voz IN (0, 1)),
    reescribir INTEGER NOT NULL DEFAULT 0 CHECK (reescribir IN (0, 1)),
    instruccion TEXT NOT NULL DEFAULT '',
    tipo_pegado TEXT NOT NULL DEFAULT 'automatico'
        CHECK (tipo_pegado IN ('normal', 'terminal', 'automatico')),
    salto_de_linea TEXT NOT NULL DEFAULT 'conservar'
        CHECK (salto_de_linea IN ('conservar', 'espacio'))
);
-- Exactamente un modo es el general, y no se puede borrar.
CREATE UNIQUE INDEX modo_general_unico ON modo (es_general) WHERE es_general = 1;
CREATE TRIGGER modo_general_no_se_borra BEFORE DELETE ON modo WHEN OLD.es_general = 1
BEGIN SELECT RAISE(ABORT, 'El modo general no se puede borrar'); END;

CREATE TABLE asignacion (
    aplicacion TEXT PRIMARY KEY CHECK (length(aplicacion) > 0),
    modo_id INTEGER NOT NULL REFERENCES modo (id),
    es_terminal INTEGER NOT NULL DEFAULT 0 CHECK (es_terminal IN (0, 1))
);
-- Si se borra un modo, sus aplicaciones pasan al general (conservan la marca de terminal).
CREATE TRIGGER modo_borrado_reasigna BEFORE DELETE ON modo WHEN OLD.es_general = 0
BEGIN
    UPDATE asignacion SET modo_id = (SELECT id FROM modo WHERE es_general = 1)
    WHERE modo_id = OLD.id;
    UPDATE dictado SET modo_id = NULL WHERE modo_id = OLD.id;
END;

CREATE TABLE dictado (
    id INTEGER PRIMARY KEY,
    creado_en TEXT NOT NULL,
    texto_crudo TEXT NOT NULL,
    texto_final TEXT NOT NULL,
    idioma TEXT NOT NULL DEFAULT '',
    duracion_audio_ms INTEGER NOT NULL CHECK (duracion_audio_ms > 0),
    duracion_proceso_ms INTEGER NOT NULL CHECK (duracion_proceso_ms >= 0),
    aplicacion TEXT NOT NULL DEFAULT '',
    modo_id INTEGER REFERENCES modo (id),
    reescrito INTEGER NOT NULL DEFAULT 0 CHECK (reescrito IN (0, 1)),
    proveedor TEXT NOT NULL DEFAULT '',
    estado TEXT NOT NULL CHECK (estado IN ('insertado', 'no_insertado', 'error'))
);
CREATE INDEX dictado_por_fecha ON dictado (creado_en);
-- Búsqueda de texto completo sobre el texto final, sin distinguir mayúsculas ni acentos.
CREATE VIRTUAL TABLE dictado_fts USING fts5(
    texto_final, content = 'dictado', content_rowid = 'id',
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER dictado_fts_alta AFTER INSERT ON dictado BEGIN
    INSERT INTO dictado_fts (rowid, texto_final) VALUES (new.id, new.texto_final);
END;
CREATE TRIGGER dictado_fts_baja AFTER DELETE ON dictado BEGIN
    INSERT INTO dictado_fts (dictado_fts, rowid, texto_final)
    VALUES ('delete', old.id, old.texto_final);
END;
CREATE TRIGGER dictado_fts_cambio AFTER UPDATE OF texto_final ON dictado BEGIN
    INSERT INTO dictado_fts (dictado_fts, rowid, texto_final)
    VALUES ('delete', old.id, old.texto_final);
    INSERT INTO dictado_fts (rowid, texto_final) VALUES (new.id, new.texto_final);
END;

-- ``*_norm`` guarda la forma sin mayúsculas ni acentos: es la que debe ser única.
CREATE TABLE entrada_diccionario (
    id INTEGER PRIMARY KEY,
    palabra TEXT NOT NULL CHECK (length(palabra) BETWEEN 1 AND 80),
    palabra_norm TEXT NOT NULL UNIQUE CHECK (length(palabra_norm) > 0),
    nota TEXT NOT NULL DEFAULT ''
);

CREATE TABLE atajo_texto (
    id INTEGER PRIMARY KEY,
    disparador TEXT NOT NULL CHECK (length(disparador) BETWEEN 1 AND 100),
    disparador_norm TEXT NOT NULL UNIQUE CHECK (length(disparador_norm) > 0),
    reemplazo TEXT NOT NULL CHECK (length(reemplazo) > 0)
);

CREATE TABLE proveedor (
    id TEXT PRIMARY KEY CHECK (id IN ('ollama', 'anthropic', 'openrouter')),
    activo INTEGER NOT NULL DEFAULT 0 CHECK (activo IN (0, 1)),
    modelo TEXT NOT NULL DEFAULT '',
    direccion TEXT NOT NULL DEFAULT '',
    tiempo_maximo_s INTEGER NOT NULL DEFAULT 15 CHECK (tiempo_maximo_s BETWEEN 3 AND 60)
);
CREATE UNIQUE INDEX proveedor_activo_unico ON proveedor (activo) WHERE activo = 1;

CREATE TABLE ajuste (
    clave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

-- Modos de fábrica.
INSERT INTO modo (nombre, es_general) VALUES ('General', 1);
INSERT INTO modo (nombre, tipo_pegado, salto_de_linea) VALUES ('Terminal', 'terminal', 'espacio');
INSERT INTO modo (nombre, puntuacion_automatica) VALUES ('Código', 0);
INSERT INTO modo (nombre, salto_de_linea) VALUES ('Mensajería', 'espacio');
INSERT INTO modo (nombre) VALUES ('Documentos');
"""

# Versión 2: por qué un dictado no llegó a insertarse (un código estable del catálogo de mensajes,
# nunca texto libre). Los dictados anteriores quedan con '' y se muestran con el mensaje genérico.
_ESQUEMA_2 = "ALTER TABLE dictado ADD COLUMN motivo TEXT NOT NULL DEFAULT '';"

_MIGRACIONES = {1: _ESQUEMA_1, 2: _ESQUEMA_2}
VERSION_DEL_ESQUEMA = max(_MIGRACIONES)


class EsquemaMasNuevo(Exception):
    """La base la creó una versión más nueva de vozflow."""


def abrir_base(ruta: Path | str | None = None) -> sqlite3.Connection:
    """Abre (y crea o migra) la base. Sin ``ruta``, la de siempre: ``~/.local/share/vozflow``."""
    destino = ruta if ruta is not None else rutas.ruta_base_de_datos()
    if str(destino) != ":memory:":
        rutas.asegurar(Path(destino).parent)
    # Una conexión sola se comparte entre el hilo del dictado y el principal.
    base = sqlite3.connect(destino, check_same_thread=False)
    base.row_factory = sqlite3.Row
    try:
        version = int(base.execute("PRAGMA user_version").fetchone()[0])
        if version > VERSION_DEL_ESQUEMA:
            raise EsquemaMasNuevo(
                f"La base es de la versión {version} del esquema y esta vozflow solo conoce "
                f"hasta la {VERSION_DEL_ESQUEMA}: actualizá vozflow"
            )
        for siguiente in range(version + 1, VERSION_DEL_ESQUEMA + 1):
            base.executescript(
                f"BEGIN;\n{_MIGRACIONES[siguiente]}\nPRAGMA user_version = {siguiente};\nCOMMIT;"
            )
        base.execute("PRAGMA foreign_keys = ON")
    except BaseException:
        base.close()
        raise
    return base
