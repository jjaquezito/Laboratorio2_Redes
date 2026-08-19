# Tests de las capas del emisor y del contrato de trama.

from __future__ import annotations

import json
import socket
import threading

import pytest

from app.capas import aplicacion, enlace, presentacion, ruido, transmision


# --------------------------------------------------------------------------- #
# PRESENTACIÓN (§4)
# --------------------------------------------------------------------------- #

def test_presentacion_ascii_de_ocho_bits():
    assert presentacion.codificar_mensaje("A") == "01000001"
    assert presentacion.codificar_mensaje("Hi") == "0100100001101001"


@pytest.mark.parametrize("texto", ["A", "Hola mundo", "Redes 2026!", "~!@#$%^&*()_+"])
def test_presentacion_ida_y_vuelta(texto):
    bits = presentacion.codificar_mensaje(texto)
    assert len(bits) == len(texto) * 8
    assert presentacion.decodificar_mensaje(bits) == texto


def test_presentacion_rechaza_no_ascii():
    with pytest.raises(presentacion.ErrorPresentacion):
        presentacion.codificar_mensaje("mañana")


def test_presentacion_descarta_relleno():
    bits = presentacion.codificar_mensaje("Hi")
    assert presentacion.decodificar_mensaje(bits + "0" * 24, len(bits)) == "Hi"


def test_presentacion_rechaza_longitud_desalineada():
    with pytest.raises(presentacion.ErrorPresentacion):
        presentacion.decodificar_mensaje("0101")


# --------------------------------------------------------------------------- #
# RUIDO (§7)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "entrada, esperado",
    [("1/100", 0.01), (0.01, 0.01), ("0.01", 0.01), ("1e-3", 0.001),
     ("5%", 0.05), ("0,02", 0.02), ("1/1000", 0.001), (0, 0.0)],
)
def test_ruido_parsea_la_tasa(entrada, esperado):
    assert ruido.parsear_tasa(entrada) == pytest.approx(esperado)


@pytest.mark.parametrize("malo", ["", "abc", "1/0", -0.5, 1.5, "2"])
def test_ruido_rechaza_tasas_invalidas(malo):
    with pytest.raises(ruido.ErrorRuido):
        ruido.parsear_tasa(malo)


def test_ruido_con_p_cero_no_altera_nada():
    trama = "0110" * 32
    resultado = ruido.aplicar_ruido(trama, 0.0)
    assert resultado.trama == trama
    assert resultado.posiciones_volteadas == []


def test_ruido_con_p_uno_voltea_todo():
    resultado = ruido.aplicar_ruido("0" * 64, 1.0)
    assert resultado.trama == "1" * 64
    assert resultado.bits_volteados == 64


def test_ruido_es_reproducible_con_semilla():
    trama = "0110" * 64
    a = ruido.aplicar_ruido(trama, 0.05, semilla=1234)
    b = ruido.aplicar_ruido(trama, 0.05, semilla=1234)
    c = ruido.aplicar_ruido(trama, 0.05, semilla=4321)
    assert a.trama == b.trama and a.posiciones_volteadas == b.posiciones_volteadas
    assert a.posiciones_volteadas != c.posiciones_volteadas


def test_ruido_las_posiciones_coinciden_con_los_bits_cambiados():
    trama = "0110" * 64
    resultado = ruido.aplicar_ruido(trama, 0.1, semilla=99)
    cambiados = [i for i, (x, y) in enumerate(zip(trama, resultado.trama)) if x != y]
    assert cambiados == resultado.posiciones_volteadas


# Con 200 000 bits, la proporción volteada debe rondar p = 0.05.
def test_ruido_tasa_empirica_se_acerca_a_p():
    resultado = ruido.aplicar_ruido("0" * 200_000, 0.05, semilla=7)
    assert resultado.bits_volteados / 200_000 == pytest.approx(0.05, abs=0.005)


def test_ruido_modo_exactos():
    resultado = ruido.aplicar_errores_exactos("0" * 100, 7, semilla=3)
    assert resultado.bits_volteados == 7
    assert len(set(resultado.posiciones_volteadas)) == 7


def test_ruido_modo_rafaga_es_contigua():
    resultado = ruido.aplicar_rafaga("0" * 200, 16, semilla=5)
    posiciones = resultado.posiciones_volteadas
    assert posiciones[-1] - posiciones[0] == 15  # extremos siempre volteados


# --------------------------------------------------------------------------- #
# ENLACE (§5, §6)
# --------------------------------------------------------------------------- #

