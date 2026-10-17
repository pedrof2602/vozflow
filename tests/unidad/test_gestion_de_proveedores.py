"""La lógica de proveedores que comparten la línea de comandos y la ventana de ajustes."""

import pytest

from tests.dobles import ReescritorFalso
from vozflow.dominio.reescritura import Proveedor
from vozflow.gestion_de_proveedores import ErrorDeProveedor, GestionDeProveedores
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.errores import DatoInvalido

CLAVE = "sk-secreta-123456"


class Claves:
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


def _gestion(reescritor: ReescritorFalso | None = None):  # type: ignore[no-untyped-def]
    base = abrir_base(":memory:")
    claves = Claves()
    fabricados: list[tuple[str, str | None]] = []
    reescritor = reescritor or ReescritorFalso("Hola, mundo.")

    def crear(proveedor: Proveedor, clave: str | None) -> ReescritorFalso:
        fabricados.append((proveedor.id, clave))
        return reescritor

    return GestionDeProveedores(base, claves, crear), claves, AjustesRepo(base), fabricados


def test_arranca_apagada_y_con_los_tres_proveedores() -> None:
    gestion, _, _, _ = _gestion()

    assert gestion.reescritura_encendida() is False
    assert [e.proveedor.id for e in gestion.estado()] == ["ollama", "anthropic", "openrouter"]


def test_el_estado_dice_si_hay_clave_sin_mostrarla() -> None:
    gestion, claves, _, _ = _gestion()
    claves.guardar("anthropic", CLAVE)

    por_id = {e.proveedor.id: e for e in gestion.estado()}

    assert por_id["anthropic"].tiene_clave is True and por_id["openrouter"].tiene_clave is False
    assert por_id["ollama"].tiene_clave is None  # no usa


def test_activar_exige_modelo_y_clave() -> None:
    gestion, claves, ajustes, _ = _gestion()

    with pytest.raises(ErrorDeProveedor, match="modelo"):
        gestion.activar("anthropic")
    gestion.configurar("anthropic", modelo="m")
    with pytest.raises(ErrorDeProveedor, match="clave"):
        gestion.activar("anthropic")

    assert gestion.reescritura_encendida() is False
    claves.guardar("anthropic", CLAVE)
    gestion.activar("anthropic")
    assert gestion.reescritura_encendida() is True
    assert ajustes.obtener("reescritura.activa") is True


def test_ollama_se_activa_sin_clave() -> None:
    gestion, _, _, _ = _gestion()
    gestion.configurar("ollama", modelo="llama3.2")

    gestion.activar("ollama")

    assert gestion.proveedor_activo() is not None and gestion.proveedor_activo().id == "ollama"


def test_desactivar_apaga_y_conserva_la_configuracion() -> None:
    gestion, _, _, _ = _gestion()
    gestion.configurar("ollama", modelo="llama3.2", tiempo_maximo_s=30)
    gestion.activar("ollama")

    gestion.desactivar()

    assert gestion.reescritura_encendida() is False and gestion.proveedor_activo() is None
    assert gestion.estado()[0].proveedor.modelo == "llama3.2"


def test_guardar_y_borrar_la_clave() -> None:
    gestion, claves, _, _ = _gestion()

    gestion.guardar_clave("anthropic", f"  {CLAVE} ")
    assert claves.guardadas == {"anthropic": CLAVE}
    gestion.borrar_clave("anthropic")
    with pytest.raises(ErrorDeProveedor, match="No había"):
        gestion.borrar_clave("anthropic")


def test_los_errores_de_datos_salen_como_errores_de_proveedor() -> None:
    gestion, _, _, _ = _gestion()

    with pytest.raises(ErrorDeProveedor, match="tiempo"):
        gestion.configurar("anthropic", tiempo_maximo_s=99)
    with pytest.raises(ErrorDeProveedor, match="ollama"):
        gestion.guardar_clave("ollama", CLAVE)


def test_probar_manda_un_texto_de_ejemplo_y_devuelve_la_respuesta() -> None:
    gestion, claves, _, fabricados = _gestion()
    gestion.configurar("anthropic", modelo="m")
    claves.guardar("anthropic", CLAVE)

    assert gestion.probar("anthropic") == "Hola, mundo."
    assert fabricados == [("anthropic", CLAVE)]


def test_probar_sin_nombre_usa_el_activo_o_pide_indicar_uno() -> None:
    gestion, _, _, fabricados = _gestion()
    with pytest.raises(ErrorDeProveedor, match="proveedor"):
        gestion.probar(None)

    gestion.configurar("ollama", modelo="llama3.2")
    gestion.activar("ollama")
    gestion.probar(None)

    assert fabricados == [("ollama", None)]


def test_probar_cuando_falla_da_el_motivo_sin_la_clave() -> None:
    gestion, claves, _, _ = _gestion(ReescritorFalso(fallo="Anthropic rechazó la clave de acceso"))
    gestion.configurar("anthropic", modelo="m")
    claves.guardar("anthropic", CLAVE)

    with pytest.raises(ErrorDeProveedor) as error:
        gestion.probar("anthropic")

    assert "rechazó la clave" in str(error.value) and CLAVE not in str(error.value)


# ---- idioma de destino de la traducción (lote 6) ---------------------------------------------------------


def test_el_idioma_de_destino_empieza_en_ingles_y_se_puede_cambiar() -> None:
    gestion, _, ajustes, _ = _gestion()

    assert gestion.idioma_de_traduccion() == "inglés"
    gestion.establecer_idioma_de_traduccion("  portugués ")

    assert gestion.idioma_de_traduccion() == "portugués"
    assert ajustes.obtener("traduccion.idioma") == "portugués"


@pytest.mark.parametrize("idioma", ["", "  ", "x", "a" * 41, "dos\nlíneas"])
def test_un_idioma_de_destino_invalido_es_un_error_de_proveedor(idioma: str) -> None:
    gestion, _, _, _ = _gestion()

    with pytest.raises(ErrorDeProveedor, match="idioma"):
        gestion.establecer_idioma_de_traduccion(idioma)

    assert gestion.idioma_de_traduccion() == "inglés"
