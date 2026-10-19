"""``diagnostico --copiable``: Markdown para pegar en un reporte, sin nada personal (RP-024)."""

from vozflow.diagnostico import DatosCopiables, formatear_copiable

BASE = DatosCopiables(
    version_de_vozflow="0.1.0",
    version_de_python="3.14.8",
    sistema="Fedora Linux 44",
    gnome="50",
    sesion="wayland",
    puede_leer_teclados=True,
    puede_escribir_uinput=True,
    tiene_portapapeles=True,
    microfonos=1,
    modelo="small",
    historial_activo=True,
    reescritura_activa=False,
)


def _con(**cambios: object) -> DatosCopiables:
    return DatosCopiables(**{**BASE.__dict__, **cambios})


def test_el_formato_es_el_del_contrato() -> None:
    texto = formatear_copiable(BASE)

    assert texto.splitlines()[0] == (
        "**vozflow** 0.1.0 · **Python** 3.14.8 · **Sistema** Fedora Linux 44 · **GNOME** 50 · "
        "**Sesión** wayland"
    )
    assert "| Permiso | Estado |" in texto
    assert "| Leer el teclado | bien |" in texto
    assert "| Teclado virtual | bien |" in texto
    assert "| Copiar y pegar | bien |" in texto
    assert "| Micrófono | 1 dispositivo |" in texto
    assert "Modelo de voz: instalado (small) · Historial: activado · Reescritura: apagada" in texto


def test_lo_que_falta_se_dice_con_palabras_llanas() -> None:
    texto = formatear_copiable(
        _con(puede_leer_teclados=False, tiene_portapapeles=False, microfonos=0, modelo=None)
    )

    assert "| Leer el teclado | falta |" in texto
    assert "| Copiar y pegar | falta |" in texto
    assert "| Micrófono | ninguno |" in texto
    assert "Modelo de voz: sin descargar" in texto


def test_varios_microfonos_se_cuentan_en_plural() -> None:
    assert "| Micrófono | 3 dispositivos |" in formatear_copiable(_con(microfonos=3))


def test_historial_apagado_y_reescritura_activa() -> None:
    texto = formatear_copiable(_con(historial_activo=False, reescritura_activa=True))

    assert "Historial: apagado" in texto and "Reescritura: activada" in texto


def test_el_hogar_y_el_usuario_nunca_salen() -> None:
    texto = formatear_copiable(
        _con(sistema="Fedora en /home/marta/trabajo"), hogar="/home/marta", usuario="marta"
    )

    assert "/home/marta" not in texto and "marta" not in texto
    assert "~/trabajo" in texto


def test_el_usuario_suelto_tambien_se_oculta() -> None:
    texto = formatear_copiable(
        _con(sistema="equipo de marta"), hogar="/home/marta", usuario="marta"
    )

    assert "marta" not in texto


def test_un_usuario_corto_no_rompe_palabras_ajenas() -> None:
    texto = formatear_copiable(BASE, hogar="/home/a", usuario="a")

    assert "vozflow" in texto and "Python" in texto


def test_la_salida_no_tiene_campos_para_texto_dictado_ni_ventanas_ni_claves() -> None:
    campos = set(DatosCopiables.__dataclass_fields__)

    assert not [c for c in campos if any(p in c for p in ("texto", "ventana", "clave", "titulo"))]


def test_la_recoleccion_real_nunca_incluye_nombres_de_dispositivos() -> None:
    from vozflow.diagnostico import reunir_datos_copiables

    class Entorno:
        def os_release(self) -> str:
            return 'PRETTY_NAME="Fedora Linux 44"\n'

        def gnome(self) -> str:
            return "50"

        def sesion(self) -> str:
            return "wayland"

        def nombres_de_microfonos(self) -> list[str]:
            return ["AirPods de Marta", "Micrófono interno"]

        def modelo_instalado(self) -> str | None:
            return "small"

        def historial_activo(self) -> bool:
            return True

        def reescritura_activa(self) -> bool:
            return False

        def puede_leer_teclados(self) -> bool:
            return True

        def puede_escribir_uinput(self) -> bool:
            return True

        def tiene_portapapeles(self) -> bool:
            return True

    datos = reunir_datos_copiables(Entorno())
    texto = formatear_copiable(datos)

    assert datos.microfonos == 2 and datos.sistema == "Fedora Linux 44"
    assert "AirPods" not in texto and "Marta" not in texto


def test_con_la_recoleccion_rota_no_se_cae() -> None:
    from vozflow.diagnostico import reunir_datos_copiables

    class Roto:
        def __getattr__(self, nombre: str):  # type: ignore[no-untyped-def]
            def falla() -> object:
                raise OSError("sin acceso")

            return falla

    texto = formatear_copiable(reunir_datos_copiables(Roto()))

    assert "**vozflow**" in texto and "desconocido" in texto
