// -----------------------------------------------------------------------------
// Capa de PRESENTACIÓN — servicio decodificar_mensaje
// Especificación: shared/PROTOCOLO.md §4
// -----------------------------------------------------------------------------
// Codificación : ASCII de 8 bits por carácter, MSB primero.  '01000001' -> 'A'
// Relleno      : longitudOriginalBits recorta el padding que agregó la capa
//                de enlace del emisor antes de decodificar
// -----------------------------------------------------------------------------

export const BITS_POR_CARACTER = 8;

// El bitstream no es representable en ASCII de 8 bits.
export class ErrorPresentacion extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorPresentacion";
  }
}

// Convierte ASCII binario de vuelta a texto. longitudOriginalBits recorta el
// relleno que agregó la capa de enlace antes de decodificar.
export function decodificarMensaje(bits: string, longitudOriginalBits?: number): string {
  const recortado = longitudOriginalBits !== undefined ? bits.slice(0, longitudOriginalBits) : bits;
  if (recortado.length % BITS_POR_CARACTER !== 0) {
    throw new ErrorPresentacion(
      `el bitstream mide ${recortado.length} bits; debe ser múltiplo de ${BITS_POR_CARACTER}`,
    );
  }

  let texto = "";
  for (let i = 0; i < recortado.length; i += BITS_POR_CARACTER) {
    texto += String.fromCharCode(parseInt(recortado.slice(i, i + BITS_POR_CARACTER), 2));
  }
  return texto;
}
