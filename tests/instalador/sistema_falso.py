"""Un «sistema» de mentira para correr ``scripts/instalar.sh`` y ``desinstalar.sh`` sin tocar el real.

Los programas que cambian el sistema (``sudo``, ``dnf``, ``apt-get``, ``usermod``, ``uv``, ``git``,
``curl``…) son guiones que solo anotan en un registro lo que les pidieron. El resto (bash, awk, grep,
tee…) es el de verdad.
"""

import subprocess
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
INSTALAR = RAIZ / "scripts" / "instalar.sh"
DESINSTALAR = RAIZ / "scripts" / "desinstalar.sh"

_REGISTRADORES = (
    "dnf", "apt-get", "usermod", "gpasswd", "modprobe", "udevadm", "update-desktop-database", "gtk-update-icon-cache",
)  # fmt: skip


class SistemaFalso:
    def __init__(
        self, tmp: Path, os_release: str = 'ID=fedora\nPRETTY_NAME="Fedora Linux 44"\n'
    ) -> None:
        self.tmp = tmp
        self.home = tmp / "home"
        self.bin = tmp / "bin"
        self.udev = tmp / "udev"
        self.modulos = tmp / "modulos"
        self.registro = tmp / "registro.txt"
        self.entrada = tmp / "entrada.txt"
        self.os_release = tmp / "os-release"
        self.os_release.write_text(os_release, encoding="utf-8")
        for carpeta in (self.home, self.bin):
            carpeta.mkdir(parents=True)
        self.registro.write_text("", encoding="utf-8")
        self.entrada.write_text("", encoding="utf-8")
        self.con_uv = True
        self._escribir_programas()

    # ---- los programas de mentira ----

    def _guion(self, nombre: str, cuerpo: str) -> None:
        ruta = self.bin / nombre
        ruta.write_text(f"#!/usr/bin/env bash\n{cuerpo}\n", encoding="utf-8")
        ruta.chmod(0o755)

    def _escribir_programas(self) -> None:
        anotar = f'echo "$(basename "$0") $*" >> "{self.registro}"'
        for nombre in _REGISTRADORES:
            self._guion(nombre, f"{anotar}\nexit 0")
        self._guion("sudo", f'echo "sudo" >> "{self.registro}"\nexec "$@"')
        self._guion(
            "git",
            f'{anotar}\nif [ "$1" = clone ]; then mkdir -p "${{@: -1}}/.git" "${{@: -1}}/scripts"; '
            f'printf \'[project]\\nname = "vozflow"\\n\' > "${{@: -1}}/pyproject.toml"; fi\nexit 0',
        )
        self._guion(
            "curl",
            f"""{anotar}
cat <<'FIN'
mkdir -p "$HOME/.local/bin"
cat > "$HOME/.local/bin/uv" <<'UV'
#!/usr/bin/env bash
echo "uv $*" >> {self.registro}
UV
chmod +x "$HOME/.local/bin/uv"
FIN""",
        )
        self._guion("uv", self._cuerpo_de_uv(anotar))
        self.bin_uv = self.bin / "uv"

    def _cuerpo_de_uv(self, anotar: str) -> str:
        return (
            f"{anotar}\n"
            'case "$*" in\n'
            '  *descargar-modelo*) [ -n "${FALLA_EL_MODELO:-}" ] && exit 1 ;;\n'
            '  *sync*) [ -n "${FALLA_EL_SYNC:-}" ] && exit 1 ;;\n'
            "esac\nexit 0"
        )

    def sin_uv(self) -> None:
        self.bin_uv.unlink()
        self.con_uv = False

    def responder(self, *respuestas: str) -> None:
        self.entrada.write_text("".join(f"{r}\n" for r in respuestas), encoding="utf-8")

    # ---- correr ----

    def entorno(self, **extra: str) -> dict[str, str]:
        entorno = {
            "PATH": f"{self.bin}:/usr/bin:/bin",
            "HOME": str(self.home),
            "USER": "prueba",
            "XDG_CURRENT_DESKTOP": "GNOME",
            "XDG_SESSION_TYPE": "wayland",
            "XDG_DATA_HOME": str(self.home / ".local" / "share"),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "VOZFLOW_OS_RELEASE": str(self.os_release),
            "VOZFLOW_UDEV_DIR": str(self.udev),
            "VOZFLOW_MODULOS_DIR": str(self.modulos),
            "VOZFLOW_ESPACIO_LIBRE_MB": "50000",
            "VOZFLOW_MEMORIA_MB": "8000",
            "VOZFLOW_GRUPOS_ACTIVOS": "prueba input",
            "VOZFLOW_ENTRADA": str(self.entrada),
            "VOZFLOW_SIN_PREGUNTAS": "1",
            "LANG": "C.UTF-8",
        }
        entorno.update(extra)
        return {k: v for k, v in entorno.items() if v != ""}

    def correr(self, script: Path = INSTALAR, /, **extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["/bin/bash", str(script)],
            env=self.entorno(**extra),
            capture_output=True,
            text=True,
            timeout=60,
            cwd=self.tmp,
            check=False,
        )

    # ---- lo que quedó ----

    def lineas_del_registro(self) -> list[str]:
        return [linea for linea in self.registro.read_text(encoding="utf-8").splitlines() if linea]

    def llamadas(self, programa: str) -> list[str]:
        return [linea for linea in self.lineas_del_registro() if linea.split(" ", 1)[0] == programa]

    def archivos_nuevos(self) -> list[str]:
        """Todo lo que hay en el hogar y en las carpetas de sistema de mentira."""
        encontrados: list[str] = []
        for base in (self.home, self.udev, self.modulos):
            if base.exists():
                encontrados += [str(p.relative_to(self.tmp)) for p in sorted(base.rglob("*"))]
        return encontrados


def fedora() -> str:
    return 'ID=fedora\nPRETTY_NAME="Fedora Linux 44"\n'


def ubuntu() -> str:
    return 'ID=ubuntu\nID_LIKE=debian\nPRETTY_NAME="Ubuntu 24.04"\n'
