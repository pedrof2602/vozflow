"""El arranque gráfico (T129): plataforma, una sola instancia, inicio automático y cableado."""

import argparse
import os
import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from tests.dobles import GrabadoraFalsa, MotorFalso
from vozflow.__main__ import CODIGO_OK, Dependencias, DependenciasDelServicio, main
from vozflow.dominio.dictado import EstadoDelDictado as E
from vozflow.ui.arranque import (
    InstanciaUnica,
    activar_autoinicio,
    autoinicio_activo,
    desactivar_autoinicio,
    elegir_plataforma,
)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


# ---- plataforma gráfica ------------------------------------------------------------------------------------


def test_usa_xcb_si_hay_xwayland() -> None:
    assert elegir_plataforma({"DISPLAY": ":0", "WAYLAND_DISPLAY": "wayland-0"}) == "xcb"


def test_vuelve_a_wayland_si_no_hay_xwayland() -> None:
    assert elegir_plataforma({"WAYLAND_DISPLAY": "wayland-0"}) == "wayland"


def test_respeta_la_plataforma_que_la_persona_ya_eligio() -> None:
    assert elegir_plataforma({"QT_QPA_PLATFORM": "offscreen", "DISPLAY": ":0"}) == "offscreen"


def test_sin_ninguna_pantalla_igual_devuelve_algo_valido() -> None:
    assert elegir_plataforma({}) == "wayland"


# ---- una sola instancia ------------------------------------------------------------------------------------


def _nombre(prueba: str) -> str:
    return f"vozflow-prueba-{os.getpid()}-{prueba}"


def test_la_primera_instancia_la_obtiene_y_la_segunda_no(qtbot: QtBot, tmp_path: Path) -> None:
    primera = InstanciaUnica(_nombre("a"), tmp_path)
    segunda = InstanciaUnica(_nombre("a"), tmp_path)
    try:
        assert primera.obtener() is True
        assert segunda.obtener() is False
    finally:
        primera.liberar()


def test_la_segunda_le_pide_a_la_primera_que_muestre_la_ventana(
    qtbot: QtBot, tmp_path: Path
) -> None:
    primera = InstanciaUnica(_nombre("b"), tmp_path)
    segunda = InstanciaUnica(_nombre("b"), tmp_path)
    try:
        assert primera.obtener()
        assert not segunda.obtener()

        with qtbot.waitSignal(primera.pedido_de_mostrar, timeout=3000):
            assert segunda.avisar_a_la_primera() is True
    finally:
        primera.liberar()


def test_al_liberar_otra_puede_tomarla(qtbot: QtBot, tmp_path: Path) -> None:
    primera = InstanciaUnica(_nombre("c"), tmp_path)
    assert primera.obtener()
    primera.liberar()

    otra = InstanciaUnica(_nombre("c"), tmp_path)
    try:
        assert otra.obtener() is True
    finally:
        otra.liberar()


def test_avisar_cuando_no_hay_nadie_devuelve_falso(qtbot: QtBot, tmp_path: Path) -> None:
    sola = InstanciaUnica(_nombre("d"), tmp_path)

    assert sola.avisar_a_la_primera() is False


# ---- inicio automático ------------------------------------------------------------------------------------


def test_activar_escribe_el_archivo_de_inicio_automatico(tmp_path: Path) -> None:
    activar_autoinicio(tmp_path, "/ruta/a/vozflow")

    archivo = tmp_path / "autostart" / "vozflow.desktop"
    texto = archivo.read_text(encoding="utf-8")
    assert "Exec=/ruta/a/vozflow" in texto and "Type=Application" in texto
    assert "X-Vozflow-Generado=true" in texto
    assert autoinicio_activo(tmp_path) is True


def test_desactivar_lo_borra_y_es_inofensivo_si_no_estaba(tmp_path: Path) -> None:
    activar_autoinicio(tmp_path, "/x")

    desactivar_autoinicio(tmp_path)
    desactivar_autoinicio(tmp_path)

    assert autoinicio_activo(tmp_path) is False


def test_no_pisa_un_archivo_que_no_es_de_vozflow(tmp_path: Path) -> None:
    ajeno = tmp_path / "autostart" / "vozflow.desktop"
    ajeno.parent.mkdir()
    ajeno.write_text("[Desktop Entry]\nName=otro\n", encoding="utf-8")

    with pytest.raises(FileExistsError):
        activar_autoinicio(tmp_path, "/x")
    desactivar_autoinicio(tmp_path)

    assert "otro" in ajeno.read_text(encoding="utf-8")


