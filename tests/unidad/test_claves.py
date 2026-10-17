"""Claves de acceso en el llavero (RF-025): nunca en la base, el historial ni los registros."""

import logging
from collections.abc import Iterator

import keyring
import keyring.backend
import keyring.errors
import pytest

from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.claves import SERVICIO, Claves, LlaveroNoDisponible
from vozflow.persistencia.errores import DatoInvalido

CLAVE = "sk-secreta-abcdef-123456"


class LlaveroEnMemoria(keyring.backend.KeyringBackend):
    priority = 1

    def __init__(self) -> None:
        super().__init__()  # type: ignore[no-untyped-call]
        self.guardado: dict[tuple[str, str], str] = {}

    def set_password(self, servicio: str, usuario: str, clave: str) -> None:
        self.guardado[(servicio, usuario)] = clave

    def get_password(self, servicio: str, usuario: str) -> str | None:
        return self.guardado.get((servicio, usuario))

    def delete_password(self, servicio: str, usuario: str) -> None:
        if (servicio, usuario) not in self.guardado:
            raise keyring.errors.PasswordDeleteError("no existe")
        del self.guardado[(servicio, usuario)]


class LlaveroRoto(keyring.backend.KeyringBackend):
    priority = 1

    def set_password(self, servicio: str, usuario: str, clave: str) -> None:
        raise keyring.errors.KeyringLocked("bloqueado")

    def get_password(self, servicio: str, usuario: str) -> str | None:
        raise keyring.errors.NoKeyringError("no hay llavero")

    def delete_password(self, servicio: str, usuario: str) -> None:
        raise keyring.errors.KeyringError("falló")


@pytest.fixture
def llavero() -> Iterator[LlaveroEnMemoria]:
    anterior = keyring.get_keyring()
    respaldo = LlaveroEnMemoria()
    keyring.set_keyring(respaldo)
    yield respaldo
    keyring.set_keyring(anterior)


@pytest.fixture
def claves(llavero: LlaveroEnMemoria) -> Claves:
    return Claves()


def test_guarda_y_lee_con_el_servicio_vozflow_y_el_nombre_del_proveedor(
    claves: Claves, llavero: LlaveroEnMemoria
) -> None:
    claves.guardar("anthropic", CLAVE)

    assert SERVICIO == "vozflow"
    assert llavero.guardado == {("vozflow", "anthropic"): CLAVE}
    assert claves.leer("anthropic") == CLAVE


def test_cada_proveedor_tiene_su_clave(claves: Claves) -> None:
    claves.guardar("anthropic", "a" * 10)
    claves.guardar("openrouter", "b" * 10)

    assert claves.leer("anthropic") == "a" * 10 and claves.leer("openrouter") == "b" * 10


def test_leer_una_clave_que_no_hay_devuelve_nada(claves: Claves) -> None:
    assert claves.leer("anthropic") is None
    assert claves.existe("anthropic") is False


def test_existe_dice_si_hay_clave_sin_mostrarla(claves: Claves) -> None:
    claves.guardar("openrouter", CLAVE)

    assert claves.existe("openrouter") is True


def test_borra_la_clave(claves: Claves) -> None:
    claves.guardar("anthropic", CLAVE)

    assert claves.borrar("anthropic") is True
    assert claves.leer("anthropic") is None
    assert claves.borrar("anthropic") is False  # ya no estaba


def test_quita_los_espacios_sobrantes_al_guardar(claves: Claves) -> None:
    claves.guardar("anthropic", f"  {CLAVE}\n")

    assert claves.leer("anthropic") == CLAVE


@pytest.mark.parametrize("clave", ["", "   ", "\n"])
def test_no_guarda_una_clave_vacia(claves: Claves, clave: str) -> None:
    with pytest.raises(DatoInvalido, match="clave"):
        claves.guardar("anthropic", clave)


@pytest.mark.parametrize("proveedor", ["ollama", "otro", ""])
def test_solo_los_proveedores_externos_llevan_clave(claves: Claves, proveedor: str) -> None:
    with pytest.raises(DatoInvalido, match="proveedor"):
        claves.guardar(proveedor, CLAVE)


# ---- si el llavero no anda -----------------------------------------------------------------------------


@pytest.mark.parametrize("operacion", ["guardar", "leer", "borrar"])
def test_un_llavero_roto_da_un_mensaje_claro_sin_la_clave(operacion: str) -> None:
    anterior = keyring.get_keyring()
    keyring.set_keyring(LlaveroRoto())  # type: ignore[no-untyped-call]
    try:
        claves = Claves()
        with pytest.raises(LlaveroNoDisponible) as error:
            if operacion == "guardar":
                claves.guardar("anthropic", CLAVE)
            elif operacion == "leer":
                claves.leer("anthropic")
            else:
                claves.borrar("anthropic")
    finally:
        keyring.set_keyring(anterior)

    assert "llavero" in str(error.value).lower() and CLAVE not in str(error.value)


# ---- la clave nunca queda en otro lado ---------------------------------------------------------------------


def test_la_clave_no_aparece_en_los_registros(
    claves: Claves, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        claves.guardar("anthropic", CLAVE)
        claves.leer("anthropic")
        claves.existe("anthropic")
        claves.borrar("anthropic")

    assert CLAVE not in caplog.text


def test_la_clave_no_aparece_en_el_repr(claves: Claves) -> None:
    claves.guardar("anthropic", CLAVE)

    assert CLAVE not in repr(claves) and CLAVE not in str(claves)


def test_la_clave_no_queda_en_la_base_ni_en_su_archivo(claves: Claves, tmp_path) -> None:  # type: ignore[no-untyped-def]
    ruta = tmp_path / "v.db"
    base = abrir_base(ruta)
    claves.guardar("anthropic", CLAVE)
    base.execute("INSERT INTO proveedor (id, activo, modelo) VALUES ('anthropic', 1, 'm')")
    base.commit()
    base.close()

    volcado = ruta.read_bytes()
    assert CLAVE.encode() not in volcado
    for extra in tmp_path.glob("v.db-*"):
        assert CLAVE.encode() not in extra.read_bytes()
