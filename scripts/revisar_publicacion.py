#!/usr/bin/env python3
"""Revisión previa a publicar el repositorio (002, RP-028).

Recorre TODO el historial de git (todas las ramas, también lo que ya se borró) y la carpeta de
trabajo, y arma un informe con lo que no debería hacerse público:

  - claves y secretos (y archivos de configuración con secretos);
  - audios y modelos (por extensión y por tamaño);
  - datos personales (correos, rutas con un usuario y el correo con que firman los commits).

Es de SOLO LECTURA: no cambia nada del repositorio, no usa la red y nunca publica. Hacerlo público
lo decide una persona (RP-029).

    uv run python scripts/revisar_publicacion.py [--repo CARPETA] [--aceptar CORREO ...]

Sale con 0 si no hay nada sin resolver, 1 si lo hay, 2 si la carpeta no es un repositorio.
"""

import argparse
import fnmatch
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

LIMITE_DE_TAMANO_MB = 5
LIMITE_PARA_LEER_BYTES = 2 * 1024 * 1024

EXTENSIONES_DE_AUDIO = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".m4a", ".aac", ".wma", ".aiff"}
EXTENSIONES_DE_MODELO = {
    ".bin", ".onnx", ".pt", ".pth", ".gguf", ".safetensors", ".ckpt", ".h5", ".tflite", ".ct2",
}  # fmt: skip

