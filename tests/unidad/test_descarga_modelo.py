"""Descarga del modelo de voz con progreso (002, RP-004): se ve el avance y se puede repetir."""

from collections.abc import Callable
from typing import Any

import pytest

from vozflow.transcripcion.faster_whisper import descargar_modelo
from vozflow.transcripcion.motor import ErrorDeTranscripcion


class SnapshotFalso:
    """Hace de ``huggingface_hub.snapshot_download``: crea las barras que se le piden y avanza."""

    def __init__(
        self,
        archivos: tuple[int, ...] = (1_000, 480_000),
        falla_tras: int | None = None,
        error: Exception | None = None,
    ) -> None:
        self.archivos = archivos
        self.falla_tras = falla_tras
        self.error = error
        self.llamadas: list[dict[str, Any]] = []

    def __call__(self, repo_id: str, **kwargs: Any) -> str:
        self.llamadas.append({"repo_id": repo_id, **kwargs})
        if self.error is not None and self.falla_tras is None:
            raise self.error
        clase = kwargs["tqdm_class"]
        # la barra de «archivos» (unidad «it») no son bytes y no debe contarse
        general = clase(total=len(self.archivos), unit="it")
        hechos = 0
        for tamano in self.archivos:
            barra = clase(total=tamano, unit="B", unit_scale=True)
            for _ in range(4):
                barra.update(tamano // 4)
                hechos += tamano // 4
                if self.falla_tras is not None and hechos >= self.falla_tras:
                    raise self.error or OSError("se cortó")
            barra.close()
            general.update(1)
        return f"/cache/{repo_id}"


def _avances() -> tuple[list[tuple[int, int]], Callable[[int, int], None]]:
    registro: list[tuple[int, int]] = []
    return registro, lambda hechos, total: registro.append((hechos, total))


def test_devuelve_la_carpeta_del_modelo() -> None:
    carpeta = descargar_modelo("small", snapshot=SnapshotFalso(), tamano_total=lambda r: 481_000)

    assert carpeta == "/cache/Systran/faster-whisper-small"


def test_pide_solo_los_archivos_del_modelo_a_su_repositorio() -> None:
    snapshot = SnapshotFalso()

    descargar_modelo("small", snapshot=snapshot, tamano_total=lambda r: 481_000)

    llamada = snapshot.llamadas[0]
    assert llamada["repo_id"] == "Systran/faster-whisper-small"
    assert "model.bin" in llamada["allow_patterns"] and "config.json" in llamada["allow_patterns"]


def test_un_identificador_de_repositorio_se_usa_tal_cual() -> None:
    snapshot = SnapshotFalso()

    descargar_modelo("otro/modelo-propio", snapshot=snapshot, tamano_total=lambda r: 481_000)

    assert snapshot.llamadas[0]["repo_id"] == "otro/modelo-propio"


def test_el_avance_crece_y_termina_en_el_total() -> None:
    registro, al_avance = _avances()

    descargar_modelo("small", al_avance, snapshot=SnapshotFalso(), tamano_total=lambda r: 481_000)

    hechos = [h for h, _ in registro]
    assert hechos == sorted(hechos) and hechos[-1] == 481_000
    assert registro[-1] == (481_000, 481_000)
    assert all(total == 481_000 for _, total in registro)


def test_solo_se_cuentan_los_bytes_no_la_barra_de_archivos() -> None:
    registro, al_avance = _avances()

    descargar_modelo("small", al_avance, snapshot=SnapshotFalso((400,)), tamano_total=lambda r: 400)

    assert registro[-1][0] == 400  # no 401: la barra de archivos no suma


def test_si_no_se_conoce_el_total_se_usa_la_suma_de_lo_que_se_va_pidiendo() -> None:
    registro, al_avance = _avances()

    descargar_modelo("small", al_avance, snapshot=SnapshotFalso((400,)), tamano_total=lambda r: 0)

    assert registro and registro[-1] == (400, 400)


def test_si_consultar_el_total_falla_igual_descarga() -> None:
    def roto(repo: str) -> int:
        raise OSError("sin red")

    registro, al_avance = _avances()

    carpeta = descargar_modelo(
        "small", al_avance, snapshot=SnapshotFalso((400,)), tamano_total=roto
    )

    assert carpeta and registro[-1] == (400, 400)


def test_sin_pedir_avance_tambien_funciona() -> None:
    assert descargar_modelo("small", snapshot=SnapshotFalso(), tamano_total=lambda r: 1)


def test_no_imprime_barras_en_la_consola(capsys: pytest.CaptureFixture[str]) -> None:
    descargar_modelo("small", snapshot=SnapshotFalso(), tamano_total=lambda r: 481_000)

    salida = capsys.readouterr()
    assert salida.out == "" and salida.err == ""


# ---- cortes y falta de internet --------------------------------------------------------------------------------


def test_sin_internet_falla_con_el_codigo_de_modelo_faltante() -> None:
    with pytest.raises(ErrorDeTranscripcion) as error:
        descargar_modelo(
            "small",
            snapshot=SnapshotFalso(error=ConnectionError("sin conexión")),
            tamano_total=lambda r: 1,
        )

    assert error.value.codigo == "modelo_faltante"


def test_un_corte_a_mitad_se_puede_repetir_sin_estado_roto() -> None:
    cortado = SnapshotFalso(falla_tras=240_000, error=OSError("se cortó"))
    with pytest.raises(ErrorDeTranscripcion):
        descargar_modelo("small", snapshot=cortado, tamano_total=lambda r: 481_000)

    registro, al_avance = _avances()
    carpeta = descargar_modelo(
        "small", al_avance, snapshot=SnapshotFalso(), tamano_total=lambda r: 481_000
    )

    assert carpeta and registro[-1] == (481_000, 481_000)


def test_el_mensaje_del_error_no_incluye_rutas_ni_claves() -> None:
    with pytest.raises(ErrorDeTranscripcion) as error:
        descargar_modelo(
            "small", snapshot=SnapshotFalso(error=OSError("x")), tamano_total=lambda r: 1
        )

    assert "/home" not in str(error.value)


def test_un_nombre_de_modelo_desconocido_es_un_error_de_transcripcion() -> None:
    with pytest.raises(ErrorDeTranscripcion):
        descargar_modelo("no-existe", snapshot=SnapshotFalso(), tamano_total=lambda r: 1)
