"""Subcomandos que operan los datos sin interfaz: diccionario, atajos, modos, historial…

Cada orden recibe la base ya abierta y escribe en ``salida``; los errores de datos se convierten
en ``ErrorDeComando`` y el que llama decide cómo mostrarlos.
"""

import argparse
import sqlite3
from collections.abc import Callable
from pathlib import Path

from vozflow.dominio.historial import Dictado
from vozflow.dominio.modos import SALTOS_DE_LINEA, TIPOS_DE_PEGADO
from vozflow.persistencia.asignaciones_repo import AsignacionesRepo
from vozflow.persistencia.atajos_texto_repo import AtajosTextoRepo
from vozflow.persistencia.copia_repo import CopiaRepo
from vozflow.persistencia.diccionario_repo import DiccionarioRepo
from vozflow.persistencia.historial import HistorialRepo
from vozflow.persistencia.modos_repo import ModosRepo

ORDENES_DE_DATOS = frozenset(
    {"diccionario", "atajos", "modos", "asignar", "historial", "exportar", "importar"}
)
_RESUMEN_MAXIMO = 60

Argumentos = argparse.Namespace
Base = sqlite3.Connection
Salida = Callable[[str], None]


class ErrorDeComando(Exception):
    """La orden no se pudo cumplir; el mensaje se muestra tal cual."""


