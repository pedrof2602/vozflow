"""Copia de seguridad (RF-022): exportar e importar según contracts/formato-de-exportacion.md."""

import contextlib
import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from vozflow.dominio.copia import FORMATO, VERSION, CopiaInvalida, VersionNoSoportada
from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.copia_repo import CopiaRepo
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.historial import HistorialRepo
from vozflow.persistencia.modos_repo import ModosRepo

AHORA = datetime(2026, 10, 17, 9, 30, tzinfo=UTC)


class Mundo:
    def __init__(self) -> None:
        self.base = abrir_base(":memory:")
        self.diccionario = DiccionarioRepo(self.base)
        self.atajos = AtajosTextoRepo(self.base)
        self.modos = ModosRepo(self.base)
        self.asignaciones = AsignacionesRepo(self.base)
        self.copia = CopiaRepo(self.base)

    def exportado(self) -> dict:  # type: ignore[type-arg]
        return json.loads(self.copia.exportar(AHORA))  # type: ignore[no-any-return]

    def estado(self) -> tuple[object, ...]:
        """Todo lo que la copia cubre, para comparar antes y después."""
        return (
            self.diccionario.listar(),
            self.atajos.listar(),
            self.modos.listar(),
            self.asignaciones.listar(),
        )


@pytest.fixture
def m() -> Mundo:
    return Mundo()


def _archivo(**cambios: object) -> str:
    base: dict[str, object] = {
        "formato": FORMATO,
        "version": VERSION,
        "creado_en": "2026-10-17T09:30:00Z",
        "diccionario": [],
        "atajos_de_texto": [],
        "modos": [],
        "asignaciones": [],
    }
    base.update(cambios)
    return json.dumps(base, ensure_ascii=False)


# ---- exportar ------------------------------------------------------------------------------------------------


def test_el_archivo_lleva_formato_y_version(m: Mundo) -> None:
    datos = m.exportado()

    assert (datos["formato"], datos["version"]) == ("vozflow-copia", 1)
    assert datos["creado_en"] == "2026-10-17T09:30:00Z"


def test_exporta_diccionario_atajos_modos_y_asignaciones(m: Mundo) -> None:
    m.diccionario.agregar("SQLAlchemy", "ORM")
    m.atajos.agregar("mi firma", "Saludos,\nPedro")
    terminal = m.modos.obtener("Terminal")
    assert terminal is not None
    m.asignaciones.asignar("org.gnome.Ptyxis", terminal.id, es_terminal=True)

    datos = m.exportado()

    assert datos["diccionario"] == [{"palabra": "SQLAlchemy", "nota": "ORM"}]
    assert datos["atajos_de_texto"] == [{"disparador": "mi firma", "reemplazo": "Saludos,\nPedro"}]
    assert datos["asignaciones"] == [
        {"aplicacion": "org.gnome.ptyxis", "modo": "Terminal", "es_terminal": True}
    ]
    terminal_exportado = next(x for x in datos["modos"] if x["nombre"] == "Terminal")
    assert terminal_exportado == {
        "nombre": "Terminal",
        "es_general": False,
        "quitar_muletillas": True,
        "puntuacion_automatica": True,
        "comandos_de_voz": True,
        "reescribir": False,
        "instruccion": "",
        "tipo_pegado": "terminal",
        "salto_de_linea": "espacio",
    }


def test_no_incluye_el_historial_ni_los_ajustes_ni_claves(m: Mundo) -> None:
    HistorialRepo(m.base).guardar(
        texto_crudo="secreto", texto_final="secreto", duracion_audio_ms=1,
        duracion_proceso_ms=1, estado="insertado",
    )  # fmt: skip
    m.base.execute("INSERT INTO ajuste (clave, valor) VALUES ('motor.hilos', '2')")

    texto = m.copia.exportar(AHORA)

    assert "secreto" not in texto and "motor.hilos" not in texto
    assert set(json.loads(texto)) == {
        "formato", "version", "creado_en", "diccionario", "atajos_de_texto", "modos", "asignaciones",
    }  # fmt: skip


def test_el_archivo_es_utf8_con_sangria_y_sin_escapar_los_acentos(m: Mundo) -> None:
    m.diccionario.agregar("Cañón")

    texto = m.copia.exportar(AHORA)

    assert "Cañón" in texto and "\\u00" not in texto
    assert "\n  " in texto  # con sangría


