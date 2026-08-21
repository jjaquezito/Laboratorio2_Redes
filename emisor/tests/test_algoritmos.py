# Tests de los algoritmos de la capa de enlace, contra los vectores dorados.

from __future__ import annotations

import json
import zlib
from pathlib import Path

import pytest

from app.algoritmos import crc32, hamming
from app.capas import enlace, presentacion

RAIZ = Path(__file__).resolve().parents[2]
VECTORES = json.loads((RAIZ / "shared" / "vectores.json").read_text(encoding="utf-8"))


def voltear(bits: str, indice: int) -> str:
    return bits[:indice] + ("1" if bits[indice] == "0" else "0") + bits[indice + 1 :]


# --------------------------------------------------------------------------- #
# CRC-32
# --------------------------------------------------------------------------- #

# PROTOCOLO.md §6: si esto falla, nada más importa.
def test_crc32_vector_canonico():
    esperado = int(VECTORES["crc32_vector_canonico"]["esperado_hex"], 16)
    assert crc32.crc32_bytes(b"123456789") == esperado == 0xCBF43926


# zlib implementa exactamente CRC-32 IEEE 802.3: es un oráculo gratis.
@pytest.mark.parametrize(
    "datos",
    [b"", b"a", b"Hola mundo", b"123456789", bytes(range(256)), b"\x00" * 64],
)
def test_crc32_coincide_con_zlib(datos):
    assert crc32.crc32_bytes(datos) == zlib.crc32(datos)


# El enunciado exige padding cuando el mensaje mide menos de 32 bits.
def test_crc32_rellena_hasta_32_bits():
    resultado = crc32.codificar(presentacion.codificar_mensaje("A"))  # 8 bits
    assert resultado.bits_relleno == 24
    assert len(resultado.bits_datos) == 32
    assert len(resultado.trama) == 64


def test_crc32_detecta_error_de_un_bit():
    trama = crc32.codificar(presentacion.codificar_mensaje("Hola mundo")).trama
    assert crc32.verificar(trama)["estado"] == "ok"
    for indice in range(len(trama)):
        assert crc32.verificar(voltear(trama, indice))["estado"] == "error_detectado"


# Propiedad teórica de CRC-32: detecta el 100 % de las ráfagas <= 32 bits.
def test_crc32_detecta_toda_rafaga_de_hasta_32_bits():
    trama = crc32.codificar(presentacion.codificar_mensaje("Redes 2026!")).trama
    for longitud in (2, 8, 17, 32):
        for inicio in range(0, len(trama) - longitud):
            corrupta = trama[:inicio] + "".join(
                "1" if b == "0" else "0" for b in trama[inicio : inicio + longitud]
            ) + trama[inicio + longitud :]
            assert crc32.verificar(corrupta)["estado"] == "error_detectado"


def test_crc32_rechaza_trama_demasiado_corta():
    with pytest.raises(crc32.ErrorCRC32):
        crc32.verificar("1" * 32)


# --------------------------------------------------------------------------- #
# Hamming
# --------------------------------------------------------------------------- #

# PROTOCOLO.md §5: m=4->n=7 · m=8->n=12 · m=11->n=15 · m=16->n=21.
@pytest.mark.parametrize(
    "m, n, r", [(4, 7, 3), (8, 12, 4), (11, 15, 4), (16, 21, 5)]
)
def test_hamming_dimensiones_de_referencia(m, n, r):
    assert hamming.dimensiones(m) == (n, r)


# r es el mínimo que satisface m + r + 1 <= 2**r.
@pytest.mark.parametrize("m", [1, 2, 4, 8, 11, 16, 32, 57])
def test_hamming_cumple_la_desigualdad(m):
    r = hamming.bits_de_redundancia(m)
    assert m + r + 1 <= 2**r
    assert m + (r - 1) + 1 > 2 ** (r - 1)


# Inyecta 1 error en cada una de las n posiciones y exige corrección.
@pytest.mark.parametrize("m", [4, 8, 11, 16])
def test_hamming_corrige_un_error_en_cada_posicion(m):
    n, _ = hamming.dimensiones(m)
    datos = "".join(str((i * 7 + 3) % 2) for i in range(m))
    trama = hamming.codificar(datos, m).trama
    assert len(trama) == n

    for indice in range(n):
        resultado = hamming.verificar(voltear(trama, indice), m)
        assert resultado["estado"] == "corregido"
        assert resultado["bits_corregidos"] == [indice]
        assert resultado["bits"] == datos


def test_hamming_sin_errores_es_ok():
    bits = presentacion.codificar_mensaje("Hola mundo")
    trama = hamming.codificar(bits, 8).trama
    resultado = hamming.verificar(trama, 8)
    assert resultado["estado"] == "ok"
    assert resultado["bits_corregidos"] == []
    assert resultado["bits"][: len(bits)] == bits


# El modo por bloques corrige 1 error *por bloque*, no 1 en toda la trama.
def test_hamming_corrige_un_error_por_bloque():
    bits = presentacion.codificar_mensaje("Hola mundo")
    codificado = hamming.codificar(bits, 8)
    n = codificado.n
    trama = codificado.trama

    for bloque in range(len(codificado.bloques)):
        trama = voltear(trama, bloque * n + (bloque % n))

    resultado = hamming.verificar(trama, 8)
    assert resultado["estado"] == "corregido"
    assert len(resultado["bits_corregidos"]) == len(codificado.bloques)
    assert resultado["bits"][: len(bits)] == bits


