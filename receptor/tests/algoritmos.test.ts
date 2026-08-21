// Tests de los algoritmos contra los vectores dorados de shared/vectores.json.

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

import * as crc32 from "../src/algoritmos/crc32.js";
import * as hamming from "../src/algoritmos/hamming.js";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

interface VectorDorado {
  mensaje: string;
  algoritmo: "hamming" | "crc32";
  params: { m?: number };
  bits_ascii: string;
  longitud_original_bits: number;
  trama_esperada: string;
  bits_redundancia: number;
  bits_relleno: number;
}

interface Vectores {
  crc32_vector_canonico: { entrada: string; esperado_hex: string };
  hamming_dimensiones: Record<string, { n: number; r: number }>;
  vectores: VectorDorado[];
}

const VECTORES: Vectores = JSON.parse(
  readFileSync(path.join(RAIZ, "shared", "vectores.json"), "utf-8"),
);

function voltear(bits: string, indice: number): string {
  const flip = bits.charAt(indice) === "0" ? "1" : "0";
  return bits.slice(0, indice) + flip + bits.slice(indice + 1);
}

// "Hola mundo" en ASCII binario, tomado de shared/vectores.json.
const BITS_HOLA_MUNDO = VECTORES.vectores.find(
  (v) => v.mensaje === "Hola mundo" && v.algoritmo === "hamming" && v.params.m === 8,
)!.bits_ascii;

describe("crc32", () => {
  // PROTOCOLO.md §6: si esto falla, nada más importa.
  it("vector canónico", () => {
    const esperado = parseInt(VECTORES.crc32_vector_canonico.esperado_hex, 16);
    expect(crc32.crc32Bytes(new TextEncoder().encode("123456789"))).toBe(esperado);
    expect(esperado).toBe(0xcbf43926);
  });

  // El enunciado exige padding cuando el mensaje mide menos de 32 bits.
  it("rellena hasta 32 bits", () => {
    const resultado = crc32.codificar("01000001"); // 'A'
    expect(resultado.bitsRelleno).toBe(24);
    expect(resultado.bitsDatos.length).toBe(32);
    expect(resultado.trama.length).toBe(64);
  });

  it("detecta un error de un bit", () => {
    const trama = crc32.codificar(BITS_HOLA_MUNDO).trama;
    expect(crc32.verificar(trama).estado).toBe("ok");
    for (let indice = 0; indice < trama.length; indice++) {
      expect(crc32.verificar(voltear(trama, indice)).estado).toBe("error_detectado");
    }
  });

  it("rechaza trama demasiado corta", () => {
    expect(() => crc32.verificar("1".repeat(32))).toThrow(crc32.ErrorCRC32);
  });
});

describe("hamming", () => {
  // PROTOCOLO.md §5: m=4->n=7 · m=8->n=12 · m=11->n=15 · m=16->n=21.
  it.each([
    [4, 7, 3],
    [8, 12, 4],
    [11, 15, 4],
    [16, 21, 5],
  ])("dimensiones de referencia m=%i -> n=%i, r=%i", (m, n, r) => {
    expect(hamming.dimensiones(m)).toEqual([n, r]);
    const esperado = VECTORES.hamming_dimensiones[String(m)]!;
    expect(n).toBe(esperado.n);
    expect(r).toBe(esperado.r);
  });

  // r es el mínimo que satisface m + r + 1 <= 2**r.
  it.each([1, 2, 4, 8, 11, 16, 32, 57])("cumple la desigualdad para m=%i", (m) => {
    const r = hamming.bitsDeRedundancia(m);
    expect(m + r + 1).toBeLessThanOrEqual(2 ** r);
    expect(m + (r - 1) + 1).toBeGreaterThan(2 ** (r - 1));
  });

  // Inyecta 1 error en cada una de las n posiciones y exige corrección.
  it.each([4, 8, 11, 16])("corrige un error en cada posición (m=%i)", (m) => {
    const [n] = hamming.dimensiones(m);
    const datos = Array.from({ length: m }, (_, i) => ((i * 7 + 3) % 2).toString()).join("");
    const trama = hamming.codificar(datos, m).trama;
    expect(trama.length).toBe(n);

    for (let indice = 0; indice < n; indice++) {
      const resultado = hamming.verificar(voltear(trama, indice), m);
      expect(resultado.estado).toBe("corregido");
      expect(resultado.bitsCorregidos).toEqual([indice]);
      expect(resultado.bits).toBe(datos);
    }
  });

  it("sin errores es ok", () => {
    const bits = BITS_HOLA_MUNDO;
    const trama = hamming.codificar(bits, 8).trama;
    const resultado = hamming.verificar(trama, 8);
    expect(resultado.estado).toBe("ok");
    expect(resultado.bitsCorregidos).toEqual([]);
    expect(resultado.bits.slice(0, bits.length)).toBe(bits);
  });

  // El modo por bloques corrige 1 error *por bloque*, no 1 en toda la trama.
  it("corrige un error por bloque", () => {
    const bits = BITS_HOLA_MUNDO;
    const codificado = hamming.codificar(bits, 8);
    const n = codificado.n;
    let trama = codificado.trama;

    for (let bloque = 0; bloque < codificado.bloques.length; bloque++) {
      trama = voltear(trama, bloque * n + (bloque % n));
    }

    const resultado = hamming.verificar(trama, 8);
    expect(resultado.estado).toBe("corregido");
    expect(resultado.bitsCorregidos.length).toBe(codificado.bloques.length);
    expect(resultado.bits.slice(0, bits.length)).toBe(bits);
  });

  it("rechaza trama desalineada", () => {
    expect(() => hamming.verificar("1".repeat(13), 8)).toThrow(hamming.ErrorHamming);
  });
});

describe("vectores dorados", () => {
  for (const vector of VECTORES.vectores) {
    const etiqueta = `${vector.mensaje} / ${vector.algoritmo}${vector.params.m ? ` m=${vector.params.m}` : ""}`;

    it(`codifica igual que el emisor: ${etiqueta}`, () => {
      expect(vector.bits_ascii.length).toBe(vector.longitud_original_bits);

      // bits_redundancia en el vector es overhead total (trama - original),
      // no la propiedad bitsRedundancia del algoritmo.
      if (vector.algoritmo === "hamming") {
        const resultado = hamming.codificar(vector.bits_ascii, vector.params.m ?? 8);
        expect(resultado.trama).toBe(vector.trama_esperada);
        expect(resultado.trama.length - vector.longitud_original_bits).toBe(vector.bits_redundancia);
        expect(resultado.bitsRelleno).toBe(vector.bits_relleno);
      } else {
        const resultado = crc32.codificar(vector.bits_ascii);
        expect(resultado.trama).toBe(vector.trama_esperada);
        expect(resultado.trama.length - vector.longitud_original_bits).toBe(vector.bits_redundancia);
        expect(resultado.bitsRelleno).toBe(vector.bits_relleno);
      }
    });

    it(`decodifica ida y vuelta: ${etiqueta}`, () => {
      if (vector.algoritmo === "hamming") {
        const resultado = hamming.verificar(vector.trama_esperada, vector.params.m ?? 8);
        expect(resultado.estado).toBe("ok");
        expect(resultado.bits.slice(0, vector.longitud_original_bits)).toBe(vector.bits_ascii);
      } else {
        const resultado = crc32.verificar(vector.trama_esperada);
        expect(resultado.estado).toBe("ok");
        expect(resultado.bits!.slice(0, vector.longitud_original_bits)).toBe(vector.bits_ascii);
      }
    });
  }
});