def test_el_orden_es_estable_sin_importar_el_orden_de_alta(m: Mundo) -> None:
    otro = Mundo()
    for palabra in ("zeta", "alfa", "Mu"):
        m.diccionario.agregar(palabra)
    for palabra in ("Mu", "zeta", "alfa"):
        otro.diccionario.agregar(palabra)

    assert m.copia.exportar(AHORA) == otro.copia.exportar(AHORA)
    assert [x["palabra"] for x in m.exportado()["diccionario"]] == ["alfa", "Mu", "zeta"]


def test_el_modo_general_va_primero(m: Mundo) -> None:
    m.modos.crear("Aaa primero alfabeticamente")

    nombres = [x["nombre"] for x in m.exportado()["modos"]]

    assert nombres[0] == "General"


def test_exportar_dos_veces_da_lo_mismo(m: Mundo) -> None:
    m.diccionario.agregar("uno")

    assert m.copia.exportar(AHORA) == m.copia.exportar(AHORA)


def test_termina_con_un_salto_de_linea(m: Mundo) -> None:
    assert m.copia.exportar(AHORA).endswith("\n")


# ---- importar: el formato y la versión ---------------------------------------------------------------------------


def test_importa_un_archivo_valido_y_resume_lo_hecho(m: Mundo) -> None:
    resumen = m.copia.importar(
        _archivo(
            diccionario=[{"palabra": "FastAPI", "nota": ""}],
            atajos_de_texto=[{"disparador": "ask", "reemplazo": "pedido"}],
        )
    )

    assert [e.palabra for e in m.diccionario.listar()] == ["FastAPI"]
    assert [a.disparador for a in m.atajos.listar()] == ["ask"]
    assert (resumen.diccionario, resumen.atajos_de_texto) == (1, 1)


def test_una_version_mayor_se_rechaza_sin_importar_nada(m: Mundo) -> None:
    antes = m.estado()

    with pytest.raises(VersionNoSoportada, match="2"):
        m.copia.importar(_archivo(version=2, diccionario=[{"palabra": "x", "nota": ""}]))

    assert m.estado() == antes


@pytest.mark.parametrize(
    "texto",
    [
        "",
        "no es json",
        "[]",
        '{"version": 1}',
        '{"formato": "otra-cosa", "version": 1}',
        '{"formato": "vozflow-copia"}',
        '{"formato": "vozflow-copia", "version": "1"}',
        '{"formato": "vozflow-copia", "version": 0}',
    ],
)
def test_un_archivo_que_no_es_una_copia_se_rechaza(m: Mundo, texto: str) -> None:
    antes = m.estado()

    with pytest.raises(CopiaInvalida):
        m.copia.importar(texto)

    assert m.estado() == antes


def test_las_secciones_que_faltan_se_toman_como_vacias(m: Mundo) -> None:
    m.copia.importar('{"formato": "vozflow-copia", "version": 1}')

    assert m.diccionario.listar() == []


# ---- importar: mezclar sin borrar -----------------------------------------------------------------------------------


def test_actualiza_lo_que_ya_existe_y_no_borra_lo_demas(m: Mundo) -> None:
    m.diccionario.agregar("SQLAlchemy", "vieja")
    m.diccionario.agregar("Solo local")
    m.atajos.agregar("firma", "vieja")

    m.copia.importar(
        _archivo(
            diccionario=[{"palabra": "sqlalchemy", "nota": "nueva"}],
            atajos_de_texto=[{"disparador": "FIRMA", "reemplazo": "nueva"}],
        )
    )

    assert {e.palabra: e.nota for e in m.diccionario.listar()} == {
        "SQLAlchemy": "nueva",
        "Solo local": "",
    }
    assert [(a.disparador, a.reemplazo) for a in m.atajos.listar()] == [("firma", "nueva")]


def test_importar_dos_veces_no_duplica(m: Mundo) -> None:
    archivo = _archivo(diccionario=[{"palabra": "uno", "nota": ""}])

    m.copia.importar(archivo)
    m.copia.importar(archivo)

    assert len(m.diccionario.listar()) == 1


