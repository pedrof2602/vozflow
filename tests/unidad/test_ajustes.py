"""Ajustes persistentes (RF-003, RF-005, RF-029): claves, valores por defecto y validación."""

import pytest

from vozflow.atajos.evdev import parsear_atajo
from vozflow.atajos.gsettings import a_formato_gnome
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.persistencia.ajustes import AjustesRepo
from vozflow.persistencia.base import abrir_base
from vozflow.persistencia.errores import DatoInvalido
from vozflow.transcripcion.faster_whisper import HILOS_POR_DEFECTO, MODELO_POR_DEFECTO


@pytest.fixture
def ajustes() -> AjustesRepo:
    return AjustesRepo(abrir_base(":memory:"))


POR_DEFECTO = {
    "atajo.mantener": "RightCtrl",
    "atajo.alternar": "<Control><Alt>space",
    "audio.dispositivo": "",
    "idioma.modo": "automatico",
    "motor.modelo": "small",
    "motor.hilos": 4,
    "historial.activo": True,
    "reescritura.activa": False,
    "interfaz.indicador": True,
    "atajo.traducir": "RightAlt",
    "atajo.mejorar": "RightShift",
    "traduccion.idioma": "inglés",
    "interfaz.tema": "auto",
    "asistente.hecho": False,
}


def test_todas_las_claves_tienen_su_valor_por_defecto(ajustes: AjustesRepo) -> None:
    assert ajustes.todos() == POR_DEFECTO


@pytest.mark.parametrize(("clave", "valor"), list(POR_DEFECTO.items()))
def test_cada_clave_se_lee_con_su_defecto(ajustes: AjustesRepo, clave: str, valor: object) -> None:
    assert ajustes.obtener(clave) == valor


def test_los_valores_del_motor_coinciden_con_los_del_motor() -> None:
    assert (MODELO_POR_DEFECTO, HILOS_POR_DEFECTO) == ("small", 4)


def test_los_atajos_por_defecto_son_validos_y_no_pisan_los_de_openwhispr() -> None:
    mantener, alternar = POR_DEFECTO["atajo.mantener"], POR_DEFECTO["atajo.alternar"]

    assert parsear_atajo(str(mantener))
    assert a_formato_gnome(str(alternar)) == alternar
    assert not {"F6", "F7", "F8"} & {mantener, alternar}


def test_el_audio_por_defecto_es_el_predeterminado_del_sistema(ajustes: AjustesRepo) -> None:
    assert ajustes.obtener("audio.dispositivo") == ""


# ---- guardar y leer ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("atajo.mantener", "F9"),
        ("atajo.alternar", "<Control><Alt>d"),
        ("audio.dispositivo", "Micrófono USB"),
        ("idioma.modo", "es"),
        ("idioma.modo", "en"),
        ("motor.modelo", "medium"),
        ("motor.hilos", 6),
        ("historial.activo", False),
        ("reescritura.activa", True),
        ("interfaz.indicador", False),
        ("atajo.traducir", "F10"),
        # 003: Shift derecho es ahora la tecla de mejorar; un modificador solo también sirve acá.
        ("atajo.traducir", "LeftShift"),
        ("atajo.mejorar", "F11"),
        ("atajo.mejorar", "LeftAlt"),
        ("traduccion.idioma", "portugués"),
        ("traduccion.idioma", "chino mandarín"),
        ("traduccion.idioma", "es"),
        ("interfaz.tema", "claro"),
        ("interfaz.tema", "oscuro"),
        ("interfaz.tema", "auto"),
        ("asistente.hecho", True),
        ("asistente.hecho", False),
    ],
)
def test_un_valor_valido_se_guarda_y_se_lee_con_su_tipo(
    ajustes: AjustesRepo, clave: str, valor: object
) -> None:
    ajustes.establecer(clave, valor)

    assert ajustes.obtener(clave) == valor
    assert type(ajustes.obtener(clave)) is type(valor)


