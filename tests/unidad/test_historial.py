"""Historial de dictados (RF-027, RF-030): guardar, buscar, recuperar y borrar."""

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from vozflow.dominio.historial import Dictado
from vozflow.insercion.puerto import Destino, ResultadoInsercion
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.historial import HistorialRepo

AHORA = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


@pytest.fixture
def base() -> sqlite3.Connection:
    return abrir_base(":memory:")


@pytest.fixture
def historial(base: sqlite3.Connection) -> HistorialRepo:
    return HistorialRepo(base)


def _guardar(historial: HistorialRepo, texto: str = "hola mundo", **extra: Any) -> Dictado | None:
    datos: dict[str, Any] = {
        "texto_crudo": texto,
        "texto_final": texto,
        "duracion_audio_ms": 2000,
        "duracion_proceso_ms": 900,
        "estado": "insertado",
    }
    datos.update(extra)
    return historial.guardar(**datos)


def test_guarda_todos_los_campos(historial: HistorialRepo, base: sqlite3.Connection) -> None:
    modo = base.execute("SELECT id FROM modo WHERE nombre = 'Terminal'").fetchone()[0]

    dictado = historial.guardar(
        texto_crudo="eh hola",
        texto_final="Hola.",
        idioma="es",
        duracion_audio_ms=1500,
        duracion_proceso_ms=800,
        aplicacion="ptyxis",
        modo_id=modo,
        reescrito=True,
        proveedor="ollama",
        estado="no_insertado",
        creado_en=AHORA,
    )

    assert dictado is not None
    guardado = historial.obtener(dictado.id)
    assert guardado == dictado
    assert (guardado.texto_crudo, guardado.texto_final, guardado.idioma) == (
        "eh hola",
        "Hola.",
        "es",
    )
    assert (guardado.duracion_audio_ms, guardado.duracion_proceso_ms) == (1500, 800)
    assert (guardado.aplicacion, guardado.modo_id, guardado.reescrito) == ("ptyxis", modo, True)
    assert (guardado.proveedor, guardado.estado, guardado.creado_en) == (
        "ollama",
        "no_insertado",
        AHORA,
    )


def test_los_valores_opcionales_tienen_defecto(historial: HistorialRepo) -> None:
    dictado = _guardar(historial)

    assert dictado is not None
    assert (dictado.idioma, dictado.aplicacion, dictado.proveedor) == ("", "", "")
    assert dictado.modo_id is None and dictado.reescrito is False
    assert dictado.creado_en.tzinfo is not None


@pytest.mark.parametrize("estado", ["insertado", "no_insertado", "error"])
def test_acepta_los_tres_estados(historial: HistorialRepo, estado: str) -> None:
    dictado = _guardar(historial, estado=estado)

    assert dictado is not None and dictado.estado == estado


def test_rechaza_un_estado_desconocido(historial: HistorialRepo) -> None:
    with pytest.raises(DatoInvalido, match="estado"):
        _guardar(historial, estado="raro")


@pytest.mark.parametrize("duracion", [0, -5])
def test_la_duracion_del_audio_tiene_que_ser_mayor_que_cero(
    historial: HistorialRepo, duracion: int
) -> None:
    with pytest.raises(DatoInvalido, match="audio"):
        _guardar(historial, duracion_audio_ms=duracion)


def test_la_duracion_del_proceso_no_puede_ser_negativa(historial: HistorialRepo) -> None:
    with pytest.raises(DatoInvalido, match="proceso"):
        _guardar(historial, duracion_proceso_ms=-1)


def test_el_audio_nunca_se_guarda(historial: HistorialRepo, base: sqlite3.Connection) -> None:
    with pytest.raises(TypeError):
        historial.guardar(  # type: ignore[call-arg]
            texto_crudo="x",
            texto_final="x",
            duracion_audio_ms=1,
            duracion_proceso_ms=1,
            estado="insertado",
            audio=b"\x00\x01",
        )
    columnas = [f["name"] for f in base.execute("PRAGMA table_info(dictado)")]
    assert not [c for c in columnas if "audio" in c and c != "duracion_audio_ms"]


