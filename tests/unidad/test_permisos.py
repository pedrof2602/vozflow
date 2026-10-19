"""Permisos del sistema, en palabras llanas (002, RP-011, ``contracts/permisos.md``)."""

import re

import pytest

from vozflow.diagnostico import Sondas
from vozflow.permisos import Estado, Permiso, comprobar_permisos


def _sondas(**cambios: object) -> Sondas:
    base: dict[str, object] = {
        "version_de_portal": lambda interfaz: 2,
        "puede_leer_teclados": lambda: True,
        "puede_escribir_uinput": lambda: True,
        "ydotoold_corre": lambda: True,
        "programa_instalado": lambda nombre: True,
        "consultar_ventana": lambda: (True, 100),
        "grupo_input_en_la_base": lambda: True,
        "grupo_input_activo": lambda: True,
        "gestor_de_paquetes": lambda: "dnf",
        "microfonos": lambda: 1,
        "es_wayland": lambda: True,
    }
    base.update(cambios)
    return Sondas(**base)  # type: ignore[arg-type]


def _por_nombre(sondas: Sondas) -> dict[str, Permiso]:
    return {p.nombre: p for p in comprobar_permisos(sondas)}


def test_con_todo_en_orden_todos_los_permisos_estan_bien() -> None:
    permisos = _por_nombre(_sondas())

    assert set(permisos) == {"teclado", "teclado_virtual", "portapapeles", "microfono"}
    assert all(p.estado is Estado.BIEN for p in permisos.values())


def test_un_permiso_que_esta_bien_no_trae_paso() -> None:
    permisos = _por_nombre(_sondas())

    assert all(p.paso == "" and p.comando == "" for p in permisos.values())


# ---- el teclado -------------------------------------------------------------------------------------------------


def test_sin_permiso_de_teclado_y_sin_grupo_falta_y_dice_el_comando() -> None:
    permisos = _por_nombre(
        _sondas(
            puede_leer_teclados=lambda: False,
            grupo_input_en_la_base=lambda: False,
            grupo_input_activo=lambda: False,
        )
    )

    teclado = permisos["teclado"]
    assert teclado.estado is Estado.FALTA
    assert teclado.comando == "sudo usermod -aG input $USER"
    assert "cerrá sesión" in teclado.paso.lower()


def test_agregado_al_grupo_pero_sin_reiniciar_sesion_se_distingue() -> None:
    permisos = _por_nombre(
        _sondas(
            puede_leer_teclados=lambda: False,
            grupo_input_en_la_base=lambda: True,
            grupo_input_activo=lambda: False,
        )
    )

    teclado = permisos["teclado"]
    assert teclado.estado is Estado.FALTA_REINICIAR_SESION
    assert teclado.comando == ""  # ya se hizo: no hay nada que copiar
    assert "cerrá sesión" in teclado.paso.lower()


def test_la_diferencia_entre_faltar_y_faltar_reiniciar_la_da_el_grupo_de_la_base() -> None:
    sin_leer = {"puede_leer_teclados": lambda: False, "grupo_input_activo": lambda: False}

    faltar = _por_nombre(_sondas(**sin_leer, grupo_input_en_la_base=lambda: False))["teclado"]
    reiniciar = _por_nombre(_sondas(**sin_leer, grupo_input_en_la_base=lambda: True))["teclado"]

    assert faltar.estado is Estado.FALTA and reiniciar.estado is Estado.FALTA_REINICIAR_SESION


def test_si_se_puede_leer_el_teclado_esta_bien_aunque_el_grupo_no_figure() -> None:
    permisos = _por_nombre(
        _sondas(grupo_input_en_la_base=lambda: False, grupo_input_activo=lambda: False)
    )

    assert permisos["teclado"].estado is Estado.BIEN


# ---- el teclado virtual ---------------------------------------------------------------------------------------


def test_sin_uinput_pero_con_el_portal_se_puede_pegar() -> None:
    permisos = _por_nombre(
        _sondas(puede_escribir_uinput=lambda: False, version_de_portal=lambda i: 2)
    )

    assert permisos["teclado_virtual"].estado is Estado.BIEN