PATRONES_DE_CLAVE = (
    ("clave de Anthropic", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("clave de OpenRouter", re.compile(r"sk-or-v1-[A-Za-z0-9]{20,}")),
    ("clave que empieza con sk-", re.compile(r"\bsk-[A-Za-z0-9]{32,}")),
    ("clave de AWS", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("token de GitHub", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}")),
    ("token de Slack", re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}")),
    ("clave privada", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
    (
        "contraseña escrita en el código",
        re.compile(
            r"""(?i)\b(?:password|passwd|secret|api_?key|token)\b\s*[=:]\s*["']([^"'\s]{8,})["']"""
        ),
    ),
)
_MARCAS_DE_EJEMPLO = ("xxx", "tu-", "tu_", "ejemplo", "example", "changeme", "***", "<", "{")

ARCHIVOS_SENSIBLES = (".env", ".env.*", "*.pem", "id_rsa", "id_ed25519", "*.p12", "*.pfx", ".netrc")
ARCHIVOS_DE_EJEMPLO = (".env.example", ".env.sample", ".env.template", ".env.dist")

CORREO = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
DOMINIOS_SIN_DATOS = {"example.com", "example.org", "example.net", "users.noreply.github.com"}
IDS_DE_EXTENSIONES_DE_GNOME = {"appindicatorsupport@rgcjonas.gmail.com"}
"""Parecen correos pero son el identificador de una extensión de GNOME (no son de una persona)."""
RUTA_PERSONAL = re.compile(r"/(?:home|Users)/([A-Za-z0-9._-]+)")
USUARIOS_DE_EJEMPLO = {"usuario", "user", "tu-usuario", "tu_usuario", "nombre", "tu", "tunombre"}

CERO = "0" * 40


@dataclass(frozen=True)
class Hallazgo:
    categoria: str
    ruta: str
    detalle: str
    commit: str = ""
    en_version_actual: bool = True


@dataclass
class Informe:
    repositorio: Path
    commits: int = 0
    archivos_revisados: int = 0
    hallazgos: list[Hallazgo] = field(default_factory=list)
    de_prueba: list[Hallazgo] = field(default_factory=list)

    def pendientes(self) -> list[Hallazgo]:
        return list(self.hallazgos)


# ---- git --------------------------------------------------


def _git(repo: Path, *args: str, entrada: bytes | None = None) -> bytes:
    resultado = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=repo,
        input=entrada,
        capture_output=True,
        check=True,
    )
    return resultado.stdout


def _es_un_repositorio(repo: Path) -> bool:
    try:
        _git(repo, "rev-parse", "--git-dir")
    except subprocess.CalledProcessError, FileNotFoundError:
        return False
    return True


def _tiene_commits(repo: Path) -> bool:
    return bool(_git(repo, "rev-list", "--all", "--max-count=1").strip())


def _blobs_del_historial(repo: Path) -> dict[tuple[str, str], str]:
    """``(sha del contenido, ruta)`` -> el commit más viejo donde apareció."""
    salida = _git(
        repo, "log", "--all", "--raw", "--no-abbrev", "--no-renames", "--format=COMMIT %H"
    )
    commit = ""
    primeros: dict[tuple[str, str], str] = {}
    for linea in salida.decode("utf-8", errors="replace").splitlines():
        if linea.startswith("COMMIT "):
            commit = linea[7:]
        elif linea.startswith(":"):
            cabecera, _, ruta = linea.partition("\t")
            sha = cabecera.split()[3]
            if sha != CERO:
                primeros[(sha, ruta)] = (
                    commit  # el log va del más nuevo al más viejo: gana el viejo
                )
    return primeros


def _tamanos(repo: Path, shas: list[str]) -> dict[str, int]:
    if not shas:
        return {}
    salida = _git(repo, "cat-file", "--batch-check", entrada="\n".join(shas).encode() + b"\n")
    tamanos: dict[str, int] = {}
    for linea in salida.decode().splitlines():
        partes = linea.split()
        if len(partes) == 3 and partes[1] == "blob":
            tamanos[partes[0]] = int(partes[2])
    return tamanos


def _contenidos(repo: Path, shas: list[str]) -> dict[str, bytes]:
    if not shas:
        return {}
    salida = _git(repo, "cat-file", "--batch", entrada="\n".join(shas).encode() + b"\n")
    contenidos: dict[str, bytes] = {}
    posicion = 0
    while posicion < len(salida):
        fin = salida.index(b"\n", posicion)
        sha, _tipo, tamano = salida[posicion:fin].decode().split()
        inicio = fin + 1
        contenidos[sha] = salida[inicio : inicio + int(tamano)]
        posicion = inicio + int(tamano) + 1
    return contenidos


def _version_actual(repo: Path) -> set[tuple[str, str]]:
    try:
        salida = _git(repo, "ls-tree", "-r", "HEAD")
    except subprocess.CalledProcessError:
        return set()
    actual = set()
    for linea in salida.decode("utf-8", errors="replace").splitlines():
        cabecera, _, ruta = linea.partition("\t")
        actual.add((cabecera.split()[2], ruta))
    return actual


# ---- qué buscar -------------------------------------------


def _es_de_pruebas(ruta: str) -> bool:
    return re.search(r"(^|/)tests?/", ruta) is not None


def _ocultar(secreto: str) -> str:
    return secreto[:13] + "…(ocultada)"


def _es_binario(contenido: bytes) -> bool:
    return b"\x00" in contenido[:8000]


def _correo_con_datos(correo: str, aceptados: set[str]) -> bool:
    local, _, dominio = correo.lower().partition("@")
    if correo.lower() in {a.lower() for a in aceptados} | IDS_DE_EXTENSIONES_DE_GNOME:
        return False
    if dominio in DOMINIOS_SIN_DATOS or dominio.endswith(".noreply.github.com"):
        return False
    return not (local.startswith(("noreply", "no-reply")) or local == "git")


def _revisar_nombre(ruta: str, tamano: int | None) -> list[tuple[str, str]]:
    """Lo que delata el nombre o el tamaño: ``[(categoria, detalle)]``."""
    nombre = ruta.rsplit("/", 1)[-1]
    sufijo = "." + nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    hallazgos: list[tuple[str, str]] = []
    if sufijo in EXTENSIONES_DE_AUDIO:
        hallazgos.append(("audio y modelos", "es un audio"))
    elif sufijo in EXTENSIONES_DE_MODELO:
        hallazgos.append(("audio y modelos", "parece un modelo"))
    elif tamano is not None and tamano > LIMITE_DE_TAMANO_MB * 1024 * 1024:
        hallazgos.append(
            ("audio y modelos", f"archivo grande ({tamano // (1024 * 1024)} MB): ¿audio o modelo?")
        )
    if nombre not in ARCHIVOS_DE_EJEMPLO and any(
        fnmatch.fnmatch(nombre, p) for p in ARCHIVOS_SENSIBLES
    ):
        hallazgos.append(("claves", "archivo de configuración con secretos"))
    return hallazgos


def _revisar_texto(texto: str, aceptados: set[str]) -> list[tuple[str, str]]:
    hallazgos: list[tuple[str, str]] = []
    conocidos: list[str] = []  # los secretos de formato conocido: el patrón genérico no los repite
    for nombre, patron in PATRONES_DE_CLAVE:
        for encontrado in patron.finditer(texto):
            secreto = encontrado.group(1) if encontrado.groups() else encontrado.group(0)
            if encontrado.groups():
                if any(m in secreto.lower() for m in _MARCAS_DE_EJEMPLO):
                    continue
                if any(secreto in c or c in secreto for c in conocidos):
                    continue
            else:
                conocidos.append(secreto)
            hallazgos.append(("claves", f"{nombre}: {_ocultar(secreto)}"))
    for correo in sorted(set(CORREO.findall(texto))):
        if _correo_con_datos(correo, aceptados):
            hallazgos.append(("datos personales", f"correo {correo}"))
    for usuario in sorted(set(RUTA_PERSONAL.findall(texto))):
        if usuario.lower() not in USUARIOS_DE_EJEMPLO:
            hallazgos.append(("datos personales", f"ruta con el usuario «{usuario}»"))
    return hallazgos


# ---- la revisión ------------------------------------------


def revisar(repo: Path, aceptar: set[str] | None = None) -> Informe:
    aceptados = aceptar or set()
    informe = Informe(repositorio=repo)
    vistos: set[tuple[str, str, str]] = set()

    def agregar(categoria: str, ruta: str, detalle: str, commit: str, actual: bool) -> None:
        clave = (categoria, ruta, detalle)
        if clave in vistos:
            return
        vistos.add(clave)
        hallazgo = Hallazgo(categoria, ruta, detalle, commit[:7], actual)
        pruebas = _es_de_pruebas(ruta) and categoria != "audio y modelos"
        (informe.de_prueba if pruebas else informe.hallazgos).append(hallazgo)

    if _tiene_commits(repo):
        informe.commits = int(_git(repo, "rev-list", "--all", "--count").strip())
        blobs = _blobs_del_historial(repo)
        actual = _version_actual(repo)
        unicos = sorted({sha for sha, _ in blobs})
        tamanos = _tamanos(repo, unicos)
        informe.archivos_revisados += len(unicos)
        a_leer = [s for s in unicos if tamanos.get(s, 0) <= LIMITE_PARA_LEER_BYTES]
        contenidos = _contenidos(repo, a_leer)
        for (sha, ruta), commit in sorted(blobs.items(), key=lambda x: x[0][1]):
            en_actual = (sha, ruta) in actual
            for categoria, detalle in _revisar_nombre(ruta, tamanos.get(sha)):
                agregar(categoria, ruta, detalle, commit, en_actual)
            contenido = contenidos.get(sha, b"")
            if contenido and not _es_binario(contenido):
                texto = contenido.decode("utf-8", errors="replace")
                for categoria, detalle in _revisar_texto(texto, aceptados):
                    agregar(categoria, ruta, detalle, commit, en_actual)
        _revisar_autores(repo, aceptados, informe, vistos)

    _revisar_carpeta_de_trabajo(repo, aceptados, informe, agregar)
    return informe


def _revisar_autores(
    repo: Path, aceptados: set[str], informe: Informe, vistos: set[tuple[str, str, str]]
) -> None:
    salida = _git(repo, "log", "--all", "--format=%ae%n%ce").decode("utf-8", errors="replace")
    cuenta: dict[str, int] = {}
    for correo in (c.strip() for c in salida.splitlines() if c.strip()):
        cuenta[correo] = cuenta.get(correo, 0) + 1
    for correo, veces in sorted(cuenta.items()):
        if _correo_con_datos(correo, aceptados):
            detalle = f"el correo {correo} firma {veces} registros de autoría de commits"
            vistos.add(("datos personales", "commits", detalle))
            informe.hallazgos.append(Hallazgo("datos personales", "commits", detalle))


def _revisar_carpeta_de_trabajo(
    repo: Path,
    aceptados: set[str],
    informe: Informe,
    agregar: Callable[[str, str, str, str, bool], None],
) -> None:
    """Lo que está sin confirmar todavía también se haría público al confirmarlo."""
    nuevos = _git(repo, "ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    modificados = _git(repo, "ls-files", "--modified", "-z").split(b"\0") if informe.commits else []
    for bruto in sorted({n for n in nuevos + modificados if n}):
        ruta = bruto.decode("utf-8", errors="replace")
        archivo = repo / ruta
        if not archivo.is_file():
            continue
        informe.archivos_revisados += 1
        tamano = archivo.stat().st_size
        for categoria, detalle in _revisar_nombre(ruta, tamano):
            agregar(categoria, ruta, detalle, "", True)
        if tamano <= LIMITE_PARA_LEER_BYTES:
            contenido = archivo.read_bytes()
            if not _es_binario(contenido):
                for categoria, detalle in _revisar_texto(
                    contenido.decode("utf-8", errors="replace"), aceptados
                ):
                    agregar(categoria, ruta, detalle, "", True)


# ---- el informe -------------------------------------------


def _linea(h: Hallazgo) -> str:
    donde = f"`{h.ruta}`" + (f" (commit {h.commit})" if h.commit else " (sin confirmar todavía)")
    extra = ""
    if not h.en_version_actual:
        extra = (
            " — ya no está en la versión actual, pero sigue en el historial: para sacarlo hay que "
            "reescribir el historial (y, si es una clave, cambiarla)"
        )
    return f"- {donde}: {h.detalle}{extra}"


def formatear(informe: Informe) -> str:
    lineas = [
        "# Revisión previa a publicar",
        "",
        f"Repositorio: {informe.repositorio} · {informe.commits} commits · "
        f"{informe.archivos_revisados} archivos distintos revisados",
        "",
    ]
    for titulo, categoria in (
        ("Claves", "claves"),
        ("Audio y modelos", "audio y modelos"),
        ("Datos personales", "datos personales"),
    ):
        encontrados = [h for h in informe.hallazgos if h.categoria == categoria]
        lineas.append(f"## {titulo}")
        lineas.append("")
        if encontrados:
            lineas.append(f"✗ {len(encontrados)} hallazgo(s) sin resolver:")
            lineas += [_linea(h) for h in encontrados]
        else:
            lineas.append("✓ No encontré nada.")
        lineas.append("")
    if informe.de_prueba:
        lineas += ["## Datos de prueba (informativo, no bloquea)", ""]
        lineas += [_linea(h) for h in informe.de_prueba]
        lineas.append("")
    lineas.append("## Resultado")
    lineas.append("")
    if informe.hallazgos:
        lineas.append(
            "**NO PUBLICAR TODAVÍA**: resolvé lo de arriba (o aceptalo con `--aceptar CORREO` "
            "si es una decisión tuya) y volvé a correr la revisión."
        )
    else:
        lineas.append(
            "**LISTO PARA PUBLICAR** (cuando vos lo decidas: esta revisión no publica nada)."
        )
    lineas.append("")
    return "\n".join(lineas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Revisión previa a publicar el repositorio.")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="carpeta del repositorio")
    parser.add_argument(
        "--aceptar",
        action="append",
        default=[],
        metavar="CORREO",
        help="un correo que sabés que va a quedar público (se puede repetir)",
    )
    argumentos = parser.parse_args(argv)
    repo = argumentos.repo.resolve()
    if not _es_un_repositorio(repo):
        print(f"{repo} no es un repositorio de git.")
        return 2
    informe = revisar(repo, aceptar=set(argumentos.aceptar))
    print(formatear(informe))
    return 1 if informe.hallazgos else 0


if __name__ == "__main__":
    sys.exit(main())
