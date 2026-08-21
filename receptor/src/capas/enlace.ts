// Capa de ENLACE — servicios verificar_integridad / corregir_mensaje.
// Especificación: shared/PROTOCOLO.md §5 y §6.

import * as crc32 from "../algoritmos/crc32.js";
import * as hamming from "../algoritmos/hamming.js";

export const ALGORITMOS = [hamming.NOMBRE, crc32.NOMBRE] as const;
export type Algoritmo = (typeof ALGORITMOS)[number];

export const TIPO_DE_ALGORITMO: Record<Algoritmo, string> = {
  [hamming.NOMBRE]: hamming.TIPO,
  [crc32.NOMBRE]: crc32.TIPO,
};

// Algoritmo desconocido o parámetros inválidos.
export class ErrorEnlace extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorEnlace";
  }
}

export interface ParamsEnlace {
  m?: number;
}

// Valida y completa los parámetros según el algoritmo.
export function normalizarParams(algoritmo: string, params: ParamsEnlace | undefined): ParamsEnlace {
  if (algoritmo === hamming.NOMBRE) {
    const m = params?.m ?? 8;
    if (m < 1) {
      throw new ErrorEnlace(`Hamming requiere m >= 1, se recibió ${m}`);
    }
    return { m };
  }
  if (algoritmo === crc32.NOMBRE) {
    return {};
  }
  throw new ErrorEnlace(`algoritmo desconocido: ${JSON.stringify(algoritmo)}. Disponibles: ${ALGORITMOS.join(", ")}`);
}

export type EstadoVerificacion = hamming.EstadoHamming | crc32.EstadoCRC32;

// Salida de verificarIntegridad(): lo que la capa de aplicación consume.
export interface ResultadoVerificacion {
  estado: EstadoVerificacion;
  bits: string | null;
  bitsCorregidos: number[];
  detalle: Record<string, unknown>;
}

// Recalcula la integridad del lado del receptor y, si se puede, corrige.
export function verificarIntegridad(trama: string, algoritmo: string, params?: ParamsEnlace): ResultadoVerificacion {
  const p = normalizarParams(algoritmo, params);

  if (algoritmo === hamming.NOMBRE) {
    const resultado = hamming.verificar(trama, p.m ?? 8);
    return {
      estado: resultado.estado,
      bits: resultado.bits,
      bitsCorregidos: resultado.bitsCorregidos,
      detalle: resultado.detalle,
    };
  }

  const resultado = crc32.verificar(trama);
  return {
    estado: resultado.estado,
    bits: resultado.bits,
    bitsCorregidos: resultado.bitsCorregidos,
    detalle: resultado.detalle,
  };
}
