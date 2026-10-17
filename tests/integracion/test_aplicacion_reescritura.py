"""La reescritura dentro del dictado, con dobles (T110): apagada por defecto y nunca estorba."""

from collections.abc import Callable

import httpx
import pytest

from tests.dobles import ReescritorFalso
from tests.integracion.test_aplicacion import Montaje, _dictar_mantenido, _esperar
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.configuracion import ConfiguracionDeBase
from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.llm.anthropic import ReescritorAnthropic
from vozflow.llm.puerto import Reescritor
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.errores import DatoInvalido
from vozflow.persistencia.historial import HistorialRepo
from vozflow.persistencia.modos_repo import ModosRepo
from vozflow.persistencia.proveedores_repo import ProveedoresRepo
from vozflow.reescritura import ReescrituraDeBase


class ClavesFalsas:
    def __init__(self, **claves: str) -> None:
        self.claves = claves

    def leer(self, proveedor: str) -> str | None:
        return self.claves.get(proveedor)


class Entorno:
    def __init__(
        self,
        *,
        texto: str = "hola mundo",
        reescritor: Reescritor | None = None,
        claves: ClavesFalsas | None = None,
        ventana: object = None,
    ) -> None:
        self.base = abrir_base(":memory:")
        self.ajustes = AjustesRepo(self.base)
        self.proveedores = ProveedoresRepo(self.base)
        self.modos = ModosRepo(self.base)
        self.historial = HistorialRepo(self.base)
        self.reescritor = reescritor or ReescritorFalso("Texto reescrito.")
        self.fabricados: list[tuple[str, str | None]] = []

        def crear(proveedor, clave):  # type: ignore[no-untyped-def]
            self.fabricados.append((proveedor.id, clave))
            return self.reescritor

        self.reescritura = ReescrituraDeBase(
            self.base, claves or ClavesFalsas(anthropic="clave-de-prueba"), crear
        )
        self.montaje = Montaje(
            texto=texto,
            ventana=ventana,  # type: ignore[arg-type]
            configuracion=ConfiguracionDeBase(self.base),
            historial=self.historial,
            reescritura=self.reescritura,
        )
        self.montaje.app.iniciar()

    def encender(self, proveedor: str = "anthropic", *, en_el_modo: bool = True) -> None:
        self.proveedores.configurar(proveedor, modelo="un-modelo", tiempo_maximo_s=9)
        self.proveedores.activar(proveedor)
        self.ajustes.establecer("reescritura.activa", True)
        if en_el_modo:
            self.modos.actualizar(self.modos.general().id, reescribir=True)

    def dictar(self) -> str:
        _dictar_mantenido(self.montaje)
        return self.montaje.insertor.insertados[-1][0]

    def dictar_traduciendo(self) -> None:
        """Mantiene y suelta la tecla de traducir; devuelve cuando el dictado terminó."""
        m = self.montaje
        m.escucha.pulsar(AccionDeAtajo.TRADUCIR)
        assert m.espera_estado(E.ESCUCHANDO)
        m.escucha.soltar(AccionDeAtajo.TRADUCIR)
        assert _esperar(lambda: m.app.estado in (E.INACTIVO, E.ERROR))

    def cerrar(self) -> None:
        self.montaje.app.detener()


@pytest.fixture
def crear():  # type: ignore[no-untyped-def]
    creados: list[Entorno] = []

    def fabrica(**kwargs):  # type: ignore[no-untyped-def]
        e = Entorno(**kwargs)
        creados.append(e)
        return e

    yield fabrica
    for e in creados:
        e.cerrar()


# ---- apagada por defecto ----------------------------------------------------------------------------


