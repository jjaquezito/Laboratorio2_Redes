# -----------------------------------------------------------------------------
# Suite de experimentos — barridos y agregación de métricas
# -----------------------------------------------------------------------------
# Modos de ejecución:
#   socket : cada envío viaja por TCP al receptor real y el veredicto es suyo
#   local  : verifica con el espejo del receptor que vive en la capa de enlace,
#            lo que permite generar datos y depurar las gráficas sin levantar
#            el receptor
#
# Métricas que alimentan las gráficas del informe:
#   tasa_entrega      métrica principal de rendimiento
#   falsos_negativos  trama corrupta aceptada como válida; mide la calidad real
#                     de la detección
#   mis_correcciones  Hamming "corrige" y entrega basura (>= 2 errores/bloque)
#   overhead          redundancia sobre el total; lo exige el enunciado
#   ms_emision        costo computacional de cada algoritmo
# -----------------------------------------------------------------------------

from __future__ import annotations

import csv
import io
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Iterator

from ..capas import aplicacion, enlace, presentacion, transmision

# Barrido por defecto: cubre cuatro órdenes de magnitud de tasa de error.
TAMANOS_POR_DEFECTO = (8, 32, 128, 512, 2048)  # bits del mensaje
BER_POR_DEFECTO = (0.0, 0.0001, 0.001, 0.005, 0.01, 0.05, 0.1)
CONFIGURACIONES_POR_DEFECTO = (
    ("hamming", {"m": 8}),
    ("hamming", {"m": 16}),
    ("crc32", {}),
)
REPETICIONES_POR_DEFECTO = 200

ESTADOS = ("ok", "corregido", "error_detectado", "error_no_corregible")


# Texto ASCII imprimible de exactamente ``bits`` bits (múltiplo de 8).
def mensaje_de_n_bits(bits: int, semilla: int = 0) -> str:
    if bits % 8 != 0:
        raise ValueError(f"{bits} bits no es múltiplo de 8")
    alfabeto = (
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .,!?"
    )
    n = bits // 8
    return "".join(alfabeto[(semilla * 31 + i * 17) % len(alfabeto)] for i in range(n))


# Un envío individual, ya cruzado con el veredicto del receptor.
@dataclass
class Corrida:

    algoritmo: str
    params: dict[str, Any]
    etiqueta: str
    bits_mensaje: int
    ber_nominal: float
    bits_trama: int
    bits_redundancia: int
    overhead: float
    bits_volteados: int
    estado: str
    mensaje_recuperado: str | None
    mensaje_original: str
    ms_emision: float
    ms_procesamiento: float | None = None

    @property
    def hubo_corrupcion(self) -> bool:
        return self.bits_volteados > 0

    # El mensaje llegó y es idéntico al original.
    @property
    def entregado_correcto(self) -> bool:
        return self.mensaje_recuperado == self.mensaje_original

    # La trama venía corrupta y el receptor la dio por buena, pero el mensaje
    # entregado NO es el original. Es el fallo silencioso: lo peor que puede
    # hacer un esquema de integridad.
    @property
    def falso_negativo(self) -> bool:
        return (
            self.hubo_corrupcion
            and self.estado in ("ok", "corregido")
            and not self.entregado_correcto
        )

    # Hamming aplicó una corrección y aun así entregó basura.
    @property
    def mis_correccion(self) -> bool:
        return self.estado == "corregido" and not self.entregado_correcto


# Una fila de resultados: una configuración a un BER dado.
@dataclass
class Agregado:

    algoritmo: str
    params: dict[str, Any]
    etiqueta: str
    bits_mensaje: int
    ber_nominal: float
    repeticiones: int
    bits_trama: int
    bits_redundancia: int
    overhead: float
    ber_empirico: float
    tasa_entrega: float
    falsos_negativos: int
    tasa_falsos_negativos: float
    mis_correcciones: int
    conteo_estados: dict[str, int] = field(default_factory=dict)
    ms_emision_medio: float = 0.0
    ms_procesamiento_medio: float | None = None

    def a_fila(self) -> dict[str, Any]:
        fila = {
            "algoritmo": self.algoritmo,
            "etiqueta": self.etiqueta,
            "m": self.params.get("m", ""),
            "bits_mensaje": self.bits_mensaje,
            "ber_nominal": self.ber_nominal,
            "repeticiones": self.repeticiones,
            "bits_trama": self.bits_trama,
            "bits_redundancia": self.bits_redundancia,
            "overhead": round(self.overhead, 6),
            "ber_empirico": round(self.ber_empirico, 6),
            "tasa_entrega": round(self.tasa_entrega, 6),
            "falsos_negativos": self.falsos_negativos,
            "tasa_falsos_negativos": round(self.tasa_falsos_negativos, 6),
            "mis_correcciones": self.mis_correcciones,
            "ms_emision_medio": round(self.ms_emision_medio, 4),
            "ms_procesamiento_medio": (
                round(self.ms_procesamiento_medio, 4)
                if self.ms_procesamiento_medio is not None
                else ""
            ),
        }
        for estado in ESTADOS:
            fila[f"n_{estado}"] = self.conteo_estados.get(estado, 0)
        return fila


# Nombre legible para las leyendas de las gráficas.
def etiquetar(algoritmo: str, params: dict[str, Any]) -> str:
    if algoritmo == "hamming":
        n, _ = enlace.hamming.dimensiones(int(params.get("m", 8)))
        return f"Hamming({n},{params.get('m', 8)})"
    return "CRC-32"


