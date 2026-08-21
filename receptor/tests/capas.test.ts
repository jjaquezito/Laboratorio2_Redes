// Tests de las capas del receptor y del contrato de trama.

import { readFileSync } from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import * as aplicacion from "../src/capas/aplicacion.js";
import * as enlace from "../src/capas/enlace.js";
import * as presentacion from "../src/capas/presentacion.js";
import * as transmision from "../src/capas/transmision.js";

const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

interface VectorDorado {
  mensaje: string;
  algoritmo: "hamming" | "crc32";
  params: { m?: number };
  bits_ascii: string;
  longitud_original_bits: number;
  trama_esperada: string;
}

const VECTORES: { vectores: VectorDorado[] } = JSON.parse(
  readFileSync(path.join(RAIZ, "shared", "vectores.json"), "utf-8"),
);

function voltear(bits: string, indice: number): string {
  const flip = bits.charAt(indice) === "0" ? "1" : "0";
  return bits.slice(0, indice) + flip + bits.slice(indice + 1);
}

function vector(mensaje: string, algoritmo: "hamming" | "crc32", m?: number): VectorDorado {
  const encontrado = VECTORES.vectores.find(
    (v) => v.mensaje === mensaje && v.algoritmo === algoritmo && v.params.m === m,
  );
  if (!encontrado) throw new Error(`vector no encontrado: ${mensaje}/${algoritmo}/m=${m}`);
  return encontrado;
}

describe("presentacion", () => {
  it("decodifica ASCII de 8 bits", () => {
    expect(presentacion.decodificarMensaje("01000001")).toBe("A");
    expect(presentacion.decodificarMensaje("0100100001101001")).toBe("Hi");
  });

  it("descarta el relleno con longitudOriginalBits", () => {
    const bits = "0100100001101001";
    expect(presentacion.decodificarMensaje(bits + "0".repeat(24), bits.length)).toBe("Hi");
  });

  it("rechaza longitud desalineada", () => {
    expect(() => presentacion.decodificarMensaje("0101")).toThrow(presentacion.ErrorPresentacion);
  });
});

describe("enlace", () => {
  it("normaliza params", () => {
    expect(enlace.normalizarParams("hamming", undefined)).toEqual({ m: 8 });
    expect(enlace.normalizarParams("hamming", { m: 16 })).toEqual({ m: 16 });
    expect(enlace.normalizarParams("crc32", { m: 8 })).toEqual({});
  });

  it("rechaza algoritmo desconocido", () => {
    expect(() => enlace.normalizarParams("fletcher", undefined)).toThrow(enlace.ErrorEnlace);
  });

  it("verifica una trama Hamming íntegra", () => {
    const v = vector("Hola mundo", "hamming", 8);
    const resultado = enlace.verificarIntegridad(v.trama_esperada, "hamming", { m: 8 });
    expect(resultado.estado).toBe("ok");
    expect(resultado.bits).not.toBeNull();
  });

  it("verifica una trama CRC-32 íntegra", () => {
    const v = vector("Hola mundo", "crc32");
    const resultado = enlace.verificarIntegridad(v.trama_esperada, "crc32", {});
    expect(resultado.estado).toBe("ok");
  });
});

describe("aplicacion.procesarTrama", () => {
  it("mensaje íntegro sale igual al original (hamming)", () => {
    const v = vector("Hola mundo", "hamming", 8);
    const resultado = aplicacion.procesarTrama({
      algoritmo: v.algoritmo,
      params: v.params,
      longitud_original_bits: v.longitud_original_bits,
      trama: v.trama_esperada,
    });
    expect(resultado.estado).toBe("ok");
    expect(resultado.mensaje).toBe(v.mensaje);
  });

  it("corrige 1 bit inyectado (hamming) y recupera el mensaje", () => {
    const v = vector("Hola mundo", "hamming", 8);
    const conError = voltear(v.trama_esperada, 3);
    const resultado = aplicacion.procesarTrama({
      algoritmo: v.algoritmo,
      params: v.params,
      longitud_original_bits: v.longitud_original_bits,
      trama: conError,
    });
    expect(resultado.estado).toBe("corregido");
    expect(resultado.mensaje).toBe(v.mensaje);
  });

  it("detecta 1 bit inyectado (crc32) y no entrega mensaje", () => {
    const v = vector("Hola mundo", "crc32");
    const conError = voltear(v.trama_esperada, 3);
    const resultado = aplicacion.procesarTrama({
      algoritmo: v.algoritmo,
      params: v.params,
      longitud_original_bits: v.longitud_original_bits,
      trama: conError,
    });
    expect(resultado.estado).toBe("error_detectado");
    expect(resultado.mensaje).toBeNull();
  });
});

describe("transmision", () => {
  it("recibe NDJSON y responde telemetría por el mismo socket", async () => {
    const servidor = await transmision.escuchar(aplicacion.procesarTrama, "127.0.0.1", 0);
    const direccion = servidor.address();
    if (direccion === null || typeof direccion === "string") throw new Error("dirección inesperada");
    const puerto = direccion.port;

    try {
      const v = vector("Hola mundo", "hamming", 8);
      const trama = {
        id: "test-id-123",
        algoritmo: v.algoritmo,
        params: v.params,
        longitud_original_bits: v.longitud_original_bits,
        trama: v.trama_esperada,
      };

      const respuesta = await new Promise<string>((resolve, reject) => {
        const socket = net.createConnection({ host: "127.0.0.1", port: puerto }, () => {
          socket.write(`${JSON.stringify(trama)}\n`);
        });
        let buffer = "";
        socket.setEncoding("utf-8");
        socket.on("data", (chunk) => {
          buffer += chunk;
          if (buffer.includes("\n")) {
            socket.end();
            resolve(buffer);
          }
        });
        socket.on("error", reject);
      });

      const telemetria = JSON.parse(respuesta.trim()) as transmision.Telemetria;
      expect(telemetria.id).toBe("test-id-123");
      expect(telemetria.estado).toBe("ok");
      expect(telemetria.mensaje).toBe("Hola mundo");
      expect(typeof telemetria.ms_procesamiento).toBe("number");
    } finally {
      servidor.close();
    }
  });

  it("reporta error_no_corregible ante JSON inválido, sin tumbar el servidor", async () => {
    const servidor = await transmision.escuchar(aplicacion.procesarTrama, "127.0.0.1", 0);
    const direccion = servidor.address();
    if (direccion === null || typeof direccion === "string") throw new Error("dirección inesperada");
    const puerto = direccion.port;

    try {
      const respuesta = await new Promise<string>((resolve, reject) => {
        const socket = net.createConnection({ host: "127.0.0.1", port: puerto }, () => {
          socket.write("{esto no es json}\n");
        });
        let buffer = "";
        socket.setEncoding("utf-8");
        socket.on("data", (chunk) => {
          buffer += chunk;
          if (buffer.includes("\n")) {
            socket.end();
            resolve(buffer);
          }
        });
        socket.on("error", reject);
      });

      const telemetria = JSON.parse(respuesta.trim()) as transmision.Telemetria;
      expect(telemetria.estado).toBe("error_no_corregible");
      expect(telemetria.mensaje).toBeNull();
    } finally {
      servidor.close();
    }
  });
});
