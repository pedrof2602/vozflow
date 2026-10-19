"""El asistente de primer uso: recorrido corto con Atrás, Siguiente y Saltear (002, RP-007, RP-013)."""

import os

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout
from pytestqt.qtbot import QtBot

from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.ui.asistente.base import PasoDelAsistente
from vozflow.ui.asistente.ventana import VentanaAsistente, debe_abrirse

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


class PasoFalso(PasoDelAsistente):
    cambio = Signal()

    def __init__(self, titulo: str, puede: bool = True) -> None:
        super().__init__()
        self.TITULO = titulo
        self.puede = puede
        self.entradas = 0
        self.salidas = 0
        QVBoxLayout(self).addWidget(QLabel(titulo))

    def puede_avanzar(self) -> bool:
        return self.puede

    def al_entrar(self) -> None:
        self.entradas += 1

    def al_salir(self) -> None:
        self.salidas += 1


def _asistente(qtbot: QtBot, pasos: list[PasoFalso] | None = None):  # type: ignore[no-untyped-def]
    ajustes = AjustesRepo(abrir_base(":memory:"))
    pasos = pasos or [
        PasoFalso("Micrófono"),
        PasoFalso("Tecla"),
        PasoFalso("Prueba"),
        PasoFalso("Arranque"),
    ]
    terminados: list[int] = []
    ventana = VentanaAsistente(pasos, ajustes, lambda: terminados.append(1))
    qtbot.addWidget(ventana)
    ventana.show()
    return ventana, ajustes, pasos, terminados


# ---- recorrido -------------------------------------------------------------------------------------------------


def test_recorre_los_pasos_en_orden_y_dice_en_cual_esta(qtbot: QtBot) -> None:
    ventana, *_ = _asistente(qtbot)

    assert ventana.titulo_del_paso() == "Paso 1 de 4: Micrófono"
    ventana.boton_siguiente.click()
    assert ventana.titulo_del_paso() == "Paso 2 de 4: Tecla"
    ventana.boton_siguiente.click()
    ventana.boton_siguiente.click()
    assert ventana.titulo_del_paso() == "Paso 4 de 4: Arranque"


def test_se_puede_volver_atras(qtbot: QtBot) -> None:
    ventana, *_ = _asistente(qtbot)
    ventana.boton_siguiente.click()

    ventana.boton_atras.click()

    assert ventana.paso_actual() == 0


def test_en_el_primer_paso_no_hay_atras(qtbot: QtBot) -> None:
    ventana, *_ = _asistente(qtbot)

    assert ventana.boton_atras.isEnabled() is False
    ventana.boton_siguiente.click()
    assert ventana.boton_atras.isEnabled() is True


def test_en_el_ultimo_paso_siguiente_pasa_a_ser_terminar(qtbot: QtBot) -> None:
    ventana, *_ = _asistente(qtbot)
    assert ventana.boton_siguiente.text() == "Siguiente"

    for _ in range(3):
        ventana.boton_siguiente.click()

    assert ventana.boton_siguiente.text() == "Terminar"


def test_cada_paso_se_entera_de_cuando_entra_y_sale(qtbot: QtBot) -> None:
    ventana, _, pasos, _ = _asistente(qtbot)

    assert pasos[0].entradas == 1
    ventana.boton_siguiente.click()

    assert pasos[0].salidas == 1 and pasos[1].entradas == 1


def test_un_paso_que_no_puede_avanzar_bloquea_siguiente(qtbot: QtBot) -> None:
    ventana, _, pasos, _ = _asistente(qtbot)
    pasos[0].puede = False
    ventana.actualizar_botones()

    assert ventana.boton_siguiente.isEnabled() is False


def test_cuando_el_paso_avisa_que_ya_puede_se_habilita(qtbot: QtBot) -> None:
    pasos = [PasoFalso("Micrófono", puede=False), PasoFalso("Tecla")]
    ventana, *_ = _asistente(qtbot, pasos)
    assert ventana.boton_siguiente.isEnabled() is False

    pasos[0].puede = True
    pasos[0].cambio.emit()

    assert ventana.boton_siguiente.isEnabled() is True


def test_saltear_no_exige_que_el_paso_pueda_avanzar(qtbot: QtBot) -> None:
    pasos = [PasoFalso("Micrófono", puede=False), PasoFalso("Tecla")]
    ventana, _, _, terminados = _asistente(qtbot, pasos)

    assert ventana.boton_saltear.isEnabled() is True
    ventana.boton_saltear.click()

    assert terminados == [1]


