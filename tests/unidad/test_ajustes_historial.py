"""Página del historial (RF-027): lista con búsqueda, copiar, volver a insertar y borrar."""

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from pytestqt.qtbot import QtBot

from vozflow.dominio.historial import EstadoDelHistorial
from vozflow.insercion.puerto import Destino, ResultadoInsercion
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.historial import HistorialRepo
from vozflow.ui.ajustes.historial import PaginaHistorial

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
AHORA = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


class Portapapeles:
    def __init__(self) -> None:
        self.copiado: list[str] = []

    def copiar(self, texto: str, *, tambien_primaria: bool) -> None:
        self.copiado.append(texto)


class Insertor:
    def __init__(self) -> None:
        self.insertados: list[tuple[str, Destino]] = []
        self.resultado = ResultadoInsercion.exito()

    def insertar(self, texto: str, destino: Destino) -> ResultadoInsercion:
        self.insertados.append((texto, destino))
        return self.resultado


def _pagina(qtbot: QtBot, activo: bool = True):  # type: ignore[no-untyped-def]
    base = abrir_base(":memory:")
    historial = HistorialRepo(base, activo=lambda: activo)
    dictados: list[tuple[str, EstadoDelHistorial]] = [
        ("Reunión con el equipo", "insertado"),
        ("Comprar pan", "no_insertado"),
        ("Llamar a Ana", "insertado"),
    ]
    for i, (texto, estado) in enumerate(dictados):
        historial.guardar(
            texto_crudo=texto, texto_final=texto, duracion_audio_ms=1000, duracion_proceso_ms=500,
            estado=estado, creado_en=AHORA + timedelta(minutes=i),
        )  # fmt: skip
    portapapeles, insertor = Portapapeles(), Insertor()
    esperas: list[int] = []

    def sin_esperar(accion: Callable[[], None]) -> None:
        esperas.append(1)
        accion()

    pagina = PaginaHistorial(historial, portapapeles, insertor, al_reinsertar=sin_esperar)
    qtbot.addWidget(pagina)
    return pagina, historial, portapapeles, insertor, esperas


def _textos(pagina: PaginaHistorial) -> list[str]:
    return [pagina.lista.item(i).text() for i in range(pagina.lista.count())]


def test_lista_los_mas_recientes_primero_con_su_estado(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    textos = _textos(pagina)

    assert "Llamar a Ana" in textos[0] and "Reunión" in textos[2]
    assert "no insertado" in textos[1].lower()


def test_busca_por_prefijo_sin_distinguir_acentos(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    pagina.campo_busqueda.setText("reunion")
    pagina.buscar()

    assert len(_textos(pagina)) == 1 and "Reunión" in _textos(pagina)[0]


def test_una_busqueda_vacia_vuelve_a_mostrar_todo(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)
    pagina.campo_busqueda.setText("pan")
    pagina.buscar()
    assert len(_textos(pagina)) == 1

    pagina.campo_busqueda.setText("")
    pagina.buscar()

    assert len(_textos(pagina)) == 3


def test_una_busqueda_sin_resultados_lo_dice(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    pagina.campo_busqueda.setText("zzzz")
    pagina.buscar()

    assert _textos(pagina) == [] and "ningún" in pagina.mensaje.lower()


def test_al_elegir_uno_muestra_el_texto_completo(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    pagina.lista.setCurrentRow(1)

    assert pagina.vista.toPlainText() == "Comprar pan"


def test_copia_el_dictado_elegido(qtbot: QtBot) -> None:
    pagina, _, portapapeles, _, _ = _pagina(qtbot)
    pagina.lista.setCurrentRow(0)

    pagina.copiar()

    assert portapapeles.copiado == ["Llamar a Ana"] and "copiado" in pagina.mensaje.lower()


def test_vuelve_a_insertar_el_dictado_elegido_y_lo_marca_insertado(qtbot: QtBot) -> None:
    pagina, historial, _, insertor, esperas = _pagina(qtbot)
    pagina.lista.setCurrentRow(1)  # el que no se pudo insertar

    pagina.reinsertar()

    assert [t for t, _ in insertor.insertados] == ["Comprar pan"] and esperas == [1]
    assert "no insertado" not in _textos(pagina)[1].lower()
    assert historial.listar()[1].estado == "insertado"


def test_si_la_reinsercion_falla_lo_avisa(qtbot: QtBot) -> None:
    pagina, _, _, insertor, _ = _pagina(qtbot)
    insertor.resultado = ResultadoInsercion.fallido("sin ventana")
    pagina.lista.setCurrentRow(1)

    pagina.reinsertar()

    assert pagina.hay_error is True and "sin ventana" in pagina.mensaje


def test_la_reinsercion_da_tiempo_para_que_la_ventana_de_ajustes_suelte_el_foco(
    qtbot: QtBot,
) -> None:
    pagina, _, _, _, esperas = _pagina(qtbot)
    pagina.lista.setCurrentRow(0)

    pagina.reinsertar()

    assert esperas == [1]  # pasó por la función que oculta la ventana y espera


def test_borra_un_dictado(qtbot: QtBot) -> None:
    pagina, historial, *_ = _pagina(qtbot)
    pagina.lista.setCurrentRow(0)

    pagina.borrar()

    assert historial.contar() == 2 and len(_textos(pagina)) == 2


def test_borra_todo_el_historial(qtbot: QtBot) -> None:
    pagina, historial, *_ = _pagina(qtbot)

    pagina.borrar_todo()

    assert historial.contar() == 0 and _textos(pagina) == []


def test_sin_elegir_nada_las_acciones_no_hacen_nada(qtbot: QtBot) -> None:
    pagina, historial, portapapeles, insertor, _ = _pagina(qtbot)
    pagina.lista.setCurrentRow(-1)

    pagina.copiar()
    pagina.reinsertar()
    pagina.borrar()

    assert portapapeles.copiado == [] and insertor.insertados == [] and historial.contar() == 3


def test_con_el_historial_apagado_lo_avisa(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot, activo=False)

    assert "apagado" in pagina.aviso_apagado.text().lower()
