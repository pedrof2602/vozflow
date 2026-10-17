"""Modos (RF-021): reglas de nombre, banderas, modo general y modos de fábrica."""

import pytest

from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.errores import DatoDuplicado, DatoInvalido
from vozflow.persistencia.modos_repo import ModosRepo


@pytest.fixture
def repo() -> ModosRepo:
    return ModosRepo(abrir_base(":memory:"))


def test_vienen_los_cinco_modos_de_fabrica(repo: ModosRepo) -> None:
    assert [m.nombre for m in repo.listar()] == [
        "General",
        "Terminal",
        "Código",
        "Mensajería",
        "Documentos",
    ]


def test_terminal_de_fabrica_pega_como_terminal_y_en_una_linea(repo: ModosRepo) -> None:
    terminal = repo.obtener("Terminal")

    assert terminal is not None
    assert (terminal.tipo_pegado, terminal.salto_de_linea) == ("terminal", "espacio")


def test_el_general_es_uno_solo_y_se_encuentra_directo(repo: ModosRepo) -> None:
    assert repo.general().nombre == "General"
    assert [m.nombre for m in repo.listar() if m.es_general] == ["General"]


def test_un_modo_nuevo_tiene_las_banderas_por_defecto(repo: ModosRepo) -> None:
    modo = repo.crear("Reuniones")

    assert modo.id > 0 and modo.es_general is False
    assert (modo.quitar_muletillas, modo.puntuacion_automatica, modo.comandos_de_voz) == (
        True,
        True,
        True,
    )
    assert modo.reescribir is False and modo.instruccion == ""
    assert (modo.tipo_pegado, modo.salto_de_linea) == ("automatico", "conservar")


def test_se_crea_con_banderas_propias(repo: ModosRepo) -> None:
    modo = repo.crear(
        "Notas",
        quitar_muletillas=False,
        puntuacion_automatica=False,
        comandos_de_voz=False,
        tipo_pegado="normal",
        salto_de_linea="espacio",
        instruccion="Frases cortas",
    )

    assert not modo.quitar_muletillas and not modo.puntuacion_automatica
    assert not modo.comandos_de_voz
    assert (modo.tipo_pegado, modo.salto_de_linea, modo.instruccion) == (
        "normal",
        "espacio",
        "Frases cortas",
    )


@pytest.mark.parametrize("nombre", ["", "   "])
def test_el_nombre_es_obligatorio(repo: ModosRepo, nombre: str) -> None:
    with pytest.raises(DatoInvalido, match="nombre"):
        repo.crear(nombre)


@pytest.mark.parametrize("repetido", ["terminal", "TERMINAL", " Terminal "])
def test_el_nombre_es_unico_sin_distinguir_mayusculas(repo: ModosRepo, repetido: str) -> None:
    with pytest.raises(DatoDuplicado):
        repo.crear(repetido)


def test_el_nombre_es_unico_sin_distinguir_acentos(repo: ModosRepo) -> None:
    with pytest.raises(DatoDuplicado):
        repo.crear("CODIGO")


def test_no_se_puede_crear_otro_modo_general(repo: ModosRepo) -> None:
    with pytest.raises(TypeError):
        repo.crear("Otro", es_general=True)  # type: ignore[call-arg]


@pytest.mark.parametrize("tipo", ["raro", "", "Terminal"])
def test_tipo_de_pegado_invalido(repo: ModosRepo, tipo: str) -> None:
    with pytest.raises(DatoInvalido, match="pegado"):
        repo.crear("X", tipo_pegado=tipo)  # type: ignore[arg-type]


@pytest.mark.parametrize("salto", ["raro", "", "Espacio"])
def test_salto_de_linea_invalido(repo: ModosRepo, salto: str) -> None:
    with pytest.raises(DatoInvalido, match="salto"):
        repo.crear("X", salto_de_linea=salto)  # type: ignore[arg-type]


def test_actualiza_solo_lo_que_se_pide(repo: ModosRepo) -> None:
    modo = repo.crear("Notas")

    nuevo = repo.actualizar(modo.id, puntuacion_automatica=False, instruccion="Breve")

    assert nuevo.puntuacion_automatica is False and nuevo.instruccion == "Breve"
    assert nuevo.quitar_muletillas is True and nuevo.nombre == "Notas"
    assert repo.obtener("Notas") == nuevo


def test_se_puede_renombrar_pero_no_a_un_nombre_ocupado(repo: ModosRepo) -> None:
    modo = repo.crear("Notas")

    assert repo.actualizar(modo.id, nombre="Apuntes").nombre == "Apuntes"
    with pytest.raises(DatoDuplicado):
        repo.actualizar(modo.id, nombre="terminal")


def test_se_puede_renombrar_a_si_mismo_cambiando_mayusculas(repo: ModosRepo) -> None:
    modo = repo.crear("Notas")

    assert repo.actualizar(modo.id, nombre="NOTAS").nombre == "NOTAS"


def test_actualizar_valida_igual_que_crear(repo: ModosRepo) -> None:
    modo = repo.crear("Notas")

    with pytest.raises(DatoInvalido):
        repo.actualizar(modo.id, tipo_pegado="raro")
    with pytest.raises(DatoInvalido):
        repo.actualizar(modo.id, nombre="")


def test_actualizar_un_modo_inexistente_es_un_error_claro(repo: ModosRepo) -> None:
    with pytest.raises(DatoInvalido, match="modo"):
        repo.actualizar(999, instruccion="x")


def test_no_se_puede_borrar_el_modo_general(repo: ModosRepo) -> None:
    with pytest.raises(DatoInvalido, match="general"):
        repo.borrar(repo.general().id)

    assert repo.general().nombre == "General"


def test_borra_un_modo_comun(repo: ModosRepo) -> None:
    modo = repo.crear("Notas")

    assert repo.borrar(modo.id) is True
    assert repo.obtener("Notas") is None
    assert repo.borrar(modo.id) is False


def test_el_general_se_puede_editar_pero_sigue_siendo_el_general(repo: ModosRepo) -> None:
    general = repo.general()

    nuevo = repo.actualizar(general.id, quitar_muletillas=False)

    assert nuevo.es_general is True and nuevo.quitar_muletillas is False