def test_persiste_en_la_base_entre_conexiones(tmp_path) -> None:  # type: ignore[no-untyped-def]
    ruta = tmp_path / "v.db"
    AjustesRepo(abrir_base(ruta)).establecer("motor.hilos", 2)

    assert AjustesRepo(abrir_base(ruta)).obtener("motor.hilos") == 2


def test_restablecer_vuelve_al_defecto(ajustes: AjustesRepo) -> None:
    ajustes.establecer("motor.hilos", 2)

    ajustes.restablecer("motor.hilos")

    assert ajustes.obtener("motor.hilos") == 4


# ---- validación -------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("clave", "valor"),
    [
        ("motor.hilos", 0),
        ("motor.hilos", 9),
        ("motor.hilos", -1),
        ("motor.hilos", "cuatro"),
        ("motor.hilos", True),
        ("motor.hilos", 2.5),
        ("idioma.modo", "fr"),
        ("idioma.modo", ""),
        ("motor.modelo", ""),
        ("motor.modelo", "   "),
        ("historial.activo", "si"),
        ("historial.activo", 1),
        ("reescritura.activa", None),
        ("interfaz.indicador", "true"),
        ("interfaz.tema", "dark"),
        ("interfaz.tema", ""),
        ("interfaz.tema", None),
        ("asistente.hecho", "si"),
        ("asistente.hecho", 1),
        ("asistente.hecho", None),
        ("atajo.mantener", ""),
        ("atajo.mantener", "TeclaQueNoExiste"),
        ("atajo.alternar", "RightCtrl"),
        ("atajo.alternar", ""),
        ("audio.dispositivo", 3),
        ("atajo.traducir", ""),
        ("atajo.traducir", "TeclaQueNoExiste"),
        ("atajo.traducir", "RightCtrl"),  # es la de mantener
        ("atajo.traducir", "<Control><Alt>space"),  # es la de alternar
        ("atajo.mejorar", ""),
        ("atajo.mejorar", "TeclaQueNoExiste"),
        ("atajo.mejorar", "<Control><Alt>space"),
        ("traduccion.idioma", ""),
        ("traduccion.idioma", "   "),
        ("traduccion.idioma", "x"),
        ("traduccion.idioma", "a" * 41),
        ("traduccion.idioma", "inglés\nfrancés"),
        ("traduccion.idioma", 5),
    ],
)
def test_rechaza_valores_invalidos_y_deja_el_anterior(
    ajustes: AjustesRepo, clave: str, valor: object
) -> None:
    antes = ajustes.obtener(clave)

    with pytest.raises(DatoInvalido):
        ajustes.establecer(clave, valor)

    assert ajustes.obtener(clave) == antes


def test_los_limites_de_hilos_son_1_y_8(ajustes: AjustesRepo) -> None:
    ajustes.establecer("motor.hilos", 1)
    ajustes.establecer("motor.hilos", 8)


def test_una_clave_desconocida_se_rechaza(ajustes: AjustesRepo) -> None:
    with pytest.raises(DatoInvalido, match="clave"):
        ajustes.establecer("no.existe", 1)
    with pytest.raises(DatoInvalido, match="clave"):
        ajustes.obtener("no.existe")


def test_los_dos_atajos_no_pueden_ser_la_misma_tecla(ajustes: AjustesRepo) -> None:
    with pytest.raises(DatoInvalido, match="distint"):
        ajustes.establecer("atajo.mantener", "<Control><Alt>space")


def test_un_valor_corrupto_en_la_base_vuelve_al_defecto(ajustes: AjustesRepo) -> None:
    ajustes._base.execute("INSERT INTO ajuste (clave, valor) VALUES ('motor.hilos', 'basura')")  # noqa: SLF001

    assert ajustes.obtener("motor.hilos") == 4


# ---- la foto de los ajustes que usa el servicio ---------------------------------------------------------------


