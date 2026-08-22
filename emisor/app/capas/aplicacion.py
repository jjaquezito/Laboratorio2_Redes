# -----------------------------------------------------------------------------
# Capa de APLICACIÓN — servicio solicitar_mensaje
# Especificación: shared/PROTOCOLO.md §2
# -----------------------------------------------------------------------------
# Punto de entrada del emisor: recibe el texto a enviar, el algoritmo de
# integridad y la tasa de error, y orquesta el descenso por la pila
#
#     APLICACIÓN -> PRESENTACIÓN -> ENLACE -> RUIDO -> TRANSMISIÓN
#
# Devuelve un ResultadoEnvio con el estado de la trama en cada nivel. Ese
# desglose es lo que la interfaz dibuja bit a bit y lo que la suite de
# experimentos cruza por `id` contra la telemetría del receptor.
# -----------------------------------------------------------------------------

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from . import enlace, presentacion, ruido, transmision

ALGORITMO_POR_DEFECTO = enlace.hamming.NOMBRE


# Entrada inválida en el servicio `solicitar_mensaje`.
class ErrorAplicacion(ValueError):
    pass


# Fotografía completa de un envío, capa por capa.
@dataclass
class ResultadoEnvio:

    id: str
    mensaje: str
    algoritmo: str
    params: dict[str, Any]

    # Estado de la trama en cada capa.
    bits_ascii: str
    trama_enlace: str
    trama_transmitida: str

    # Métricas y verdad-terreno (nunca se envían al receptor).
    posiciones_redundancia: list[int]
    posiciones_volteadas: list[int]
    tasa_error: float
    bits_relleno: int
    bits_redundancia: int
    overhead: float
    longitud_original_bits: int
    detalle_enlace: dict[str, Any] = field(default_factory=dict)

    ms_emision: float = 0.0
    enviado: bool = False
    telemetria: dict[str, Any] | None = None
    error_transmision: str | None = None

    @property
    def bits_volteados(self) -> int:
        return len(self.posiciones_volteadas)

    # Objeto NDJSON del §2 del protocolo: id, algoritmo, params,
    # longitud_original_bits y trama. Las posiciones volteadas NO viajan; si lo
    # hicieran, el receptor estaría haciendo trampa.
    def trama_para_receptor(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "algoritmo": self.algoritmo,
            "params": self.params,
            "longitud_original_bits": self.longitud_original_bits,
            "trama": self.trama_transmitida,
        }

    def a_dict(self) -> dict[str, Any]:
        datos = asdict(self)
        datos["bits_volteados"] = self.bits_volteados
        return datos


# Recorre la pila del emisor **sin** transmitir. Aislado para poder testear.
def preparar_envio(
    mensaje: str,
    algoritmo: str = ALGORITMO_POR_DEFECTO,
    params: dict[str, Any] | None = None,
    tasa_error: str | float | int = 0.0,
    semilla: int | None = None,
    modo_ruido: str = "bernoulli",
    parametro_ruido: int | None = None,
) -> ResultadoEnvio:
    if not mensaje:
        raise ErrorAplicacion("el mensaje no puede estar vacío")

    inicio = time.perf_counter()

    # PRESENTACIÓN: texto -> ASCII binario de 8 bits, MSB primero.
    bits_ascii = presentacion.codificar_mensaje(mensaje)

    # ENLACE: calcular integridad y concatenarla al mensaje binario.
    trama = enlace.calcular_integridad(bits_ascii, algoritmo, params)

    # RUIDO: el canal no confiable. Afecta payload y redundancia por igual.
    if modo_ruido == "bernoulli":
        canal = ruido.aplicar_ruido(trama.trama, tasa_error, semilla=semilla)
    elif modo_ruido == "exactos":
        canal = ruido.aplicar_errores_exactos(
            trama.trama, int(parametro_ruido or 0), semilla=semilla
        )
    elif modo_ruido == "rafaga":
        canal = ruido.aplicar_rafaga(
            trama.trama, int(parametro_ruido or 1), semilla=semilla
        )
    else:
        raise ErrorAplicacion(
            f"modo de ruido desconocido: {modo_ruido!r} "
            "(use 'bernoulli', 'exactos' o 'rafaga')"
        )

    ms = (time.perf_counter() - inicio) * 1000.0

    return ResultadoEnvio(
        id=str(uuid.uuid4()),
        mensaje=mensaje,
        algoritmo=trama.algoritmo,
        params=trama.params,
        bits_ascii=bits_ascii,
        trama_enlace=trama.trama,
        trama_transmitida=canal.trama,
        posiciones_redundancia=trama.posiciones_redundancia,
        posiciones_volteadas=canal.posiciones_volteadas,
        tasa_error=canal.tasa,
        bits_relleno=trama.bits_relleno,
        bits_redundancia=trama.bits_redundancia,
        overhead=trama.overhead,
        longitud_original_bits=len(bits_ascii),
        detalle_enlace=trama.detalle,
        ms_emision=ms,
    )


# Servicio completo: prepara la trama y la entrega a TRANSMISIÓN.
def solicitar_mensaje(
    mensaje: str,
    algoritmo: str = ALGORITMO_POR_DEFECTO,
    params: dict[str, Any] | None = None,
    tasa_error: str | float | int = 0.0,
    semilla: int | None = None,
    modo_ruido: str = "bernoulli",
    parametro_ruido: int | None = None,
    host: str = transmision.HOST_POR_DEFECTO,
    puerto: int = transmision.PUERTO_POR_DEFECTO,
    esperar_telemetria: bool = True,
    timeout: float = transmision.TIMEOUT_POR_DEFECTO,
    conexion: transmision.Conexion | None = None,
) -> ResultadoEnvio:
    resultado = preparar_envio(
        mensaje,
        algoritmo=algoritmo,
        params=params,
        tasa_error=tasa_error,
        semilla=semilla,
        modo_ruido=modo_ruido,
        parametro_ruido=parametro_ruido,
    )

    # Con `conexion` se reutiliza un socket ya abierto: lo usa la suite de
    # experimentos, donde abrir uno por mensaje agotaría los puertos efímeros.
    try:
        if conexion is not None:
            telemetria = conexion.enviar(
                resultado.trama_para_receptor(),
                esperar_telemetria=esperar_telemetria,
            )
        else:
            telemetria = transmision.enviar_informacion(
                resultado.trama_para_receptor(),
                host=host,
                puerto=puerto,
                timeout=timeout,
                esperar_telemetria=esperar_telemetria,
            )
        resultado.enviado = True
        resultado.telemetria = asdict(telemetria) if telemetria else None
    except transmision.ErrorTransmision as exc:
        resultado.enviado = False
        resultado.error_transmision = str(exc)

    return resultado
