"""La documentación para quien no es técnico, la licencia y la colaboración (002, RP-025 a RP-027, RP-030)."""

import re
import tomllib
from pathlib import Path

import pytest

from vozflow.__main__ import _crear_parser

RAIZ = Path(__file__).resolve().parents[2]
README = (RAIZ / "README.md").read_text(encoding="utf-8")


def _secciones(texto: str) -> list[str]:
    return [linea[3:].strip() for linea in texto.splitlines() if linea.startswith("## ")]


def _seccion(texto: str, titulo: str) -> str:
    partes = re.split(r"^## ", texto, flags=re.MULTILINE)
    return next(p for p in partes if p.startswith(titulo))


# ---- licencia (RP-025) -------------------------------------------------------------------------------------


def test_la_licencia_es_mit_con_su_texto_completo() -> None:
    licencia = (RAIZ / "LICENSE").read_text(encoding="utf-8")

    assert licencia.startswith("MIT License")
    assert "Permission is hereby granted, free of charge" in licencia
    assert 'THE SOFTWARE IS PROVIDED "AS IS"' in licencia
    assert re.search(r"Copyright \(c\) 2026 \S", licencia)


def test_el_proyecto_declara_la_licencia_mit() -> None:
    proyecto = tomllib.loads((RAIZ / "pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert proyecto["license"] == "MIT"


def test_el_readme_dice_que_es_de_codigo_abierto_con_licencia_mit() -> None:
    assert "MIT" in _seccion(README, "Licencia")


# ---- el README (RP-026, RP-030) ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "titulo",
    [
        "Qué hace",
        "Tu privacidad",
        "Instalar",
        "Usarla en 3 pasos",
        "Si algo no anda",
        "Cómo reportar un problema",
        "Desinstalar",
        "Licencia",
    ],
)
def test_el_readme_tiene_cada_seccion(titulo: str) -> None:
    assert titulo in _secciones(README)


def test_las_secciones_estan_en_un_orden_que_se_lee_de_arriba_hacia_abajo() -> None:
    secciones = _secciones(README)
    orden = ["Qué hace", "Tu privacidad", "Instalar", "Usarla en 3 pasos", "Si algo no anda"]

    assert [secciones.index(s) for s in orden] == sorted(secciones.index(s) for s in orden)


def test_el_readme_dice_que_todo_queda_en_la_computadora_y_que_no_hay_telemetria() -> None:
    privacidad = _seccion(README, "Tu privacidad").lower()

    assert "no sale de tu computadora" in privacidad or "se queda en tu computadora" in privacidad
    assert "telemetría" in privacidad and "llavero" in privacidad
    assert "audio" in privacidad and "nunca" in privacidad


def test_la_privacidad_aclara_que_sale_con_el_asistente_de_ia() -> None:
    privacidad = _seccion(README, "Tu privacidad").lower()

    assert "asistente de ia" in privacidad and "solo el texto" in privacidad


def test_instalar_muestra_el_comando_y_los_requisitos() -> None:
    instalar = _seccion(README, "Instalar")

    assert "./scripts/instalar.sh" in instalar
    assert "GNOME" in instalar and "3 GB" in instalar


def test_el_uso_en_tres_pasos_son_tres_pasos() -> None:
    pasos = _seccion(README, "Usarla en 3 pasos")

    numerados = re.findall(r"^\d+\. ", pasos, flags=re.MULTILINE)
    assert len(numerados) == 3


def test_los_problemas_se_explican_como_sintoma_y_que_hacer() -> None:
    problemas = _seccion(README, "Si algo no anda")

    assert "| Si pasa esto | Probá esto |" in problemas
    assert problemas.count("\n| ") >= 6


def test_reportar_un_problema_pide_el_diagnostico_copiable() -> None:
    reportar = _seccion(README, "Cómo reportar un problema")

    assert "diagnostico --copiable" in reportar
    assert "no incluye" in reportar.lower()


def test_desinstalar_menciona_el_script_y_que_pregunta_antes_de_borrar() -> None:
    desinstalar = _seccion(README, "Desinstalar")

    assert "./scripts/desinstalar.sh" in desinstalar and "pregunta" in desinstalar.lower()


def test_el_readme_no_tiene_rutas_ni_correos_personales() -> None:
    assert not re.search(r"/home/\w+", README)
    assert "@gmail" not in README and "@hotmail" not in README


@pytest.mark.parametrize("jerga", ["evdev", "uinput", "D-Bus", "AT-SPI", "RemoteDesktop"])
def test_el_readme_no_usa_jerga_tecnica_del_sistema(jerga: str) -> None:
    assert jerga not in README


def test_los_comandos_que_menciona_el_readme_existen() -> None:
    import argparse

    ordenes: set[str] = set()
    for accion in _crear_parser()._actions:  # noqa: SLF001
        if isinstance(accion, argparse._SubParsersAction):  # noqa: SLF001
            ordenes |= set(accion.choices)
    mencionados = set(re.findall(r"python -m vozflow ([a-z][a-z-]+)", README))

    assert mencionados and mencionados <= ordenes, mencionados - ordenes


def test_los_scripts_que_menciona_el_readme_existen() -> None:
    for script in set(re.findall(r"\./(scripts/[\w.-]+\.sh)", README)):
        assert (RAIZ / script).is_file(), script


def test_el_readme_declara_que_es_solo_para_linux_con_gnome_y_que_es_en_espanol() -> None:
    instalar = _seccion(README, "Instalar")

    assert "Fedora" in instalar and "Ubuntu" in instalar
    assert "Windows" in README  # aclara que todavía no


def test_el_readme_reconoce_a_openwhispr_como_inspiracion_y_no_como_codigo_copiado() -> None:
    assert "OpenWhispr" in README and "desde cero" in README


# ---- colaborar (RP-027) -----------------------------------------------------------------------------------------


def test_existe_la_guia_para_colaborar_y_dice_como_correr_las_pruebas() -> None:
    guia = (RAIZ / "CONTRIBUTING.md").read_text(encoding="utf-8")

    assert "scripts/ci.sh" in guia
    assert "prueba" in guia.lower() and "español" in guia.lower()


def test_la_guia_pide_no_subir_audios_modelos_ni_claves() -> None:
    guia = (RAIZ / "CONTRIBUTING.md").read_text(encoding="utf-8").lower()

    assert "audio" in guia and "modelo" in guia and "clave" in guia


def test_existen_las_plantillas_de_incidencias() -> None:
    plantillas = RAIZ / ".github" / "ISSUE_TEMPLATE"

    assert (plantillas / "fallo.md").is_file() and (plantillas / "sugerencia.md").is_file()


def test_la_plantilla_de_fallo_pide_el_diagnostico_y_avisa_que_no_se_pegue_lo_dictado() -> None:
    fallo = (RAIZ / ".github" / "ISSUE_TEMPLATE" / "fallo.md").read_text(encoding="utf-8")

    assert "diagnostico --copiable" in fallo
    assert "no pegues" in fallo.lower()


def test_las_plantillas_tienen_el_encabezado_que_github_necesita() -> None:
    for nombre in ("fallo.md", "sugerencia.md"):
        texto = (RAIZ / ".github" / "ISSUE_TEMPLATE" / nombre).read_text(encoding="utf-8")
        assert texto.startswith("---\n") and "name:" in texto and "about:" in texto, nombre


def test_la_guia_pide_los_cambios_de_especificacion_aparte_y_la_prueba_primero() -> None:
    guia = (RAIZ / "CONTRIBUTING.md").read_text(encoding="utf-8").lower()

    assert "primero" in guia and "fallar" in guia


# ---- publicar: lo decide una persona (RP-029) ----------------------------------------------------------------


def test_la_guia_de_publicacion_dice_que_solo_el_dueno_cambia_la_visibilidad() -> None:
    guia = (RAIZ / "docs" / "publicar.md").read_text(encoding="utf-8")

    assert "scripts/revisar_publicacion.py" in guia
    assert "solo vos" in guia.lower() and "visibilidad" in guia.lower()


def test_la_guia_explica_como_resolver_el_correo_personal() -> None:
    guia = (RAIZ / "docs" / "publicar.md").read_text(encoding="utf-8")

    assert "noreply" in guia and "--aceptar" in guia


def test_la_guia_lista_lo_que_hay_que_confirmar_antes_de_publicar() -> None:
    guia = (RAIZ / "docs" / "publicar.md").read_text(encoding="utf-8")

    assert "titular de la licencia" in guia.lower()
    assert guia.count("- [ ]") >= 5


def test_ningun_script_ni_flujo_del_repositorio_cambia_la_visibilidad() -> None:
    for archivo in list((RAIZ / "scripts").glob("*")) + list((RAIZ / ".github").rglob("*.yml")):
        if archivo.is_file():
            texto = archivo.read_text(encoding="utf-8", errors="replace")
            assert "gh repo edit" not in texto and "--visibility" not in texto, archivo
