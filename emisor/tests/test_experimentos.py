# Tests de la suite de experimentos.

from __future__ import annotations

import csv
import io
import json
import socket
import threading

import pytest

from app.capas import enlace, presentacion
from app.experimentos import runner


# Receptor NDJSON de prueba que cuenta cuántas conexiones y cuántas tramas vio.
class _ReceptorContador:
    def __init__(self) -> None:
        self.servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.servidor.bind(("127.0.0.1", 0))
        self.servidor.listen(4)
        self.puerto = self.servidor.getsockname()[1]
        self.conexiones = 0
        self.tramas = 0
        threading.Thread(target=self._atender, daemon=True).start()

    def _atender(self) -> None:
        while True:
            try:
                conexion, _ = self.servidor.accept()
            except OSError:
                return
            self.conexiones += 1
            threading.Thread(
                target=self._sesion, args=(conexion,), daemon=True
            ).start()

    def _sesion(self, conexion: socket.socket) -> None:
        with conexion, conexion.makefile("rb") as flujo:
            for linea in flujo:
                linea = linea.strip()
                if not linea:
                    continue
                self.tramas += 1
                trama = json.loads(linea)
                verificado = enlace.verificar_integridad(
                    trama["trama"], trama["algoritmo"], trama["params"]
                )
                mensaje = (
                    presentacion.decodificar_mensaje(
                        verificado["bits"], trama["longitud_original_bits"]
                    )
                    if verificado["bits"] is not None
                    else None
                )
                conexion.sendall(
                    (json.dumps({
                        "id": trama["id"],
                        "estado": verificado["estado"],
                        "mensaje": mensaje,
                        "bits_corregidos": verificado["bits_corregidos"],
                        "detalle": verificado["detalle"],
                        "ms_procesamiento": 0.0,
                    }) + "\n").encode()
                )

    def cerrar(self) -> None:
        self.servidor.close()


@pytest.fixture
def receptor_contador():
    servidor = _ReceptorContador()
    yield servidor
    servidor.cerrar()



# Quita las columnas de reloj de pared, que no son deterministas.
def sin_tiempos(filas: list[dict]) -> list[dict]:
    return [{k: v for k, v in fila.items() if not k.startswith("ms_")} for fila in filas]


def barrido(semilla: int | None, **extra) -> list[dict]:
    opciones = dict(
        tamanos=[64, 128], bers=[0.0, 0.01, 0.05], repeticiones=60, semilla=semilla
    )
    opciones.update(extra)
    return [a.a_fila() for a in runner.barrer(**opciones)]


# --------------------------------------------------------------------------- #
# Reproducibilidad
# --------------------------------------------------------------------------- #

# Dos corridas con la misma semilla dan resultados idénticos.
def test_barrido_es_reproducible_con_la_misma_semilla():
    assert sin_tiempos(barrido(99)) == sin_tiempos(barrido(99))


def test_semillas_distintas_dan_resultados_distintos():
    assert sin_tiempos(barrido(99)) != sin_tiempos(barrido(7))


def test_sin_semilla_el_barrido_es_aleatorio():
    assert sin_tiempos(barrido(None)) != sin_tiempos(barrido(None))


# --------------------------------------------------------------------------- #
# Métricas
# --------------------------------------------------------------------------- #

def test_mensaje_de_n_bits_mide_lo_pedido():
    for bits in (8, 64, 512, 2048):
        assert len(runner.mensaje_de_n_bits(bits)) * 8 == bits


def test_mensaje_de_n_bits_rechaza_longitudes_desalineadas():
    with pytest.raises(ValueError):
        runner.mensaje_de_n_bits(12)


def test_etiquetas_de_serie():
    assert runner.etiquetar("hamming", {"m": 8}) == "Hamming(12,8)"
    assert runner.etiquetar("hamming", {"m": 16}) == "Hamming(21,16)"
    assert runner.etiquetar("crc32", {}) == "CRC-32"


def test_sin_ruido_todo_se_entrega():
    for fila in barrido(1, bers=[0.0]):
        assert fila["tasa_entrega"] == 1.0
        assert fila["falsos_negativos"] == 0
        assert fila["n_ok"] == fila["repeticiones"]


# Hallazgo central del informe: CRC-32 no entrega basura en silencio.
def test_crc32_nunca_produce_falsos_negativos():
    filas = barrido(5, bers=[0.01, 0.05, 0.1], configuraciones=[("crc32", {})])
    assert filas
    for fila in filas:
        assert fila["falsos_negativos"] == 0
        assert fila["mis_correcciones"] == 0


