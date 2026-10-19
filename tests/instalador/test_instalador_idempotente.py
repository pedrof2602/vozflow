"""Correr el instalador otra vez da el mismo resultado y repara lo que falte (002, RP-001, CP-005)."""

import shutil
from pathlib import Path

from tests.instalador.sistema_falso import INSTALAR, SistemaFalso


def test_correrlo_dos_veces_termina_bien_las_dos(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)

    primera = sistema.correr()
    segunda = sistema.correr()

    assert primera.returncode == 0 and segunda.returncode == 0


def test_las_dos_corridas_hacen_lo_mismo(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)

    sistema.correr()
    primera = sistema.lineas_del_registro()
    sistema.registro.write_text("", encoding="utf-8")
    sistema.correr()

    assert sistema.lineas_del_registro() == primera


def test_no_duplica_la_regla_ni_la_carga_del_modulo(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)

    sistema.correr()
    sistema.correr()

    reglas = sorted(p.name for p in sistema.udev.iterdir())
    assert reglas == ["60-vozflow-uinput.rules"]
    regla = (sistema.udev / reglas[0]).read_text(encoding="utf-8")
    assert regla == 'KERNEL=="uinput", GROUP="input", MODE="0660"\n'  # una sola línea
    assert (sistema.modulos / "vozflow-uinput.conf").read_text(encoding="utf-8") == "uinput\n"


def test_repara_una_regla_borrada(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    sistema.correr()
    (sistema.udev / "60-vozflow-uinput.rules").unlink()

    sistema.correr()

    assert (sistema.udev / "60-vozflow-uinput.rules").is_file()


def test_repara_una_regla_modificada(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    sistema.correr()
    (sistema.udev / "60-vozflow-uinput.rules").write_text("roto\n", encoding="utf-8")

    sistema.correr()

    assert "MODE" in (sistema.udev / "60-vozflow-uinput.rules").read_text(encoding="utf-8")


def test_dentro_de_un_clon_actualiza_con_pull(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)

    sistema.correr()  # el script del repositorio real: es un clon (tiene .git)

    assert any(
        linea.startswith("git -C") and linea.endswith("pull --ff-only")
        for linea in sistema.lineas_del_registro()
    )
    assert not any(linea.startswith("git clone") for linea in sistema.lineas_del_registro())


def _script_suelto(tmp_path: Path) -> Path:
    """El script solo, en una carpeta que no es un clon: como cuando llega por curl."""
    carpeta = tmp_path / "suelto" / "scripts"
    carpeta.mkdir(parents=True)
    destino = carpeta / "instalar.sh"
    shutil.copy(INSTALAR, destino)
    return destino


def test_fuera_de_un_clon_baja_el_codigo_en_la_carpeta_de_la_aplicacion(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    destino = tmp_path / "home" / ".local" / "share" / "vozflow-app"

    resultado = sistema.correr(_script_suelto(tmp_path))

    assert resultado.returncode == 0, resultado.stdout
    assert any(
        linea.startswith("git clone") and linea.endswith(str(destino))
        for linea in sistema.lineas_del_registro()
    )
    assert (
        f"uv run --project {destino} python -m vozflow descargar-modelo"
        in sistema.lineas_del_registro()
    )


def test_la_segunda_vez_fuera_de_un_clon_actualiza_en_vez_de_clonar(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    script = _script_suelto(tmp_path)
    sistema.correr(script)
    sistema.registro.write_text("", encoding="utf-8")

    sistema.correr(script)

    registro = sistema.lineas_del_registro()
    assert not any(linea.startswith("git clone") for linea in registro)
    assert any(linea.startswith("git -C") and "pull" in linea for linea in registro)


def test_se_puede_elegir_la_carpeta_de_destino(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    elegida = tmp_path / "mi-carpeta"

    sistema.correr(_script_suelto(tmp_path), VOZFLOW_DIRECTORIO=str(elegida))

    assert any(
        linea.startswith("git clone") and linea.endswith(str(elegida))
        for linea in sistema.lineas_del_registro()
    )


def test_si_no_se_puede_bajar_el_codigo_lo_dice_y_sale_con_1(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    (sistema.bin / "git").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")

    resultado = sistema.correr(_script_suelto(tmp_path))

    assert resultado.returncode == 1 and "No pude bajar vozflow" in resultado.stdout
