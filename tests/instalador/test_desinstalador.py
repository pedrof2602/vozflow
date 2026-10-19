"""El desinstalador: retira lo que puso la instalación y pregunta antes de lo irreversible (002, RP-006)."""

from pathlib import Path

from tests.instalador.sistema_falso import DESINSTALAR, SistemaFalso

MARCA = "X-Vozflow-Generado=true"


class Puesto:
    """Lo que dejó una instalación: menú, ícono, arranque, datos, modelo y reglas del sistema."""

    def __init__(self, sistema: SistemaFalso) -> None:
        self.sistema = sistema
        home = sistema.home
        self.entrada = home / ".local" / "share" / "applications" / "vozflow.desktop"
        self.icono = (
            home / ".local" / "share" / "icons" / "hicolor" / "scalable" / "apps" / "vozflow.svg"
        )
        self.arranque = home / ".config" / "autostart" / "vozflow.desktop"
        self.datos = home / ".local" / "share" / "vozflow"
        self.modelo = (
            home / ".cache" / "huggingface" / "hub" / "models--Systran--faster-whisper-small"
        )
        self.otro_modelo = home / ".cache" / "huggingface" / "hub" / "models--otro--modelo-ajeno"
        self.regla = sistema.udev / "60-vozflow-uinput.rules"
        self.modulo = sistema.modulos / "vozflow-uinput.conf"
        for archivo in (self.entrada, self.icono, self.arranque):
            archivo.parent.mkdir(parents=True, exist_ok=True)
            archivo.write_text(f"[Desktop Entry]\n{MARCA}\n", encoding="utf-8")
        self.icono.write_text("<svg><!-- Generado por vozflow --></svg>", encoding="utf-8")
        for carpeta in (self.datos, self.modelo, self.otro_modelo):
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "archivo").write_text("x", encoding="utf-8")
        sistema.udev.mkdir(parents=True, exist_ok=True)
        sistema.modulos.mkdir(parents=True, exist_ok=True)
        self.regla.write_text('KERNEL=="uinput"\n', encoding="utf-8")
        self.modulo.write_text("uinput\n", encoding="utf-8")


def _puesto(tmp_path: Path) -> Puesto:
    return Puesto(SistemaFalso(tmp_path))


def _correr(puesto: Puesto, *respuestas: str, **extra: str):  # type: ignore[no-untyped-def]
    if respuestas:
        puesto.sistema.responder(*respuestas)
        extra.setdefault("VOZFLOW_SIN_PREGUNTAS", "")
    return puesto.sistema.correr(DESINSTALAR, **extra)


def test_sin_preguntas_retira_menu_icono_y_arranque_y_deja_lo_demas(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    resultado = _correr(puesto)

    assert resultado.returncode == 0, resultado.stdout
    assert (
        not puesto.entrada.exists() and not puesto.icono.exists() and not puesto.arranque.exists()
    )
    assert puesto.datos.exists() and puesto.modelo.exists()
    assert puesto.regla.exists() and puesto.modulo.exists()


def test_nunca_borra_datos_modelo_ni_permisos_sin_preguntar(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    _correr(puesto)

    assert (puesto.datos / "archivo").exists() and (puesto.modelo / "archivo").exists()
    assert puesto.sistema.llamadas("sudo") == [] and puesto.sistema.llamadas("gpasswd") == []


def test_un_archivo_que_no_genero_vozflow_no_se_toca(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)
    puesto.entrada.write_text("[Desktop Entry]\nName=mi propia entrada\n", encoding="utf-8")
    puesto.arranque.write_text("[Desktop Entry]\nName=otro\n", encoding="utf-8")
    puesto.icono.write_text("<svg>de otra persona</svg>", encoding="utf-8")

    _correr(puesto)

    assert puesto.entrada.exists() and puesto.arranque.exists() and puesto.icono.exists()


def test_cada_cosa_irreversible_se_pregunta_por_separado(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    resultado = _correr(puesto, "s", "s", "n", "n", "n", "n")  # seguir; datos sí; el resto no

    assert resultado.returncode == 0, resultado.stdout
    assert not puesto.datos.exists()
    assert puesto.modelo.exists() and puesto.regla.exists()
    assert "historial" in resultado.stdout and "vocabulario" in resultado.stdout


def test_si_se_acepta_borrar_el_modelo_solo_borra_los_de_whisper(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    _correr(puesto, "s", "n", "s", "n", "n", "n")

    assert not puesto.modelo.exists() and puesto.otro_modelo.exists()


def test_si_se_acepta_borrar_las_claves_las_borra_del_llavero(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    _correr(puesto, "s", "n", "n", "s", "n", "n")

    registro = puesto.sistema.lineas_del_registro()
    for proveedor in ("ollama", "anthropic", "openrouter"):
        assert any(
            linea.endswith(f"vozflow proveedor borrar-clave {proveedor}") for linea in registro
        )


def test_si_se_acepta_quitar_los_permisos_usa_un_solo_sudo(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    _correr(puesto, "s", "n", "n", "n", "s", "n")

    assert puesto.sistema.llamadas("sudo") == ["sudo"]
    assert not puesto.regla.exists() and not puesto.modulo.exists()
    assert "gpasswd -d prueba input" in puesto.sistema.lineas_del_registro()


def test_decir_que_no_a_todo_deja_todo_lo_irreversible_intacto(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    _correr(puesto, "s", "n", "n", "n", "n", "n")

    assert puesto.datos.exists() and puesto.modelo.exists() and puesto.regla.exists()


def test_cancelar_desde_el_principio_no_toca_nada(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    resultado = _correr(puesto, "n")

    assert resultado.returncode == 3 and "Cancelado" in resultado.stdout
    assert puesto.entrada.exists() and puesto.arranque.exists() and puesto.icono.exists()


def test_la_carpeta_del_programa_no_se_borra_si_es_tu_copia_del_codigo(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)

    resultado = _correr(puesto, "s", "n", "n", "n", "n", "s")  # sí a borrar la carpeta

    assert "tu copia del código" in resultado.stdout


def test_la_carpeta_instalada_por_el_instalador_se_borra_si_se_acepta(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)
    carpeta = tmp_path / "home" / ".local" / "share" / "vozflow-app"
    (carpeta / "scripts").mkdir(parents=True)
    (carpeta / "pyproject.toml").write_text('[project]\nname = "vozflow"\n', encoding="utf-8")
    script = carpeta / "scripts" / "desinstalar.sh"
    script.write_text(DESINSTALAR.read_text(encoding="utf-8"), encoding="utf-8")

    puesto.sistema.responder("s", "n", "n", "n", "n", "s")
    resultado = puesto.sistema.correr(script, VOZFLOW_SIN_PREGUNTAS="")

    assert resultado.returncode == 0, resultado.stdout
    assert not carpeta.exists()


def test_correrlo_otra_vez_no_falla_aunque_ya_no_quede_nada(tmp_path: Path) -> None:
    puesto = _puesto(tmp_path)
    _correr(puesto)

    resultado = _correr(puesto)

    assert resultado.returncode == 0 and "ya estaba retirado" in resultado.stdout


def test_dice_que_retiro_y_que_dejo(tmp_path: Path) -> None:
    resultado = _correr(_puesto(tmp_path))

    assert "✓ Retiré vozflow del menú" in resultado.stdout
    assert "Dejé tus datos" in resultado.stdout