# 'Hi' son 16 bits; con m=11 hay relleno y aun así debe volver 'Hi'.
def test_hamming_padding_se_descarta_con_longitud_original():
    bits = presentacion.codificar_mensaje("Hi")
    codificado = hamming.codificar(bits, 11)
    assert codificado.bits_relleno == 6

    recuperado = hamming.verificar(codificado.trama, 11)["bits"]
    assert presentacion.decodificar_mensaje(recuperado, len(bits)) == "Hi"


# Modo de fallo conocido: con 2 errores por bloque Hamming se equivoca.
def test_hamming_dos_errores_en_un_bloque_no_se_recuperan():
    datos = "01000001"
    trama = hamming.codificar(datos, 8).trama
    fallos = 0
    for i in range(len(trama)):
        for j in range(i + 1, len(trama)):
            resultado = hamming.verificar(voltear(voltear(trama, i), j), 8)
            assert resultado["bits"] != datos, (i, j)
            fallos += 1
    assert fallos == 66  # C(12,2)


# Dos errores en un bloque dan sindrome p^q (posiciones 1-based). Solo cuando ese
# valor excede n el bloque se declara no corregible; en el resto de los casos
# Hamming "corrige" mal y entrega basura, que es el modo de fallo silencioso.
def _trama_no_corregible(mensaje: str, m: int = 8) -> str:
    n, _ = hamming.dimensiones(m)
    trama = hamming.codificar(presentacion.codificar_mensaje(mensaje), m).trama
    for p in range(1, n + 1):
        for q in range(p + 1, n + 1):
            if p ^ q > n:
                return voltear(voltear(trama, p - 1), q - 1)
    raise AssertionError(f"no hay sindrome fuera de rango para m={m}")


# PROTOCOLO.md §3: si la trama no es confiable, no se entrega mensaje. Los datos
# de un bloque con >= 2 errores son basura y no deben salir de la capa de enlace,
# aunque el resto de la trama haya quedado intacta.
# Solo los codigos NO perfectos (n < 2**r - 1) tienen sindromes fuera de rango.
@pytest.mark.parametrize("m", [8, 16])
def test_hamming_no_entrega_bits_cuando_no_es_corregible(m):
    resultado = hamming.verificar(_trama_no_corregible("Mensaje de prueba", m), m)

    assert resultado["estado"] == "error_no_corregible"
    assert resultado["bits"] is None


# Un codigo de Hamming es perfecto cuando n == 2**r - 1: todo sindrome apunta a
# una posicion valida, asi que con 2 errores en un bloque NUNCA puede reportar
# error_no_corregible y siempre corrige mal en silencio. Es el peor caso para la
# integridad y depende del m elegido, no de la tasa de error.
@pytest.mark.parametrize("m, perfecto", [(4, True), (8, False), (11, True), (16, False)])
def test_hamming_perfecto_no_puede_declararse_no_corregible(m, perfecto):
    n, r = hamming.dimensiones(m)
    assert (n == 2**r - 1) is perfecto

    fuera_de_rango = [
        (p, q)
        for p in range(1, n + 1)
        for q in range(p + 1, n + 1)
        if p ^ q > n
    ]
    assert (fuera_de_rango == []) is perfecto


# CRC-32 ya cumplia la misma regla; se comprueban juntos para que no diverjan.
def test_ambos_algoritmos_callan_el_mensaje_si_no_es_confiable():
    crc = crc32.codificar(presentacion.codificar_mensaje("Mensaje de prueba"))
    assert crc32.verificar(voltear(crc.trama, 3))["bits"] is None

    assert hamming.verificar(_trama_no_corregible("Mensaje de prueba"), 8)["bits"] is None


def test_hamming_rechaza_trama_desalineada():
    with pytest.raises(hamming.ErrorHamming):
        hamming.verificar("1" * 13, 8)


# --------------------------------------------------------------------------- #
# Vectores dorados compartidos con el receptor (TypeScript)
# --------------------------------------------------------------------------- #

# La misma trama debe salir en Python y en TypeScript.
@pytest.mark.parametrize(
    "vector", VECTORES["vectores"], ids=lambda v: f"{v['mensaje']}-{v['algoritmo']}"
)
def test_vectores_dorados(vector):
    bits = presentacion.codificar_mensaje(vector["mensaje"])
    assert bits == vector["bits_ascii"]
    assert len(bits) == vector["longitud_original_bits"]

    trama = enlace.calcular_integridad(bits, vector["algoritmo"], vector["params"])
    assert trama.trama == vector["trama_esperada"]
    assert trama.bits_redundancia == vector["bits_redundancia"]
    assert trama.bits_relleno == vector["bits_relleno"]


# Sin ruido, toda trama dorada se decodifica de vuelta al mensaje.
@pytest.mark.parametrize(
    "vector", VECTORES["vectores"], ids=lambda v: f"{v['mensaje']}-{v['algoritmo']}"
)
def test_vectores_dorados_ida_y_vuelta(vector):
    resultado = enlace.verificar_integridad(
        vector["trama_esperada"], vector["algoritmo"], vector["params"]
    )
    assert resultado["estado"] == "ok"
    assert (
        presentacion.decodificar_mensaje(
            resultado["bits"], vector["longitud_original_bits"]
        )
        == vector["mensaje"]
    )