def test_el_comando_con_espacios_se_escribe_entre_comillas(tmp_path: Path) -> None:
    activar_autoinicio(tmp_path, "/mi carpeta/vozflow")

    assert 'Exec="/mi carpeta/vozflow"' in (tmp_path / "autostart" / "vozflow.desktop").read_text(
        encoding="utf-8"
    )


# ---- qué arranca cada forma de llamar al programa ------------------------------------------------------------


def _dependencias() -> Dependencias:
    return Dependencias(
        crear_grabadora=GrabadoraFalsa,
        crear_motor=lambda modelo: MotorFalso(),
        esperar=lambda s: None,
        descargar_modelo=lambda m: "",
        abrir_base=lambda: abrir_base(":memory:"),
    )


def _abre_la_interfaz(llamadas: list[str]) -> Callable[[argparse.Namespace, Dependencias], int]:
    def abrir(argumentos: argparse.Namespace, dependencias: Dependencias) -> int:
        llamadas.append("ui")
        return CODIGO_OK

    return abrir


def test_sin_orden_abre_la_interfaz() -> None:
    llamadas: list[str] = []

    codigo = main([], _dependencias(), interfaz=_abre_la_interfaz(llamadas))

    assert codigo == CODIGO_OK and llamadas == ["ui"]


def test_sin_interfaz_conserva_el_servicio_y_no_abre_la_interfaz() -> None:
    llamadas: list[str] = []
    servicio = DependenciasDelServicio(
        crear_escucha=lambda: (_ for _ in ()).throw(AssertionError("no debería armarse")),
        crear_ventana=lambda: None,  # type: ignore[arg-type,return-value]
        crear_insertor=lambda: None,  # type: ignore[arg-type,return-value]
        crear_motor=lambda m, h: MotorFalso(),
        esperar_cierre=lambda: None,
    )

    with pytest.raises(AssertionError, match="no debería armarse"):
        main(
            ["--sin-interfaz"],
            _dependencias(),
            servicio,
            interfaz=_abre_la_interfaz(llamadas),
        )

    assert llamadas == []


def test_un_subcomando_no_abre_la_interfaz(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from vozflow import __main__ as principal

    monkeypatch.setattr(principal, "_hacer_diagnostico", lambda: [])
    llamadas: list[str] = []

    main(["diagnostico"], _dependencias(), interfaz=_abre_la_interfaz(llamadas))

    assert llamadas == []


def test_el_subcomando_autoinicio(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))

    assert main(["autoinicio", "activar"], _dependencias()) == CODIGO_OK
    assert autoinicio_activo(tmp_path) is True
    assert main(["autoinicio", "estado"], _dependencias()) == CODIGO_OK
    assert "activado" in capsys.readouterr().out
    assert main(["autoinicio", "desactivar"], _dependencias()) == CODIGO_OK
    assert autoinicio_activo(tmp_path) is False


# ---- el cableado de la interfaz ------------------------------------------------------------------------------------

from vozflow.persistencia.ajustes import AjustesRepo  # noqa: E402
from vozflow.persistencia.base import abrir_base  # noqa: E402
from vozflow.ui.aplicacion_grafica import InterfazGrafica  # noqa: E402


class Controlador:
    def __init__(self) -> None:
        self.pausas: list[bool] = []
        self.salidas = 0

    def pausar(self, pausado: bool) -> None:
        self.pausas.append(pausado)

    def salir(self) -> None:
        self.salidas += 1


def _interfaz(qtbot: QtBot, nivel: Callable[[], float] = lambda: 0.0):  # type: ignore[no-untyped-def]
    from tests.dobles import ReescritorFalso
    from tests.unidad.test_gestion_de_proveedores import Claves
    from tests.unidad.test_ventana_ajustes import Insertor, Portapapeles
    from vozflow.ui.ajustes.ventana import ContextoDeAjustes

    base = abrir_base(":memory:")
    controlador = Controlador()
    contexto = ContextoDeAjustes(
        base=base,
        claves=Claves(),
        crear_reescritor=lambda p, c: ReescritorFalso(),
        aplicar_atajos=lambda atajos: None,
        portapapeles=Portapapeles(),
        insertor=Insertor(),
        listar_dispositivos=lambda: [],
    )
    interfaz = InterfazGrafica(
        controlador=controlador,
        ajustes=AjustesRepo(base),
        contexto=contexto,
        nivel=nivel,
        bandeja_disponible=lambda: False,
        intervalo_de_nivel_ms=10,
    )
    qtbot.addWidget(interfaz.ventana)
    qtbot.addWidget(interfaz.indicador)
    return interfaz, controlador


