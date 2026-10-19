"""La revisión previa a publicar: claves, audios, modelos y datos personales (002, RP-028, RP-029)."""

import importlib.util
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

RAIZ = Path(__file__).resolve().parents[2]
SCRIPT = RAIZ / "scripts" / "revisar_publicacion.py"

CLAVE_REAL = "sk-ant-api03-" + "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
CLAVE_ENMASCARADA = "sk-ant-api03-"


def _modulo() -> ModuleType:
    especificacion = importlib.util.spec_from_file_location("revisar_publicacion", SCRIPT)
    assert especificacion and especificacion.loader
    modulo = importlib.util.module_from_spec(especificacion)
    sys.modules["revisar_publicacion"] = modulo
    especificacion.loader.exec_module(modulo)
    return modulo


class Repo:
    """Un repositorio git de mentira, con historial armado a mano."""

    def __init__(self, carpeta: Path) -> None:
        self.carpeta = carpeta
        carpeta.mkdir(parents=True, exist_ok=True)
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, correo: str = "autor@users.noreply.github.com") -> str:
        entorno = {
            **os.environ,
            "GIT_AUTHOR_NAME": "Autor",
            "GIT_AUTHOR_EMAIL": correo,
            "GIT_COMMITTER_NAME": "Autor",
            "GIT_COMMITTER_EMAIL": correo,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        }
        resultado = subprocess.run(
            ["git", *args],
            cwd=self.carpeta,
            env=entorno,
            capture_output=True,
            text=True,
            check=True,
        )
        return resultado.stdout

    def archivo(self, ruta: str, contenido: str | bytes) -> None:
        destino = self.carpeta / ruta
        destino.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contenido, str):
            destino.write_text(contenido, encoding="utf-8")
        else:
            destino.write_bytes(contenido)

    def confirmar(
        self, mensaje: str = "cambio", correo: str = "autor@users.noreply.github.com"
    ) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", mensaje, correo=correo)

    def borrar(self, ruta: str) -> None:
        (self.carpeta / ruta).unlink()
        self.confirmar(f"borra {ruta}")


@pytest.fixture
def repo(tmp_path: Path) -> Repo:
    r = Repo(tmp_path / "repo")
    r.archivo("README.md", "# Un proyecto\n")
    r.archivo("src/app.py", "print('hola')\n")
    r.confirmar("inicio")
    return r


def _revisar(repo: Repo, *aceptar: str):  # type: ignore[no-untyped-def]
    return _modulo().revisar(repo.carpeta, aceptar=set(aceptar))


def _correr(repo: Repo, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(repo.carpeta), *args],
        capture_output=True,
        text=True,
        check=False,
    )


# ---- un repositorio limpio -----------------------------------------------------------------------------------


def test_un_repositorio_limpio_no_tiene_nada_sin_resolver(repo: Repo) -> None:
    informe = _revisar(repo)

    assert informe.pendientes() == []


def test_el_comando_sale_con_0_si_esta_limpio_y_dice_listo(repo: Repo) -> None:
    resultado = _correr(repo)

    assert resultado.returncode == 0, resultado.stdout
    assert "LISTO PARA PUBLICAR" in resultado.stdout


def test_el_informe_tiene_una_seccion_por_categoria(repo: Repo) -> None:
    salida = _correr(repo).stdout

    for titulo in ("## Claves", "## Audio y modelos", "## Datos personales"):
        assert titulo in salida


def test_un_repositorio_sin_commits_no_rompe(tmp_path: Path) -> None:
    vacio = Repo(tmp_path / "vacio")

    resultado = _correr(vacio)

    assert resultado.returncode == 0 and "0 commits" in resultado.stdout


# ---- claves ------------------------------------------------------------------------------------------------


