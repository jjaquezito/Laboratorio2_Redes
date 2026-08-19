# -----------------------------------------------------------------------------
# Capa de PRESENTACIÓN — servicios codificar_mensaje / decodificar_mensaje
# Especificación: shared/PROTOCOLO.md §4
# -----------------------------------------------------------------------------
# Codificación : ASCII de 8 bits por carácter, MSB primero.  'A' -> 01000001
# Restricción  : el emisor rechaza con un error explícito todo carácter fuera
#                del rango ASCII 0–127
# Relleno      : decodificar_mensaje recorta con longitud_original_bits el
#                padding que agregó la capa de enlace
# -----------------------------------------------------------------------------

from __future__ import annotations

BITS_POR_CARACTER = 8
ASCII_MAXIMO = 127


# El mensaje no es representable en ASCII de 7 bits.
class ErrorPresentacion(ValueError):
    pass


# Convierte texto a su representación ASCII binaria, MSB primero.
def codificar_mensaje(texto: str) -> str:
    piezas = []
    for indice, caracter in enumerate(texto):
        punto = ord(caracter)
        if punto > ASCII_MAXIMO:
            raise ErrorPresentacion(
                f"el carácter {caracter!r} (posición {indice}, código {punto}) "
                "está fuera del rango ASCII 0–127"
            )
        piezas.append(format(punto, f"0{BITS_POR_CARACTER}b"))
    return "".join(piezas)


# Convierte ASCII binario de vuelta a texto. longitud_original_bits recorta el
# relleno que agregó la capa de enlace antes de decodificar.
def decodificar_mensaje(bits: str, longitud_original_bits: int | None = None) -> str:
    if longitud_original_bits is not None:
        bits = bits[:longitud_original_bits]
    if len(bits) % BITS_POR_CARACTER != 0:
        raise ErrorPresentacion(
            f"el bitstream mide {len(bits)} bits; debe ser múltiplo de "
            f"{BITS_POR_CARACTER}"
        )
    return "".join(
        chr(int(bits[i : i + BITS_POR_CARACTER], 2))
        for i in range(0, len(bits), BITS_POR_CARACTER)
    )
