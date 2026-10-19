"""Qué pasos arma el asistente y que ninguno pida cuentas, claves ni datos personales (002, RP-014)."""

import os
from collections.abc import Callable

from PySide6.QtWidgets import QLabel, QLineEdit
from pytestqt.qtbot import QtBot

from tests.unidad.test_asistente_prueba import ProbadorFalso
from tests.unidad.test_permisos import _sondas
from vozflow.audio.captura import Dispositivo
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.asistente.fabrica import ContextoDelAsistente, crear_pasos

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class MedidorFalso:
    def iniciar(self, dispositivo: str | int | None) -> None:
        pass

    def nivel(self) -> float:
        return 0.0

    def detener(self) -> None:
        pass


def _contexto(**sondas: Callable[[], object]) -> ContextoDelAsistente:
    return ContextoDelAsistente(
        ajustes=AjustesRepo(abrir_base(":memory:")),
        aplicar_atajos=lambda atajos: None,
        listar_dispositivos=lambda: [Dispositivo(0, "Micrófono", 1, es_predeterminado=True)],
        sondas=_sondas(**sondas),
        copiar=lambda texto: None,
        teclas_del_teclado=lambda: set(),
        medidor=MedidorFalso(),
        probador=ProbadorFalso(),
        autoinicio_activo=lambda: False,
        fijar_autoinicio=lambda activo: None,
    )


def test_con_todos_los_permisos_en_orden_no_hay_paso_de_permisos(qtbot: QtBot) -> None:
    pasos = crear_pasos(_contexto())
    for paso in pasos:
        qtbot.addWidget(paso)

    assert [p.TITULO for p in pasos] == [
        "Micrófono", "Tu tecla para dictar", "Probá tu voz", "Arrancar con tu computadora",
    ]  # fmt: skip


def test_si_falta_un_permiso_el_primer_paso_es_el_de_permisos(qtbot: QtBot) -> None:
    pasos = crear_pasos(
        _contexto(
            puede_leer_teclados=lambda: False,
            grupo_input_en_la_base=lambda: False,
            grupo_input_activo=lambda: False,
        )
    )
    for paso in pasos:
        qtbot.addWidget(paso)

    assert [p.TITULO for p in pasos][:2] == ["Permisos", "Micrófono"]
    assert len(pasos) == 5


def test_si_falta_reiniciar_la_sesion_tambien_se_muestra_el_paso(qtbot: QtBot) -> None:
    pasos = crear_pasos(
        _contexto(puede_leer_teclados=lambda: False, grupo_input_activo=lambda: False)
    )
    for paso in pasos:
        qtbot.addWidget(paso)

    assert pasos[0].TITULO == "Permisos"


def test_ningun_paso_pide_cuentas_claves_ni_datos_personales(qtbot: QtBot) -> None:
    pasos = crear_pasos(
        _contexto(
            puede_leer_teclados=lambda: False,
            grupo_input_en_la_base=lambda: False,
            grupo_input_activo=lambda: False,
        )
    )
    for paso in pasos:
        qtbot.addWidget(paso)
        paso.al_entrar()
        paso.al_salir()
        campos_ocultos = [
            c for c in paso.findChildren(QLineEdit) if c.echoMode() != QLineEdit.EchoMode.Normal
        ]
        assert campos_ocultos == [], paso.TITULO
        texto = " ".join(e.text() for e in paso.findChildren(QLabel)).lower()
        prohibidas = ("clave de acceso", "correo", "email", "cuenta de", "token", "api")
        assert not [p for p in prohibidas if p in texto], paso.TITULO


def test_todos_los_pasos_dejan_avanzar_en_una_instalacion_en_orden(qtbot: QtBot) -> None:
    pasos = crear_pasos(_contexto())
    for paso in pasos:
        qtbot.addWidget(paso)
        paso.al_entrar()
        assert paso.puede_avanzar() is True, paso.TITULO
        paso.al_salir()