def test_encuentra_una_clave_aunque_se_haya_borrado_despues(repo: Repo) -> None:
    repo.archivo("config.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.confirmar("agrega la clave")
    repo.borrar("config.py")

    informe = _revisar(repo)

    claves = [h for h in informe.pendientes() if h.categoria == "claves"]
    assert len(claves) == 1 and claves[0].ruta == "config.py"
    assert claves[0].commit  # en qué commit entró


def test_el_informe_nunca_muestra_la_clave_completa(repo: Repo) -> None:
    repo.archivo("config.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.confirmar("agrega la clave")

    resultado = _correr(repo)

    assert resultado.returncode == 1
    assert CLAVE_REAL not in resultado.stdout and CLAVE_ENMASCARADA in resultado.stdout


def test_avisa_que_una_clave_ya_borrada_igual_esta_en_el_historial(repo: Repo) -> None:
    repo.archivo("config.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.confirmar("agrega la clave")
    repo.borrar("config.py")

    salida = _correr(repo).stdout

    assert "ya no está en la versión actual" in salida and "reescribir el historial" in salida


def test_una_clave_en_pruebas_se_informa_pero_no_bloquea(repo: Repo) -> None:
    repo.archivo("tests/test_clave.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.confirmar("prueba")

    informe = _revisar(repo)

    assert informe.pendientes() == []
    assert [h.ruta for h in informe.de_prueba] == ["tests/test_clave.py"]


def test_una_clave_en_pruebas_y_tambien_fuera_de_ellas_bloquea(repo: Repo) -> None:
    repo.archivo("tests/test_clave.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.archivo("src/usa.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.confirmar("las dos")

    assert [h.ruta for h in _revisar(repo).pendientes()] == ["src/usa.py"]


@pytest.mark.parametrize(
    "texto",
    [
        'token = "ghp_' + "a" * 36 + '"',
        "AKIAIOSFODNN7EXAMPLE",
        "sk-or-v1-" + "a1b2c3d4" * 4,
        "-----BEGIN RSA PRIVATE KEY-----\nMIIE...\n-----END RSA PRIVATE KEY-----",
        'password = "correcto-caballo-bateria"',
    ],
)
def test_reconoce_otros_tipos_de_secretos(repo: Repo, texto: str) -> None:
    repo.archivo("algo.txt", texto + "\n")
    repo.confirmar("secreto")

    assert [h.categoria for h in _revisar(repo).pendientes()] == ["claves"]


def test_un_archivo_env_se_marca_aunque_este_vacio_de_patrones(repo: Repo) -> None:
    repo.archivo(".env", "ALGO=1\n")
    repo.confirmar("env")

    assert [h.ruta for h in _revisar(repo).pendientes()] == [".env"]


def test_un_ejemplo_de_env_no_se_marca(repo: Repo) -> None:
    repo.archivo(".env.example", "ALGO=\n")
    repo.confirmar("ejemplo")

    assert _revisar(repo).pendientes() == []


def test_un_secreto_solo_en_otra_rama_tambien_se_encuentra(repo: Repo) -> None:
    repo.git("checkout", "-q", "-b", "otra")
    repo.archivo("config.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.confirmar("en otra rama")
    repo.git("checkout", "-q", "main")

    assert [h.categoria for h in _revisar(repo).pendientes()] == ["claves"]


def test_un_secreto_sin_commitear_tambien_se_encuentra(repo: Repo) -> None:
    repo.archivo("nuevo.py", f'CLAVE = "{CLAVE_REAL}"\n')

    assert [h.ruta for h in _revisar(repo).pendientes()] == ["nuevo.py"]


def test_un_archivo_ignorado_por_git_no_se_cuenta(repo: Repo) -> None:
    repo.archivo(".gitignore", "secreto.txt\n")
    repo.confirmar("ignora")
    repo.archivo("secreto.txt", f'CLAVE = "{CLAVE_REAL}"\n')

    assert _revisar(repo).pendientes() == []


# ---- audio y modelos ------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "nombre", ["voz.wav", "nota.mp3", "x/y/clip.flac", "audio.ogg", "grabacion.m4a"]
)
def test_encuentra_audios_por_la_extension(repo: Repo, nombre: str) -> None:
    repo.archivo(nombre, b"RIFF....")
    repo.confirmar("audio")

    assert [h.categoria for h in _revisar(repo).pendientes()] == ["audio y modelos"]


@pytest.mark.parametrize("nombre", ["model.bin", "pesos.onnx", "x.safetensors", "m.gguf", "w.pt"])
def test_encuentra_modelos_por_la_extension(repo: Repo, nombre: str) -> None:
    repo.archivo(nombre, b"\x00\x01\x02")
    repo.confirmar("modelo")

    assert [h.categoria for h in _revisar(repo).pendientes()] == ["audio y modelos"]


def test_encuentra_un_archivo_grande_aunque_tenga_otro_nombre(repo: Repo) -> None:
    repo.archivo("datos.dat", os.urandom(6 * 1024 * 1024))
    repo.confirmar("grande")

    hallazgos = _revisar(repo).pendientes()

    assert [h.categoria for h in hallazgos] == ["audio y modelos"]
    assert "MB" in hallazgos[0].detalle


def test_un_audio_borrado_despues_igual_esta_en_el_historial(repo: Repo) -> None:
    repo.archivo("voz.wav", b"RIFF....")
    repo.confirmar("audio")
    repo.borrar("voz.wav")

    assert [h.ruta for h in _revisar(repo).pendientes()] == ["voz.wav"]


# ---- datos personales ----------------------------------------------------------------------------------------


def test_encuentra_un_correo_en_un_archivo(repo: Repo) -> None:
    repo.archivo("docs/contacto.md", "Escribime a marta.gomez@gmail.com\n")
    repo.confirmar("contacto")

    hallazgos = _revisar(repo).pendientes()

    assert [(h.categoria, h.ruta) for h in hallazgos] == [("datos personales", "docs/contacto.md")]


def test_un_correo_aceptado_no_se_marca(repo: Repo) -> None:
    repo.archivo("docs/contacto.md", "Escribime a marta.gomez@gmail.com\n")
    repo.confirmar("contacto")

    assert _revisar(repo, "marta.gomez@gmail.com").pendientes() == []


@pytest.mark.parametrize(
    "correo",
    ["noreply@anthropic.com", "alguien@example.com", "12345+marta@users.noreply.github.com"],
)
def test_los_correos_de_mentira_o_sin_datos_no_se_marcan(repo: Repo, correo: str) -> None:
    repo.archivo("docs/x.md", f"{correo}\n")
    repo.confirmar("x")

    assert _revisar(repo).pendientes() == []


def test_encuentra_una_ruta_con_el_nombre_de_usuario(repo: Repo) -> None:
    repo.archivo("docs/guia.md", "Está en /home/marta/proyectos/app\n")
    repo.confirmar("guia")

    assert [h.categoria for h in _revisar(repo).pendientes()] == ["datos personales"]


@pytest.mark.parametrize(
    "ruta",
    [
        "/home/usuario/x",
        "/home/tu-usuario/x",
        "/home/nombre/x",
        "/home/$USER/x",
        "/Users/usuario/x",
    ],
)
def test_las_rutas_de_ejemplo_no_se_marcan(repo: Repo, ruta: str) -> None:
    repo.archivo("docs/guia.md", f"{ruta}\n")
    repo.confirmar("guia")

    assert _revisar(repo).pendientes() == []


def test_marca_el_correo_personal_de_los_autores_de_los_commits(repo: Repo) -> None:
    repo.archivo("a.txt", "a\n")
    repo.confirmar("personal", correo="marta@gmail.com")

    hallazgos = _revisar(repo).pendientes()

    assert [(h.categoria, h.ruta) for h in hallazgos] == [("datos personales", "commits")]
    assert "marta@gmail.com" in hallazgos[0].detalle


def test_el_correo_noreply_de_github_esta_bien_como_autor(repo: Repo) -> None:
    repo.archivo("a.txt", "a\n")
    repo.confirmar("ok", correo="123+marta@users.noreply.github.com")

    assert _revisar(repo).pendientes() == []


def test_un_autor_aceptado_no_se_marca(repo: Repo) -> None:
    repo.archivo("a.txt", "a\n")
    repo.confirmar("personal", correo="marta@gmail.com")

    assert _revisar(repo, "marta@gmail.com").pendientes() == []


def test_los_correos_de_pruebas_se_informan_aparte(repo: Repo) -> None:
    repo.archivo("tests/test_x.py", 'CORREO = "juan.perez@gmail.com"\n')
    repo.confirmar("prueba")

    informe = _revisar(repo)

    assert informe.pendientes() == [] and len(informe.de_prueba) == 1


# ---- el comando ---------------------------------------------------------------------------------------------


def test_con_pendientes_sale_con_1_y_dice_que_no_publique(repo: Repo) -> None:
    repo.archivo("voz.wav", b"RIFF....")
    repo.confirmar("audio")

    resultado = _correr(repo)

    assert resultado.returncode == 1 and "NO PUBLICAR TODAVÍA" in resultado.stdout


def test_la_opcion_aceptar_se_puede_repetir(repo: Repo) -> None:
    repo.archivo("docs/x.md", "a@gmail.com y b@gmail.com\n")
    repo.confirmar("dos")

    resultado = _correr(repo, "--aceptar", "a@gmail.com", "--aceptar", "b@gmail.com")

    assert resultado.returncode == 0


def test_la_revision_no_cambia_nada_del_repositorio(repo: Repo) -> None:
    repo.archivo("voz.wav", b"RIFF....")
    repo.archivo("config.py", f'CLAVE = "{CLAVE_REAL}"\n')
    repo.confirmar("cosas")
    antes = (
        repo.git("rev-parse", "HEAD"),
        repo.git("status", "--porcelain"),
        sorted(p.name for p in repo.carpeta.iterdir()),
    )

    _correr(repo)

    despues = (
        repo.git("rev-parse", "HEAD"),
        repo.git("status", "--porcelain"),
        sorted(p.name for p in repo.carpeta.iterdir()),
    )
    assert antes == despues


def test_no_publica_nada_ni_toca_la_red() -> None:
    codigo = SCRIPT.read_text(encoding="utf-8")

    for prohibido in (
        "push",
        "gh repo",
        "visibility",
        "requests",
        "urllib",
        "http.client",
        "socket",
    ):
        assert prohibido not in codigo, prohibido


def test_un_archivo_con_bytes_raros_no_rompe_la_revision(repo: Repo) -> None:
    repo.archivo("latin.txt", "caf\xe9 ni\xf1o\n".encode("latin-1"))
    repo.confirmar("latin1")

    assert _revisar(repo).pendientes() == []


def test_el_informe_es_markdown_con_el_resumen_al_principio(repo: Repo) -> None:
    salida = _correr(repo).stdout

    assert salida.startswith("# Revisión previa a publicar")
    assert "commits" in salida.splitlines()[2]


def test_el_script_revisa_el_repositorio_actual_por_defecto(repo: Repo) -> None:
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=repo.carpeta, capture_output=True, text=True, check=False
    )

    assert resultado.returncode == 0 and "LISTO PARA PUBLICAR" in resultado.stdout


def test_si_no_es_un_repositorio_lo_explica(tmp_path: Path) -> None:
    resultado = subprocess.run(
        [sys.executable, str(SCRIPT), "--repo", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 2 and "no es un repositorio" in resultado.stdout.lower()


def test_el_id_de_una_extension_de_gnome_no_es_un_correo_personal(repo: Repo) -> None:
    repo.archivo("README.md", "gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com\n")
    repo.confirmar("extension")

    assert _revisar(repo).pendientes() == []


def test_un_correo_de_ejemplo_en_espanol_no_se_marca(repo: Repo) -> None:
    repo.archivo("docs/x.md", "tu-correo@ejemplo.com\n")
    repo.confirmar("x")

    assert _revisar(repo).pendientes() == []


def test_el_hallazgo_de_los_autores_no_dice_sin_confirmar(repo: Repo) -> None:
    repo.archivo("a.txt", "a\n")
    repo.confirmar("personal", correo="marta@gmail.com")

    salida = _correr(repo).stdout

    assert "`commits`:" in salida and "sin confirmar" not in salida
