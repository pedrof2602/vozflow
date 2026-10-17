"""``diagnostico``: qué tiene este escritorio para atajos e inserción."""

import pytest

from vozflow.diagnostico import Comprobacion, Sondas, ejecutar_diagnostico, formatear


def _sondas(**cambios: object) -> Sondas:
    base: dict[str, object] = {
        "version_de_portal": lambda interfaz: 2,
        "puede_leer_teclados": lambda: True,
        "puede_escribir_uinput": lambda: True,
        "ydotoold_corre": lambda: True,
        "programa_instalado": lambda nombre: True,
        "consultar_ventana": lambda: (True, 120),
    }
    base.update(cambios)
    return Sondas(**base)  # type: ignore[arg-type]


def _por_nombre(resultado: list[Comprobacion]) -> dict[str, Comprobacion]:
    return {c.nombre: c for c in resultado}


def test_informa_cada_portal_con_su_version() -> None:
    resultado = _por_nombre(ejecutar_diagnostico(_sondas(version_de_portal=lambda i: 3)))

    for portal in ("GlobalShortcuts", "RemoteDesktop", "Clipboard"):
        assert resultado[f"Portal {portal}"].ok is True
        assert "versión 3" in resultado[f"Portal {portal}"].detalle


def test_un_portal_que_no_responde_se_marca_como_ausente() -> None:
    resultado = _por_nombre(
        ejecutar_diagnostico(_sondas(version_de_portal=lambda i: 0 if "Clipboard" in i else 1))
    )

    assert resultado["Portal Clipboard"].ok is False
    assert resultado["Portal RemoteDesktop"].ok is True


def test_si_el_bus_falla_no_se_cae_y_lo_dice() -> None:
    def roto(interfaz: str) -> int:
        raise OSError("sin bus de sesión")

    resultado = _por_nombre(ejecutar_diagnostico(_sondas(version_de_portal=roto)))

    assert resultado["Portal RemoteDesktop"].ok is False
    assert "sin bus" in resultado["Portal RemoteDesktop"].detalle


@pytest.mark.parametrize(
    ("sonda", "nombre"),
    [
        ("puede_leer_teclados", "Lectura de /dev/input"),
        ("puede_escribir_uinput", "Escritura en /dev/uinput"),
        ("ydotoold_corre", "ydotoold"),
    ],
)
def test_cada_acceso_se_marca_segun_su_sonda(sonda: str, nombre: str) -> None:
    bien = _por_nombre(ejecutar_diagnostico(_sondas(**{sonda: lambda: True})))
    mal = _por_nombre(ejecutar_diagnostico(_sondas(**{sonda: lambda: False})))

    assert bien[nombre].ok is True and mal[nombre].ok is False


def test_un_acceso_que_falta_explica_como_arreglarlo() -> None:
    resultado = _por_nombre(ejecutar_diagnostico(_sondas(puede_leer_teclados=lambda: False)))

    assert "input" in resultado["Lectura de /dev/input"].detalle


def test_revisa_que_esten_los_programas_necesarios() -> None:
    resultado = _por_nombre(
        ejecutar_diagnostico(_sondas(programa_instalado=lambda nombre: nombre != "wl-copy"))
    )

    assert resultado["Programa wl-copy"].ok is False
    assert resultado["Programa gsettings"].ok is True


def test_el_ayudante_de_ventana_informa_cuanto_tarda() -> None:
    resultado = _por_nombre(ejecutar_diagnostico(_sondas(consultar_ventana=lambda: (True, 340))))

    assert resultado["Ventana activa (AT-SPI)"].ok is True
    assert "340 ms" in resultado["Ventana activa (AT-SPI)"].detalle


def test_sin_ventana_identificada_no_es_una_falla_pero_se_dice() -> None:
    resultado = _por_nombre(ejecutar_diagnostico(_sondas(consultar_ventana=lambda: (False, 90))))

    assert "no identificó" in resultado["Ventana activa (AT-SPI)"].detalle


def test_un_informe_nunca_incluye_el_nombre_ni_el_titulo_de_la_ventana() -> None:
    informe = formatear(ejecutar_diagnostico(_sondas()))

    assert "ptyxis" not in informe.lower()


def test_el_informe_marca_cada_linea_con_ok_o_falta() -> None:
    informe = formatear([Comprobacion("Uno", True, "bien"), Comprobacion("Dos", False, "mal")])

    assert "✓" in informe.splitlines()[0] and "✗" in informe.splitlines()[1]
