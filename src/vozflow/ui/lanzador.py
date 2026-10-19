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
from vozflow.atajos.disponibilidad import teclas_del_teclado
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.audio.captura import listar_dispositivos
from vozflow.autoinicio import (
    activar_autoinicio,
    autoinicio_activo,
    desactivar_autoinicio,
    fijar_plataforma,
)
from vozflow.configuracion import ConfiguracionDeBase
from vozflow.diagnostico import sondas_reales
from vozflow.escritorio import argumentos_de_inicio
from vozflow.insercion.portapapeles import PortapapelesWayland
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.historial import HistorialRepo
from vozflow.reescritura import ReescrituraDeBase
from vozflow.transcripcion.faster_whisper import modelo_disponible
from vozflow.transcripcion.motor import MotorDeTranscripcion
from vozflow.ui.ajustes.ventana import ContextoDeAjustes
from vozflow.ui.aplicacion_grafica import InterfazGrafica
from vozflow.ui.arranque import InstanciaUnica
from vozflow.ui.asistente.fabrica import ContextoDelAsistente, crear_pasos
from vozflow.ui.asistente.real import MedidorReal, ProbadorReal
from vozflow.ui.asistente.ventana import VentanaAsistente
from vozflow.ui.aspecto import Aspecto

_registro = logging.getLogger(__name__)


def _directorio_del_candado() -> Path:
    corrida = os.environ.get("XDG_RUNTIME_DIR")
    if corrida:
        return Path(corrida)
    # Sin carpeta de ejecución del usuario no se usa /tmp a secas: otro usuario podría ocupar
    # el candado.
    propia = Path(tempfile.gettempdir()) / f"vozflow-{os.getuid()}"
    propia.mkdir(mode=0o700, exist_ok=True)
    propia.chmod(0o700)
    return propia


def _crear_asistente(
    repo: AjustesRepo,
    aplicacion: Aplicacion,
    motor: MotorDeTranscripcion,
    nombre_del_modelo: str,
    dependencias: Dependencias,
    app: QApplication,
) -> VentanaAsistente:
    """El asistente de primer uso; los pasos se arman de nuevo cada vez que se abre."""

    def descargar(al_avance: Callable[[int, int], None]) -> str:
        con_avance = dependencias.descargar_modelo_con_avance
        if con_avance is None:
            return dependencias.descargar_modelo(nombre_del_modelo)
        return con_avance(nombre_del_modelo, al_avance)

    def idioma() -> str | None:
        modo = repo.obtener("idioma.modo")
        return None if modo == "automatico" else str(modo)

    contexto = ContextoDelAsistente(
        ajustes=repo,
        aplicar_atajos=_aplicar_atajos(aplicacion),
        listar_dispositivos=listar_dispositivos,
        sondas=sondas_reales(),
        copiar=app.clipboard().setText,
        teclas_del_teclado=teclas_del_teclado,
        medidor=MedidorReal(dependencias.crear_grabadora),
        probador=ProbadorReal(
            motor=motor,
            crear_grabadora=dependencias.crear_grabadora,
            dispositivo=lambda: str(repo.obtener("audio.dispositivo")) or None,
            idioma=idioma,
            modelo_disponible=lambda: modelo_disponible(nombre_del_modelo),
            descargar=descargar,
        ),
        autoinicio_activo=lambda: autoinicio_activo(_directorio_de_config()),
        fijar_autoinicio=_fijar_autoinicio,
    )
    return VentanaAsistente(lambda: crear_pasos(contexto), repo)


def _directorio_de_config() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")


def _fijar_autoinicio(activo: bool) -> None:
    config = _directorio_de_config()
    if activo:
        activar_autoinicio(config, argumentos_de_inicio())
    else:
        desactivar_autoinicio(config)


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
    aspecto.seguir_al_sistema()
    instancia = InstanciaUnica("vozflow", _directorio_del_candado())
    if not instancia.obtener():
        instancia.avisar_a_la_primera()
        print("vozflow ya está corriendo: se abrió su ventana.", file=sys.stderr)
        return 0

    base = dependencias.abrir_base()
    try:
        repo = AjustesRepo(base)
        aspecto.establecer_modo(repo.obtener("interfaz.tema"))
        ajustes = repo.cargar().con_atajos(
            argumentos.mantener, argumentos.alternar, argumentos.traducir, argumentos.mejorar
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

        nombre_del_modelo = argumentos.modelo or ajustes.modelo
        motor = servicio.crear_motor(nombre_del_modelo, ajustes.hilos)
        aplicacion = Aplicacion(
            escucha=servicio.crear_escucha(),
            grabadora=grabadora,
            motor=motor,
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
        asistente = _crear_asistente(repo, aplicacion, motor, nombre_del_modelo, dependencias, app)
        contexto = ContextoDeAjustes(
            base=base,
            claves=dependencias.claves(),
            crear_reescritor=dependencias.crear_reescritor,
            aplicar_atajos=_aplicar_atajos(aplicacion),
            portapapeles=PortapapelesWayland(),
            insertor=insertor,
            listar_dispositivos=listar_dispositivos,
            aplicar_tema=aspecto.establecer_modo,
            autoinicio_activo=lambda: autoinicio_activo(_directorio_de_config()),
            fijar_autoinicio=_fijar_autoinicio,
            repetir_asistente=asistente.abrir,
        )
        interfaz = InterfazGrafica(
            controlador=_Controlador(aplicacion, app),
            ajustes=repo,
            contexto=contexto,
            nivel=lambda: float(getattr(grabadora, "nivel", 0.0)),
            destino_de_traduccion=lambda: aplicacion.idioma_en_curso,
            mejorando=lambda: aplicacion.intencion_en_curso == "mejorar",
            asistente=asistente,
        )
        aspecto.al_cambiar(lambda _: interfaz.ventana.actualizar_iconos())
        instancia.pedido_de_mostrar.connect(lambda: interfaz.mostrar_ajustes("Dictado"))
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
        interfaz.puente.abrir_pagina.emit("Dictado")  # para que la persona pueda cambiarlos
        return
    interfaz.puente.aviso.emit("vozflow está listo.")


def _atender_ctrl_c(salir: Callable[[], None]) -> QTimer:
    signal.signal(signal.SIGINT, lambda *_: salir())
    signal.signal(signal.SIGTERM, lambda *_: salir())
    reloj = QTimer()  # deja que Python atienda las señales mientras corre Qt
    reloj.start(250)
    reloj.timeout.connect(lambda: None)
    return reloj
