"""Cada fallo del instalador dice qué pasó y qué hacer, con los códigos de salida del contrato (002)."""

import re
from pathlib import Path

import pytest

from tests.instalador.sistema_falso import DESINSTALAR, INSTALAR, SistemaFalso


def _romper(sistema: SistemaFalso, que: str) -> dict[str, str]:
    if que == "paquetes":
        (sistema.bin / "dnf").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    elif que == "git":
        (sistema.bin / "git").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    elif que == "sync":
        return {"FALLA_EL_SYNC": "1"}
    elif que == "modelo":
        return {"FALLA_EL_MODELO": "1"}
    elif que == "uv":
        sistema.sin_uv()
        (sistema.bin / "curl").write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
    return {}


@pytest.mark.parametrize("que", ["paquetes", "sync", "modelo", "uv"])
def test_un_fallo_da_codigo_1_con_el_que_paso_y_el_que_hacer(tmp_path: Path, que: str) -> None:
    sistema = SistemaFalso(tmp_path)
    extra = _romper(sistema, que)

    resultado = sistema.correr(**extra)

    lineas = resultado.stdout.splitlines()
    errores = [i for i, linea in enumerate(lineas) if linea.startswith("✗ ")]
    assert resultado.returncode == 1, resultado.stdout
    assert len(errores) == 1
    siguientes = lineas[errores[0] + 1 :]
    assert any("volvé a correr" in linea.lower() or "Revisá" in linea for linea in siguientes)


def test_un_fallo_de_git_fuera_de_un_clon_da_codigo_1(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    _romper(sistema, "git")
    suelto = tmp_path / "suelto" / "scripts"
    suelto.mkdir(parents=True)
    (suelto / "instalar.sh").write_text(INSTALAR.read_text(encoding="utf-8"), encoding="utf-8")

    resultado = sistema.correr(suelto / "instalar.sh")

    assert resultado.returncode == 1 and resultado.stdout.count("✗ ") == 1


def test_los_mensajes_de_error_no_muestran_nada_tecnico(tmp_path: Path) -> None:
    sistema = SistemaFalso(tmp_path)
    extra = _romper(sistema, "sync")

    texto = sistema.correr(**extra).stdout

    assert "Traceback" not in texto and "line " not in texto and "bash:" not in texto


@pytest.mark.parametrize("script", [INSTALAR, DESINSTALAR])
def test_el_script_solo_sale_con_los_codigos_del_contrato(script: Path) -> None:
    codigos = set(re.findall(r"^\s*exit (\d+)", script.read_text(encoding="utf-8"), re.MULTILINE))

    assert codigos <= {"0", "1", "2", "3"}


@pytest.mark.parametrize("script", [INSTALAR, DESINSTALAR])
def test_el_script_tiene_una_sintaxis_valida(script: Path) -> None:
    import subprocess

    assert subprocess.run(["bash", "-n", str(script)], check=False).returncode == 0


def test_el_encabezado_documenta_los_codigos_de_salida() -> None:
    cabecera = INSTALAR.read_text(encoding="utf-8").split("set -u")[0]

    assert "0 listo" in cabecera and "2 requisito" in cabecera and "3 cancelaste" in cabecera
