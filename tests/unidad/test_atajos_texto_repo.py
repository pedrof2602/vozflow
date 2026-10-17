"""Atajos de texto (RF-020): validación y unicidad del disparador."""

import pytest

from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.errores import DatoDuplicado, DatoInvalido


@pytest.fixture
def repo() -> AtajosTextoRepo:
    return AtajosTextoRepo(abrir_base(":memory:"))


def test_agrega_y_lista(repo: AtajosTextoRepo) -> None:
    atajo = repo.agregar("mi firma", "Pedro Freimeyer")

    assert atajo.id > 0
    assert [(a.disparador, a.reemplazo) for a in repo.listar()] == [("mi firma", "Pedro Freimeyer")]


def test_el_reemplazo_puede_tener_varias_lineas_y_se_conserva_tal_cual(
    repo: AtajosTextoRepo,
) -> None:
    firma = "Saludos,\n  Pedro\n\n"

    repo.agregar("firma", firma)

    assert repo.listar()[0].reemplazo == firma


@pytest.mark.parametrize("disparador", ["", "   "])
def test_el_disparador_es_obligatorio(repo: AtajosTextoRepo, disparador: str) -> None:
    with pytest.raises(DatoInvalido, match="disparador"):
        repo.agregar(disparador, "x")


@pytest.mark.parametrize("reemplazo", ["", "   ", "\n\n"])
def test_el_reemplazo_es_obligatorio(repo: AtajosTextoRepo, reemplazo: str) -> None:
    with pytest.raises(DatoInvalido, match="reemplazo"):
        repo.agregar("firma", reemplazo)


def test_el_disparador_tiene_un_maximo_de_100_caracteres(repo: AtajosTextoRepo) -> None:
    repo.agregar("a" * 100, "x")

    with pytest.raises(DatoInvalido, match="100"):
        repo.agregar("b" * 101, "x")


def test_el_disparador_se_guarda_sin_espacios_sobrantes(repo: AtajosTextoRepo) -> None:
    assert repo.agregar("  mi firma ", "x").disparador == "mi firma"


@pytest.mark.parametrize("repetido", ["MI FIRMA", "mi  firma", "Mi Firma "])
def test_es_unico_sin_distinguir_mayusculas_ni_espacios_repetidos(
    repo: AtajosTextoRepo, repetido: str
) -> None:
    repo.agregar("mi firma", "uno")

    with pytest.raises(DatoDuplicado):
        repo.agregar(repetido, "dos")


def test_es_unico_sin_distinguir_acentos(repo: AtajosTextoRepo) -> None:
    repo.agregar("mi dirección", "uno")

    with pytest.raises(DatoDuplicado):
        repo.agregar("MI DIRECCION", "dos")


def test_borra_por_id_y_por_disparador(repo: AtajosTextoRepo) -> None:
    a = repo.agregar("uno", "1")
    repo.agregar("dos", "2")

    assert repo.borrar(a.id) is True
    assert repo.borrar_disparador("DOS") is True
    assert repo.borrar(a.id) is False
    assert repo.listar() == []


def test_actualiza_el_reemplazo_de_un_disparador_existente(repo: AtajosTextoRepo) -> None:
    repo.agregar("firma", "vieja")

    repo.reemplazar("FIRMA", "nueva")

    assert [a.reemplazo for a in repo.listar()] == ["nueva"]