# ---- historial desactivado ------------------------------------------------------------------------


def test_con_el_historial_apagado_no_se_escribe_ninguna_fila(base: sqlite3.Connection) -> None:
    historial = HistorialRepo(base, activo=lambda: False)

    resultado = _guardar(historial)

    assert resultado is None
    assert base.execute("SELECT COUNT(*) FROM dictado").fetchone()[0] == 0
    assert base.execute("SELECT COUNT(*) FROM dictado_fts").fetchone()[0] == 0


def test_se_puede_apagar_y_prender_en_caliente(base: sqlite3.Connection) -> None:
    encendido = [True]
    historial = HistorialRepo(base, activo=lambda: encendido[0])

    _guardar(historial, "uno")
    encendido[0] = False
    _guardar(historial, "dos")
    encendido[0] = True
    _guardar(historial, "tres")

    assert [d.texto_final for d in historial.listar()] == ["tres", "uno"]


# ---- listar --------------------------------------------------------------------------------------------


def test_lista_primero_los_mas_recientes(historial: HistorialRepo) -> None:
    for i in range(3):
        _guardar(historial, f"dictado {i}", creado_en=AHORA + timedelta(minutes=i))

    assert [d.texto_final for d in historial.listar()] == ["dictado 2", "dictado 1", "dictado 0"]


def test_pagina_con_limite_y_desplazamiento(historial: HistorialRepo) -> None:
    for i in range(5):
        _guardar(historial, f"d{i}", creado_en=AHORA + timedelta(minutes=i))

    assert [d.texto_final for d in historial.listar(limite=2)] == ["d4", "d3"]
    assert [d.texto_final for d in historial.listar(limite=2, desplazamiento=2)] == ["d2", "d1"]


def test_a_igual_fecha_el_ultimo_guardado_va_primero(historial: HistorialRepo) -> None:
    _guardar(historial, "a", creado_en=AHORA)
    _guardar(historial, "b", creado_en=AHORA)

    assert [d.texto_final for d in historial.listar()] == ["b", "a"]


def test_cuenta_los_dictados(historial: HistorialRepo) -> None:
    assert historial.contar() == 0
    _guardar(historial)
    assert historial.contar() == 1


# ---- búsqueda de texto completo ------------------------------------------------------------------------------


def test_busca_sin_distinguir_mayusculas_ni_acentos(historial: HistorialRepo) -> None:
    _guardar(historial, "Reunión con el equipo de ventas")
    _guardar(historial, "Comprar pan")

    assert [d.texto_final for d in historial.buscar("REUNION")] == [
        "Reunión con el equipo de ventas"
    ]


def test_busca_por_prefijo_de_palabra(historial: HistorialRepo) -> None:
    _guardar(historial, "Reunión con el equipo")

    assert len(historial.buscar("reun")) == 1


def test_varias_palabras_tienen_que_estar_todas(historial: HistorialRepo) -> None:
    _guardar(historial, "reunión con el equipo")
    _guardar(historial, "reunión con el cliente")

    assert [d.texto_final for d in historial.buscar("reunion equipo")] == ["reunión con el equipo"]


def test_solo_busca_en_el_texto_final_no_en_el_crudo(historial: HistorialRepo) -> None:
    _guardar(historial, texto_crudo="eh muletilla", texto_final="Texto limpio")

    assert historial.buscar("muletilla") == []
    assert len(historial.buscar("limpio")) == 1


@pytest.mark.parametrize(
    "consulta", ['"', "'", "*", "-", "OR", "NEAR(", "a AND", "c++", "(", ":", "^x", '"a" "b']
)
def test_los_signos_raros_de_la_busqueda_no_rompen(historial: HistorialRepo, consulta: str) -> None:
    _guardar(historial, "texto normal")

    historial.buscar(consulta)  # no lanza


def test_una_busqueda_vacia_devuelve_lo_ultimo(historial: HistorialRepo) -> None:
    _guardar(historial, "uno")

    assert [d.texto_final for d in historial.buscar("   ")] == ["uno"]


