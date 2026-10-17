"""Valores por defecto de la configuración (la persistencia llega en el lote 3)."""

from vozflow.ajustes_por_defecto import Ajustes
from vozflow.atajos.evdev import parsear_atajo
from vozflow.atajos.gsettings import a_formato_gnome
from vozflow.atajos.puerto import AccionDeAtajo
from vozflow.transcripcion.faster_whisper import MODELO_POR_DEFECTO


def test_los_valores_por_defecto_son_los_decididos() -> None:
    ajustes = Ajustes()

    assert ajustes.atajo_mantener == "RightCtrl"
    assert ajustes.atajo_alternar == "<Control><Alt>space"
    assert ajustes.modelo == "small"
    assert ajustes.hilos == 4


def test_el_modelo_coincide_con_el_del_motor() -> None:
    assert Ajustes().modelo == MODELO_POR_DEFECTO


def test_los_atajos_se_entregan_por_accion() -> None:
    assert Ajustes().atajos() == {
        AccionDeAtajo.MANTENER: "RightCtrl",
        AccionDeAtajo.ALTERNAR: "<Control><Alt>space",
    }


def test_ambos_atajos_son_validos_para_su_tecnica() -> None:
    ajustes = Ajustes()

    assert parsear_atajo(ajustes.atajo_mantener)
    assert a_formato_gnome(ajustes.atajo_alternar) == ajustes.atajo_alternar


def test_no_pisa_las_teclas_que_usa_openwhispr() -> None:
    ajustes = Ajustes()

    for usada in ("F6", "F7", "F8"):
        assert usada not in (ajustes.atajo_mantener, ajustes.atajo_alternar)


def test_se_pueden_cambiar_los_atajos_desde_la_linea_de_comandos() -> None:
    ajustes = Ajustes().con_atajos(mantener="F9", alternar=None)

    assert ajustes.atajo_mantener == "F9"
    assert ajustes.atajo_alternar == "<Control><Alt>space"
