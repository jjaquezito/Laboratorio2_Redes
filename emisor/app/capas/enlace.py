# -----------------------------------------------------------------------------
# Capa de ENLACE — servicio calcular_integridad
# Especificación: shared/PROTOCOLO.md §5 y §6
# -----------------------------------------------------------------------------
# Toma el bitstream de la capa de presentación, calcula la información de
# redundancia con el algoritmo indicado en solicitar_mensaje y la concatena al
# mensaje binario original.
#
# Los servicios verificar_integridad y corregir_mensaje corren en el RECEPTOR.
# Aquí se expone verificar_integridad como espejo local, para poder cerrar el
# lazo en los tests y en la suite de experimentos sin levantar el receptor.
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..algoritmos import crc32, hamming

ALGORITMOS = (hamming.NOMBRE, crc32.NOMBRE)

TIPO_DE_ALGORITMO = {
    hamming.NOMBRE: hamming.TIPO,   # corrección
    crc32.NOMBRE: crc32.TIPO,       # detección
}


# Algoritmo desconocido o parámetros inválidos.
class ErrorEnlace(ValueError):
    pass


# Trama lista para la capa de ruido, con el desglose que consume la UI.
@dataclass
class TramaEnlace:

    trama: str
    bits_datos: str
    algoritmo: str
    params: dict[str, Any]
    bits_relleno: int
    posiciones_redundancia: list[int] = field(default_factory=list)
    detalle: dict[str, Any] = field(default_factory=dict)

    @property
    def bits_redundancia(self) -> int:
        return len(self.trama) - len(self.bits_datos)

    # Fracción de la trama que es redundancia (0.0 – 1.0).
    @property
    def overhead(self) -> float:
        return self.bits_redundancia / len(self.trama) if self.trama else 0.0


# Valida y completa los parámetros según el algoritmo.
def normalizar_params(algoritmo: str, params: dict[str, Any] | None) -> dict[str, Any]:
    params = dict(params or {})
    if algoritmo == hamming.NOMBRE:
        m = int(params.get("m", 8))
        if m < 1:
            raise ErrorEnlace(f"Hamming requiere m >= 1, se recibió {m}")
        return {"m": m}
    if algoritmo == crc32.NOMBRE:
        return {}
    raise ErrorEnlace(
        f"algoritmo desconocido: {algoritmo!r}. Disponibles: {', '.join(ALGORITMOS)}"
    )


# Concatena la información de integridad al bitstream original.
def calcular_integridad(
    bits: str, algoritmo: str, params: dict[str, Any] | None = None
) -> TramaEnlace:
    params = normalizar_params(algoritmo, params)

    if algoritmo == hamming.NOMBRE:
        resultado = hamming.codificar(bits, m=params["m"])
        return TramaEnlace(
            trama=resultado.trama,
            bits_datos=bits,
            algoritmo=algoritmo,
            params=params,
            bits_relleno=resultado.bits_relleno,
            posiciones_redundancia=resultado.posiciones_redundancia,
            detalle={
                "m": resultado.m,
                "n": resultado.n,
                "r": resultado.r,
                "bloques": len(resultado.bloques),
                "bits_redundancia": resultado.bits_redundancia,
            },
        )

    resultado = crc32.codificar(bits)
    return TramaEnlace(
        trama=resultado.trama,
        bits_datos=bits,
        algoritmo=algoritmo,
        params=params,
        bits_relleno=resultado.bits_relleno,
        posiciones_redundancia=resultado.posiciones_redundancia,
        detalle={
            "crc": format(resultado.crc, "08X"),
            "crc_bits": resultado.crc_bits,
            "bits_redundancia": crc32.BITS_CRC,
        },
    )


# Espejo local del receptor: verifica y, si puede, corrige.
# En producción corre en el receptor; aquí sirve para tests y experimentos.
def verificar_integridad(
    trama: str, algoritmo: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    params = normalizar_params(algoritmo, params)
    if algoritmo == hamming.NOMBRE:
        return hamming.verificar(trama, m=params["m"])
    return crc32.verificar(trama)
