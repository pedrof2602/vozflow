"""Asignación de aplicaciones a modos (RF-021)."""

import pytest

from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.modos_repo import ModosRepo


@pytest.fixture
def repos() -> tuple[AsignacionesRepo, ModosRepo]:
    base = abrir_base(":memory:")
    return AsignacionesRepo(base), ModosRepo(base)


def test_asigna_una_aplicacion_a_un_modo(repos: tuple[AsignacionesRepo, ModosRepo]) -> None:
    asignaciones, modos = repos
    terminal = modos.obtener("Terminal")
    assert terminal is not None

    asignaciones.asignar("ptyxis", terminal.id)

    (asignacion,) = asignaciones.listar()
    assert (asignacion.aplicacion, asignacion.modo_id, asignacion.es_terminal) == (
        "ptyxis",
        terminal.id,
        False,
    )


def test_el_identificador_se_guarda_en_minusculas_y_sin_espacios_sobrantes(
    repos: tuple[AsignacionesRepo, ModosRepo],
) -> None:
    asignaciones, modos = repos

    asignaciones.asignar("  Google-Chrome ", modos.general().id)

    assert asignaciones.obtener("GOOGLE-CHROME") is not None
    assert asignaciones.listar()[0].aplicacion == "google-chrome"


def test_volver_a_asignar_cambia_el_modo_y_la_marca(
    repos: tuple[AsignacionesRepo, ModosRepo],
) -> None:
    asignaciones, modos = repos
    terminal = modos.obtener("Terminal")
    assert terminal is not None
    asignaciones.asignar("kitty", modos.general().id)

    asignaciones.asignar("kitty", terminal.id, es_terminal=True)

    (asignacion,) = asignaciones.listar()
    assert asignacion.modo_id == terminal.id and asignacion.es_terminal is True


def test_marcar_a_mano_una_aplicacion_como_terminal(
    repos: tuple[AsignacionesRepo, ModosRepo],
) -> None:
    asignaciones, modos = repos

    asignaciones.asignar("vscodium", modos.general().id, es_terminal=True)

    asignacion = asignaciones.obtener("vscodium")
    assert asignacion is not None and asignacion.es_terminal is True


def test_el_modo_es_obligatorio_y_tiene_que_existir(
    repos: tuple[AsignacionesRepo, ModosRepo],
) -> None:
    asignaciones, _ = repos

    with pytest.raises(DatoInvalido, match="modo"):
        asignaciones.asignar("ptyxis", 9999)


@pytest.mark.parametrize("aplicacion", ["", "   "])
def test_la_aplicacion_es_obligatoria(
    repos: tuple[AsignacionesRepo, ModosRepo], aplicacion: str
) -> None:
    asignaciones, modos = repos

    with pytest.raises(DatoInvalido, match="aplicaci"):
        asignaciones.asignar(aplicacion, modos.general().id)


def test_quita_una_asignacion(repos: tuple[AsignacionesRepo, ModosRepo]) -> None:
    asignaciones, modos = repos
    asignaciones.asignar("ptyxis", modos.general().id)

    assert asignaciones.quitar("PTYXIS") is True
    assert asignaciones.quitar("ptyxis") is False
    assert asignaciones.listar() == []


def test_al_borrar_el_modo_la_aplicacion_pasa_al_general_y_conserva_su_marca(
    repos: tuple[AsignacionesRepo, ModosRepo],
) -> None:
    asignaciones, modos = repos
    notas = modos.crear("Notas")
    asignaciones.asignar("obsidian", notas.id, es_terminal=True)

    modos.borrar(notas.id)

    asignacion = asignaciones.obtener("obsidian")
    assert asignacion is not None
    assert asignacion.modo_id == modos.general().id and asignacion.es_terminal is True
