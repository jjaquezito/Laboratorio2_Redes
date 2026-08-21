// Hamming(n, m) por bloques. Especificación: shared/PROTOCOLO.md §5.
// Debe producir lo mismo que hamming.py del emisor (shared/vectores.json).

export const NOMBRE = "hamming" as const;
export const TIPO = "correccion" as const;

export const M_SUGERIDOS = [4, 8, 11, 16] as const;

// Parámetros o trama inválidos para Hamming.
export class ErrorHamming extends Error {
  constructor(mensaje: string) {
    super(mensaje);
    this.name = "ErrorHamming";
  }
}

// Mínimo `r` tal que `m + r + 1 <= 2**r`.
export function bitsDeRedundancia(m: number): number {
  if (m < 1) {
    throw new ErrorHamming(`m debe ser >= 1, se recibió ${m}`);
  }
  let r = 1;
  while (m + r + 1 > 2 ** r) r += 1;
  return r;
}

// Devuelve [n, r] para un bloque de `m` bits de datos.
export function dimensiones(m: number): [n: number, r: number] {
  const r = bitsDeRedundancia(m);
  return [m + r, r];
}

function esPotenciaDeDos(x: number): boolean {
  return x > 0 && (x & (x - 1)) === 0;
}

// Posiciones (base 1) ocupadas por bits de paridad en un bloque de `n`.
export function posicionesDeParidad(n: number): number[] {
  const posiciones: number[] = [];
  for (let p = 1; p <= n; p++) {
    if (esPotenciaDeDos(p)) posiciones.push(p);
  }
  return posiciones;
}

// Posiciones (base 1) ocupadas por bits de datos en un bloque de `n`.
export function posicionesDeDatos(n: number): number[] {
  const posiciones: number[] = [];
  for (let p = 1; p <= n; p++) {
    if (!esPotenciaDeDos(p)) posiciones.push(p);
  }
  return posiciones;
}

// Codifica exactamente `m` bits de datos en una palabra de `n` bits.
export function codificarBloque(bloque: string, m: number): string {
  if (bloque.length !== m) {
    throw new ErrorHamming(`el bloque mide ${bloque.length} bits, se esperaban ${m}`);
  }

  const [n] = dimensiones(m);

  // `palabra` está indexada desde 1: la casilla 0 no se usa.
  const palabra = new Array<number>(n + 1).fill(0);
  const posDatos = posicionesDeDatos(n);
  for (let i = 0; i < posDatos.length; i++) {
    const bit = bloque.charAt(i);
    if (bit !== "0" && bit !== "1") {
      throw new ErrorHamming(`carácter inválido en el bloque: ${JSON.stringify(bit)}`);
    }
    palabra[posDatos[i]!] = Number(bit);
  }

  // Paridad par: el bit en 2**i es el XOR de los datos que cubre.
  for (const p of posicionesDeParidad(n)) {
    let paridad = 0;
    for (let j = 1; j <= n; j++) {
      if (j !== p && j & p) paridad ^= palabra[j]!;
    }
    palabra[p] = paridad;
  }

  return palabra.slice(1).join("");
}

// XOR de los índices (base 1) cuyo bit vale 1.
// 0 = palabra íntegra; cualquier otro valor es la posición que hay que voltear.
export function sindrome(palabra: string): number {
  let s = 0;
  for (let indice = 0; indice < palabra.length; indice++) {
    if (palabra.charAt(indice) === "1") s ^= indice + 1;
  }
  return s;
}

// Recupera los `m` bits de datos de una palabra ya corregida.
export function extraerDatos(palabra: string, m: number): string {
  const [n] = dimensiones(m);
  if (palabra.length !== n) {
    throw new ErrorHamming(`la palabra mide ${palabra.length} bits, se esperaban ${n}`);
  }
  return posicionesDeDatos(n)
    .map((pos) => palabra.charAt(pos - 1))
    .join("");
}

// Salida de codificar(), con el detalle que consume la UI.
export interface ResultadoHamming {
  trama: string;
  bloques: string[];
  m: number;
  n: number;
  r: number;
  bitsRelleno: number;
  posicionesRedundancia: number[];
  readonly bitsRedundancia: number;
  readonly overhead: number;
}

// Codifica el bitstream en bloques de m bits; el último se rellena con ceros.
export function codificar(bits: string, m = 8): ResultadoHamming {
  if (!/^[01]*$/.test(bits)) {
    throw new ErrorHamming("el bitstream solo puede contener '0' y '1'");
  }
  if (!bits) {
    throw new ErrorHamming("no hay bits que codificar");
  }

  const [n, r] = dimensiones(m);

  const relleno = ((-bits.length % m) + m) % m;
  const acolchado = bits + "0".repeat(relleno);

  const bloques: string[] = [];
  for (let i = 0; i < acolchado.length; i += m) {
    bloques.push(codificarBloque(acolchado.slice(i, i + m), m));
  }

  // Posiciones absolutas de los bits de paridad, para resaltarlas en la UI.
  const paridadLocal = posicionesDeParidad(n);
  const posicionesRedundancia: number[] = [];
  for (let indice = 0; indice < bloques.length; indice++) {
    for (const p of paridadLocal) posicionesRedundancia.push(indice * n + (p - 1));
  }

  const trama = bloques.join("");
  const bitsRedundancia = bloques.length * r;

  return {
    trama,
    bloques,
    m,
    n,
    r,
    bitsRelleno: relleno,
    posicionesRedundancia,
    bitsRedundancia,
    overhead: trama.length ? bitsRedundancia / trama.length : 0,
  };
}

export type EstadoHamming = "ok" | "corregido" | "error_no_corregible";

// Salida de verificar(): lo que la capa de enlace del receptor consume.
export interface VerificacionHamming {
  estado: EstadoHamming;
  bits: string;
  bitsCorregidos: number[];
  detalle: { sindromes: number[]; m: number; n: number; r: number };
}

// Contraparte del emisor: verifica y, si puede, corrige la trama recibida.
export function verificar(trama: string, m = 8): VerificacionHamming {
  const [n, r] = dimensiones(m);
  if (trama.length % n !== 0) {
    throw new ErrorHamming(`la trama (${trama.length} bits) no es múltiplo de n=${n}`);
  }

  const datos: string[] = [];
  const sindromes: number[] = [];
  const corregidos: number[] = [];
  let corregible = true;

  for (let indice = 0; indice < trama.length; indice += n) {
    let palabra = trama.slice(indice, indice + n);
    const s = sindrome(palabra);
    sindromes.push(s);

    if (s === 0) {
      // intacto
    } else if (s <= n) {
      const posicion = s - 1;
      const flip = palabra.charAt(posicion) === "0" ? "1" : "0";
      palabra = palabra.slice(0, posicion) + flip + palabra.slice(posicion + 1);
      corregidos.push(indice + posicion);
    } else {
      // Síndrome fuera de rango: >= 2 errores en el bloque.
      corregible = false;
    }

    datos.push(extraerDatos(palabra, m));
  }

  const estado: EstadoHamming = !corregible ? "error_no_corregible" : corregidos.length ? "corregido" : "ok";

  return {
    estado,
    bits: datos.join(""),
    bitsCorregidos: corregidos,
    detalle: { sindromes, m, n, r },
  };
}
