"""El instalador comprueba la computadora antes de cambiar nada (002, RP-002, RP-005)."""

from pathlib import Path

import pytest

from tests.instalador.sistema_falso import SistemaFalso, fedora, ubuntu


def _sistema(tmp_path: Path, os_release: str = "") -> SistemaFalso:
    return SistemaFalso(tmp_path, os_release or fedora())


# ---- qué familia de sistema es -----------------------------------------------------------------------------


def test_en_fedora_instala_con_dnf(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr()

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert sistema.llamadas("dnf") and not sistema.llamadas("apt-get")


@pytest.mark.parametrize(
    "os_release",
    [
        ubuntu(),
        'ID=debian\nPRETTY_NAME="Debian 13"\n',
        'ID=linuxmint\nID_LIKE="ubuntu debian"\nPRETTY_NAME="Mint"\n',
    ],
)
def test_en_debian_y_parecidos_instala_con_apt(tmp_path: Path, os_release: str) -> None:
    sistema = _sistema(tmp_path, os_release)

    resultado = sistema.correr()

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert sistema.llamadas("apt-get") and not sistema.llamadas("dnf")


@pytest.mark.parametrize(
    "os_release",
    [
        'ID=rocky\nID_LIKE="rhel centos fedora"\nPRETTY_NAME="Rocky"\n',
        'ID=nobara\nID_LIKE=fedora\nPRETTY_NAME="N"\n',
    ],
)
def test_los_derivados_de_fedora_usan_dnf(tmp_path: Path, os_release: str) -> None:
    sistema = _sistema(tmp_path, os_release)

    assert sistema.correr().returncode == 0 and sistema.llamadas("dnf")


def test_dice_que_sistema_detecto(tmp_path: Path) -> None:
    resultado = _sistema(tmp_path).correr()

    assert "Fedora Linux 44" in resultado.stdout


# ---- lo que no se soporta: sale con 2 y no toca nada -----------------------------------------------------------------


def _no_toco_nada(sistema: SistemaFalso) -> None:
    assert sistema.lineas_del_registro() == []
    assert sistema.archivos_nuevos() == []


def test_otra_distribucion_se_rechaza_con_claridad_sin_cambiar_nada(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path, 'ID=arch\nPRETTY_NAME="Arch Linux"\n')

    resultado = sistema.correr()

    assert resultado.returncode == 2
    assert "todavía no está soportado" in resultado.stdout and "Arch Linux" in resultado.stdout
    assert "No cambié nada" in resultado.stdout
    _no_toco_nada(sistema)


def test_sin_gnome_se_rechaza(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(XDG_CURRENT_DESKTOP="KDE")

    assert resultado.returncode == 2 and "GNOME" in resultado.stdout
    _no_toco_nada(sistema)


def test_sin_escritorio_grafico_se_explica_como_abrir_la_terminal(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(XDG_CURRENT_DESKTOP="")

    assert resultado.returncode == 2 and "sesión gráfica" in resultado.stdout
    _no_toco_nada(sistema)


def test_con_xorg_se_rechaza_y_dice_como_elegir_wayland(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(XDG_SESSION_TYPE="x11")

    assert resultado.returncode == 2 and "Wayland" in resultado.stdout
    _no_toco_nada(sistema)


def test_sin_archivo_de_sistema_se_rechaza(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)
    sistema.os_release.unlink()

    resultado = sistema.correr()

    assert resultado.returncode == 2
    _no_toco_nada(sistema)


def test_con_poco_espacio_se_rechaza_y_dice_cuanto_hace_falta(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(VOZFLOW_ESPACIO_LIBRE_MB="500")

    assert resultado.returncode == 2
    assert "500 MB" in resultado.stdout and "3 GB" in resultado.stdout
    _no_toco_nada(sistema)


def test_con_el_espacio_justo_sigue(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    assert sistema.correr(VOZFLOW_ESPACIO_LIBRE_MB="3000").returncode == 0


def test_con_poca_memoria_avisa_pero_sigue(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    resultado = sistema.correr(VOZFLOW_MEMORIA_MB="2000")

    assert resultado.returncode == 0 and "poca memoria" in resultado.stdout


def test_cada_requisito_cumplido_se_muestra_con_una_tilde(tmp_path: Path) -> None:
    resultado = _sistema(tmp_path).correr()

    assert "✓ Sistema:" in resultado.stdout and "✓ Escritorio GNOME con Wayland" in resultado.stdout
    assert "✓ Espacio libre:" in resultado.stdout


def test_los_mensajes_de_rechazo_no_tienen_jerga(tmp_path: Path) -> None:
    sistema = _sistema(tmp_path)

    texto = sistema.correr(XDG_SESSION_TYPE="x11").stdout.lower()

    assert "traceback" not in texto and "stderr" not in texto
