// -----------------------------------------------------------------------------
// Historial en memoria — alimenta la UI del receptor (extensión fuera del
// enunciado, igual que la telemetría del §3 del protocolo). No es parte del
// contrato de trama: el emisor nunca ve este módulo.
// -----------------------------------------------------------------------------

export interface RegistroTrama {
  id: string;
  algoritmo: string;
  params: Record<string, unknown>;
  longitudOriginalBits: number;
  trama: string;
  estado: string;
  mensaje: string | null;
  bitsCorregidos: number[];
  detalle: Record<string, unknown>;
  msProcesamiento: number;
  marcaDeTiempo: number;
}

export type Contadores = Record<"ok" | "corregido" | "error_detectado" | "error_no_corregible", number>;

const MAXIMO_HISTORIAL = 200;

const historial: RegistroTrama[] = [];
const contadores: Contadores = { ok: 0, corregido: 0, error_detectado: 0, error_no_corregible: 0 };

export function registrar(entrada: RegistroTrama): void {
  historial.unshift(entrada);
  if (historial.length > MAXIMO_HISTORIAL) historial.pop();
  if (entrada.estado in contadores) {
    contadores[entrada.estado as keyof Contadores] += 1;
  }
}

export interface Snapshot {
  historial: RegistroTrama[];
  contadores: Contadores;
}

export function obtenerSnapshot(): Snapshot {
  return { historial, contadores };
}
