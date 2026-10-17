"""``python -m vozflow``: el servicio sin interfaz que escucha los atajos y dicta."""

import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.dobles import EscuchaFalsa, GrabadoraFalsa, InsertorFalso, MotorFalso, VentanaFalsa
from vozflow.__main__ import (
    CODIGO_ERROR,
    CODIGO_OK,
    Dependencias,
    DependenciasDelServicio,
    main,
)
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.insercion.puerto import ResultadoInsercion
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.historial import HistorialRepo
from vozflow.servicio_dbus import InstanciaYaEnEjecucion

M, A = AccionDeAtajo.MANTENER, AccionDeAtajo.ALTERNAR
_DIRECTORIO: list[Path] = [Path()]


@pytest.fixture(autouse=True)
def _directorio_de_la_base(tmp_path: Path) -> None:
    _DIRECTORIO[0] = tmp_path


class Montaje:
    def __init__(self, *, cierre: Callable[[Montaje], None] | None = None) -> None:
        self.escucha = EscuchaFalsa()
        self.grabadora = GrabadoraFalsa()
        self.motor = MotorFalso(texto="mi contraseña secreta")
        self.insertor = InsertorFalso()
        self.atajos_pedidos: dict[AccionDeAtajo, str] = {}
        self._cierre = cierre
        iniciar = self.escucha.iniciar

        def iniciar_registrando(atajos, al_evento):  # type: ignore[no-untyped-def]
            self.atajos_pedidos = dict(atajos)
            iniciar(atajos, al_evento)

        self.escucha.iniciar = iniciar_registrando  # type: ignore[method-assign]
        self.dependencias = Dependencias(
            crear_grabadora=lambda: self.grabadora,
            crear_motor=lambda modelo: self.motor,
            esperar=lambda s: None,
            descargar_modelo=lambda m: "",
            abrir_base=lambda: abrir_base(self.ruta),
        )
        # Un archivo de verdad: el servicio abre su propia conexión y la cierra al apagarse.
        self.ruta = _DIRECTORIO[0] / "vozflow.db"
        self.base = abrir_base(self.ruta)
        self.modelo_pedido: tuple[str, int] | None = None
        self.servicio = DependenciasDelServicio(
            crear_escucha=lambda: self.escucha,
            crear_ventana=VentanaFalsa,
            crear_insertor=lambda: self.insertor,
            crear_motor=self._crear_motor,
            esperar_cierre=self._esperar_cierre,
        )

    def _crear_motor(self, modelo: str, hilos: int) -> MotorFalso:
        self.modelo_pedido = (modelo, hilos)
        return self.motor

    def _esperar_cierre(self) -> None:
        if self._cierre is not None:
            self._cierre(self)

    def correr(self, *argumentos: str) -> int:
        return main(list(argumentos), self.dependencias, self.servicio)


def _dictar(m: Montaje) -> None:
    m.escucha.pulsar(M)
    time.sleep(0.1)
    m.escucha.soltar(M)
    limite = time.monotonic() + 3
    while time.monotonic() < limite and not m.insertor.insertados:
        time.sleep(0.01)
    time.sleep(0.1)


def test_arranca_carga_el_modelo_escucha_los_atajos_por_defecto_y_se_apaga_limpio(
    capsys: pytest.CaptureFixture[str],
) -> None:
    m = Montaje()

    codigo = m.correr()

    assert codigo == CODIGO_OK
    assert m.motor.veces_cargado >= 1 and m.motor.cargado is False  # lo libera al apagar
    assert m.atajos_pedidos == {M: "RightCtrl", A: "<Control><Alt>space"}
    assert "RightCtrl" in capsys.readouterr().err


def test_acepta_la_bandera_sin_interfaz() -> None:
    assert Montaje().correr("--sin-interfaz") == CODIGO_OK


def test_los_atajos_se_pueden_cambiar_por_la_linea_de_comandos() -> None:
    m = Montaje()

    m.correr("--mantener", "F9", "--alternar", "<Control><Alt>d")

    assert m.atajos_pedidos == {M: "F9", A: "<Control><Alt>d"}


def test_muestra_el_estado_por_consola_sin_mostrar_lo_dictado(
    capsys: pytest.CaptureFixture[str],
) -> None:
    m = Montaje(cierre=_dictar)

    m.correr()

    salida = capsys.readouterr()
    assert "Escuchando" in salida.err and "Transcribiendo" in salida.err
    assert "contraseña" not in salida.err and "contraseña" not in salida.out
    assert len(m.insertor.insertados) == 1


