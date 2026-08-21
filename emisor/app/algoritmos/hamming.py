# -----------------------------------------------------------------------------
# Hamming(n, m) genérico — algoritmo de CORRECCIÓN de errores
# Especificación: shared/PROTOCOLO.md §5
# -----------------------------------------------------------------------------
# Redundancia : r = mínimo entero que cumple  m + r + 1 <= 2**r ;  n = m + r
# Posiciones  : indexadas desde 1; los bits de paridad ocupan las potencias de
#               dos (1, 2, 4, 8, ...) y los de datos rellenan el resto en orden
# Cobertura   : el bit de paridad en 2**i cubre toda posición j con
#               j & 2**i != 0, incluyéndose a sí mismo. Paridad par: el XOR de
#               las posiciones cubiertas debe dar 0
# Bloques     : el bitstream se parte en bloques de m bits y el último se
#               rellena con ceros. Cada bloque se codifica por separado, de modo
#               que se corrige un error POR BLOQUE y no uno en toda la trama
#
# Valores de referencia:
#   m=4 -> n=7   ·   m=8 -> n=12   ·   m=11 -> n=15   ·   m=16 -> n=21
# -----------------------------------------------------------------------------

from __future__ import annotations

from dataclasses import dataclass, field

NOMBRE = "hamming"
TIPO = "correccion"

# `m` ofrecidos en la interfaz. Cualquier m >= 1 funciona, estos son los
# tamaños con los que se generan las gráficas de overhead vs m.
M_SUGERIDOS = (4, 8, 11, 16)


# Parámetros o trama inválidos para Hamming.
class ErrorHamming(ValueError):
    pass


# Mínimo ``r`` tal que ``m + r + 1 <= 2**r``.
def bits_de_redundancia(m: int) -> int:
    if m < 1:
        raise ErrorHamming(f"m debe ser >= 1, se recibió {m}")
    r = 1
    while m + r + 1 > 2**r:
        r += 1
    return r


# Devuelve ``(n, r)`` para un bloque de ``m`` bits de datos.
def dimensiones(m: int) -> tuple[int, int]:
    r = bits_de_redundancia(m)
    return m + r, r


def _es_potencia_de_dos(x: int) -> bool:
    return x > 0 and (x & (x - 1)) == 0


# Posiciones (base 1) ocupadas por bits de paridad en un bloque de ``n``.
def posiciones_de_paridad(n: int) -> list[int]:
    return [p for p in range(1, n + 1) if _es_potencia_de_dos(p)]


# Posiciones (base 1) ocupadas por bits de datos en un bloque de ``n``.
def posiciones_de_datos(n: int) -> list[int]:
    return [p for p in range(1, n + 1) if not _es_potencia_de_dos(p)]


# Codifica exactamente ``m`` bits de datos en una palabra de ``n`` bits.
def codificar_bloque(bloque: str, m: int) -> str:
    if len(bloque) != m:
        raise ErrorHamming(f"el bloque mide {len(bloque)} bits, se esperaban {m}")

    n, _ = dimensiones(m)

    # `palabra` está indexada desde 1: la casilla 0 no se usa.
    palabra = [0] * (n + 1)
    for pos, bit in zip(posiciones_de_datos(n), bloque):
        if bit not in "01":
            raise ErrorHamming(f"carácter inválido en el bloque: {bit!r}")
        palabra[pos] = int(bit)

    # Paridad par: el bit en 2**i es el XOR de los datos que cubre.
    for p in posiciones_de_paridad(n):
        paridad = 0
        for j in range(1, n + 1):
            if j != p and (j & p):
                paridad ^= palabra[j]
        palabra[p] = paridad

    return "".join(str(b) for b in palabra[1:])


# XOR de los índices (base 1) cuyo bit vale 1.
# 0 = palabra íntegra; cualquier otro valor es la posición que hay que voltear.
def sindrome(palabra: str) -> int:
    s = 0
    for indice, bit in enumerate(palabra, start=1):
        if bit == "1":
            s ^= indice
    return s


