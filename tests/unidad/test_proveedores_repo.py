"""Proveedores de reescritura (RF-024, RF-025): reglas de ``data-model.md``."""

import pytest

from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.proveedores_repo import DIRECCION_DE_OLLAMA, ProveedoresRepo


@pytest.fixture
def repo() -> ProveedoresRepo:
    return ProveedoresRepo(abrir_base(":memory:"))


def test_los_tres_proveedores_existen_desde_el_principio_y_ninguno_esta_activo(
    repo: ProveedoresRepo,
) -> None:
    proveedores = repo.listar()

    assert [p.id for p in proveedores] == ["ollama", "anthropic", "openrouter"]
    assert not any(p.activo for p in proveedores)
    assert repo.activo() is None


def test_los_valores_por_defecto(repo: ProveedoresRepo) -> None:
    ollama = repo.obtener("ollama")

    assert ollama.direccion == "http://127.0.0.1:11434" == DIRECCION_DE_OLLAMA
    assert ollama.tiempo_maximo_s == 15 and ollama.modelo == ""
    assert repo.obtener("anthropic").direccion == ""


@pytest.mark.parametrize("id_", ["gpt", "", "OLLAMA"])
def test_solo_existen_ollama_anthropic_y_openrouter(repo: ProveedoresRepo, id_: str) -> None:
    with pytest.raises(DatoInvalido, match="proveedor"):
        repo.obtener(id_)
    with pytest.raises(DatoInvalido, match="proveedor"):
        repo.configurar(id_, modelo="x")


def test_configura_el_modelo_y_el_tiempo(repo: ProveedoresRepo) -> None:
    repo.configurar("anthropic", modelo="claude-haiku-5-5", tiempo_maximo_s=30)

    anthropic = repo.obtener("anthropic")
    assert (anthropic.modelo, anthropic.tiempo_maximo_s) == ("claude-haiku-5-5", 30)


def test_configurar_un_dato_no_toca_los_demas(repo: ProveedoresRepo) -> None:
    repo.configurar("anthropic", modelo="m", tiempo_maximo_s=30)

    repo.configurar("anthropic", modelo="otro")

    assert repo.obtener("anthropic").tiempo_maximo_s == 30


@pytest.mark.parametrize("segundos", [3, 15, 60])
def test_el_tiempo_acepta_de_3_a_60(repo: ProveedoresRepo, segundos: int) -> None:
    repo.configurar("openrouter", tiempo_maximo_s=segundos)

    assert repo.obtener("openrouter").tiempo_maximo_s == segundos


@pytest.mark.parametrize("segundos", [0, 2, 61, -5, 600])
def test_el_tiempo_fuera_de_3_a_60_se_rechaza(repo: ProveedoresRepo, segundos: int) -> None:
    with pytest.raises(DatoInvalido, match="tiempo"):
        repo.configurar("openrouter", tiempo_maximo_s=segundos)

    assert repo.obtener("openrouter").tiempo_maximo_s == 15


def test_la_direccion_es_solo_de_ollama(repo: ProveedoresRepo) -> None:
    repo.configurar("ollama", direccion="http://192.168.1.5:11434")

    assert repo.obtener("ollama").direccion == "http://192.168.1.5:11434"
    with pytest.raises(DatoInvalido, match="dirección"):
        repo.configurar("anthropic", direccion="http://x")


@pytest.mark.parametrize(
    "direccion", ["", "localhost:11434", "ftp://x", "no es una url", "http://"]
)
def test_la_direccion_de_ollama_tiene_que_ser_una_url_http(
    repo: ProveedoresRepo, direccion: str
) -> None:
    with pytest.raises(DatoInvalido, match="dirección"):
        repo.configurar("ollama", direccion=direccion)


def test_la_direccion_se_guarda_sin_barra_final(repo: ProveedoresRepo) -> None:
    repo.configurar("ollama", direccion="http://127.0.0.1:11434/")

    assert repo.obtener("ollama").direccion == "http://127.0.0.1:11434"


# ---- activar: solo uno a la vez -------------------------------------------------------------------------


def test_activar_marca_al_proveedor_y_apaga_a_los_demas(repo: ProveedoresRepo) -> None:
    repo.configurar("anthropic", modelo="a")
    repo.configurar("openrouter", modelo="b")

    repo.activar("anthropic")
    repo.activar("openrouter")

    assert repo.activo() is not None and repo.activo().id == "openrouter"  # type: ignore[union-attr]
    assert [p.id for p in repo.listar() if p.activo] == ["openrouter"]


def test_no_se_puede_activar_sin_elegir_un_modelo(repo: ProveedoresRepo) -> None:
    with pytest.raises(DatoInvalido, match="modelo"):
        repo.activar("anthropic")

    assert repo.activo() is None


def test_un_fallo_al_activar_no_apaga_al_que_estaba(repo: ProveedoresRepo) -> None:
    repo.configurar("anthropic", modelo="a")
    repo.activar("anthropic")

    with pytest.raises(DatoInvalido):
        repo.activar("openrouter")  # sin modelo

    assert repo.activo() is not None and repo.activo().id == "anthropic"  # type: ignore[union-attr]


def test_desactivar_apaga_a_todos_pero_conserva_la_configuracion(repo: ProveedoresRepo) -> None:
    repo.configurar("anthropic", modelo="a", tiempo_maximo_s=20)
    repo.activar("anthropic")

    repo.desactivar()

    assert repo.activo() is None
    assert repo.obtener("anthropic").modelo == "a"
    assert repo.obtener("anthropic").tiempo_maximo_s == 20


def test_la_base_tambien_impide_dos_activos(repo: ProveedoresRepo) -> None:
    import sqlite3

    repo.configurar("anthropic", modelo="a")
    repo.activar("anthropic")

    with pytest.raises(sqlite3.IntegrityError):
        repo._base.execute("UPDATE proveedor SET activo = 1 WHERE id = 'openrouter'")  # noqa: SLF001