def test_un_cambio_de_estado_llega_al_indicador_y_a_la_ventana(qtbot: QtBot) -> None:
    interfaz, _ = _interfaz(qtbot)

    interfaz.puente.estado.emit(E.ESCUCHANDO)

    assert interfaz.indicador.isVisible()
    assert "Escuchando" in interfaz.ventana.texto_de_estado()
    interfaz.puente.estado.emit(E.INACTIVO)
    assert not interfaz.indicador.isVisible()


def test_el_estado_publicado_desde_otro_hilo_tambien_llega(qtbot: QtBot) -> None:
    interfaz, _ = _interfaz(qtbot)

    hilo = threading.Thread(target=lambda: interfaz.puente.estado.emit(E.ESCUCHANDO))
    hilo.start()
    hilo.join()

    qtbot.waitUntil(lambda: interfaz.indicador.isVisible(), timeout=2000)


def test_mientras_escucha_el_indicador_sigue_el_nivel_del_microfono(qtbot: QtBot) -> None:
    niveles = [0.7]
    interfaz, _ = _interfaz(qtbot, nivel=lambda: niveles[0])

    interfaz.puente.estado.emit(E.ESCUCHANDO)

    qtbot.waitUntil(lambda: interfaz.indicador.nivel == pytest.approx(0.7), timeout=2000)
    niveles[0] = 0.2
    qtbot.waitUntil(lambda: interfaz.indicador.nivel == pytest.approx(0.2), timeout=2000)


def test_fuera_de_escuchar_no_se_consulta_el_nivel(qtbot: QtBot) -> None:
    consultas: list[int] = []

    def nivel() -> float:
        consultas.append(1)
        return 0.0

    interfaz, _ = _interfaz(qtbot, nivel=nivel)

    interfaz.puente.estado.emit(E.INACTIVO)
    qtbot.wait(80)

    assert consultas == []


def test_pausar_y_salir_de_la_bandeja_llegan_al_controlador(qtbot: QtBot) -> None:
    interfaz, controlador = _interfaz(qtbot)

    interfaz.bandeja.menu.actions()[2].trigger()  # Pausar
    interfaz.bandeja.menu.actions()[-1].trigger()  # Salir

    assert controlador.pausas == [True] and controlador.salidas == 1


def test_abrir_ajustes_y_historial_desde_la_bandeja(qtbot: QtBot) -> None:
    interfaz, _ = _interfaz(qtbot)

    interfaz.bandeja.menu.actions()[1].trigger()  # Historial
    assert interfaz.ventana.pagina_actual() == "Historial" and interfaz.ventana.isVisible()
    interfaz.bandeja.menu.actions()[0].trigger()  # Abrir ajustes
    assert interfaz.ventana.pagina_actual() == "Teclas"


def test_un_aviso_se_ve_en_la_ventana_si_no_hay_bandeja(qtbot: QtBot) -> None:
    interfaz, _ = _interfaz(qtbot)

    interfaz.puente.aviso.emit("No se pudo reescribir")

    assert "No se pudo reescribir" in interfaz.ventana.statusBar().currentMessage()


def test_sin_bandeja_la_ventana_se_muestra_al_arrancar(qtbot: QtBot) -> None:
    interfaz, _ = _interfaz(qtbot)

    interfaz.mostrar_al_arrancar()

    assert interfaz.ventana.isVisible()


def test_la_segunda_instancia_hace_aparecer_la_ventana(qtbot: QtBot) -> None:
    interfaz, _ = _interfaz(qtbot)

    interfaz.mostrar_ajustes()

    assert interfaz.ventana.isVisible()


def test_salir_deja_que_la_ventana_se_cierre_para_que_qt_pueda_terminar(qtbot: QtBot) -> None:
    from PySide6.QtGui import QCloseEvent

    interfaz, controlador = _interfaz(qtbot)
    interfaz.mostrar_ajustes()

    interfaz.salir()

    evento = QCloseEvent()
    interfaz.ventana.closeEvent(evento)
    # Si la ventana siguiera ignorando el cierre, Qt cancelaría el quit() y el programa no terminaría.
    assert evento.isAccepted() and controlador.salidas == 1
