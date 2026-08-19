# -----------------------------------------------------------------------------
# CRC-32 IEEE 802.3 — algoritmo de DETECCIÓN de errores
# Especificación: shared/PROTOCOLO.md §6
# -----------------------------------------------------------------------------
# Polinomio  : 0x04C11DB7  (forma reflejada 0xEDB88320)
# Parámetros : init 0xFFFFFFFF · reflect in/out · xorout 0xFFFFFFFF
# Vector     : CRC32("123456789") = 0xCBF43926  (obligatorio)
# Padding    : ceros a la derecha hasta 32 bits si el mensaje mide menos
# Trama      : bits de datos (ya con padding) + 32 bits de CRC, MSB primero
#
# CRC-32 no corrige: solo distingue una trama íntegra de una corrupta.
#
# Esta implementación debe producir exactamente lo mismo que el crc32.ts del
# receptor; los vectores dorados de shared/vectores.json lo verifican.
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, field

NOMBRE = "crc32"
TIPO = "deteccion"

POLINOMIO = 0x04C11DB7
POLINOMIO_REFLEJADO = 0xEDB88320
VALOR_INICIAL = 0xFFFFFFFF
XOR_FINAL = 0xFFFFFFFF
BITS_CRC = 32

# El enunciado exige n > 32; si el mensaje es menor se rellena hasta 32 bits.
MINIMO_BITS_DATOS = 32


# Trama inválida para CRC-32.
class ErrorCRC32(ValueError):
    pass


def _tabla() -> tuple[int, ...]:
    tabla = []
    for byte in range(256):
        crc = byte
        for _ in range(8):
            crc = (crc >> 1) ^ (POLINOMIO_REFLEJADO if crc & 1 else 0)
        tabla.append(crc)
    return tuple(tabla)


TABLA = _tabla()


# CRC-32 sobre una secuencia de bytes. Devuelve un entero de 32 bits.
def crc32_bytes(datos: bytes) -> int:
    crc = VALOR_INICIAL
    for byte in datos:
        crc = TABLA[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ XOR_FINAL


# CRC-32 sobre una cadena de bits. La longitud debe ser múltiplo de 8, cosa
# que aquí siempre se cumple porque todo el bitstream viene de ASCII 8 bits.
def crc32_bits(bits: str) -> int:
    if any(c not in "01" for c in bits):
        raise ErrorCRC32("el bitstream solo puede contener '0' y '1'")
    if len(bits) % 8 != 0:
        raise ErrorCRC32(
            f"el bitstream mide {len(bits)} bits; debe ser múltiplo de 8"
        )
    octetos = bytes(int(bits[i : i + 8], 2) for i in range(0, len(bits), 8))
    return crc32_bytes(octetos)


# Rellena con ceros a la derecha hasta el mínimo de 32 bits.
def _rellenar(bits: str) -> tuple[str, int]:
    relleno = max(0, MINIMO_BITS_DATOS - len(bits))
    return bits + "0" * relleno, relleno


# Salida de :func:`codificar`, con el detalle que consume la UI.
@dataclass
class ResultadoCRC32:

    trama: str
    bits_datos: str
    crc: int
    crc_bits: str
    bits_relleno: int
    posiciones_redundancia: list[int] = field(default_factory=list)

    @property
    def bits_redundancia(self) -> int:
        return BITS_CRC

    @property
    def overhead(self) -> float:
        return BITS_CRC / len(self.trama) if self.trama else 0.0


# Anexa 32 bits de CRC (MSB primero) al bitstream.
def codificar(bits: str) -> ResultadoCRC32:
    if not bits:
        raise ErrorCRC32("no hay bits que codificar")

    datos, relleno = _rellenar(bits)
    valor = crc32_bits(datos)
    crc_bits = format(valor, "032b")

    return ResultadoCRC32(
        trama=datos + crc_bits,
        bits_datos=datos,
        crc=valor,
        crc_bits=crc_bits,
        bits_relleno=relleno,
        posiciones_redundancia=list(range(len(datos), len(datos) + BITS_CRC)),
    )


# Contraparte del receptor: verifica la integridad de una trama recibida.
# En producción corre en el receptor; aquí sirve para tests y experimentos.
def verificar(trama: str) -> dict:
    if len(trama) <= BITS_CRC:
        raise ErrorCRC32(
            f"la trama mide {len(trama)} bits; se requieren más de {BITS_CRC}"
        )

    datos = trama[:-BITS_CRC]
    crc_recibido = trama[-BITS_CRC:]
    crc_calculado = format(crc32_bits(datos), "032b")
    integro = crc_recibido == crc_calculado

    return {
        "estado": "ok" if integro else "error_detectado",
        "bits": datos if integro else None,
        "bits_corregidos": [],
        "detalle": {"crc_rx": crc_recibido, "crc_calc": crc_calculado},
    }
