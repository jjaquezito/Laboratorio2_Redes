# -----------------------------------------------------------------------------
# Capa de RUIDO — servicio aplicar_ruido (existe solo del lado del emisor)
# Especificación: shared/PROTOCOLO.md §7
# -----------------------------------------------------------------------------
# Modelo  : cada bit se voltea de forma independiente con probabilidad p
#           (proceso Bernoulli)
# Alcance : afecta por igual al payload y a la redundancia, como exige el
#           enunciado
# Tasa    : se expresa en errores por bit transmitido; se admite 0.01, 1/100,
#           1e-3 o 5 %
# Semilla : opcional, para reproducir los experimentos
#
# Modos adicionales, fuera del enunciado, para las pruebas dirigidas del
# informe: aplicar_errores_exactos y aplicar_rafaga.
# -----------------------------------------------------------------------------

from __future__ import annotations

import random
from dataclasses import dataclass, field


# Tasa de error mal formada o fuera del rango [0, 1].
class ErrorRuido(ValueError):
    pass


# Interpreta ``0.01``, ``"0.01"``, ``"1/100"`` o ``"1e-3"`` como float.
def parsear_tasa(valor: str | float | int) -> float:
    if isinstance(valor, (int, float)):
        tasa = float(valor)
    else:
        texto = str(valor).strip().replace(",", ".")
        if not texto:
            raise ErrorRuido("la tasa de error no puede estar vacía")
        try:
            if "/" in texto:
                numerador, _, denominador = texto.partition("/")
                den = float(denominador)
                if den == 0:
                    raise ErrorRuido("el denominador de la tasa no puede ser 0")
                tasa = float(numerador) / den
            elif texto.endswith("%"):
                tasa = float(texto[:-1]) / 100.0
            else:
                tasa = float(texto)
        except ErrorRuido:
            raise
        except ValueError as exc:
            raise ErrorRuido(f"tasa de error inválida: {valor!r}") from exc

    if not 0.0 <= tasa <= 1.0:
        raise ErrorRuido(f"la tasa debe estar entre 0 y 1, se recibió {tasa}")
    return tasa


# Trama tras el canal, más la verdad-terreno que el emisor guarda local.
@dataclass
class ResultadoRuido:

    trama: str
    posiciones_volteadas: list[int] = field(default_factory=list)
    tasa: float = 0.0

    @property
    def bits_volteados(self) -> int:
        return len(self.posiciones_volteadas)


# Voltea cada bit de forma independiente con probabilidad ``tasa``.
def aplicar_ruido(
    trama: str,
    tasa: str | float | int = 0.0,
    semilla: int | None = None,
) -> ResultadoRuido:
    p = parsear_tasa(tasa)
    rng = random.Random(semilla)

    if p == 0.0:
        return ResultadoRuido(trama=trama, posiciones_volteadas=[], tasa=p)

    bits = list(trama)
    volteadas: list[int] = []
    for indice, bit in enumerate(bits):
        if rng.random() < p:
            bits[indice] = "1" if bit == "0" else "0"
            volteadas.append(indice)

    return ResultadoRuido(trama="".join(bits), posiciones_volteadas=volteadas, tasa=p)


# Modo alterno: voltea exactamente `cantidad` bits distintos. Para las pruebas
# dirigidas del informe, donde Bernoulli daría resultados variables.
def aplicar_errores_exactos(
    trama: str, cantidad: int, semilla: int | None = None
) -> ResultadoRuido:
    if cantidad < 0:
        raise ErrorRuido("la cantidad de errores no puede ser negativa")
    if cantidad > len(trama):
        raise ErrorRuido(
            f"se pidieron {cantidad} errores en una trama de {len(trama)} bits"
        )

    rng = random.Random(semilla)
    volteadas = sorted(rng.sample(range(len(trama)), cantidad))
    bits = list(trama)
    for indice in volteadas:
        bits[indice] = "1" if bits[indice] == "0" else "0"

    tasa = cantidad / len(trama) if trama else 0.0
    return ResultadoRuido(trama="".join(bits), posiciones_volteadas=volteadas, tasa=tasa)


# Modo alterno: ráfaga contigua de `longitud` bits. CRC-32 detecta toda ráfaga
# de hasta 32 bits; Hamming falla en cuanto mete 2 errores en un mismo bloque.
def aplicar_rafaga(
    trama: str, longitud: int, semilla: int | None = None
) -> ResultadoRuido:
    if longitud <= 0:
        raise ErrorRuido("la longitud de la ráfaga debe ser >= 1")
    if longitud > len(trama):
        raise ErrorRuido(
            f"ráfaga de {longitud} bits en una trama de {len(trama)} bits"
        )

    rng = random.Random(semilla)
    inicio = rng.randrange(0, len(trama) - longitud + 1)
    bits = list(trama)
    volteadas = []
    for indice in range(inicio, inicio + longitud):
        # Dentro de la ráfaga cada bit se voltea con probabilidad 1/2; los
        # extremos siempre, que es la definición estándar de ráfaga.
        if indice in (inicio, inicio + longitud - 1) or rng.random() < 0.5:
            bits[indice] = "1" if bits[indice] == "0" else "0"
            volteadas.append(indice)

    tasa = len(volteadas) / len(trama) if trama else 0.0
    return ResultadoRuido(trama="".join(bits), posiciones_volteadas=volteadas, tasa=tasa)
