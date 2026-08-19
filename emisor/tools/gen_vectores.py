# Genera `shared/vectores.json`: los vectores dorados cross-lenguaje.

from __future__ import annotations

import json
from pathlib import Path

from app.algoritmos import crc32
from app.capas import enlace, presentacion

RAIZ = Path(__file__).resolve().parents[2]
DESTINO = RAIZ / "shared" / "vectores.json"

# Mensajes elegidos para cubrir: 1 carácter, sub-32 bits (fuerza padding CRC),
# múltiplo exacto de m, texto largo, y símbolos ASCII no alfabéticos.
MENSAJES = ["A", "Hi", "Hola", "Hola mundo", "Redes 2026!", "The quick brown fox"]

CASOS = (
    [("hamming", {"m": m}) for m in (4, 8, 11, 16)]
    + [("crc32", {})]
)


def construir() -> dict:
    vectores = []
    for mensaje in MENSAJES:
        bits = presentacion.codificar_mensaje(mensaje)
        for algoritmo, params in CASOS:
            trama = enlace.calcular_integridad(bits, algoritmo, params)
            vectores.append(
                {
                    "mensaje": mensaje,
                    "algoritmo": algoritmo,
                    "params": trama.params,
                    "bits_ascii": bits,
                    "longitud_original_bits": len(bits),
                    "trama_esperada": trama.trama,
                    "bits_redundancia": trama.bits_redundancia,
                    "bits_relleno": trama.bits_relleno,
                }
            )

    return {
        "descripcion": (
            "Vectores dorados del Laboratorio 2 (CC3067 Redes). Generados por el "
            "emisor (Python) con emisor/tools/gen_vectores.py. Emisor y receptor "
            "deben producir exactamente estas tramas. Ver shared/PROTOCOLO.md §8."
        ),
        "generado_por": "emisor/tools/gen_vectores.py",
        "crc32_vector_canonico": {
            "entrada": "123456789",
            "esperado_hex": "CBF43926",
            "nota": "Vector obligatorio de CRC-32 IEEE 802.3 (PROTOCOLO.md §6).",
        },
        "hamming_dimensiones": {
            str(m): {"n": enlace.hamming.dimensiones(m)[0],
                     "r": enlace.hamming.dimensiones(m)[1]}
            for m in (4, 8, 11, 16)
        },
        "vectores": vectores,
    }


def main() -> None:
    datos = construir()
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    DESTINO.write_text(
        json.dumps(datos, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    assert crc32.crc32_bytes(b"123456789") == 0xCBF43926, "vector canónico roto"
    print(f"{len(datos['vectores'])} vectores -> {DESTINO}")


if __name__ == "__main__":
    main()
