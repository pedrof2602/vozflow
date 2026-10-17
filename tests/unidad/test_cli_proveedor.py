"""``vozflow proveedor``: configurar la reescritura sin interfaz (nunca la clave por argumento)."""

from pathlib import Path

import pytest

from tests.dobles import GrabadoraFalsa, MotorFalso, ReescritorFalso
from vozflow.__main__ import CODIGO_ERROR, CODIGO_OK, Dependencias, main
from vozflow.dominio.reescritura import Proveedor
from vozflow.llm.puerto import Reescritor
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.claves import LlaveroNoDisponible
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.proveedores_repo import ProveedoresRepo

CLAVE = "sk-secreta-para-la-prueba-123"


class ClavesEnMemoria:
    def __init__(self) -> None:
        self.guardadas: dict[str, str] = {}

    def guardar(self, proveedor: str, clave: str) -> None:
        if proveedor == "ollama":
            raise DatoInvalido("El proveedor «ollama» no usa clave")
        if not clave.strip():
            raise DatoInvalido("La clave no puede estar vacía")
        self.guardadas[proveedor] = clave.strip()

    def leer(self, proveedor: str) -> str | None:
        return self.guardadas.get(proveedor)

    def existe(self, proveedor: str) -> bool:
        return proveedor in self.guardadas

    def borrar(self, proveedor: str) -> bool:
        return self.guardadas.pop(proveedor, None) is not None


class Banco:
    def __init__(self, ruta: Path) -> None:
        self.ruta = ruta
        self.claves = ClavesEnMemoria()
        self.reescritor: Reescritor = ReescritorFalso("Hola, mundo.")
        self.pidieron_clave: list[str] = []
        self.fabricados: list[tuple[str, str | None]] = []
        self.clave_tipeada = CLAVE
        self.dependencias = Dependencias(
            crear_grabadora=GrabadoraFalsa,
            crear_motor=lambda modelo: MotorFalso(),
            esperar=lambda s: None,
            descargar_modelo=lambda m: "",
            abrir_base=lambda: abrir_base(ruta),
            leer_clave=self._leer_clave,
            claves=lambda: self.claves,
            crear_reescritor=self._crear,
        )

    def _leer_clave(self, pregunta: str) -> str:
        self.pidieron_clave.append(pregunta)
        return self.clave_tipeada

    def _crear(self, proveedor: Proveedor, clave: str | None) -> Reescritor:
        self.fabricados.append((proveedor.id, clave))
        return self.reescritor

    def correr(self, *argumentos: str) -> int:
        return main(list(argumentos), self.dependencias)

    def proveedores(self) -> ProveedoresRepo:
        return ProveedoresRepo(abrir_base(self.ruta))

    def ajustes(self) -> AjustesRepo:
        return AjustesRepo(abrir_base(self.ruta))


@pytest.fixture
def b(tmp_path: Path) -> Banco:
    return Banco(tmp_path / "vozflow.db")