def test_por_defecto_no_se_reescribe_ni_se_prepara_nada(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()

    assert e.dictar() == "Hola mundo."
    assert e.fabricados == [] and e.reescritor.llamadas == []


def test_con_la_reescritura_apagada_no_se_abre_ninguna_conexion_de_red(crear) -> None:  # type: ignore[no-untyped-def]
    pedidos: list[httpx.Request] = []

    def prohibido(pedido: httpx.Request) -> httpx.Response:
        pedidos.append(pedido)
        raise AssertionError("no debería haber ninguna conexión")

    reescritor = ReescritorAnthropic("m", "clave", transporte=httpx.MockTransport(prohibido))
    e = crear(reescritor=reescritor)
    e.proveedores.configurar("anthropic", modelo="m")
    e.proveedores.activar("anthropic")  # hay proveedor, pero el interruptor general está apagado
    e.modos.actualizar(e.modos.general().id, reescribir=True)

    assert e.dictar() == "Hola mundo."
    assert pedidos == [] and e.fabricados == []


def test_activa_pero_con_el_modo_sin_reescribir_tampoco_sale_nada(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender(en_el_modo=False)

    assert e.dictar() == "Hola mundo."
    assert e.fabricados == [] and e.reescritor.llamadas == []


def test_el_interruptor_general_apagado_manda_aunque_el_modo_pida_reescribir(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender()
    e.ajustes.establecer("reescritura.activa", False)

    assert e.dictar() == "Hola mundo."
    assert e.fabricados == []


# ---- reescribir ---------------------------------------------------------------------------------------


def test_con_todo_activo_se_inserta_el_texto_reescrito(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender()

    assert e.dictar() == "Texto reescrito."


def test_el_historial_marca_la_reescritura_y_el_proveedor(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(texto="eh hola mundo")
    e.encender()
    e.dictar()

    (dictado,) = e.historial.listar()
    assert dictado.reescrito is True and dictado.proveedor == "anthropic"
    assert dictado.texto_final == "Texto reescrito." and dictado.texto_crudo == "eh hola mundo"


def test_el_reescritor_recibe_el_texto_ya_limpio_y_el_tiempo_del_proveedor(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(texto="eh hola mundo")
    e.encender()
    e.dictar()

    texto, _, tiempo = e.reescritor.llamadas[0]
    assert texto == "Hola mundo." and tiempo == 9


def test_la_instruccion_lleva_el_estilo_del_modo_y_el_diccionario(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.encender()
    e.modos.actualizar(e.modos.general().id, instruccion="Tono muy formal")
    DiccionarioRepo(e.base).agregar("SQLAlchemy")
    e.dictar()

    instruccion = e.reescritor.llamadas[0][1]
    assert "Tono muy formal" in instruccion and "SQLAlchemy" in instruccion


def test_usa_la_clave_del_llavero_del_proveedor_activo(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(claves=ClavesFalsas(anthropic="la-clave-guardada"))
    e.encender()
    e.dictar()

    assert e.fabricados == [("anthropic", "la-clave-guardada")]


def test_ollama_no_usa_clave(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(claves=ClavesFalsas())
    e.encender("ollama")

    assert e.dictar() == "Texto reescrito."
    assert e.fabricados == [("ollama", None)]


def test_los_atajos_de_texto_se_expanden_despues_y_no_pasan_por_el_modelo(crear) -> None:  # type: ignore[no-untyped-def]
    from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo

    e = crear(texto="gracias mi firma", reescritor=_EnMayusculas())
    e.encender()
    AtajosTextoRepo(e.base).agregar("mi firma", "Pedro Freimeyer")

    assert e.dictar() == "GRACIAS Pedro Freimeyer"
    assert "Pedro" not in e.reescritor.recibidos[0]


def test_en_una_terminal_el_texto_reescrito_sale_en_una_sola_linea(crear) -> None:  # type: ignore[no-untyped-def]
    from vozflow.ventana.puerto import InfoVentana

    e = crear(
        reescritor=ReescritorFalso("Primera línea.\nSegunda línea."),
        ventana=InfoVentana("ptyxis", "t", 1),
    )
    e.encender()

    assert e.dictar() == "Primera línea. Segunda línea."


class _EnMayusculas:
    def __init__(self) -> None:
        self.recibidos: list[str] = []

    def reescribir(self, texto: str, instruccion: str, tiempo_maximo_s: int) -> str:
        self.recibidos.append(texto)
        return texto.upper()


# ---- cuando falla: texto limpio y un aviso (RF-026) --------------------------------------------------------------


@pytest.mark.parametrize(
    "motivo",
    [
        "No se pudo conectar con Anthropic",
        "Anthropic no respondió a tiempo",
        "Anthropic rechazó la clave de acceso",
    ],
)
def test_si_falla_se_inserta_el_texto_limpio_y_se_avisa(crear, motivo: str) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso(fallo=motivo))
    e.encender()

    assert e.dictar() == "Hola mundo."
    assert any(motivo in aviso for aviso in e.montaje.avisos)
    (dictado,) = e.historial.listar()
    assert dictado.reescrito is False and dictado.proveedor == "" and dictado.estado == "insertado"


def test_un_fallo_de_reescritura_no_deja_la_aplicacion_en_error(crear) -> None:  # type: ignore[no-untyped-def]
    from vozflow.dominio.dictado import EstadoDelDictado

    e = crear(reescritor=ReescritorFalso(fallo="se cayó"))
    e.encender()
    e.dictar()

    assert e.montaje.app.estado is EstadoDelDictado.INACTIVO


def test_sin_clave_guardada_se_inserta_limpio_y_se_avisa(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(claves=ClavesFalsas())
    e.encender()

    assert e.dictar() == "Hola mundo."
    assert any("clave" in aviso.lower() for aviso in e.montaje.avisos)
    assert e.fabricados == []


def test_activada_sin_ningun_proveedor_se_avisa(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()
    e.ajustes.establecer("reescritura.activa", True)
    e.modos.actualizar(e.modos.general().id, reescribir=True)

    assert e.dictar() == "Hola mundo."
    assert any("proveedor" in aviso.lower() for aviso in e.montaje.avisos)


def test_un_llavero_que_no_anda_se_avisa_y_se_inserta_limpio(crear) -> None:  # type: ignore[no-untyped-def]
    from vozflow.persistencia.claves import LlaveroNoDisponible

    class LlaveroRoto:
        def leer(self, proveedor: str) -> str | None:
            raise LlaveroNoDisponible("No se pudo usar el llavero del escritorio")

    e = crear(claves=LlaveroRoto())
    e.encender()

    assert e.dictar() == "Hola mundo."
    assert any("llavero" in aviso.lower() for aviso in e.montaje.avisos)


def test_la_clave_nunca_aparece_en_los_avisos(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso(fallo="Anthropic rechazó la clave de acceso"))
    e.encender()
    e.dictar()

    assert not [a for a in e.montaje.avisos if "clave-de-prueba" in a]


def test_el_modelo_vacio_no_deja_activar(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear()

    with pytest.raises(DatoInvalido):
        e.proveedores.activar("anthropic")


# ---- la tecla de traducir (lote 6) ---------------------------------------------------------------------


def test_la_tecla_de_traducir_inserta_la_traduccion_aunque_el_modo_no_reescriba(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso("Hello, world."))
    e.encender(en_el_modo=False)  # el modo General NO tiene «reescribir»

    e.dictar_traduciendo()

    assert [t for t, _ in e.montaje.insertor.insertados] == ["Hello, world."]


def test_la_instruccion_pide_traducir_al_idioma_de_los_ajustes(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso("Olá, mundo."))
    e.encender(en_el_modo=False)
    e.ajustes.establecer("traduccion.idioma", "portugués")

    e.dictar_traduciendo()

    texto, instruccion, tiempo = e.reescritor.llamadas[0]
    assert texto == "Hola mundo." and tiempo == 9
    assert "portugués" in instruccion and "traduc" in instruccion.lower()


def test_el_historial_marca_la_traduccion_con_su_proveedor(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(texto="eh hola mundo", reescritor=ReescritorFalso("Hello, world."))
    e.encender(en_el_modo=False)

    e.dictar_traduciendo()

    (dictado,) = e.historial.listar()
    assert dictado.reescrito is True and dictado.proveedor == "anthropic"
    assert dictado.texto_crudo == "eh hola mundo" and dictado.texto_final == "Hello, world."


def test_las_otras_dos_teclas_no_traducen(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso("Hello, world."))
    e.encender(en_el_modo=False)

    assert e.dictar() == "Hola mundo."
    assert e.reescritor.llamadas == []


def test_los_atajos_de_texto_se_expanden_despues_de_traducir(crear) -> None:  # type: ignore[no-untyped-def]
    from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo

    e = crear(texto="gracias mi firma", reescritor=_EnMayusculas())
    e.encender(en_el_modo=False)
    AtajosTextoRepo(e.base).agregar("mi firma", "Pedro Freimeyer")

    e.dictar_traduciendo()

    assert e.montaje.insertor.insertados[-1][0] == "GRACIAS Pedro Freimeyer"
    assert "Pedro" not in e.reescritor.recibidos[0]


def test_en_una_terminal_la_traduccion_sale_en_una_sola_linea(crear) -> None:  # type: ignore[no-untyped-def]
    from vozflow.ventana.puerto import InfoVentana

    e = crear(
        reescritor=ReescritorFalso("First line.\nSecond line."),
        ventana=InfoVentana("ptyxis", "t", 1),
    )
    e.encender(en_el_modo=False)

    e.dictar_traduciendo()

    assert e.montaje.insertor.insertados[-1][0] == "First line. Second line."


# ---- cuando no se puede traducir: nada en el idioma equivocado (RF-033, RF-034) ------------------------


def _sin_insertar_y_en_el_historial(e: Entorno) -> None:
    assert e.montaje.insertor.insertados == []
    (dictado,) = e.historial.listar()
    assert dictado.estado == "no_insertado" and dictado.texto_final == "Hola mundo."
    assert dictado.reescrito is False
    assert e.montaje.app.estado is E.ERROR
    assert e.montaje.sin_insertar == ["Hola mundo."]


@pytest.mark.parametrize(
    "motivo",
    [
        "No se pudo conectar con Anthropic",
        "Anthropic no respondió a tiempo",
        "Anthropic rechazó la clave de acceso",
    ],
)
def test_si_la_traduccion_falla_no_se_inserta_nada_y_el_texto_queda_en_el_historial(
    crear: Callable[..., Entorno], motivo: str
) -> None:
    e = crear(reescritor=ReescritorFalso(fallo=motivo))
    e.encender(en_el_modo=False)

    e.dictar_traduciendo()

    _sin_insertar_y_en_el_historial(e)
    assert any(motivo in aviso for aviso in e.montaje.avisos)
    assert any("traduc" in aviso.lower() for aviso in e.montaje.avisos)


def test_con_la_reescritura_apagada_la_tecla_de_traducir_no_manda_nada_y_avisa(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso("Hello."))

    e.dictar_traduciendo()

    _sin_insertar_y_en_el_historial(e)
    assert e.fabricados == []  # ni siquiera se arma un cliente de red
    assert any("reescritura" in aviso.lower() for aviso in e.montaje.avisos)


def test_con_el_interruptor_general_apagado_tampoco_se_traduce(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso("Hello."))
    e.encender(en_el_modo=False)
    e.ajustes.establecer("reescritura.activa", False)

    e.dictar_traduciendo()

    _sin_insertar_y_en_el_historial(e)
    assert e.fabricados == []


def test_sin_clave_guardada_no_se_traduce_y_se_avisa(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(claves=ClavesFalsas(), reescritor=ReescritorFalso("Hello."))
    e.encender(en_el_modo=False)

    e.dictar_traduciendo()

    _sin_insertar_y_en_el_historial(e)
    assert any("clave" in aviso.lower() for aviso in e.montaje.avisos)


def test_con_ollama_se_traduce_sin_clave(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(claves=ClavesFalsas(), reescritor=ReescritorFalso("Hello."))
    e.encender("ollama", en_el_modo=False)

    e.dictar_traduciendo()

    assert e.montaje.insertor.insertados[-1][0] == "Hello."


def test_despues_de_un_fallo_se_puede_volver_a_dictar(crear) -> None:  # type: ignore[no-untyped-def]
    e = crear(reescritor=ReescritorFalso(fallo="sin red"))
    e.encender(en_el_modo=False)
    e.dictar_traduciendo()
    assert isinstance(e.reescritor, ReescritorFalso)
    e.reescritor.fallo = None

    e.dictar_traduciendo()

    assert e.montaje.insertor.insertados[-1][0] == "Texto reescrito."