def test_cargar_arma_la_foto_de_los_ajustes(ajustes: AjustesRepo) -> None:
    ajustes.establecer("atajo.mantener", "F9")

    foto = ajustes.cargar()

    assert foto.atajos() == {
        AccionDeAtajo.MANTENER: "F9",
        AccionDeAtajo.ALTERNAR: "<Control><Alt>space",
        AccionDeAtajo.TRADUCIR: "RightAlt",  # mejorar y traducir (003)
        AccionDeAtajo.MEJORAR: "RightShift",  # solo mejorar (003)
    }
    assert (foto.modelo, foto.hilos, foto.idioma, foto.dispositivo) == ("small", 4, None, None)


def test_el_idioma_automatico_es_ninguno_y_el_dispositivo_vacio_tambien(
    ajustes: AjustesRepo,
) -> None:
    ajustes.establecer("idioma.modo", "en")
    ajustes.establecer("audio.dispositivo", "USB")

    foto = ajustes.cargar()

    assert foto.idioma == "en" and foto.dispositivo == "USB"


def test_se_puede_cambiar_un_atajo_solo_para_esta_ejecucion(ajustes: AjustesRepo) -> None:
    foto = ajustes.cargar().con_atajos(mantener="F10", alternar=None)

    assert foto.atajo_mantener == "F10" and foto.atajo_alternar == "<Control><Alt>space"
    assert ajustes.obtener("atajo.mantener") == "RightCtrl"


# ---- los dos atajos a la vez (la pantalla de teclas los cambia juntos) ---------------------------------------


def test_cambia_los_dos_atajos_de_una_vez(ajustes: AjustesRepo) -> None:
    ajustes.establecer_atajos("F9", "<Control><Alt>d")

    assert ajustes.obtener("atajo.mantener") == "F9"
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>d"


def test_se_pueden_intercambiar_los_dos_atajos(ajustes: AjustesRepo) -> None:
    ajustes.establecer_atajos("F9", "<Control><Alt>d")

    ajustes.establecer_atajos("F10", "<Control><Alt>d")  # mantener cambia, alternar igual
    ajustes.establecer_atajos("F9", "<Control><Alt>e")

    assert ajustes.obtener("atajo.mantener") == "F9"


def test_si_uno_de_los_dos_es_invalido_no_se_guarda_ninguno(ajustes: AjustesRepo) -> None:
    with pytest.raises(DatoInvalido):
        ajustes.establecer_atajos("F9", "Ctrl")  # el segundo no sirve

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>space"


def test_dos_atajos_iguales_se_rechazan_juntos(ajustes: AjustesRepo) -> None:
    with pytest.raises(DatoInvalido, match="distint"):
        ajustes.establecer_atajos("<Control><Alt>d", "<Control><Alt>d")

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"


# ---- la tecla de traducir y el idioma de destino (lote 6) -------------------------------------------------


def test_los_tres_atajos_se_cambian_juntos(ajustes: AjustesRepo) -> None:
    ajustes.establecer_atajos("F9", "<Control><Alt>d", "F10")

    assert ajustes.obtener("atajo.mantener") == "F9"
    assert ajustes.obtener("atajo.alternar") == "<Control><Alt>d"
    assert ajustes.obtener("atajo.traducir") == "F10"


def test_sin_indicar_la_de_traducir_se_conserva_la_que_habia(ajustes: AjustesRepo) -> None:
    ajustes.establecer("atajo.traducir", "F10")

    ajustes.establecer_atajos("F9", "<Control><Alt>d")

    assert ajustes.obtener("atajo.traducir") == "F10"


def test_los_tres_atajos_tienen_que_ser_distintos(ajustes: AjustesRepo) -> None:
    with pytest.raises(DatoInvalido, match="distint"):
        ajustes.validar_atajos("F9", "<Control><Alt>d", "F9")
    with pytest.raises(DatoInvalido, match="distint"):
        ajustes.validar_atajos("F9", "<Control><Alt>d", "<Control><Alt>d")


