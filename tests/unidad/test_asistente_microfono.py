"""Paso del micrófono: elegirlo y ver que reacciona a la voz (002, RP-008)."""

import os

from PySide6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from vozflow.audio.captura import Dispositivo, ErrorDeAudio
from vozflow.mensajes import explicar
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.asistente.microfono import PasoMicrofono

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DISPOSITIVOS = [
    Dispositivo(0, "Micrófono interno", 2, es_predeterminado=True),
    Dispositivo(3, "Auriculares USB", 1, es_predeterminado=False),
]


class MedidorFalso:
    def __init__(self) -> None:
        self.nivel_actual = 0.0
        self.iniciados: list[str | int | None] = []
        self.detenciones = 0
        self.falla: Exception | None = None

    def iniciar(self, dispositivo: str | int | None) -> None:
        if self.falla is not None:
            raise self.falla
        self.iniciados.append(dispositivo)

    def nivel(self) -> float:
        return self.nivel_actual

    def detener(self) -> None:
        self.detenciones += 1


def _paso(
    qtbot: QtBot, dispositivos: list[Dispositivo] | None = None, medidor: MedidorFalso | None = None
) -> tuple[PasoMicrofono, AjustesRepo, MedidorFalso]:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    medidor = medidor or MedidorFalso()
    lista = DISPOSITIVOS if dispositivos is None else dispositivos
    paso = PasoMicrofono(ajustes, lambda: lista, medidor)
    qtbot.addWidget(paso)
    paso.al_entrar()
    paso.show()
    return paso, ajustes, medidor


def _textos(paso: PasoMicrofono) -> str:
    return " ".join(e.text() for e in paso.findChildren(QLabel))


def test_lista_el_predeterminado_y_cada_microfono(qtbot: QtBot) -> None:
    paso, _, _ = _paso(qtbot)

    nombres = [paso.combo.itemText(i) for i in range(paso.combo.count())]

    assert nombres[0].startswith("Predeterminado")
    assert "Micrófono interno" in nombres[1] and "Auriculares USB" in nombres[2]


def test_al_entrar_empieza_a_medir_con_el_microfono_guardado(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ajustes.establecer("audio.dispositivo", "Auriculares USB")
    medidor = MedidorFalso()
    paso = PasoMicrofono(ajustes, lambda: DISPOSITIVOS, medidor)
    qtbot.addWidget(paso)

    paso.al_entrar()

    assert medidor.iniciados == ["Auriculares USB"]
    assert paso.combo.currentData() == "Auriculares USB"


def test_con_el_predeterminado_mide_el_del_sistema(qtbot: QtBot) -> None:
    _, _, medidor = _paso(qtbot)

    assert medidor.iniciados == [None]


def test_el_medidor_reacciona_a_la_voz(qtbot: QtBot) -> None:
    paso, _, medidor = _paso(qtbot)
    assert paso.nivel_mostrado() == 0.0

    medidor.nivel_actual = 0.7
    paso.actualizar_medidor()

    assert paso.nivel_mostrado() == 0.7


def test_el_nivel_se_acota_entre_0_y_1(qtbot: QtBot) -> None:
    paso, _, medidor = _paso(qtbot)

    medidor.nivel_actual = 5.0
    paso.actualizar_medidor()
    assert paso.nivel_mostrado() == 1.0
    medidor.nivel_actual = -2.0
    paso.actualizar_medidor()
    assert paso.nivel_mostrado() == 0.0


def test_elegir_otro_microfono_lo_guarda_y_mide_ese(qtbot: QtBot) -> None:
    paso, ajustes, medidor = _paso(qtbot)

    paso.combo.setCurrentIndex(2)

    assert ajustes.obtener("audio.dispositivo") == "Auriculares USB"
    assert medidor.detenciones >= 1 and medidor.iniciados[-1] == "Auriculares USB"


def test_al_salir_suelta_el_microfono(qtbot: QtBot) -> None:
    paso, _, medidor = _paso(qtbot)

    paso.al_salir()

    assert medidor.detenciones == 1


def test_con_microfonos_deja_avanzar(qtbot: QtBot) -> None:
    paso, _, _ = _paso(qtbot)

    assert paso.puede_avanzar() is True


def test_sin_microfonos_no_deja_avanzar_y_lo_explica(qtbot: QtBot) -> None:
    paso, _, medidor = _paso(qtbot, dispositivos=[])

    assert paso.puede_avanzar() is False
    assert explicar("sin_microfono").que_paso in _textos(paso)
    assert explicar("sin_microfono").que_hacer in _textos(paso)
    assert medidor.iniciados == []  # no hay nada que medir


def test_buscar_de_nuevo_encuentra_un_microfono_recien_conectado(qtbot: QtBot) -> None:
    conectados: list[Dispositivo] = []
    ajustes = AjustesRepo(abrir_base(":memory:"))
    paso = PasoMicrofono(ajustes, lambda: conectados, MedidorFalso())
    qtbot.addWidget(paso)
    paso.al_entrar()
    avisos: list[int] = []
    paso.cambio.connect(lambda: avisos.append(1))

    conectados.append(DISPOSITIVOS[0])
    paso.boton_buscar.click()

    assert paso.puede_avanzar() is True and avisos == [1]


def test_si_no_se_puede_listar_no_se_cae_y_cuenta_como_sin_microfono(qtbot: QtBot) -> None:
    def falla() -> list[Dispositivo]:
        raise OSError("sin sonido")

    ajustes = AjustesRepo(abrir_base(":memory:"))
    paso = PasoMicrofono(ajustes, falla, MedidorFalso())
    qtbot.addWidget(paso)

    paso.al_entrar()

    assert paso.puede_avanzar() is False


def test_si_el_microfono_esta_ocupado_lo_explica_y_no_deja_avanzar(qtbot: QtBot) -> None:
    medidor = MedidorFalso()
    medidor.falla = ErrorDeAudio("detalle técnico", "microfono_ocupado")

    paso, _, _ = _paso(qtbot, medidor=medidor)

    assert paso.puede_avanzar() is False
    assert explicar("microfono_ocupado").que_paso in _textos(paso)
    assert "detalle técnico" not in _textos(paso)


def test_el_titulo_y_la_ayuda_estan_en_lenguaje_llano(qtbot: QtBot) -> None:
    paso, _, _ = _paso(qtbot)

    assert PasoMicrofono.TITULO == "Micrófono"
    assert "hablá" in _textos(paso).lower()
