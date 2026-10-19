"""uv, las piezas de vozflow y el modelo de voz (002, RP-004)."""

from pathlib import Path

from tests.instalador.sistema_falso import RAIZ, SistemaFalso


def _sistema(tmp_path: Path) -> SistemaFalso:
    return SistemaFalso(tmp_path)


def test_si_uv_ya_esta_no_se_baja_ni_se_pregunta(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr()

    assert sistema.llamadas("curl") == [] and "Falta «uv»" not in resultado.stdout


def test_si_falta_uv_muestra_que_va_a_bajar_y_lo_instala(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    sistema.sin_uv()

    resultado = sistema.correr()

    assert resultado.returncode == 0, resultado.stdout
    assert (
        "Falta «uv»" in resultado.stdout and "https://astral.sh/uv/install.sh" in resultado.stdout
    )
    assert sistema.llamadas("curl") == ["curl -LsSf https://astral.sh/uv/install.sh"]
    assert (sistema.home / ".local" / "bin" / "uv").is_file()


def test_pregunta_aparte_antes_de_bajar_uv_y_si_dice_que_no_cancela(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    sistema.sin_uv()
    sistema.responder("s", "n")  # seguir con los permisos; pero no bajar uv

    resultado = sistema.correr(VOZFLOW_SIN_PREGUNTAS="")

    assert resultado.returncode == 3 and "¿Lo instalo?" in resultado.stdout
    assert sistema.llamadas("curl") == []


def test_sincroniza_las_piezas_con_el_lock_exacto(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    sistema.correr()

    assert "uv sync --locked" in sistema.lineas_del_registro()


def test_baja_el_modelo_con_el_proyecto_correcto_y_la_barra(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr()

    esperado = f"uv run --project {RAIZ} python -m vozflow descargar-modelo"
    assert esperado in sistema.lineas_del_registro()
    assert "Bajo el modelo de voz" in resultado.stdout and "480 MB" in resultado.stdout


def test_el_modelo_se_baja_despues_de_sincronizar(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    sistema.correr()

    registro = sistema.lineas_del_registro()
    posicion_sync = registro.index("uv sync --locked")
    posicion_modelo = next(i for i, linea in enumerate(registro) if "descargar-modelo" in linea)
    assert posicion_sync < posicion_modelo


def test_si_se_corta_la_descarga_dice_que_vuelva_a_correr_y_que_retoma(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(FALLA_EL_MODELO="1")

    assert resultado.returncode == 1
    assert "No pude bajar el modelo" in resultado.stdout
    assert "internet" in resultado.stdout and "retoma" in resultado.stdout


def test_si_falla_sincronizar_dice_que_hacer_y_no_baja_el_modelo(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(FALLA_EL_SYNC="1")

    assert resultado.returncode == 1 and "No pude instalar las piezas" in resultado.stdout
    assert not any("descargar-modelo" in linea for linea in sistema.lineas_del_registro())


def test_pone_vozflow_en_el_menu_despues_del_modelo(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr()

    registro = sistema.lineas_del_registro()
    assert any(linea.endswith("python -m vozflow entrada instalar") for linea in registro)
    assert "menú de aplicaciones" in resultado.stdout


# ---- el final: sesión y arranque -------------------------------------------------------------------------------


def test_si_el_grupo_input_ya_esta_activo_no_pide_cerrar_sesion(tmp_path: Path) -> None:
    resultado = _sistema(tmp_path).correr(VOZFLOW_GRUPOS_ACTIVOS="prueba input")

    assert "cerrá sesión" not in resultado.stdout and "¡Listo!" in resultado.stdout


def test_si_el_grupo_input_no_esta_activo_pide_cerrar_sesion_una_vez(tmp_path: Path) -> None:
    resultado = _sistema(tmp_path).correr(VOZFLOW_GRUPOS_ACTIVOS="prueba")

    assert resultado.stdout.count("cerrá sesión") == 1
    assert "Mientras tanto" in resultado.stdout


def test_dice_como_abrir_vozflow_desde_el_menu(tmp_path: Path) -> None:
    resultado = _sistema(tmp_path).correr()

    assert "buscá «vozflow»" in resultado.stdout


def test_el_arranque_automatico_se_ofrece_pero_no_se_impone(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    sistema.correr()  # sin preguntas: el valor por defecto es que no

    assert not any("autoinicio" in linea for linea in sistema.lineas_del_registro())


def test_si_la_persona_acepta_el_arranque_automatico_se_activa(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    sistema.responder("s", "s")

    sistema.correr(VOZFLOW_SIN_PREGUNTAS="")

    assert any(
        linea.endswith("vozflow autoinicio activar") for linea in sistema.lineas_del_registro()
    )