def test_si_uno_de_los_tres_falla_no_se_guarda_ninguno(ajustes: AjustesRepo) -> None:
    with pytest.raises(DatoInvalido):
        ajustes.establecer_atajos("F9", "<Control><Alt>d", "TeclaQueNoExiste")

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert ajustes.obtener("atajo.traducir") == "RightAlt"


def test_la_foto_incluye_la_tecla_y_el_idioma_de_traduccion(ajustes: AjustesRepo) -> None:
    ajustes.establecer("traduccion.idioma", "portugués")

    foto = ajustes.cargar()

    assert foto.atajos()[AccionDeAtajo.TRADUCIR] == "RightAlt"
    assert foto.idioma_de_traduccion == "portugués"


def test_el_idioma_de_destino_se_guarda_sin_espacios_sobrantes(ajustes: AjustesRepo) -> None:
    ajustes.establecer("traduccion.idioma", "  francés ")

    assert ajustes.obtener("traduccion.idioma") == "francés"


def test_se_puede_cambiar_la_tecla_de_traducir_solo_para_esta_ejecucion(
    ajustes: AjustesRepo,
) -> None:
    foto = ajustes.cargar().con_atajos(mantener=None, alternar=None, traducir="F11")

    assert foto.atajo_traducir == "F11" and foto.atajo_mantener == "RightCtrl"
    assert ajustes.obtener("atajo.traducir") == "RightAlt"


# ---- la tecla de mejorar (003) ---------------------------------------------------------------------------------


def test_las_cuatro_teclas_se_cambian_juntas(ajustes: AjustesRepo) -> None:
    ajustes.establecer_atajos("F9", "<Control><Alt>d", "F10", "F11")

    assert ajustes.obtener("atajo.mejorar") == "F11"
    assert ajustes.obtener("atajo.traducir") == "F10"
    assert ajustes.obtener("atajo.mantener") == "F9"


def test_validar_devuelve_los_cuatro_atajos_normalizados(ajustes: AjustesRepo) -> None:
    validos = ajustes.validar_atajos("F9", "Ctrl+Alt+D", "F10", "F11")

    assert validos == ("F9", "<Control><Alt>d", "F10", "F11")


def test_sin_indicar_la_de_mejorar_se_conserva_la_que_habia(ajustes: AjustesRepo) -> None:
    ajustes.establecer("atajo.mejorar", "F11")

    ajustes.establecer_atajos("F9", "<Control><Alt>d")

    assert ajustes.obtener("atajo.mejorar") == "F11"


@pytest.mark.parametrize(
    "repetida",
    [("F9", "<Control><Alt>d", "F10", "F9"), ("F9", "<Control><Alt>d", "F10", "F10"),
     ("F9", "<Control><Alt>d", "F10", "<Control><Alt>d")],
)  # fmt: skip
def test_las_cuatro_teclas_tienen_que_ser_distintas(
    ajustes: AjustesRepo, repetida: tuple[str, str, str, str]
) -> None:
    with pytest.raises(DatoInvalido, match="distint"):
        ajustes.validar_atajos(*repetida)


def test_si_la_de_mejorar_falla_no_se_guarda_ninguna(ajustes: AjustesRepo) -> None:
    with pytest.raises(DatoInvalido):
        ajustes.establecer_atajos("F9", "<Control><Alt>d", "F10", "TeclaQueNoExiste")

    assert ajustes.obtener("atajo.mantener") == "RightCtrl"
    assert ajustes.obtener("atajo.mejorar") == "RightShift"


def test_se_puede_cambiar_la_tecla_de_mejorar_solo_para_esta_ejecucion(
    ajustes: AjustesRepo,
) -> None:
    foto = ajustes.cargar().con_atajos(mantener=None, alternar=None, mejorar="F11")

    assert foto.atajo_mejorar == "F11" and foto.atajos()[AccionDeAtajo.MEJORAR] == "F11"
    assert ajustes.obtener("atajo.mejorar") == "RightShift"