def _modo(nombre: str, **cambios: object) -> dict[str, object]:
    base: dict[str, object] = {
        "nombre": nombre,
        "es_general": False,
        "quitar_muletillas": True,
        "puntuacion_automatica": True,
        "comandos_de_voz": True,
        "reescribir": False,
        "instruccion": "",
        "tipo_pegado": "automatico",
        "salto_de_linea": "conservar",
    }
    base.update(cambios)
    return base


def test_un_modo_nuevo_se_crea_y_uno_existente_se_actualiza(m: Mundo) -> None:
    m.copia.importar(
        _archivo(
            modos=[
                _modo("Reuniones", instruccion="Formal"),
                _modo("terminal", puntuacion_automatica=False),
            ]
        )
    )

    reuniones = m.modos.obtener("Reuniones")
    terminal = m.modos.obtener("Terminal")
    assert reuniones is not None and reuniones.instruccion == "Formal"
    assert terminal is not None and terminal.puntuacion_automatica is False
    assert terminal.nombre == "Terminal"  # conserva su nombre


def test_el_modo_general_actualiza_sus_banderas_pero_no_cambia_de_nombre(m: Mundo) -> None:
    m.copia.importar(_archivo(modos=[_modo("Principal", es_general=True, quitar_muletillas=False)]))

    general = m.modos.general()
    assert general.nombre == "General" and general.quitar_muletillas is False
    assert m.modos.obtener("Principal") is None
    assert len([x for x in m.modos.listar() if x.es_general]) == 1


def test_nunca_se_crea_un_segundo_modo_general(m: Mundo) -> None:
    m.copia.importar(_archivo(modos=[_modo("Otro", es_general=True)]))

    assert len([x for x in m.modos.listar() if x.es_general]) == 1


def test_las_asignaciones_se_resuelven_por_nombre_de_modo(m: Mundo) -> None:
    m.copia.importar(
        _archivo(
            modos=[_modo("Reuniones")],
            asignaciones=[
                {"aplicacion": "Teams", "modo": "reuniones", "es_terminal": False},
                {"aplicacion": "ptyxis", "modo": "TERMINAL", "es_terminal": True},
            ],
        )
    )

    reuniones = m.modos.obtener("Reuniones")
    terminal = m.modos.obtener("Terminal")
    assert reuniones is not None and terminal is not None
    asignado = {a.aplicacion: (a.modo_id, a.es_terminal) for a in m.asignaciones.listar()}
    assert asignado == {"teams": (reuniones.id, False), "ptyxis": (terminal.id, True)}


def test_una_asignacion_al_modo_general_con_otro_nombre_va_al_general(m: Mundo) -> None:
    m.copia.importar(
        _archivo(
            modos=[_modo("Principal", es_general=True)],
            asignaciones=[{"aplicacion": "x", "modo": "Principal", "es_terminal": False}],
        )
    )

    assert m.asignaciones.obtener("x").modo_id == m.modos.general().id  # type: ignore[union-attr]


# ---- importar: todo o nada ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("seccion", "entrada", "debe_decir"),
    [
        ("atajos_de_texto", {"disparador": "", "reemplazo": "x"}, "atajos_de_texto"),
        ("atajos_de_texto", {"disparador": "a", "reemplazo": ""}, "reemplazo"),
        ("diccionario", {"palabra": "", "nota": ""}, "diccionario"),
        ("diccionario", {"palabra": "x" * 81, "nota": ""}, "80"),
        ("diccionario", {"nota": "sin palabra"}, "palabra"),
        ("diccionario", "texto suelto", "diccionario"),
        ("modos", {**_modo("X"), "tipo_pegado": "raro"}, "pegado"),
        ("modos", {**_modo("X"), "salto_de_linea": "raro"}, "salto"),
        ("modos", {**_modo("X"), "quitar_muletillas": "si"}, "quitar_muletillas"),
        ("modos", {**_modo(""), "nombre": ""}, "nombre"),
        (
            "asignaciones",
            {"aplicacion": "x", "modo": "No existe", "es_terminal": False},
            "No existe",
        ),
        ("asignaciones", {"aplicacion": "", "modo": "General", "es_terminal": False}, "aplicaci"),
        (
            "asignaciones",
            {"aplicacion": "x", "modo": "General", "es_terminal": "no"},
            "es_terminal",
        ),
    ],
)
def test_una_entrada_invalida_anula_todo_y_dice_cual_fallo(
    m: Mundo, seccion: str, entrada: object, debe_decir: str
) -> None:
    antes = m.estado()
    validas: dict[str, list[object]] = {
        "diccionario": [{"palabra": "valida", "nota": ""}],
        "atajos_de_texto": [{"disparador": "valido", "reemplazo": "x"}],
        "modos": [_modo("Valido")],
    }
    validas[seccion] = [*validas.get(seccion, []), entrada]

    with pytest.raises(CopiaInvalida) as error:
        m.copia.importar(_archivo(**validas))

    assert debe_decir in str(error.value)
    assert m.estado() == antes