def test_la_busqueda_respeta_el_limite(historial: HistorialRepo) -> None:
    for i in range(5):
        _guardar(historial, f"casa {i}")

    assert len(historial.buscar("casa", limite=3)) == 3


def test_un_dictado_borrado_deja_de_aparecer_en_la_busqueda(historial: HistorialRepo) -> None:
    dictado = _guardar(historial, "secreto")
    assert dictado is not None

    historial.borrar(dictado.id)

    assert historial.buscar("secreto") == []


# ---- copiar, volver a insertar y borrar -------------------------------------------------------------------------------


class PortapapelesFalso:
    def __init__(self) -> None:
        self.copiado: list[tuple[str, bool]] = []

    def copiar(self, texto: str, *, tambien_primaria: bool) -> None:
        self.copiado.append((texto, tambien_primaria))


class InsertorFalso:
    def __init__(self, resultado: ResultadoInsercion) -> None:
        self.resultado = resultado
        self.insertados: list[tuple[str, Destino]] = []

    def insertar(self, texto: str, destino: Destino) -> ResultadoInsercion:
        self.insertados.append((texto, destino))
        return self.resultado


def test_copia_el_texto_final_al_portapapeles(historial: HistorialRepo) -> None:
    dictado = _guardar(historial, texto_crudo="eh hola", texto_final="Hola.")
    assert dictado is not None
    portapapeles = PortapapelesFalso()

    assert historial.copiar(dictado.id, portapapeles) is True

    assert portapapeles.copiado == [("Hola.", False)]


def test_copiar_algo_que_no_existe_no_hace_nada(historial: HistorialRepo) -> None:
    portapapeles = PortapapelesFalso()

    assert historial.copiar(999, portapapeles) is False
    assert portapapeles.copiado == []


def test_vuelve_a_insertar_un_dictado_que_no_se_pudo_insertar(historial: HistorialRepo) -> None:
    dictado = _guardar(historial, "importante", estado="no_insertado")
    assert dictado is not None
    insertor = InsertorFalso(ResultadoInsercion.exito())

    resultado = historial.reinsertar(dictado.id, insertor, Destino())

    assert resultado.insertado is True
    assert insertor.insertados == [("importante", Destino())]
    reinsertado = historial.obtener(dictado.id)
    assert reinsertado is not None and reinsertado.estado == "insertado"


def test_si_la_reinsercion_falla_el_estado_no_cambia(historial: HistorialRepo) -> None:
    dictado = _guardar(historial, "importante", estado="no_insertado")
    assert dictado is not None
    insertor = InsertorFalso(ResultadoInsercion.fallido("sin ventana"))

    resultado = historial.reinsertar(dictado.id, insertor, Destino())

    assert resultado.insertado is False
    sigue = historial.obtener(dictado.id)
    assert sigue is not None and sigue.estado == "no_insertado"


def test_reinsertar_algo_que_no_existe_es_un_fallo_claro(historial: HistorialRepo) -> None:
    resultado = historial.reinsertar(999, InsertorFalso(ResultadoInsercion.exito()), Destino())

    assert resultado.insertado is False and resultado.motivo


def test_borra_uno_y_borra_todo(historial: HistorialRepo) -> None:
    a = _guardar(historial, "a")
    _guardar(historial, "b")
    _guardar(historial, "c")
    assert a is not None

    assert historial.borrar(a.id) is True
    assert historial.borrar(a.id) is False
    assert historial.contar() == 2
    assert historial.borrar_todo() == 2
    assert historial.contar() == 0


def test_si_se_borra_el_modo_el_dictado_queda_sin_modo(
    historial: HistorialRepo, base: sqlite3.Connection
) -> None:
    modo = base.execute("INSERT INTO modo (nombre) VALUES ('Temporal')").lastrowid
    dictado = _guardar(historial, modo_id=modo)
    assert dictado is not None

    base.execute("DELETE FROM modo WHERE id = ?", (modo,))

    sobrevive = historial.obtener(dictado.id)
    assert sobrevive is not None and sobrevive.modo_id is None
