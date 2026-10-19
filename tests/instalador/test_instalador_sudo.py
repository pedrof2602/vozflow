"""Los permisos de administrador: un solo resumen, una sola confirmación y un solo sudo (002, RP-003)."""

from pathlib import Path

from tests.instalador.sistema_falso import SistemaFalso, fedora, ubuntu


def _sistema(tmp_path: Path, os_release: str = "") -> SistemaFalso:
    return SistemaFalso(tmp_path, os_release or fedora())


def test_cuenta_antes_que_hace_lo_que_va_a_hacer_con_permisos(tmp_path: Path) -> None:
    resultado = _sistema(tmp_path).correr()

    salida = resultado.stdout
    assert "permisos de administrador una sola vez" in salida
    assert "Instalar estos programas:" in salida
    assert "leer el teclado" in salida and "teclado virtual" in salida
    assert salida.index("permisos de administrador") < salida.index("Programas y permisos listos")


def test_el_resumen_lista_los_paquetes_de_fedora_incluido_el_compilador(tmp_path: Path) -> None:
    salida = _sistema(tmp_path).correr().stdout

    for paquete in ("wl-clipboard", "ydotool", "portaudio", "gcc", "kernel-headers", "git"):
        assert paquete in salida


def test_el_resumen_lista_los_paquetes_de_debian_incluido_el_compilador(tmp_path: Path) -> None:
    salida = _sistema(tmp_path, ubuntu()).correr().stdout

    for paquete in ("wl-clipboard", "libportaudio2", "build-essential", "linux-libc-dev", "git"):
        assert paquete in salida


def test_usa_un_solo_sudo_para_todo(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    sistema.correr()

    assert sistema.llamadas("sudo") == ["sudo"]


def test_dentro_de_ese_sudo_instala_agrega_al_grupo_y_deja_la_regla(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    sistema.correr()

    assert any(
        linea.startswith("dnf install -y") and "wl-clipboard" in linea
        for linea in sistema.lineas_del_registro()
    )
    assert "usermod -aG input prueba" in sistema.lineas_del_registro()
    assert any(linea.startswith("modprobe uinput") for linea in sistema.lineas_del_registro())


def test_en_debian_actualiza_la_lista_e_instala_con_apt(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path, ubuntu())

    sistema.correr()

    llamadas = sistema.llamadas("apt-get")
    assert llamadas[0] == "apt-get update"
    assert llamadas[1].startswith("apt-get install -y") and "build-essential" in llamadas[1]


def test_escribe_la_regla_de_uinput_y_la_carga_del_modulo(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    sistema.correr()

    regla = (sistema.udev / "60-vozflow-uinput.rules").read_text(encoding="utf-8")
    assert regla == 'KERNEL=="uinput", GROUP="input", MODE="0660"\n'
    assert (sistema.modulos / "vozflow-uinput.conf").read_text(encoding="utf-8") == "uinput\n"


def test_si_la_persona_dice_que_no_sale_con_3_sin_cambiar_nada(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    sistema.responder("n")

    resultado = sistema.correr(VOZFLOW_SIN_PREGUNTAS="")

    assert resultado.returncode == 3 and "Cancelado" in resultado.stdout
    assert sistema.lineas_del_registro() == [] and sistema.archivos_nuevos() == []


def test_si_la_persona_dice_que_si_sigue(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    sistema.responder("s", "")  # seguir; y no al arranque automático (por defecto)

    resultado = sistema.correr(VOZFLOW_SIN_PREGUNTAS="")

    assert resultado.returncode == 0 and sistema.llamadas("sudo") == ["sudo"]


def test_enter_solo_cuenta_como_si_porque_es_lo_recomendado(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    sistema.responder("", "")

    assert sistema.correr(VOZFLOW_SIN_PREGUNTAS="").returncode == 0


def test_sin_terminal_no_instala_nada_y_lo_explica(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(
        VOZFLOW_SIN_PREGUNTAS="", VOZFLOW_ENTRADA=str(tmp_path / "no-existe")
    )

    assert resultado.returncode == 3 and "terminal" in resultado.stdout
    assert sistema.lineas_del_registro() == []


def test_si_falla_la_instalacion_de_paquetes_sale_con_1_y_dice_que_hacer(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    (sistema.bin / "dnf").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")

    resultado = sistema.correr()

    assert resultado.returncode == 1
    assert "No pude instalar los programas" in resultado.stdout
    assert "volvé a correr este mismo comando" in resultado.stdout


def test_si_falla_el_paso_de_permisos_no_sigue_con_lo_demas(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    (sistema.bin / "dnf").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")

    sistema.correr()

    assert not any(linea.startswith("uv") for linea in sistema.lineas_del_registro())
