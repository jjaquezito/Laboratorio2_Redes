// -----------------------------------------------------------------------------
// Capa de APLICACIÓN — servicio mostrar_mensaje
// Especificación: shared/PROTOCOLO.md §2
// -----------------------------------------------------------------------------
// Punto de entrada del receptor: recibe la trama cruda (ya deserializada por
// la capa de transmisión) y orquesta la subida por la pila
//
//     TRANSMISIÓN -> ENLACE -> PRESENTACIÓN -> APLICACIÓN
//
// Si la integridad no se pudo verificar o corregir, `mensaje` queda en
// `null` — es la capa de transmisión/UI la que decide cómo mostrar el error.
// -----------------------------------------------------------------------------

import * as enlace from "./enlace.js";
import * as presentacion from "./presentacion.js";

export interface TramaRecibida {
  algoritmo: string;
  params?: enlace.ParamsEnlace;
  longitud_original_bits: number;
  trama: string;
}

export interface ResultadoRecepcion {
  estado: enlace.EstadoVerificacion;
  mensaje: string | null;
  bitsCorregidos: number[];
  detalle: Record<string, unknown>;
}

// Servicio `mostrar_mensaje`: verifica/corrige y decodifica si es confiable.
export function procesarTrama(trama: TramaRecibida): ResultadoRecepcion {
  const verificado = enlace.verificarIntegridad(trama.trama, trama.algoritmo, trama.params);

  const mensaje =
    verificado.bits !== null ? presentacion.decodificarMensaje(verificado.bits, trama.longitud_original_bits) : null;

  return {
    estado: verificado.estado,
    mensaje,
    bitsCorregidos: verificado.bitsCorregidos,
    detalle: verificado.detalle,
  };
}