def test_enlace_concatena_redundancia_al_mensaje_original():
    bits = presentacion.codificar_mensaje("Hola mundo")
    for algoritmo, params in [("hamming", {"m": 8}), ("crc32", {})]:
        trama = enlace.calcular_integridad(bits, algoritmo, params)
        assert len(trama.trama) > len(bits)
        assert trama.bits_redundancia == len(trama.trama) - len(bits)
        assert 0.0 < trama.overhead < 1.0


def test_enlace_crc32_deja_los_datos_intactos_al_frente():
    bits = presentacion.codificar_mensaje("Hola mundo")
    trama = enlace.calcular_integridad(bits, "crc32")
    assert trama.trama[: len(bits)] == bits
    assert len(trama.trama) == len(bits) + 32


def test_enlace_rechaza_algoritmo_desconocido():
    with pytest.raises(enlace.ErrorEnlace):
        enlace.calcular_integridad("01000001", "fletcher")


def test_enlace_normaliza_params():
    assert enlace.normalizar_params("hamming", None) == {"m": 8}
    assert enlace.normalizar_params("hamming", {"m": "16"}) == {"m": 16}
    assert enlace.normalizar_params("crc32", {"m": 8}) == {}


# CRC-32 son 32 bits fijos; Hamming crece con el mensaje.
def test_enlace_overhead_crc32_se_amortiza_y_hamming_no():
    corto = presentacion.codificar_mensaje("Hi")
    largo = presentacion.codificar_mensaje("A" * 256)

    crc_corto = enlace.calcular_integridad(corto, "crc32").overhead
    crc_largo = enlace.calcular_integridad(largo, "crc32").overhead
    assert crc_largo < crc_corto / 10

    ham_corto = enlace.calcular_integridad(corto, "hamming", {"m": 8}).overhead
    ham_largo = enlace.calcular_integridad(largo, "hamming", {"m": 8}).overhead
    assert ham_corto == pytest.approx(ham_largo, abs=0.01)


# --------------------------------------------------------------------------- #
# APLICACIÓN (§2) — contrato de trama
# --------------------------------------------------------------------------- #

def test_aplicacion_trama_para_receptor_respeta_el_contrato():
    resultado = aplicacion.preparar_envio("Hola mundo", "hamming", {"m": 8}, "1/10", 1)
    trama = resultado.trama_para_receptor()

    assert set(trama) == {
        "id", "algoritmo", "params", "longitud_original_bits", "trama"
    }
    assert trama["algoritmo"] in enlace.ALGORITMOS
    assert trama["longitud_original_bits"] == 80
    assert set(trama["trama"]) <= {"0", "1"}
    assert json.loads(json.dumps(trama)) == trama  # serializable


# Regla de oro: si viajaran, el receptor estaría haciendo trampa.
def test_aplicacion_no_filtra_las_posiciones_volteadas():
    resultado = aplicacion.preparar_envio("Hola mundo", "crc32", tasa_error=0.5, semilla=1)
    assert resultado.posiciones_volteadas  # hubo ruido...
    serializado = json.dumps(resultado.trama_para_receptor())
    assert "volteada" not in serializado and "posiciones" not in serializado


# El enunciado lo exige explícitamente.
def test_aplicacion_el_ruido_afecta_tambien_la_redundancia():
    resultado = aplicacion.preparar_envio("Hola mundo", "crc32", tasa_error=0.5, semilla=2)
    cola = set(range(len(resultado.bits_ascii), len(resultado.trama_enlace)))
    assert cola & set(resultado.posiciones_volteadas)


def test_aplicacion_sin_ruido_la_trama_no_cambia():
    resultado = aplicacion.preparar_envio("Hola mundo", "hamming", {"m": 8}, 0.0)
    assert resultado.trama_transmitida == resultado.trama_enlace
    assert resultado.posiciones_volteadas == []


def test_aplicacion_rechaza_mensaje_vacio():
    with pytest.raises(aplicacion.ErrorAplicacion):
        aplicacion.preparar_envio("")


def test_aplicacion_rechaza_modo_de_ruido_desconocido():
    with pytest.raises(aplicacion.ErrorAplicacion):
        aplicacion.preparar_envio("Hola", modo_ruido="gaussiano")


# Sin ruido, el mensaje debe salir intacto del otro lado.
@pytest.mark.parametrize("algoritmo, params", [("hamming", {"m": 8}), ("crc32", {})])
def test_aplicacion_lazo_completo_sin_ruido(algoritmo, params):
    resultado = aplicacion.preparar_envio("Hola mundo", algoritmo, params, 0.0)
    verificado = enlace.verificar_integridad(
        resultado.trama_transmitida, algoritmo, params
    )
    assert verificado["estado"] == "ok"
    assert (
        presentacion.decodificar_mensaje(
            verificado["bits"], resultado.longitud_original_bits
        )
        == "Hola mundo"
    )


