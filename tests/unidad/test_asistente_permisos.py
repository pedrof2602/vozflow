"""Paso de permisos del asistente: explica lo que falta y vuelve a comprobar (002, RP-011)."""

import os

from PySide6.QtWidgets import QLabel, QPushButton
from pytestqt.qtbot import QtBot

from vozflow.permisos import Estado, Permiso
from vozflow.ui.asistente.permisos import PasoPermisos, hay_permisos_pendientes

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

BIEN = Permiso("microfono", "Micrófono", Estado.BIEN, "Para escucharte.")
FALTA_TECLADO = Permiso(
    "teclado", "Leer el teclado", Estado.FALTA, "Para saber qué tecla apretás para dictar.",
    "Copiá este comando en una terminal y después cerrá sesión y volvé a entrar.",
    "sudo usermod -aG input $USER",
)  # fmt: skip
REINICIAR_TECLADO = Permiso(
    "teclado", "Leer el teclado", Estado.FALTA_REINICIAR_SESION, "Para saber qué tecla apretás.",
    "Ya diste el permiso, pero falta una cosa: cerrá sesión y volvé a entrar para que se active.",
)  # fmt: skip
NO_APLICA = Permiso("portapapeles", "Copiar y pegar", Estado.NO_APLICA, "Para copiar.")


class Comprobador:
    def __init__(self, *resultados: list[Permiso]) -> None:
        self.resultados = list(resultados)
        self.llamadas = 0

    def __call__(self) -> list[Permiso]:
        self.llamadas += 1
        return self.resultados[min(self.llamadas, len(self.resultados)) - 1]


def _paso(qtbot: QtBot, comprobar: Comprobador, copiados: list[str] | None = None):  # type: ignore[no-untyped-def]
    paso = PasoPermisos(comprobar, (copiados if copiados is not None else []).append)
    qtbot.addWidget(paso)
    paso.al_entrar()
    paso.show()
    return paso


def _textos(paso: PasoPermisos) -> str:
    return " ".join(e.text() for e in paso.findChildren(QLabel))


def test_hay_permisos_pendientes_solo_si_falta_alguno() -> None:
    assert hay_permisos_pendientes([BIEN, NO_APLICA]) is False
    assert hay_permisos_pendientes([BIEN, FALTA_TECLADO]) is True
    assert hay_permisos_pendientes([REINICIAR_TECLADO]) is True


def test_muestra_lo_que_falta_para_que_sirve_y_el_paso(qtbot: QtBot) -> None:
    paso = _paso(qtbot, Comprobador([BIEN, FALTA_TECLADO]))

    texto = _textos(paso)

    assert FALTA_TECLADO.titulo in texto and FALTA_TECLADO.por_que in texto
    assert FALTA_TECLADO.paso in texto


def test_no_muestra_lo_que_ya_esta_bien(qtbot: QtBot) -> None:
    paso = _paso(qtbot, Comprobador([BIEN, FALTA_TECLADO]))

    assert BIEN.titulo not in _textos(paso)


def test_muestra_el_comando_exacto_y_se_puede_copiar(qtbot: QtBot) -> None:
    copiados: list[str] = []
    paso = _paso(qtbot, Comprobador([FALTA_TECLADO]), copiados)

    assert paso.comando_visible() == "sudo usermod -aG input $USER"
    paso.boton_copiar_comando.click()

    assert copiados == ["sudo usermod -aG input $USER"]


def test_si_ya_se_hizo_y_falta_reiniciar_no_hay_comando_y_lo_dice(qtbot: QtBot) -> None:
    paso = _paso(qtbot, Comprobador([REINICIAR_TECLADO]))

    assert paso.comando_visible() == "" and paso.boton_copiar_comando.isHidden() is True
    assert "cerrá sesión" in _textos(paso).lower()


def test_ya_lo_hice_vuelve_a_comprobar_y_muestra_lo_nuevo(qtbot: QtBot) -> None:
    comprobar = Comprobador([FALTA_TECLADO], [REINICIAR_TECLADO])
    paso = _paso(qtbot, comprobar)

    paso.boton_ya_lo_hice.click()

    assert comprobar.llamadas == 2
    assert paso.comando_visible() == ""
    assert "falta una cosa" in _textos(paso)


def test_cuando_todo_queda_en_orden_lo_celebra_y_deja_seguir(qtbot: QtBot) -> None:
    comprobar = Comprobador([FALTA_TECLADO], [BIEN])
    paso = _paso(qtbot, comprobar)
    avisos: list[int] = []
    paso.cambio.connect(lambda: avisos.append(1))

    paso.boton_ya_lo_hice.click()

    assert "todo en orden" in _textos(paso).lower()
    assert paso.boton_ya_lo_hice.isHidden() is True and avisos == [1]


def test_el_paso_siempre_deja_avanzar_para_no_trabar_a_nadie(qtbot: QtBot) -> None:
    paso = _paso(qtbot, Comprobador([FALTA_TECLADO]))

    assert paso.puede_avanzar() is True


def test_al_entrar_comprueba_de_nuevo(qtbot: QtBot) -> None:
    comprobar = Comprobador([FALTA_TECLADO], [BIEN])
    paso = _paso(qtbot, comprobar)

    paso.al_entrar()

    assert comprobar.llamadas == 2 and "todo en orden" in _textos(paso).lower()


def test_un_comprobador_que_falla_no_rompe_el_paso(qtbot: QtBot) -> None:
    def roto() -> list[Permiso]:
        raise OSError("sin acceso")

    paso = PasoPermisos(roto, lambda texto: None)
    qtbot.addWidget(paso)

    paso.al_entrar()

    assert "no pude comprobar" in _textos(paso).lower()


def test_el_titulo_del_paso_esta_en_lenguaje_llano() -> None:
    assert PasoPermisos.TITULO == "Permisos"


def test_los_botones_dicen_lo_que_hacen(qtbot: QtBot) -> None:
    paso = _paso(qtbot, Comprobador([FALTA_TECLADO]))

    botones = [b.text() for b in paso.findChildren(QPushButton)]

    assert "Copiar el comando" in botones and "Ya lo hice" in botones