# ---- terminar o saltear: se guarda y no vuelve a aparecer ------------------------------------------------------


def test_terminar_guarda_que_el_asistente_esta_hecho(qtbot: QtBot) -> None:
    ventana, ajustes, _, terminados = _asistente(qtbot)

    for _ in range(4):
        ventana.boton_siguiente.click()

    assert ajustes.obtener("asistente.hecho") is True and terminados == [1]
    assert ventana.isVisible() is False


def test_saltear_tambien_lo_da_por_hecho(qtbot: QtBot) -> None:
    ventana, ajustes, _, terminados = _asistente(qtbot)

    ventana.boton_saltear.click()

    assert ajustes.obtener("asistente.hecho") is True and terminados == [1]
    assert ventana.isVisible() is False


def test_cerrar_la_ventana_cuenta_como_saltear(qtbot: QtBot) -> None:
    ventana, ajustes, _, terminados = _asistente(qtbot)

    ventana.close()

    assert ajustes.obtener("asistente.hecho") is True and terminados == [1]


def test_avisa_una_sola_vez_aunque_se_cierre_dos_veces(qtbot: QtBot) -> None:
    ventana, _, _, terminados = _asistente(qtbot)

    ventana.boton_saltear.click()
    ventana.close()

    assert terminados == [1]


def test_debe_abrirse_solo_si_no_esta_hecho() -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    assert debe_abrirse(ajustes) is True

    ajustes.establecer("asistente.hecho", True)

    assert debe_abrirse(ajustes) is False


def test_reabrirlo_vuelve_al_primer_paso(qtbot: QtBot) -> None:
    ventana, *_ = _asistente(qtbot)
    ventana.boton_siguiente.click()
    ventana.boton_saltear.click()

    ventana.abrir()

    assert ventana.isVisible() and ventana.paso_actual() == 0


def test_reabrirlo_permite_terminar_otra_vez_y_avisa(qtbot: QtBot) -> None:
    ventana, _, _, terminados = _asistente(qtbot)
    ventana.boton_saltear.click()

    ventana.abrir()
    ventana.boton_saltear.click()

    assert terminados == [1, 1]


def test_un_asistente_sin_pasos_no_falla_y_termina_enseguida(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    terminados: list[int] = []
    ventana = VentanaAsistente([], ajustes, lambda: terminados.append(1))
    qtbot.addWidget(ventana)

    ventana.abrir()

    assert ajustes.obtener("asistente.hecho") is True and terminados == [1]


# ---- una fábrica de pasos: se arman de nuevo cada vez que se abre ---------------------------------------------


def test_con_una_fabrica_los_pasos_se_arman_cada_vez_que_se_abre(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    armados: list[int] = []

    def fabrica() -> list[PasoFalso]:
        armados.append(1)
        return [PasoFalso("Uno"), PasoFalso("Dos")]

    ventana = VentanaAsistente(fabrica, ajustes)
    qtbot.addWidget(ventana)

    ventana.abrir()
    assert ventana.titulo_del_paso() == "Paso 1 de 2: Uno"
    ventana.boton_saltear.click()
    ventana.abrir()

    assert armados == [1, 1] and ventana.titulo_del_paso() == "Paso 1 de 2: Uno"


def test_la_fabrica_puede_dar_una_cantidad_distinta_de_pasos_cada_vez(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    cantidades = iter([2, 3])
    ventana = VentanaAsistente(
        lambda: [PasoFalso(f"P{i}") for i in range(next(cantidades))], ajustes
    )
    qtbot.addWidget(ventana)

    ventana.abrir()
    assert ventana.titulo_del_paso().startswith("Paso 1 de 2")
    ventana.boton_saltear.click()
    ventana.abrir()

    assert ventana.titulo_del_paso().startswith("Paso 1 de 3")


def test_con_una_fabrica_los_pasos_viejos_se_sueltan(qtbot: QtBot) -> None:
    ajustes = AjustesRepo(abrir_base(":memory:"))
    ventana = VentanaAsistente(lambda: [PasoFalso("Uno")], ajustes)
    qtbot.addWidget(ventana)
    ventana.abrir()
    primero = ventana._pasos[0]  # noqa: SLF001

    ventana.boton_saltear.click()
    ventana.abrir()

    assert ventana._pasos[0] is not primero  # noqa: SLF001
    assert ventana._pila.count() == 1  # noqa: SLF001
