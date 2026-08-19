// -----------------------------------------------------------------------------
// CRC-32 IEEE 802.3 — algoritmo de DETECCIÓN de errores
// Especificación: shared/PROTOCOLO.md §6
// -----------------------------------------------------------------------------
// Polinomio  : 0x04C11DB7  (forma reflejada 0xEDB88320)
// Parámetros : init 0xFFFFFFFF · reflect in/out · xorout 0xFFFFFFFF
// Vector     : CRC32("123456789") = 0xCBF43926  (obligatorio)
// Padding    : ceros a la derecha hasta 32 bits si el mensaje mide menos
// Trama      : bits de datos (ya con padding) + 32 bits de CRC, MSB primero
//
// CRC-32 no corrige: solo distingue una trama íntegra de una corrupta.
//
// Debe producir exactamente lo mismo que el crc32.py del emisor; los vectores
// dorados de shared/vectores.json lo verifican.
// -----------------------------------------------------------------------------

export const NOMBRE = "crc32" as const;
export const TIPO = "deteccion" as const;

export const POLINOMIO = 0x04c11db7;
export const POLINOMIO_REFLEJADO = 0xedb88320;
export const VALOR_INICIAL = 0xffffffff;
export const XOR_FINAL = 0xffffffff;
export const BITS_CRC = 32;

// El enunciado exige n > 32; si el mensaje es menor se rellena hasta 32 bits.
export const MINIMO_BITS_DATOS = 32;

// Trama inválida para CRC-32.
export class ErrorCRC32 extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorCRC32";
  }
}

function construirTabla(): readonly number[] {
  const tabla: number[] = [];
  for (let byte = 0; byte < 256; byte++) {
    let crc = byte;
    for (let i = 0; i < 8; i++) {
      crc = crc & 1 ? (crc >>> 1) ^ POLINOMIO_REFLEJADO : crc >>> 1;
    }
    tabla.push(crc >>> 0);
  }
  return tabla;
}

const TABLA = construirTabla();

// CRC-32 sobre una secuencia de bytes. Devuelve un entero de 32 bits (0..2^32-1).
export function crc32Bytes(datos: Uint8Array): number {
  let crc = VALOR_INICIAL;
  for (const byte of datos) {
    crc = TABLA[(crc ^ byte) & 0xff]! ^ (crc >>> 8);
  }
  return (crc ^ XOR_FINAL) >>> 0;
}

// CRC-32 sobre una cadena de bits. La longitud debe ser múltiplo de 8, cosa
// que aquí siempre se cumple porque todo el bitstream viene de ASCII 8 bits.
export function crc32Bits(bits: string): number {
  if (!/^[01]*$/.test(bits)) {
    throw new ErrorCRC32("el bitstream solo puede contener '0' y '1'");
  }
  if (bits.length % 8 !== 0) {
    throw new ErrorCRC32(`el bitstream mide ${bits.length} bits; debe ser múltiplo de 8`);
  }
  const octetos = new Uint8Array(bits.length / 8);
  for (let i = 0; i < bits.length; i += 8) {
    octetos[i / 8] = parseInt(bits.slice(i, i + 8), 2);
  }
  return crc32Bytes(octetos);
}

// Rellena con ceros a la derecha hasta el mínimo de 32 bits.
function rellenar(bits: string): { datos: string; relleno: number } {
  const relleno = Math.max(0, MINIMO_BITS_DATOS - bits.length);
  return { datos: bits + "0".repeat(relleno), relleno };
}

// Salida de codificar(), con el detalle que consume la UI.
export interface ResultadoCRC32 {
  trama: string;
  bitsDatos: string;
  crc: number;
  crcBits: string;
  bitsRelleno: number;
  posicionesRedundancia: number[];
  readonly bitsRedundancia: number;
  readonly overhead: number;
}

// Anexa 32 bits de CRC (MSB primero) al bitstream.
export function codificar(bits: string): ResultadoCRC32 {
  if (!bits) {
    throw new ErrorCRC32("no hay bits que codificar");
  }

  const { datos, relleno } = rellenar(bits);
  const valor = crc32Bits(datos);
  const crcBits = valor.toString(2).padStart(BITS_CRC, "0");
  const trama = datos + crcBits;

  const posicionesRedundancia: number[] = [];
  for (let i = datos.length; i < datos.length + BITS_CRC; i++) posicionesRedundancia.push(i);

  return {
    trama,
    bitsDatos: datos,
    crc: valor,
    crcBits,
    bitsRelleno: relleno,
    posicionesRedundancia,
    bitsRedundancia: BITS_CRC,
    overhead: trama.length ? BITS_CRC / trama.length : 0,
  };
}

export type EstadoCRC32 = "ok" | "error_detectado";

// Salida de verificar(): lo que la capa de enlace del receptor consume.
export interface VerificacionCRC32 {
  estado: EstadoCRC32;
  bits: string | null;
  bitsCorregidos: number[];
  detalle: { crcRx: string; crcCalc: string };
}

// Verifica la integridad de una trama recibida. CRC-32 no corrige.
export function verificar(trama: string): VerificacionCRC32 {
  if (trama.length <= BITS_CRC) {
    throw new ErrorCRC32(`la trama mide ${trama.length} bits; se requieren más de ${BITS_CRC}`);
  }

  const datos = trama.slice(0, -BITS_CRC);
  const crcRecibido = trama.slice(-BITS_CRC);
  const crcCalculado = crc32Bits(datos).toString(2).padStart(BITS_CRC, "0");
  const integro = crcRecibido === crcCalculado;

  return {
    estado: integro ? "ok" : "error_detectado",
    bits: integro ? datos : null,
    bitsCorregidos: [],
    detalle: { crcRx: crcRecibido, crcCalc: crcCalculado },
  };
}