# Espejo del receptor, para el modo offline.
def veredicto_local(resultado: aplicacion.ResultadoEnvio) -> tuple[str, str | None]:
    try:
        verificado = enlace.verificar_integridad(
            resultado.trama_transmitida, resultado.algoritmo, resultado.params
        )
    except (enlace.ErrorEnlace, ValueError):
        return "error_no_corregible", None

    if verificado["bits"] is None:
        return verificado["estado"], None

    try:
        mensaje = presentacion.decodificar_mensaje(
            verificado["bits"], resultado.longitud_original_bits
        )
    except presentacion.ErrorPresentacion:
        mensaje = None
    return verificado["estado"], mensaje


def _una_corrida(
    mensaje: str,
    algoritmo: str,
    params: dict[str, Any],
    ber: float,
    semilla: int | None,
    modo: str,
    host: str,
    puerto: int,
) -> Corrida:
    if modo == "socket":
        resultado = aplicacion.solicitar_mensaje(
            mensaje, algoritmo, params, tasa_error=ber, semilla=semilla,
            host=host, puerto=puerto,
        )
        if not resultado.enviado:
            raise transmision.ErrorTransmision(resultado.error_transmision or "")
        telemetria = resultado.telemetria or {}
        estado = telemetria.get("estado", "desconocido")
        recuperado = telemetria.get("mensaje")
        ms_proc = telemetria.get("ms_procesamiento")
    else:
        resultado = aplicacion.preparar_envio(
            mensaje, algoritmo, params, tasa_error=ber, semilla=semilla
        )
        estado, recuperado = veredicto_local(resultado)
        ms_proc = None

    return Corrida(
        algoritmo=algoritmo,
        params=dict(params),
        etiqueta=etiquetar(algoritmo, params),
        bits_mensaje=resultado.longitud_original_bits,
        ber_nominal=ber,
        bits_trama=len(resultado.trama_enlace),
        bits_redundancia=resultado.bits_redundancia,
        overhead=resultado.overhead,
        bits_volteados=resultado.bits_volteados,
        estado=estado,
        mensaje_recuperado=recuperado,
        mensaje_original=mensaje,
        ms_emision=resultado.ms_emision,
        ms_procesamiento=ms_proc,
    )


# Colapsa las repeticiones de una celda del barrido en una fila.
def agregar(corridas: list[Corrida]) -> Agregado:
    primera = corridas[0]
    total = len(corridas)
    conteo = {estado: 0 for estado in ESTADOS}
    for corrida in corridas:
        conteo[corrida.estado] = conteo.get(corrida.estado, 0) + 1

    falsos = sum(1 for c in corridas if c.falso_negativo)
    bits_totales = sum(c.bits_trama for c in corridas)
    volteados = sum(c.bits_volteados for c in corridas)
    ms_proc = [c.ms_procesamiento for c in corridas if c.ms_procesamiento is not None]

    return Agregado(
        algoritmo=primera.algoritmo,
        params=primera.params,
        etiqueta=primera.etiqueta,
        bits_mensaje=primera.bits_mensaje,
        ber_nominal=primera.ber_nominal,
        repeticiones=total,
        bits_trama=primera.bits_trama,
        bits_redundancia=primera.bits_redundancia,
        overhead=primera.overhead,
        ber_empirico=volteados / bits_totales if bits_totales else 0.0,
        tasa_entrega=sum(1 for c in corridas if c.entregado_correcto) / total,
        falsos_negativos=falsos,
        tasa_falsos_negativos=falsos / total,
        mis_correcciones=sum(1 for c in corridas if c.mis_correccion),
        conteo_estados=conteo,
        ms_emision_medio=statistics.fmean(c.ms_emision for c in corridas),
        ms_procesamiento_medio=statistics.fmean(ms_proc) if ms_proc else None,
    )


# Ejecuta el barrido completo y va emitiendo una fila por celda.
def barrer(
    tamanos: Iterable[int] = TAMANOS_POR_DEFECTO,
    bers: Iterable[float] = BER_POR_DEFECTO,
    configuraciones: Iterable[tuple[str, dict]] = CONFIGURACIONES_POR_DEFECTO,
    repeticiones: int = REPETICIONES_POR_DEFECTO,
    semilla: int | None = 2026,
    modo: str = "local",
    host: str = transmision.HOST_POR_DEFECTO,
    puerto: int = transmision.PUERTO_POR_DEFECTO,
    progreso: Callable[[int, int], None] | None = None,
) -> Iterator[Agregado]:
    tamanos = list(tamanos)
    bers = list(bers)
    configuraciones = list(configuraciones)
    total = len(tamanos) * len(bers) * len(configuraciones)
    hechas = 0
    contador = 0

    for bits in tamanos:
        mensaje = mensaje_de_n_bits(bits)
        for algoritmo, params in configuraciones:
            for ber in bers:
                corridas = []
                for _ in range(repeticiones):
                    contador += 1
                    sub = None if semilla is None else semilla + contador
                    corridas.append(
                        _una_corrida(
                            mensaje, algoritmo, params, ber, sub, modo, host, puerto
                        )
                    )
                hechas += 1
                if progreso:
                    progreso(hechas, total)
                yield agregar(corridas)


# Serializa los resultados a CSV para `docs/resultados/` y el informe.
def a_csv(agregados: list[Agregado]) -> str:
    if not agregados:
        return ""
    filas = [a.a_fila() for a in agregados]
    salida = io.StringIO()
    escritor = csv.DictWriter(salida, fieldnames=list(filas[0]))
    escritor.writeheader()
    escritor.writerows(filas)
    return salida.getvalue()