def test_el_mensaje_indica_la_posicion_de_la_entrada_que_fallo(m: Mundo) -> None:
    with pytest.raises(CopiaInvalida, match=r"atajos_de_texto\[1\]"):
        m.copia.importar(
            _archivo(
                atajos_de_texto=[
                    {"disparador": "bien", "reemplazo": "x"},
                    {"disparador": "", "reemplazo": "x"},
                ]
            )
        )


# ---- archivos --------------------------------------------------------------------------------------------------------------


def test_escribe_y_lee_un_archivo_utf8(m: Mundo, tmp_path: Path) -> None:
    m.diccionario.agregar("Cañón")
    destino = tmp_path / "copia.json"

    m.copia.exportar_a(destino, AHORA)
    otro = Mundo()
    otro.copia.importar_de(destino)

    assert destino.read_bytes().decode("utf-8").count("Cañón") == 1
    assert [e.palabra for e in otro.diccionario.listar()] == ["Cañón"]


def test_importar_un_archivo_que_no_existe_es_un_error_claro(m: Mundo, tmp_path: Path) -> None:
    with pytest.raises(CopiaInvalida, match="leer"):
        m.copia.importar_de(tmp_path / "no-existe.json")


# ---- propiedad: exportar → importar reproduce lo exportado --------------------------------------------------------------------

_TEXTO = st.text(
    alphabet=st.characters(categories=("Lu", "Ll", "Nd"), include_characters=" ñáéíóúü\n"),
    min_size=1,
    max_size=15,
)
_ESTADOS = st.fixed_dictionaries(
    {
        "palabras": st.lists(st.tuples(_TEXTO, _TEXTO), max_size=6),
        "atajos": st.lists(st.tuples(_TEXTO, _TEXTO), max_size=6),
        "modos": st.lists(
            st.tuples(
                _TEXTO,
                st.booleans(),
                st.booleans(),
                st.sampled_from(["normal", "terminal", "automatico"]),
                st.sampled_from(["conservar", "espacio"]),
            ),
            max_size=4,
        ),
        "apps": st.lists(st.tuples(_TEXTO, st.booleans(), st.integers(0, 9)), max_size=5),
    }
)


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(_ESTADOS)
def test_exportar_e_importar_en_una_base_vacia_reproduce_lo_exportado(
    estado: dict[str, Any],
) -> None:
    origen = Mundo()
    for palabra, nota in estado["palabras"]:
        _intentar(partial(origen.diccionario.agregar, palabra, nota))
    for disparador, reemplazo in estado["atajos"]:
        _intentar(partial(origen.atajos.agregar, disparador, reemplazo))
    for nombre, muletillas, puntuacion, pegado, salto in estado["modos"]:
        _intentar(
            partial(
                origen.modos.crear,
                nombre,
                quitar_muletillas=muletillas,
                puntuacion_automatica=puntuacion,
                tipo_pegado=pegado,
                salto_de_linea=salto,
            )
        )
    modos = origen.modos.listar()
    for aplicacion, terminal, indice in estado["apps"]:
        _intentar(
            partial(
                origen.asignaciones.asignar,
                aplicacion,
                modos[indice % len(modos)].id,
                es_terminal=terminal,
            )
        )

    texto = origen.copia.exportar(AHORA)
    destino = Mundo()
    destino.copia.importar(texto)

    assert destino.copia.exportar(AHORA) == texto


def _intentar(accion: Callable[[], object]) -> None:
    # Si el generador produjo algo repetido o fuera de las reglas, se descarta.
    with contextlib.suppress(DatoInvalido):
        accion()


def test_el_sqlite_de_la_prueba_es_el_que_se_espera() -> None:
    assert sqlite3.sqlite_version_info >= (3, 35)