def test_sin_uinput_ni_portal_falta_el_teclado_virtual() -> None:
    permisos = _por_nombre(
        _sondas(puede_escribir_uinput=lambda: False, version_de_portal=lambda i: 0)
    )

    virtual = permisos["teclado_virtual"]
    assert virtual.estado is Estado.FALTA and virtual.paso and virtual.por_que


def test_si_el_portal_falla_no_se_cae_y_cuenta_como_ausente() -> None:
    def roto(interfaz: str) -> int:
        raise OSError("sin bus")

    permisos = _por_nombre(_sondas(puede_escribir_uinput=lambda: False, version_de_portal=roto))

    assert permisos["teclado_virtual"].estado is Estado.FALTA


# ---- el portapapeles ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("gestor", "comando"),
    [("dnf", "sudo dnf install wl-clipboard"), ("apt", "sudo apt install wl-clipboard")],
)
def test_sin_wl_clipboard_el_comando_depende_del_gestor(gestor: str, comando: str) -> None:
    permisos = _por_nombre(
        _sondas(programa_instalado=lambda n: n != "wl-copy", gestor_de_paquetes=lambda: gestor)
    )

    assert permisos["portapapeles"].estado is Estado.FALTA
    assert permisos["portapapeles"].comando == comando


def test_sin_gestor_conocido_se_explica_sin_comando() -> None:
    permisos = _por_nombre(
        _sondas(programa_instalado=lambda n: n != "wl-copy", gestor_de_paquetes=lambda: "")
    )

    assert (
        permisos["portapapeles"].comando == "" and "wl-clipboard" in permisos["portapapeles"].paso
    )


def test_fuera_de_wayland_el_portapapeles_no_aplica() -> None:
    permisos = _por_nombre(_sondas(es_wayland=lambda: False, programa_instalado=lambda n: False))

    assert permisos["portapapeles"].estado is Estado.NO_APLICA


# ---- el micrófono ---------------------------------------------------------------------------------------------


def test_sin_microfonos_falta_y_se_explica() -> None:
    permisos = _por_nombre(_sondas(microfonos=lambda: 0))

    microfono = permisos["microfono"]
    assert microfono.estado is Estado.FALTA and "micrófono" in microfono.paso.lower()


def test_si_no_se_pueden_contar_los_microfonos_falta_sin_caerse() -> None:
    def roto() -> int:
        raise OSError("sin audio")

    assert _por_nombre(_sondas(microfonos=roto))["microfono"].estado is Estado.FALTA


# ---- el lenguaje ------------------------------------------------------------------------------------------------


JERGA = ("evdev", "uinput", "d-bus", "dbus", "portal", "wayland", "api", "grupo input")


def _sin_comandos(texto: str) -> str:
    return re.sub(r"`[^`]*`", "", texto)


@pytest.mark.parametrize("nombre", ["teclado", "teclado_virtual", "portapapeles", "microfono"])
def test_las_frases_no_llevan_jerga_fuera_del_comando(nombre: str) -> None:
    peor = _sondas(
        puede_leer_teclados=lambda: False,
        puede_escribir_uinput=lambda: False,
        version_de_portal=lambda i: 0,
        grupo_input_en_la_base=lambda: False,
        grupo_input_activo=lambda: False,
        programa_instalado=lambda n: False,
        microfonos=lambda: 0,
    )
    permiso = _por_nombre(peor)[nombre]
    texto = _sin_comandos(f"{permiso.titulo} {permiso.por_que} {permiso.paso}").lower()

    assert permiso.estado is Estado.FALTA
    assert not [j for j in JERGA if re.search(rf"\b{re.escape(j)}\b", texto)]
    assert permiso.titulo.strip() and permiso.por_que.strip() and permiso.paso.strip()


def test_los_permisos_que_faltan_explican_para_que_sirven() -> None:
    permisos = _por_nombre(
        _sondas(
            puede_leer_teclados=lambda: False,
            grupo_input_en_la_base=lambda: False,
            grupo_input_activo=lambda: False,
        )
    )

    assert "tecla" in permisos["teclado"].por_que.lower()