def test_aplicacion_hamming_corrige_un_bit_inyectado():
    resultado = aplicacion.preparar_envio(
        "Hola mundo", "hamming", {"m": 8}, modo_ruido="exactos", parametro_ruido=1,
        semilla=11,
    )
    verificado = enlace.verificar_integridad(
        resultado.trama_transmitida, "hamming", {"m": 8}
    )
    assert verificado["estado"] == "corregido"
    assert verificado["bits_corregidos"] == resultado.posiciones_volteadas
    assert (
        presentacion.decodificar_mensaje(
            verificado["bits"], resultado.longitud_original_bits
        )
        == "Hola mundo"
    )


def test_aplicacion_crc32_detecta_un_bit_inyectado():
    resultado = aplicacion.preparar_envio(
        "Hola mundo", "crc32", modo_ruido="exactos", parametro_ruido=1, semilla=11,
    )
    verificado = enlace.verificar_integridad(resultado.trama_transmitida, "crc32")
    assert verificado["estado"] == "error_detectado"
    assert verificado["bits"] is None


# --------------------------------------------------------------------------- #
# TRANSMISIÓN (§1, §3)
# --------------------------------------------------------------------------- #

# Receptor NDJSON mínimo, para probar la capa de transmisión sin Node.
class ReceptorDePrueba:

    def __init__(self):
        self.servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.servidor.bind(("127.0.0.1", 0))
        self.servidor.listen(4)
        self.puerto = self.servidor.getsockname()[1]
        self.recibidas: list[dict] = []
        self.hilo = threading.Thread(target=self._atender, daemon=True)
        self.hilo.start()

    def _atender(self):
        while True:
            try:
                conexion, _ = self.servidor.accept()
            except OSError:
                return
            with conexion:
                datos = b""
                while b"\n" not in datos:
                    trozo = conexion.recv(4096)
                    if not trozo:
                        return
                    datos += trozo
                linea, _, _ = datos.partition(b"\n")
                trama = json.loads(linea)
                self.recibidas.append(trama)

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
                respuesta = {
                    "id": trama["id"],
                    "estado": verificado["estado"],
                    "mensaje": mensaje,
                    "bits_corregidos": verificado["bits_corregidos"],
                    "detalle": verificado["detalle"],
                    "ms_procesamiento": 0.0,
                }
                conexion.sendall(
                    (json.dumps(respuesta, ensure_ascii=False) + "\n").encode()
                )

    def cerrar(self):
        self.servidor.close()


@pytest.fixture
def receptor():
    servidor = ReceptorDePrueba()
    yield servidor
    servidor.cerrar()


def test_transmision_entrega_ndjson_y_lee_telemetria(receptor):
    resultado = aplicacion.solicitar_mensaje(
        "Hola mundo", "hamming", {"m": 8}, tasa_error=0.0,
        host="127.0.0.1", puerto=receptor.puerto,
    )
    assert resultado.enviado
    assert resultado.error_transmision is None
    assert resultado.telemetria["estado"] == "ok"
    assert resultado.telemetria["mensaje"] == "Hola mundo"
    assert resultado.telemetria["id"] == resultado.id


# 50 envíos con p=0 sobre un socket real deben dar 50/50 íntegros.
    # Si esto falla, hay desalineación entre el emisor y el receptor.
def test_transmision_cincuenta_mensajes_sin_ruido(receptor):
    for algoritmo, params in [("hamming", {"m": 8}), ("crc32", {})]:
        for i in range(25):
            resultado = aplicacion.solicitar_mensaje(
                f"Mensaje {i}", algoritmo, params, tasa_error=0.0,
                host="127.0.0.1", puerto=receptor.puerto,
            )
            assert resultado.telemetria["estado"] == "ok"
            assert resultado.telemetria["mensaje"] == f"Mensaje {i}"


# Sin receptor, el emisor falla con un mensaje accionable, no con traceback.
def test_transmision_reporta_receptor_caido():
    resultado = aplicacion.solicitar_mensaje(
        "Hola", "crc32", host="127.0.0.1", puerto=1, timeout=0.5
    )
    assert not resultado.enviado
    assert "receptor" in resultado.error_transmision.lower()


def test_transmision_probar_conexion(receptor):
    assert transmision.probar_conexion("127.0.0.1", receptor.puerto)
    assert not transmision.probar_conexion("127.0.0.1", 1, timeout=0.3)