# Contraparte: con >= 2 errores por bloque, Hamming "corrige" mal.
def test_hamming_produce_falsos_negativos_a_tasas_altas():
    filas = barrido(5, bers=[0.1], configuraciones=[("hamming", {"m": 8})])
    assert sum(fila["falsos_negativos"] for fila in filas) > 0


# La corrección gana cuando el canal es bueno: recupera lo que CRC-32 tira.
def test_hamming_supera_a_crc32_en_entrega_a_tasas_bajas():
    filas = barrido(3, tamanos=[128], bers=[0.005])
    entrega = {fila["etiqueta"]: fila["tasa_entrega"] for fila in filas}
    assert entrega["Hamming(12,8)"] > entrega["CRC-32"]


def test_overhead_de_crc32_se_amortiza():
    filas = barrido(1, tamanos=[64, 2048], bers=[0.0], configuraciones=[("crc32", {})])
    por_tamano = {fila["bits_mensaje"]: fila["overhead"] for fila in filas}
    assert por_tamano[2048] < por_tamano[64] / 10


def test_overhead_de_hamming_es_constante():
    filas = barrido(
        1, tamanos=[64, 2048], bers=[0.0], configuraciones=[("hamming", {"m": 8})]
    )
    valores = [fila["overhead"] for fila in filas]
    assert valores[0] == pytest.approx(valores[1], abs=0.001)


def test_ber_empirico_se_acerca_al_nominal():
    for fila in barrido(11, tamanos=[2048], bers=[0.01]):
        assert fila["ber_empirico"] == pytest.approx(0.01, abs=0.003)


# --------------------------------------------------------------------------- #
# Exportación
# --------------------------------------------------------------------------- #

def test_csv_tiene_una_fila_por_celda_y_las_columnas_del_informe():
    agregados = list(
        runner.barrer(tamanos=[64], bers=[0.0, 0.01], repeticiones=20, semilla=1)
    )
    texto = runner.a_csv(agregados)
    filas = list(csv.DictReader(io.StringIO(texto)))

    assert len(filas) == len(agregados)
    for columna in (
        "algoritmo", "etiqueta", "bits_mensaje", "ber_nominal", "overhead",
        "tasa_entrega", "falsos_negativos", "mis_correcciones",
        "n_ok", "n_corregido", "n_error_detectado", "n_error_no_corregible",
    ):
        assert columna in filas[0]


def test_csv_vacio_no_revienta():
    assert runner.a_csv([]) == ""


# Sin receptor, el barrido en modo socket falla al abrir la conexión y no llega a
# emitir ninguna trama: es preferible a descubrirlo a los cientos de envíos.
def test_barrido_por_socket_falla_rapido_sin_receptor(monkeypatch):
    llamadas = []
    original = runner.aplicacion.solicitar_mensaje

    def espia(*args, **kwargs):
        llamadas.append(kwargs.get("puerto"))
        return original(*args, **kwargs)

    monkeypatch.setattr(runner.aplicacion, "solicitar_mensaje", espia)
    with pytest.raises(runner.transmision.ErrorTransmision):
        list(runner.barrer(
            tamanos=[64], bers=[0.0], repeticiones=50,
            configuraciones=[("crc32", {})], modo="socket", puerto=1,
        ))
    assert llamadas == []


# El barrido reutiliza UNA conexión para todas sus tramas. Abrir una por mensaje
# agota los puertos efímeros del sistema (~16 000 en macOS) y el barrido muere a
# media corrida con "Can't assign requested address".
def test_barrido_por_socket_reutiliza_una_sola_conexion(receptor_contador):
    agregados = list(runner.barrer(
        tamanos=[64], bers=[0.0, 0.01], repeticiones=40,
        configuraciones=[("hamming", {"m": 8}), ("crc32", {})],
        semilla=1, modo="socket", puerto=receptor_contador.puerto,
    ))

    assert len(agregados) == 4
    assert sum(a.repeticiones for a in agregados) == 160
    assert receptor_contador.tramas == 160
    assert receptor_contador.conexiones == 1


# La telemetría del receptor real debe llegar y ser coherente con el protocolo.
def test_barrido_por_socket_recoge_los_veredictos(receptor_contador):
    agregados = list(runner.barrer(
        tamanos=[64], bers=[0.0], repeticiones=30,
        configuraciones=[("hamming", {"m": 8})],
        semilla=1, modo="socket", puerto=receptor_contador.puerto,
    ))
    assert agregados[0].tasa_entrega == 1.0
    assert agregados[0].conteo_estados["ok"] == 30