def test_listar_muestra_los_tres_proveedores_apagados(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("proveedor", "listar") == CODIGO_OK

    salida = capsys.readouterr().out
    for nombre in ("ollama", "anthropic", "openrouter"):
        assert nombre in salida
    assert "apagada" in salida.lower()  # la reescritura viene apagada


def test_configurar_el_modelo_el_tiempo_y_la_direccion(b: Banco) -> None:
    assert (
        b.correr(
            "proveedor", "configurar", "anthropic", "--modelo", "claude-haiku-5-5", "--tiempo", "20"
        )
        == CODIGO_OK
    )
    assert (
        b.correr("proveedor", "configurar", "ollama", "--direccion", "http://127.0.0.1:9999")
        == CODIGO_OK
    )

    assert b.proveedores().obtener("anthropic").modelo == "claude-haiku-5-5"
    assert b.proveedores().obtener("anthropic").tiempo_maximo_s == 20
    assert b.proveedores().obtener("ollama").direccion == "http://127.0.0.1:9999"


def test_un_tiempo_fuera_de_rango_es_un_error(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert b.correr("proveedor", "configurar", "anthropic", "--tiempo", "99") == CODIGO_ERROR
    assert "tiempo" in capsys.readouterr().err


# ---- la clave: nunca como argumento ---------------------------------------------------------------------


def test_la_clave_se_pide_por_teclado_oculto_y_se_guarda(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("proveedor", "clave", "anthropic") == CODIGO_OK

    assert b.claves.guardadas == {"anthropic": CLAVE}
    assert len(b.pidieron_clave) == 1
    salida = capsys.readouterr()
    assert CLAVE not in salida.out and CLAVE not in salida.err


def test_la_clave_no_se_acepta_como_argumento(b: Banco) -> None:
    with pytest.raises(SystemExit) as salida:
        b.correr("proveedor", "clave", "anthropic", "--clave", CLAVE)
    assert salida.value.code == 2

    with pytest.raises(SystemExit):
        b.correr("proveedor", "clave", "anthropic", CLAVE)  # tampoco posicional

    assert b.claves.guardadas == {}


def test_una_clave_vacia_es_un_error(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    b.clave_tipeada = "   "

    assert b.correr("proveedor", "clave", "anthropic") == CODIGO_ERROR
    assert b.claves.guardadas == {}


def test_ollama_no_tiene_clave(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    assert b.correr("proveedor", "clave", "ollama") == CODIGO_ERROR
    assert "ollama" in capsys.readouterr().err


def test_borrar_la_clave(b: Banco) -> None:
    b.claves.guardar("anthropic", CLAVE)

    assert b.correr("proveedor", "borrar-clave", "anthropic") == CODIGO_OK
    assert b.correr("proveedor", "borrar-clave", "anthropic") == CODIGO_ERROR


def test_el_listado_dice_si_hay_clave_pero_nunca_la_muestra(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    b.claves.guardar("anthropic", CLAVE)

    b.correr("proveedor", "listar")

    salida = capsys.readouterr().out
    assert CLAVE not in salida and "clave guardada" in salida.lower()


def test_un_llavero_que_no_anda_es_un_error_claro(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    def guardar(proveedor: str, clave: str) -> None:
        raise LlaveroNoDisponible("No se pudo usar el llavero del escritorio")

    b.claves.guardar = guardar  # type: ignore[method-assign]

    assert b.correr("proveedor", "clave", "anthropic") == CODIGO_ERROR
    assert "llavero" in capsys.readouterr().err


# ---- activar y desactivar ---------------------------------------------------------------------------------


def test_activar_prende_el_proveedor_y_el_interruptor_general(b: Banco) -> None:
    b.correr("proveedor", "configurar", "anthropic", "--modelo", "m")
    b.claves.guardar("anthropic", CLAVE)

    assert b.correr("proveedor", "activar", "anthropic") == CODIGO_OK

    activo = b.proveedores().activo()
    assert activo is not None and activo.id == "anthropic"
    assert b.ajustes().obtener("reescritura.activa") is True


def test_activar_sin_modelo_es_un_error_y_no_cambia_nada(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    b.claves.guardar("anthropic", CLAVE)

    assert b.correr("proveedor", "activar", "anthropic") == CODIGO_ERROR

    assert "modelo" in capsys.readouterr().err
    assert b.proveedores().activo() is None
    assert b.ajustes().obtener("reescritura.activa") is False


def test_activar_sin_clave_guardada_es_un_error(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    b.correr("proveedor", "configurar", "openrouter", "--modelo", "m")

    assert b.correr("proveedor", "activar", "openrouter") == CODIGO_ERROR

    assert "clave" in capsys.readouterr().err
    assert b.ajustes().obtener("reescritura.activa") is False


def test_ollama_se_activa_sin_clave(b: Banco) -> None:
    b.correr("proveedor", "configurar", "ollama", "--modelo", "llama3.2")

    assert b.correr("proveedor", "activar", "ollama") == CODIGO_OK


def test_activar_otro_apaga_al_anterior(b: Banco) -> None:
    for id_ in ("anthropic", "openrouter"):
        b.correr("proveedor", "configurar", id_, "--modelo", "m")
        b.claves.guardar(id_, CLAVE)

    b.correr("proveedor", "activar", "anthropic")
    b.correr("proveedor", "activar", "openrouter")

    assert [p.id for p in b.proveedores().listar() if p.activo] == ["openrouter"]


def test_desactivar_apaga_todo_y_conserva_la_configuracion(b: Banco) -> None:
    b.correr("proveedor", "configurar", "ollama", "--modelo", "llama3.2")
    b.correr("proveedor", "activar", "ollama")

    assert b.correr("proveedor", "desactivar") == CODIGO_OK

    assert b.proveedores().activo() is None
    assert b.ajustes().obtener("reescritura.activa") is False
    assert b.proveedores().obtener("ollama").modelo == "llama3.2"


# ---- probar la conexión ---------------------------------------------------------------------------------------


def test_probar_manda_un_texto_de_prueba_y_muestra_el_resultado(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    b.correr("proveedor", "configurar", "anthropic", "--modelo", "m")
    b.claves.guardar("anthropic", CLAVE)
    capsys.readouterr()

    assert b.correr("proveedor", "probar", "anthropic") == CODIGO_OK

    salida = capsys.readouterr().out
    assert "Hola, mundo." in salida and CLAVE not in salida
    assert b.fabricados == [("anthropic", CLAVE)]


def test_probar_sin_nombre_usa_el_proveedor_activo(b: Banco) -> None:
    b.correr("proveedor", "configurar", "ollama", "--modelo", "llama3.2")
    b.correr("proveedor", "activar", "ollama")

    assert b.correr("proveedor", "probar") == CODIGO_OK
    assert b.fabricados == [("ollama", None)]


def test_probar_sin_proveedor_activo_pide_indicar_uno(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("proveedor", "probar") == CODIGO_ERROR
    assert "proveedor" in capsys.readouterr().err


def test_probar_cuando_falla_muestra_el_motivo_sin_la_clave(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    b.correr("proveedor", "configurar", "anthropic", "--modelo", "m")
    b.claves.guardar("anthropic", CLAVE)
    b.reescritor = ReescritorFalso(fallo="Anthropic rechazó la clave de acceso")

    assert b.correr("proveedor", "probar", "anthropic") == CODIGO_ERROR

    err = capsys.readouterr().err
    assert "rechazó la clave" in err and CLAVE not in err


def test_probar_sin_clave_guardada_lo_dice(b: Banco, capsys: pytest.CaptureFixture[str]) -> None:
    b.correr("proveedor", "configurar", "anthropic", "--modelo", "m")

    assert b.correr("proveedor", "probar", "anthropic") == CODIGO_ERROR
    assert "clave" in capsys.readouterr().err


# ---- traducción (lote 6) ------------------------------------------------------------------------------


def test_el_idioma_de_destino_se_ve_y_se_cambia_por_consola(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("proveedor", "idioma") == CODIGO_OK
    assert "inglés" in capsys.readouterr().out

    assert b.correr("proveedor", "idioma", "portugués") == CODIGO_OK
    assert b.ajustes().obtener("traduccion.idioma") == "portugués"
    b.correr("proveedor", "idioma")
    assert "portugués" in capsys.readouterr().out


def test_un_idioma_invalido_por_consola_es_un_error(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    assert b.correr("proveedor", "idioma", "x") == CODIGO_ERROR
    assert "idioma" in capsys.readouterr().err
    assert b.ajustes().obtener("traduccion.idioma") == "inglés"


def test_el_listado_muestra_el_idioma_de_destino(
    b: Banco, capsys: pytest.CaptureFixture[str]
) -> None:
    b.correr("proveedor", "listar")

    assert "inglés" in capsys.readouterr().out
