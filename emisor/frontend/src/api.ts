/** Cliente del backend del emisor (FastAPI) y tipos del contrato de trama. */

export type Estado = "ok" | "corregido" | "error_detectado" | "error_no_corregible";

export interface AlgoritmoInfo {
  nombre: string;
  titulo: string;
  tipo: string;
  descripcion: string;
  m_sugeridos?: { m: number; n: number; r: number }[];
  polinomio?: string;
}

export interface Config {
  algoritmos: AlgoritmoInfo[];
  defaults: {
    m: number;
    tasa_error: string;
    host: string;
    puerto: number;
    tamanos: number[];
    bers: number[];
    repeticiones: number;
  };
  modos_ruido: string[];
  estados: Estado[];
}

/** Respuesta de POST /api/enviar: la trama en cada capa. */
export interface ResultadoEnvio {
  id: string;
  mensaje: string;
  algoritmo: string;
  etiqueta: string;
  params: Record<string, number>;
  bits_ascii: string;
  trama_enlace: string;
  trama_transmitida: string;
  posiciones_redundancia: number[];
  posiciones_volteadas: number[];
  bits_volteados: number;
  tasa_error: number;
  bits_relleno: number;
  bits_redundancia: number;
  overhead: number;
  longitud_original_bits: number;
  detalle_enlace: Record<string, unknown>;
  ms_emision: number;
  enviado: boolean;
  error_transmision: string | null;
  telemetria: {
    id: string;
    estado: Estado;
    mensaje: string | null;
    bits_corregidos: number[];
    detalle: Record<string, unknown>;
    ms_procesamiento: number | null;
  } | null;
  veredicto_local: { estado: Estado; mensaje: string | null };
  trama_enviada: Record<string, unknown>;
}

/** Una fila del barrido de experimentos. */
export interface FilaExperimento {
  algoritmo: string;
  etiqueta: string;
  m: number | "";
  bits_mensaje: number;
  ber_nominal: number;
  repeticiones: number;
  bits_trama: number;
  bits_redundancia: number;
  overhead: number;
  ber_empirico: number;
  tasa_entrega: number;
  falsos_negativos: number;
  tasa_falsos_negativos: number;
  mis_correcciones: number;
  ms_emision_medio: number;
  ms_procesamiento_medio: number | "";
  n_ok: number;
  n_corregido: number;
  n_error_detectado: number;
  n_error_no_corregible: number;
}

export interface PeticionEnvio {
  mensaje: string;
  algoritmo: string;
  m: number;
  tasa_error: string;
  semilla: number | null;
  modo_ruido: string;
  parametro_ruido: number | null;
  host: string;
  puerto: number;
  transmitir: boolean;
}

export interface PeticionExperimentos {
  tamanos: number[];
  bers: number[];
  m_hamming: number[];
  incluir_crc32: boolean;
  repeticiones: number;
  semilla: number | null;
  modo: string;
  host: string;
  puerto: number;
}

async function pedir<T>(ruta: string, opciones?: RequestInit): Promise<T> {
  const respuesta = await fetch(ruta, opciones);
  if (!respuesta.ok) {
    let detalle = `HTTP ${respuesta.status}`;
    try {
      const cuerpo = await respuesta.json();
      if (cuerpo?.detail) detalle = String(cuerpo.detail);
    } catch {
      /* la respuesta no era JSON: nos quedamos con el código */
    }
    throw new Error(detalle);
  }
  return respuesta.json() as Promise<T>;
}

const json = (cuerpo: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(cuerpo),
});

export const obtenerConfig = () => pedir<Config>("/api/config");

export const obtenerEstado = (host: string, puerto: number) =>
  pedir<{ receptor_activo: boolean }>(
    `/api/estado?host=${encodeURIComponent(host)}&puerto=${puerto}`,
  );

export const enviar = (peticion: PeticionEnvio) =>
  pedir<ResultadoEnvio>("/api/enviar", json(peticion));

export const correrExperimentos = (peticion: PeticionExperimentos) =>
  pedir<{ filas: FilaExperimento[]; total: number }>(
    "/api/experimentos",
    json({ ...peticion, formato: "json" }),
  );

/** Descarga el barrido como CSV para adjuntarlo al informe. */
export async function descargarCsv(peticion: PeticionExperimentos): Promise<void> {
  const respuesta = await fetch(
    "/api/experimentos",
    json({ ...peticion, formato: "csv" }),
  );
  if (!respuesta.ok) throw new Error(`HTTP ${respuesta.status}`);
  const blob = await respuesta.blob();
  const url = URL.createObjectURL(blob);
  const enlace = document.createElement("a");
  enlace.href = url;
  enlace.download = "barrido.csv";
  enlace.click();
  URL.revokeObjectURL(url);
}

/** Colores de serie: la identidad sigue a la entidad, nunca al orden de filtrado. */
export function colorDeSerie(etiqueta: string): string {
  if (etiqueta.startsWith("CRC")) return "var(--serie-3)";
  const m = Number(etiqueta.match(/,(\d+)\)/)?.[1] ?? 8);
  return m <= 8 ? "var(--serie-1)" : "var(--serie-2)";
}

export const ETIQUETAS_ESTADO: Record<Estado, string> = {
  ok: "Íntegro",
  corregido: "Corregido",
  error_detectado: "Error detectado",
  error_no_corregible: "Error no corregible",
};
