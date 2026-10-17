"""Los subcomandos que operan los datos sin interfaz: diccionario, atajos, modos, historial…"""

import sqlite3
from pathlib import Path

import pytest

from tests.dobles import GrabadoraFalsa, MotorFalso
from vozflow.__main__ import CODIGO_ERROR, CODIGO_OK, Dependencias, main
from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.historial import HistorialRepo
from vozflow.persistencia.modos_repo import ModosRepo


class Banco:
    """Un archivo de base por prueba; cada orden abre y cierra su propia conexión."""

    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self.dependencias = Dependencias(
            crear_grabadora=GrabadoraFalsa,
            crear_motor=lambda modelo: MotorFalso(),
            esperar=lambda s: None,
            descargar_modelo=lambda m: "",
            abrir_base=lambda: abrir_base(ruta),
        )

    def correr(self, *argumentos: str) -> int:
        return main(list(argumentos), self.dependencias)

    def base(self) -> sqlite3.Connection:
        return abrir_base(self.ruta)


@pytest.fixture
def b(tmp_path: Path) -> Banco:
    return Banco(tmp_path / "vozflow.db")


# ---- diccionario -------------------------------------------------------------------------------------


def test_diccionario_agregar_listar_y_borrar(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert b.correr("diccionario", "agregar", "SQLAlchemy", "--nota", "ORM de Python") == CODIGO_OK
    capsys.readouterr()

    assert b.correr("diccionario", "listar") == CODIGO_OK
    listado = capsys.readouterr().out
    assert "SQLAlchemy" in listado and "ORM de Python" in listado

    assert b.correr("diccionario", "borrar", "sqlalchemy") == CODIGO_OK
    b.correr("diccionario", "listar")
    assert "SQLAlchemy" not in capsys.readouterr().out


def test_una_palabra_repetida_es_un_error_claro(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    b.correr("diccionario", "agregar", "SQLAlchemy")
    capsys.readouterr()

    assert b.correr("diccionario", "agregar", "sqlalchemy") == CODIGO_ERROR

    salida = capsys.readouterr()
    assert "ya está" in salida.err and salida.out == ""


def test_borrar_algo_que_no_existe_avisa(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert b.correr("diccionario", "borrar", "nada") == CODIGO_ERROR
    assert "no está" in capsys.readouterr().err


def test_un_diccionario_vacio_lo_dice(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    b.correr("diccionario", "listar")

    assert "vacío" in capsys.readouterr().out


# ---- atajos de texto ---------------------------------------------------------------------------------------


def test_atajos_agregar_con_saltos_de_linea_escritos_como_barra_n(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("atajos", "agregar", "mi firma", r"Saludos,\nPedro") == CODIGO_OK

    (atajo,) = AtajosTextoRepo(b.base()).listar()
    assert atajo.reemplazo == "Saludos,\nPedro"
    capsys.readouterr()
    b.correr("atajos", "listar")
    listado = capsys.readouterr().out
    assert "mi firma" in listado and r"Saludos,\nPedro" in listado
    assert len(listado.strip().splitlines()) == 1  # un atajo por línea


def test_atajos_borrar(b: Banco) -> None:
    b.correr("atajos", "agregar", "ask", "pedido")

    assert b.correr("atajos", "borrar", "ASK") == CODIGO_OK
    assert b.correr("atajos", "borrar", "ask") == CODIGO_ERROR


def test_un_atajo_con_reemplazo_vacio_es_un_error(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("atajos", "agregar", "ask", "   ") == CODIGO_ERROR
    assert "reemplazo" in capsys.readouterr().err


# ---- modos y asignaciones -------------------------------------------------------------------------------------


def test_modos_listar_muestra_los_de_fabrica(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert b.correr("modos", "listar") == CODIGO_OK

    salida = capsys.readouterr().out
    for nombre in ("General", "Terminal", "Código", "Mensajería", "Documentos"):
        assert nombre in salida


def test_modos_crear_con_banderas_y_borrar(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert (
        b.correr(
            "modos",
            "crear",
            "Notas",
            "--sin-puntuacion",
            "--pegado",
            "normal",
            "--salto",
            "espacio",
        )
        == CODIGO_OK
    )
    modo = next(m for m in ModosRepo(b.base()).listar() if m.nombre == "Notas")
    assert not modo.puntuacion_automatica and modo.tipo_pegado == "normal"
    assert modo.salto_de_linea == "espacio"

    assert b.correr("modos", "borrar", "notas") == CODIGO_OK


def test_no_se_puede_borrar_el_modo_general(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert b.correr("modos", "borrar", "General") == CODIGO_ERROR
    assert "general" in capsys.readouterr().err


def test_asignar_una_aplicacion_a_un_modo(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert b.correr("asignar", "ptyxis", "Terminal", "--terminal") == CODIGO_OK
    capsys.readouterr()

    b.correr("asignar", "--listar")

    listado = capsys.readouterr().out
    assert "ptyxis" in listado and "Terminal" in listado


def test_asignar_a_un_modo_que_no_existe_es_un_error(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("asignar", "ptyxis", "Inventado") == CODIGO_ERROR
    assert "Inventado" in capsys.readouterr().err


def test_quitar_una_asignacion(b: Banco) -> None:
    b.correr("asignar", "ptyxis", "Terminal")

    assert b.correr("asignar", "--quitar", "ptyxis") == CODIGO_OK
    assert b.correr("asignar", "--quitar", "ptyxis") == CODIGO_ERROR


# ---- historial -----------------------------------------------------------------------------------------------------


def _con_dictados(b: Banco) -> None:
    historial = HistorialRepo(b.base())
    for texto in ("Reunión con el equipo", "Comprar pan"):
        historial.guardar(
            texto_crudo=texto,
            texto_final=texto,
            duracion_audio_ms=1000,
            duracion_proceso_ms=500,
            estado="insertado",
        )


def test_historial_listar_y_buscar(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    _con_dictados(b)

    assert b.correr("historial", "listar") == CODIGO_OK
    todo = capsys.readouterr().out
    assert "Reunión" in todo and "Comprar pan" in todo

    assert b.correr("historial", "buscar", "reunion") == CODIGO_OK
    hallado = capsys.readouterr().out
    assert "Reunión" in hallado and "pan" not in hallado


def test_historial_mostrar_un_dictado_completo(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    _con_dictados(b)
    b.correr("historial", "listar")
    id_ = capsys.readouterr().out.split()[0]

    assert b.correr("historial", "mostrar", id_) == CODIGO_OK

    assert "Comprar pan" in capsys.readouterr().out


def test_historial_borrar_uno_y_todo(b: Banco) -> None:
    _con_dictados(b)
    historial = HistorialRepo(b.base())
    id_ = str(historial.listar()[0].id)

    assert b.correr("historial", "borrar", id_) == CODIGO_OK
    assert historial.contar() == 1
    assert b.correr("historial", "borrar", id_) == CODIGO_ERROR
    assert b.correr("historial", "borrar-todo") == CODIGO_OK
    assert historial.contar() == 0


def test_un_id_que_no_es_numero_es_un_error_de_uso(b: Banco) -> None:
    with pytest.raises(SystemExit) as salida:
        b.correr("historial", "mostrar", "abc")

    assert salida.value.code == 2


# ---- exportar e importar -----------------------------------------------------------------------------------------------


def test_exportar_e_importar_reproducen_los_datos(
    b: Banco, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    b.correr("diccionario", "agregar", "SQLAlchemy")
    b.correr("atajos", "agregar", "mi firma", "Pedro")
    archivo = tmp_path / "copia.json"
    assert b.correr("exportar", str(archivo)) == CODIGO_OK
    assert archivo.is_file()

    b.correr("diccionario", "borrar", "SQLAlchemy")
    b.correr("atajos", "borrar", "mi firma")
    assert b.correr("importar", str(archivo)) == CODIGO_OK

    assert [e.palabra for e in DiccionarioRepo(b.base()).listar()] == ["SQLAlchemy"]
    assert "importó" in capsys.readouterr().out.lower()


def test_importar_un_archivo_invalido_no_cambia_nada(
    b: Banco, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    b.correr("diccionario", "agregar", "uno")
    archivo = tmp_path / "malo.json"
    archivo.write_text('{"formato": "vozflow-copia", "version": 9}', encoding="utf-8")
    capsys.readouterr()

    assert b.correr("importar", str(archivo)) == CODIGO_ERROR

    assert "versión" in capsys.readouterr().err
    assert [e.palabra for e in DiccionarioRepo(b.base()).listar()] == ["uno"]


def test_importar_un_archivo_que_no_existe(
    b: Banco, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("importar", str(tmp_path / "no.json")) == CODIGO_ERROR
    assert "leer" in capsys.readouterr().err


# ---- la prueba independiente del lote -----------------------------------------------------------------------------------


def test_recorrido_completo_del_lote_3(
    b: Banco, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("diccionario", "agregar", "SQLAlchemy") == CODIGO_OK
    assert b.correr("atajos", "agregar", "mi firma", r"Saludos,\nPedro") == CODIGO_OK
    assert b.correr("asignar", "ptyxis", "Terminal") == CODIGO_OK
    _con_dictados(b)
    capsys.readouterr()
    assert b.correr("historial", "buscar", "pan") == CODIGO_OK
    assert "Comprar pan" in capsys.readouterr().out
    assert b.correr("exportar", str(tmp_path / "c.json")) == CODIGO_OK
    assert b.correr("diccionario", "borrar", "SQLAlchemy") == CODIGO_OK

    assert b.correr("importar", str(tmp_path / "c.json")) == CODIGO_OK

    assert [e.palabra for e in DiccionarioRepo(b.base()).listar()] == ["SQLAlchemy"]
