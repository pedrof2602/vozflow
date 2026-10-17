"""Entradas del diccionario personal (RF-019): validación, unicidad y orden."""

import pytest

from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.errores import DatoDuplicado, DatoInvalido


@pytest.fixture
def repo() -> DiccionarioRepo:
    return DiccionarioRepo(abrir_base(":memory:"))


def test_agrega_y_lista_con_nota(repo: DiccionarioRepo) -> None:
    entrada = repo.agregar("SQLAlchemy", nota="ORM de Python")

    assert entrada.id > 0
    assert [(e.palabra, e.nota) for e in repo.listar()] == [("SQLAlchemy", "ORM de Python")]


def test_la_nota_es_opcional(repo: DiccionarioRepo) -> None:
    assert repo.agregar("Kubernetes").nota == ""


def test_lista_en_orden_de_alta(repo: DiccionarioRepo) -> None:
    for palabra in ("uno", "dos", "tres"):
        repo.agregar(palabra)

    assert [e.palabra for e in repo.listar()] == ["uno", "dos", "tres"]


def test_quita_espacios_sobrantes(repo: DiccionarioRepo) -> None:
    assert repo.agregar("  FastAPI \n").palabra == "FastAPI"


@pytest.mark.parametrize("palabra", ["", "   ", "\n"])
def test_la_palabra_es_obligatoria(repo: DiccionarioRepo, palabra: str) -> None:
    with pytest.raises(DatoInvalido, match="palabra"):
        repo.agregar(palabra)


def test_el_maximo_es_80_caracteres(repo: DiccionarioRepo) -> None:
    repo.agregar("a" * 80)

    with pytest.raises(DatoInvalido, match="80"):
        repo.agregar("b" * 81)


@pytest.mark.parametrize("repetida", ["sqlalchemy", "SQLALCHEMY", " SqlAlchemy "])
def test_es_unica_sin_distinguir_mayusculas(repo: DiccionarioRepo, repetida: str) -> None:
    repo.agregar("SQLAlchemy")

    with pytest.raises(DatoDuplicado):
        repo.agregar(repetida)

    assert len(repo.listar()) == 1


def test_es_unica_sin_distinguir_acentos(repo: DiccionarioRepo) -> None:
    repo.agregar("Cañón")

    with pytest.raises(DatoDuplicado):
        repo.agregar("CANON")


def test_el_duplicado_no_toca_la_entrada_original(repo: DiccionarioRepo) -> None:
    repo.agregar("SQLAlchemy", nota="la buena")

    with pytest.raises(DatoDuplicado):
        repo.agregar("sqlalchemy", nota="otra")

    assert repo.listar()[0].nota == "la buena"


def test_borra_por_id(repo: DiccionarioRepo) -> None:
    primera = repo.agregar("uno")
    repo.agregar("dos")

    assert repo.borrar(primera.id) is True

    assert [e.palabra for e in repo.listar()] == ["dos"]


def test_borrar_algo_que_no_existe_devuelve_falso(repo: DiccionarioRepo) -> None:
    assert repo.borrar(999) is False


def test_borra_por_palabra_sin_importar_mayusculas(repo: DiccionarioRepo) -> None:
    repo.agregar("SQLAlchemy")

    assert repo.borrar_palabra("sqlalchemy") is True
    assert repo.listar() == []


def test_se_puede_volver_a_agregar_lo_borrado(repo: DiccionarioRepo) -> None:
    entrada = repo.agregar("uno")
    repo.borrar(entrada.id)

    repo.agregar("uno")

    assert len(repo.listar()) == 1
