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
    insertor.resultado = ResultadoInsercion.fallido("sin ventana", "pegado_fallo")
    pagina.lista.setCurrentRow(1)

    pagina.reinsertar()

    # 002 (RP-022): el aviso es el del catálogo, no el detalle técnico.
    assert pagina.hay_error is True and "No pude pegar el texto" in pagina.mensaje
    assert "sin ventana" not in pagina.mensaje


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


# ---- el motivo del fallo, en palabras llanas (002, RP-022, RP-023) ------------------------------------------


def _pagina_con_fallo(qtbot: QtBot, motivo: str):  # type: ignore[no-untyped-def]
    base = abrir_base(":memory:")
    historial = HistorialRepo(base)
    historial.guardar(
        texto_crudo="comprar pan", texto_final="Comprar pan.", duracion_audio_ms=1000,
        duracion_proceso_ms=500, estado="no_insertado", motivo=motivo, creado_en=AHORA,
    )  # fmt: skip
    historial.guardar(
        texto_crudo="todo bien", texto_final="Todo bien.", duracion_audio_ms=1000,
        duracion_proceso_ms=500, estado="insertado", creado_en=AHORA + timedelta(minutes=1),
    )  # fmt: skip
    insertor = Insertor()
    pagina = PaginaHistorial(historial, Portapapeles(), insertor, al_reinsertar=lambda a: a())
    qtbot.addWidget(pagina)
    return pagina, insertor


def test_un_dictado_no_insertado_muestra_que_paso_y_que_hacer(qtbot: QtBot) -> None:
    from vozflow.mensajes import explicar

    pagina, _ = _pagina_con_fallo(qtbot, "pegado_fallo")

    pagina.lista.setCurrentRow(1)  # el más viejo: el no insertado

    texto = pagina.explicacion.text()
    assert explicar("pegado_fallo").que_paso in texto
    assert explicar("pegado_fallo").que_hacer in texto
    assert pagina.explicacion.isHidden() is False


def test_un_dictado_anterior_sin_motivo_muestra_el_mensaje_generico(qtbot: QtBot) -> None:
    from vozflow.mensajes import explicar

    pagina, _ = _pagina_con_fallo(qtbot, "")

    pagina.lista.setCurrentRow(1)

    assert explicar("generico").que_paso in pagina.explicacion.text()


def test_un_dictado_insertado_no_muestra_explicacion(qtbot: QtBot) -> None:
    pagina, _ = _pagina_con_fallo(qtbot, "pegado_fallo")

    pagina.lista.setCurrentRow(0)  # el más nuevo: insertado

    assert pagina.explicacion.isHidden() is True


def test_al_cambiar_de_fila_la_explicacion_sigue_a_la_fila(qtbot: QtBot) -> None:
    pagina, _ = _pagina_con_fallo(qtbot, "pegado_fallo")
    pagina.lista.setCurrentRow(1)

    pagina.lista.setCurrentRow(0)

    assert pagina.explicacion.isHidden() is True


def test_el_texto_se_puede_copiar_a_un_clic_desde_el_fallo(qtbot: QtBot) -> None:
    pagina, _ = _pagina_con_fallo(qtbot, "pegado_fallo")
    pagina.lista.setCurrentRow(1)

    pagina.boton_copiar.click()

    assert pagina._portapapeles.copiado == ["Comprar pan."]
    assert pagina.boton_copiar.isVisibleTo(pagina) is True


def test_si_al_reinsertar_falla_el_aviso_es_el_del_catalogo(qtbot: QtBot) -> None:
    from vozflow.mensajes import explicar

    pagina, insertor = _pagina_con_fallo(qtbot, "pegado_fallo")
    insertor.resultado = ResultadoInsercion.fallido("detalle técnico", "pegado_fallo")
    pagina.lista.setCurrentRow(1)

    pagina.reinsertar()

    assert pagina.hay_error is True
    assert explicar("pegado_fallo").que_paso in pagina.mensaje
    assert "detalle técnico" not in pagina.mensaje


# ---- guardar lo que dictás, con un interruptor (002, RP-015, RP-016) ----------------------------------------


def _pagina_con_ajustes(qtbot: QtBot):  # type: ignore[no-untyped-def]
    from vozflow.persistencia.ajustes import AjustesRepo

    base = abrir_base(":memory:")
    ajustes = AjustesRepo(base)
    historial = HistorialRepo(base, activo=lambda: bool(ajustes.obtener("historial.activo")))
    pagina = PaginaHistorial(
        historial, Portapapeles(), Insertor(), al_reinsertar=lambda a: a(), ajustes=ajustes
    )
    qtbot.addWidget(pagina)
    pagina.show()
    return pagina, ajustes


def test_el_interruptor_de_guardar_arranca_prendido(qtbot: QtBot) -> None:
    pagina, _ = _pagina_con_ajustes(qtbot)

    assert pagina.interruptor_guardar is not None and pagina.interruptor_guardar.isChecked()


def test_apagar_el_interruptor_deja_de_guardar_y_avisa(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina_con_ajustes(qtbot)

    assert pagina.interruptor_guardar is not None
    pagina.interruptor_guardar.setChecked(False)

    assert ajustes.obtener("historial.activo") is False
    assert "apagado" in pagina.aviso_apagado.text().lower()


def test_volver_a_prenderlo_quita_el_aviso(qtbot: QtBot) -> None:
    pagina, ajustes = _pagina_con_ajustes(qtbot)
    assert pagina.interruptor_guardar is not None
    pagina.interruptor_guardar.setChecked(False)

    pagina.interruptor_guardar.setChecked(True)

    assert ajustes.obtener("historial.activo") is True and pagina.aviso_apagado.text() == ""


def test_el_interruptor_lleva_titulo_y_ayuda_en_lenguaje_llano(qtbot: QtBot) -> None:
    from PySide6.QtWidgets import QLabel

    from vozflow.ui.textos import ayuda_de, texto_de

    pagina, _ = _pagina_con_ajustes(qtbot)
    textos = [e.text() for e in pagina.findChildren(QLabel)]

    assert texto_de("historial.activo").titulo in textos and ayuda_de("historial.activo") in textos


def test_sin_ajustes_la_pagina_no_ofrece_el_interruptor(qtbot: QtBot) -> None:
    pagina, *_ = _pagina(qtbot)

    assert pagina.interruptor_guardar is None


def test_la_pagina_declara_su_clave_para_el_inventario() -> None:
    assert PaginaHistorial.CLAVES == ("historial.activo",)
