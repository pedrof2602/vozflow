"""Arranca la interfaz real: une ``Aplicacion`` con la bandeja, el indicador y los ajustes.

Es la raíz de composición del programa gráfico; las piezas que cablea ya se prueban por separado.
"""

import argparse
import logging
import os
import signal
import sys
import tempfile
import threading
from collections.abc import Callable, Mapping
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from vozflow.__main__ import Dependencias, DependenciasDelServicio
from vozflow.aplicacion import Aplicacion
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.audio.captura import listar_dispositivos
from vozflow.autoinicio import fijar_plataforma
from vozflow.configuracion import ConfiguracionDeBase
from vozflow.insercion.portapapeles import PortapapelesWayland
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.historial import HistorialRepo
from vozflow.reescritura import ReescrituraDeBase
from vozflow.ui.ajustes.ventana import ContextoDeAjustes
from vozflow.ui.aplicacion_grafica import InterfazGrafica
from vozflow.ui.arranque import InstanciaUnica
from vozflow.ui.aspecto import Aspecto, esquema_del_sistema

_registro = logging.getLogger(__name__)


def _directorio_del_candado() -> Path:
    return Path(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir())


def _directorio_del_tema() -> Path:
    base = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return base / "vozflow" / "tema"


class _Controlador:
    def __init__(self, aplicacion: Aplicacion, app: QApplication) -> None:
        self._aplicacion = aplicacion
        self._app = app

    def pausar(self, pausado: bool) -> None:
        self._aplicacion.pausar(pausado)

    def salir(self) -> None:
        self._app.quit()


def arrancar_interfaz(
    argumentos: argparse.Namespace, dependencias: Dependencias, servicio: DependenciasDelServicio
) -> int:
    fijar_plataforma()  # antes de crear la QApplication
    app = QApplication(sys.argv[:1])
    app.setApplicationName("vozflow")
    app.setQuitOnLastWindowClosed(False)  # vive en la bandeja
    aspecto = Aspecto(app, _directorio_del_tema())
    aspecto.aplicar(esquema_del_sistema(app))
    aspecto.seguir_al_sistema()
    instancia = InstanciaUnica("vozflow", _directorio_del_candado())
    if not instancia.obtener():
        instancia.avisar_a_la_primera()
        print("vozflow ya está corriendo: se abrió su ventana.", file=sys.stderr)
        return 0

    base = dependencias.abrir_base()
    try:
        repo = AjustesRepo(base)
        ajustes = repo.cargar().con_atajos(
            argumentos.mantener, argumentos.alternar, argumentos.traducir
        )
        grabadora = dependencias.crear_grabadora()
        insertor = servicio.crear_insertor()
        interfaz: InterfazGrafica | None = None

        def emitir_estado(estado):  # type: ignore[no-untyped-def]
            if interfaz is not None:
                interfaz.puente.estado.emit(estado)

        def emitir_aviso(texto: str) -> None:
            if interfaz is not None:
                interfaz.puente.aviso.emit(texto)

        aplicacion = Aplicacion(
            escucha=servicio.crear_escucha(),
            grabadora=grabadora,
            motor=servicio.crear_motor(argumentos.modelo or ajustes.modelo, ajustes.hilos),
            ventana=servicio.crear_ventana(),
            insertor=insertor,
            atajos=ajustes.atajos(),
            idioma=ajustes.idioma,
            dispositivo=argumentos.dispositivo or ajustes.dispositivo,
            configuracion=ConfiguracionDeBase(base),
            historial=HistorialRepo(base, activo=lambda: bool(repo.obtener("historial.activo"))),
            reescritura=ReescrituraDeBase(
                base, dependencias.claves(), dependencias.crear_reescritor
            ),
            al_cambiar_estado=emitir_estado,
            al_aviso=emitir_aviso,
            # El texto que no se pudo insertar ya queda en el historial; el aviso lo explica.
            al_texto_sin_insertar=lambda _: emitir_aviso(
                "El texto no se pudo insertar: quedó en el historial para recuperarlo."
            ),
        )
        contexto = ContextoDeAjustes(
            base=base,
            claves=dependencias.claves(),
            crear_reescritor=dependencias.crear_reescritor,
            aplicar_atajos=_aplicar_atajos(aplicacion),
            portapapeles=PortapapelesWayland(),
            insertor=insertor,
            listar_dispositivos=listar_dispositivos,
        )
        interfaz = InterfazGrafica(
            controlador=_Controlador(aplicacion, app),
            ajustes=repo,
            contexto=contexto,
            nivel=lambda: float(getattr(grabadora, "nivel", 0.0)),
            destino_de_traduccion=lambda: aplicacion.idioma_en_curso,
        )
        aspecto.al_cambiar(lambda _: interfaz.ventana.actualizar_iconos())
        instancia.pedido_de_mostrar.connect(lambda: interfaz.mostrar_ajustes("Teclas"))
        reloj_de_senales = _atender_ctrl_c(interfaz.salir)  # que no se libere mientras corre Qt
        interfaz.mostrar_al_arrancar()
        threading.Thread(
            target=_iniciar_en_segundo_plano, args=(aplicacion, interfaz), daemon=True
        ).start()
        try:
            return app.exec()
        finally:
            reloj_de_senales.stop()
            interfaz.cerrar()
            aplicacion.detener()
    finally:
        base.close()
        instancia.liberar()


def _aplicar_atajos(aplicacion: Aplicacion):  # type: ignore[no-untyped-def]
    def aplicar(atajos: Mapping[AccionDeAtajo, str]) -> None:
        aplicacion.reconfigurar_atajos(atajos)

    return aplicar


def _iniciar_en_segundo_plano(aplicacion: Aplicacion, interfaz: InterfazGrafica) -> None:
    """Cargar el modelo tarda: la interfaz ya está a la vista mientras tanto."""
    interfaz.puente.aviso.emit("Cargando el modelo de transcripción…")
    try:
        aplicacion.iniciar()
    except Exception as error:
        _registro.warning("No se pudo iniciar la escucha de atajos: %s", type(error).__name__)
        interfaz.puente.aviso.emit(f"No se pudieron activar los atajos: {error}")
        interfaz.puente.abrir_pagina.emit("Teclas")  # para que la persona pueda cambiarlos
        return
    interfaz.puente.aviso.emit("vozflow está listo.")


def _atender_ctrl_c(salir: Callable[[], None]) -> QTimer:
    signal.signal(signal.SIGINT, lambda *_: salir())
    signal.signal(signal.SIGTERM, lambda *_: salir())
    reloj = QTimer()  # deja que Python atienda las señales mientras corre Qt
    reloj.start(250)
    reloj.timeout.connect(lambda: None)
    return reloj