# Recupera los ``m`` bits de datos de una palabra ya corregida.
def extraer_datos(palabra: str, m: int) -> str:
    n, _ = dimensiones(m)
    if len(palabra) != n:
        raise ErrorHamming(f"la palabra mide {len(palabra)} bits, se esperaban {n}")
    return "".join(palabra[pos - 1] for pos in posiciones_de_datos(n))


# Salida de :func:`codificar`, con el detalle que consume la UI.
@dataclass
class ResultadoHamming:

    trama: str
    bloques: list[str]
    m: int
    n: int
    r: int
    bits_relleno: int
    posiciones_redundancia: list[int] = field(default_factory=list)

    @property
    def bits_redundancia(self) -> int:
        return len(self.bloques) * self.r

    # Fracción de la trama que es redundancia (0.0 – 1.0).
    @property
    def overhead(self) -> float:
        return self.bits_redundancia / len(self.trama) if self.trama else 0.0


# Codifica un bitstream completo en modo por bloques.
# El último bloque se rellena con ceros; longitud_original_bits lo descarta.
def codificar(bits: str, m: int = 8) -> ResultadoHamming:
    if any(c not in "01" for c in bits):
        raise ErrorHamming("el bitstream solo puede contener '0' y '1'")
    if not bits:
        raise ErrorHamming("no hay bits que codificar")

    n, r = dimensiones(m)

    relleno = (-len(bits)) % m
    acolchado = bits + "0" * relleno

    bloques = [
        codificar_bloque(acolchado[i : i + m], m) for i in range(0, len(acolchado), m)
    ]

    # Posiciones absolutas de los bits de paridad dentro de la trama completa,
    # para que el frontend pueda resaltarlas.
    paridad_local = posiciones_de_paridad(n)
    posiciones = [
        indice * n + (p - 1) for indice in range(len(bloques)) for p in paridad_local
    ]

    return ResultadoHamming(
        trama="".join(bloques),
        bloques=bloques,
        m=m,
        n=n,
        r=r,
        bits_relleno=relleno,
        posiciones_redundancia=posiciones,
    )


# Contraparte del receptor: verifica y, si puede, corrige la trama recibida.
# En producción corre en el receptor; aquí sirve para tests y experimentos.
def verificar(trama: str, m: int = 8) -> dict:
    n, r = dimensiones(m)
    if len(trama) % n != 0:
        raise ErrorHamming(f"la trama ({len(trama)} bits) no es múltiplo de n={n}")

    datos: list[str] = []
    sindromes: list[int] = []
    corregidos: list[int] = []
    corregible = True

    for indice in range(0, len(trama), n):
        palabra = trama[indice : indice + n]
        s = sindrome(palabra)
        sindromes.append(s)

        if s == 0:
            pass
        elif s <= n:
            posicion = s - 1
            palabra = (
                palabra[:posicion]
                + ("1" if palabra[posicion] == "0" else "0")
                + palabra[posicion + 1 :]
            )
            corregidos.append(indice + posicion)
        else:
            # Síndrome fuera de rango: >= 2 errores en el bloque.
            corregible = False

        datos.append(extraer_datos(palabra, m))

    if not corregible:
        estado = "error_no_corregible"
    elif corregidos:
        estado = "corregido"
    else:
        estado = "ok"

    # PROTOCOLO.md §3: el mensaje es null cuando la trama no es confiable. Si un
    # bloque tuvo >= 2 errores, los datos extraídos son basura y no deben
    # entregarse, aunque el resto de la trama haya quedado bien.
    return {
        "estado": estado,
        "bits": None if estado == "error_no_corregible" else "".join(datos),
        "bits_corregidos": corregidos,
        "detalle": {"sindromes": sindromes, "m": m, "n": n, "r": r},
    }