def test_si_no_se_pudo_insertar_lo_avisa_y_muestra_el_texto_para_no_perderlo(
    capsys: pytest.CaptureFixture[str],
) -> None:
    m = Montaje(cierre=_dictar)
    m.insertor.resultado = ResultadoInsercion.fallido("No se pudo pegar")

    m.correr()

    err = capsys.readouterr().err
    assert "No se pudo pegar" in err and "contraseña" in err


def test_un_atajo_ocupado_termina_con_un_mensaje_claro(
    capsys: pytest.CaptureFixture[str],
) -> None:
    m = Montaje()
    m.escucha.ocupar("RightCtrl")

    codigo = m.correr()

    assert codigo == CODIGO_ERROR
    assert "RightCtrl" in capsys.readouterr().err
    assert m.motor.cargado is False


def test_otra_instancia_corriendo_termina_con_un_mensaje_claro(
    capsys: pytest.CaptureFixture[str],
) -> None:
    m = Montaje()

    def iniciar(atajos, al_evento):  # type: ignore[no-untyped-def]
        raise InstanciaYaEnEjecucion("vozflow ya está corriendo")

    m.escucha.iniciar = iniciar  # type: ignore[method-assign]

    assert m.correr() == CODIGO_ERROR
    assert "ya está corriendo" in capsys.readouterr().err


def test_ctrl_c_es_un_apagado_normal() -> None:
    def interrumpir(_: Montaje) -> None:
        raise KeyboardInterrupt

    m = Montaje(cierre=interrumpir)

    assert m.correr() == CODIGO_OK
    assert m.motor.cargado is False


def test_el_subcomando_diagnostico_imprime_el_informe(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from vozflow import __main__ as principal
    from vozflow.diagnostico import Comprobacion

    monkeypatch.setattr(
        principal, "_hacer_diagnostico", lambda: [Comprobacion("Algo", True, "bien")]
    )

    codigo = Montaje().correr("diagnostico")

    assert codigo == CODIGO_OK and "✓ Algo: bien" in capsys.readouterr().out


# ---- los ajustes, el diccionario y el historial salen de la base ----------------------------------------------


def test_los_atajos_y_el_motor_salen_de_los_ajustes_guardados() -> None:
    m = Montaje()
    ajustes = AjustesRepo(m.base)
    ajustes.establecer("atajo.mantener", "F9")
    ajustes.establecer("motor.modelo", "medium")
    ajustes.establecer("motor.hilos", 6)

    m.correr()

    assert m.atajos_pedidos[M] == "F9" and m.atajos_pedidos[A] == "<Control><Alt>space"
    assert m.modelo_pedido == ("medium", 6)


def test_la_linea_de_comandos_manda_sobre_los_ajustes_sin_cambiarlos() -> None:
    m = Montaje()
    ajustes = AjustesRepo(m.base)
    ajustes.establecer("atajo.mantener", "F9")

    m.correr("--mantener", "F10", "--modelo", "base")

    assert m.atajos_pedidos[M] == "F10" and m.modelo_pedido == ("base", 4)
    assert AjustesRepo(abrir_base(m.ruta)).obtener("atajo.mantener") == "F9"


def test_el_diccionario_de_la_base_llega_al_motor() -> None:
    m = Montaje(cierre=_dictar)
    DiccionarioRepo(m.base).agregar("SQLAlchemy")

    m.correr()

    assert m.motor.llamadas[0].pista == "SQLAlchemy"


def test_cada_dictado_queda_en_el_historial() -> None:
    m = Montaje(cierre=_dictar)

    m.correr()

    (dictado,) = HistorialRepo(abrir_base(m.ruta)).listar()
    assert dictado.estado == "insertado" and dictado.texto_crudo == "mi contraseña secreta"


def test_con_el_historial_apagado_en_los_ajustes_no_se_guarda() -> None:
    m = Montaje(cierre=_dictar)
    AjustesRepo(m.base).establecer("historial.activo", False)

    m.correr()

    assert HistorialRepo(abrir_base(m.ruta)).contar() == 0 and len(m.insertor.insertados) == 1


def test_el_idioma_fijado_en_los_ajustes_llega_al_motor() -> None:
    m = Montaje(cierre=_dictar)
    AjustesRepo(m.base).establecer("idioma.modo", "en")

    m.correr()

    assert m.motor.llamadas[0].idioma == "en"