def registrar(ordenes: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    diccionario = ordenes.add_parser("diccionario", help="palabras propias para el motor")
    acciones = diccionario.add_subparsers(dest="accion", required=True, metavar="acción")
    agregar = acciones.add_parser("agregar", help="agrega una palabra")
    agregar.add_argument("palabra")
    agregar.add_argument("--nota", default="")
    acciones.add_parser("listar", help="muestra las palabras")
    borrar = acciones.add_parser("borrar", help="borra una palabra")
    borrar.add_argument("palabra")

    atajos = ordenes.add_parser("atajos", help="palabras clave que se expanden a un texto")
    acciones = atajos.add_subparsers(dest="accion", required=True, metavar="acción")
    agregar = acciones.add_parser("agregar", help="agrega un atajo (\\n para un salto de línea)")
    agregar.add_argument("disparador")
    agregar.add_argument("reemplazo")
    acciones.add_parser("listar", help="muestra los atajos")
    borrar = acciones.add_parser("borrar", help="borra un atajo")
    borrar.add_argument("disparador")

    modos = ordenes.add_parser("modos", help="reglas de texto y de pegado por tipo de aplicación")
    acciones = modos.add_subparsers(dest="accion", required=True, metavar="acción")
    acciones.add_parser("listar", help="muestra los modos")
    crear = acciones.add_parser("crear", help="crea un modo")
    crear.add_argument("nombre")
    crear.add_argument("--sin-muletillas", action="store_true")
    crear.add_argument("--sin-puntuacion", action="store_true")
    crear.add_argument("--sin-comandos", action="store_true")
    crear.add_argument("--reescribir", action="store_true")
    crear.add_argument("--instruccion", default="")
    crear.add_argument("--pegado", choices=TIPOS_DE_PEGADO, default="automatico")
    crear.add_argument("--salto", choices=SALTOS_DE_LINEA, default="conservar")
    borrar = acciones.add_parser("borrar", help="borra un modo (el general no se puede)")
    borrar.add_argument("nombre")

    asignar = ordenes.add_parser("asignar", help="asigna una aplicación a un modo")
    asignar.add_argument("aplicacion", nargs="?")
    asignar.add_argument("modo", nargs="?")
    asignar.add_argument("--terminal", action="store_true", help="marcarla como terminal")
    asignar.add_argument("--quitar", metavar="APLICACION", help="quita la asignación")
    asignar.add_argument("--listar", action="store_true", help="muestra las asignaciones")

    historial = ordenes.add_parser("historial", help="dictados anteriores")
    acciones = historial.add_subparsers(dest="accion", required=True, metavar="acción")
    listar = acciones.add_parser("listar", help="los más recientes")
    listar.add_argument("--limite", type=int, default=20)
    buscar = acciones.add_parser("buscar", help="busca en el texto final")
    buscar.add_argument("consulta")
    buscar.add_argument("--limite", type=int, default=20)
    mostrar = acciones.add_parser("mostrar", help="muestra un dictado completo")
    mostrar.add_argument("id", type=int)
    borrar = acciones.add_parser("borrar", help="borra un dictado")
    borrar.add_argument("id", type=int)
    acciones.add_parser("borrar-todo", help="borra todo el historial")

    exportar = ordenes.add_parser(
        "exportar", help="guarda diccionario, atajos y modos en un archivo"
    )
    exportar.add_argument("archivo", type=Path)
    importar = ordenes.add_parser("importar", help="mezcla un archivo de copia con lo que hay")
    importar.add_argument("archivo", type=Path)


def ejecutar(
    argumentos: argparse.Namespace, base: sqlite3.Connection, salida: Callable[[str], None] = print
) -> int:
    orden = {
        "diccionario": _diccionario,
        "atajos": _atajos,
        "modos": _modos,
        "asignar": _asignar,
        "historial": _historial,
        "exportar": _exportar,
        "importar": _importar,
    }[argumentos.orden]
    orden(argumentos, base, salida)
    return 0


# ---- diccionario y atajos ------------------------------------------------------------------------


def _diccionario(a: Argumentos, base: Base, salida: Salida) -> None:
    repo = DiccionarioRepo(base)
    if a.accion == "agregar":
        entrada = repo.agregar(a.palabra, a.nota)
        salida(f"Agregada «{entrada.palabra}».")
    elif a.accion == "borrar":
        if not repo.borrar_palabra(a.palabra):
            raise ErrorDeComando(f"«{a.palabra}» no está en el diccionario")
        salida(f"Borrada «{a.palabra}».")
    else:
        entradas = repo.listar()
        if not entradas:
            salida("El diccionario está vacío.")
        for e in entradas:
            salida(f"{e.palabra}  {e.nota}".rstrip())


def _atajos(a: Argumentos, base: Base, salida: Salida) -> None:
    repo = AtajosTextoRepo(base)
    if a.accion == "agregar":
        atajo = repo.agregar(a.disparador, a.reemplazo.replace("\\n", "\n"))
        salida(f"Agregado «{atajo.disparador}».")
    elif a.accion == "borrar":
        if not repo.borrar_disparador(a.disparador):
            raise ErrorDeComando(f"No hay un atajo «{a.disparador}»")
        salida(f"Borrado «{a.disparador}».")
    else:
        atajos = repo.listar()
        if not atajos:
            salida("No hay atajos de texto.")
        for t in atajos:
            salida(f"{t.disparador} → {t.reemplazo.replace(chr(10), chr(92) + 'n')}")


# ---- modos y asignaciones ------------------------------------------------------------------------


def _si_no(valor: bool) -> str:
    return "sí" if valor else "no"


def _modos(a: Argumentos, base: Base, salida: Salida) -> None:
    repo = ModosRepo(base)
    if a.accion == "crear":
        modo = repo.crear(
            a.nombre,
            quitar_muletillas=not a.sin_muletillas,
            puntuacion_automatica=not a.sin_puntuacion,
            comandos_de_voz=not a.sin_comandos,
            reescribir=a.reescribir,
            instruccion=a.instruccion,
            tipo_pegado=a.pegado,
            salto_de_linea=a.salto,
        )
        salida(f"Creado el modo «{modo.nombre}».")
    elif a.accion == "borrar":
        existente = repo.obtener(a.nombre)
        if existente is None:
            raise ErrorDeComando(f"No existe el modo «{a.nombre}»")
        repo.borrar(existente.id)
        salida(f"Borrado el modo «{existente.nombre}».")
    else:
        for m in repo.listar():
            etiqueta = " (general)" if m.es_general else ""
            salida(
                f"{m.nombre}{etiqueta}  pegado={m.tipo_pegado}  salto={m.salto_de_linea}  "
                f"muletillas={_si_no(m.quitar_muletillas)}  "
                f"puntuación={_si_no(m.puntuacion_automatica)}  "
                f"comandos={_si_no(m.comandos_de_voz)}"
            )


def _asignar(a: Argumentos, base: Base, salida: Salida) -> None:
    asignaciones, modos = AsignacionesRepo(base), ModosRepo(base)
    if a.listar:
        nombres = {m.id: m.nombre for m in modos.listar()}
        lista = asignaciones.listar()
        if not lista:
            salida("No hay aplicaciones asignadas: todas usan el modo general.")
        for x in lista:
            marca = "  (terminal)" if x.es_terminal else ""
            salida(f"{x.aplicacion} → {nombres.get(x.modo_id, '?')}{marca}")
    elif a.quitar:
        if not asignaciones.quitar(a.quitar):
            raise ErrorDeComando(f"«{a.quitar}» no tenía modo asignado")
        salida(f"«{a.quitar}» vuelve al modo general.")
    else:
        if not a.aplicacion or not a.modo:
            raise ErrorDeComando("Indicá la aplicación y el modo: asignar APLICACION MODO")
        modo = modos.obtener(a.modo)
        if modo is None:
            raise ErrorDeComando(f"No existe el modo «{a.modo}»")
        asignaciones.asignar(a.aplicacion, modo.id, es_terminal=a.terminal)
        salida(f"«{a.aplicacion}» usa el modo «{modo.nombre}».")


# ---- historial -----------------------------------------------------------------------------------


def _resumen(dictado: Dictado) -> str:
    texto = " ".join(dictado.texto_final.split())
    if len(texto) > _RESUMEN_MAXIMO:
        texto = texto[: _RESUMEN_MAXIMO - 1] + "…"
    fecha = dictado.creado_en.astimezone().strftime("%Y-%m-%d %H:%M")
    return f"{dictado.id}  {fecha}  {dictado.estado}  {texto}"


def _historial(a: Argumentos, base: Base, salida: Salida) -> None:
    repo = HistorialRepo(base)
    if a.accion in ("listar", "buscar"):
        dictados = (
            repo.listar(a.limite) if a.accion == "listar" else repo.buscar(a.consulta, a.limite)
        )
        if not dictados:
            salida("No hay dictados.")
        for d in dictados:
            salida(_resumen(d))
    elif a.accion == "mostrar":
        dictado = repo.obtener(a.id)
        if dictado is None:
            raise ErrorDeComando(f"No hay un dictado {a.id}")
        salida(dictado.texto_final)
    elif a.accion == "borrar":
        if not repo.borrar(a.id):
            raise ErrorDeComando(f"No hay un dictado {a.id}")
        salida(f"Borrado el dictado {a.id}.")
    else:
        salida(f"Se borraron {repo.borrar_todo()} dictados.")


# ---- copia de seguridad --------------------------------------------------------------------------


def _exportar(a: Argumentos, base: Base, salida: Salida) -> None:
    try:
        CopiaRepo(base).exportar_a(a.archivo)
    except OSError as error:
        raise ErrorDeComando(f"No se pudo escribir {a.archivo}: {error.strerror}") from error
    salida(f"Copia guardada en {a.archivo}.")


def _importar(a: Argumentos, base: Base, salida: Salida) -> None:
    resumen = CopiaRepo(base).importar_de(a.archivo)
    salida(
        f"Se importó: {resumen.diccionario} palabras, {resumen.atajos_de_texto} atajos de texto, "
        f"{resumen.modos} modos y {resumen.asignaciones} asignaciones."
    )
