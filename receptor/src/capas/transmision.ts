// -----------------------------------------------------------------------------
// Capa de TRANSMISIÓN — servicio recibir_informacion
// Especificación: shared/PROTOCOLO.md §1 y §3
// -----------------------------------------------------------------------------
// Canal  : TCP con NDJSON — un objeto JSON por línea, terminado en \n, UTF-8
// Puerto : 5001 por defecto
// Sesión : el receptor siempre está escuchando; el emisor abre una conexión
//          por mensaje, así que cada socket puede traer varias líneas o solo
//          una — se procesa línea por línea a medida que llegan
//
// Por cada trama de datos recibida, se responde por el mismo socket con un
// objeto de telemetría (§3). Esa respuesta es una extensión fuera del
// enunciado: alimenta la UI y la suite de experimentos del emisor.
// -----------------------------------------------------------------------------

import net from "node:net";
import type { TramaRecibida, ResultadoRecepcion } from "./aplicacion.js";

export const HOST_POR_DEFECTO = "0.0.0.0";
export const PUERTO_POR_DEFECTO = 5001;

// Trama de datos tal como llega por el socket (§2 del protocolo).
export interface TramaEntrante extends TramaRecibida {
  id: string;
}

// Telemetría de vuelta al emisor (§3 del protocolo).
export interface Telemetria {
  id: string;
  estado: string;
  mensaje: string | null;
  bits_corregidos: number[];
  detalle: Record<string, unknown>;
  ms_procesamiento: number;
}

export type Manejador = (trama: TramaEntrante) => ResultadoRecepcion;

// Procesa una línea NDJSON: parsea, delega a `manejar` y arma la telemetría.
// Cualquier excepción (JSON inválido, algoritmo desconocido, trama
// desalineada) se reporta como `error_no_corregible` en vez de tumbar la
// conexión — el receptor siempre debe seguir escuchando.
export function procesarLinea(linea: string, manejar: Manejador): Telemetria {
  const inicio = performance.now();
  let id = "";
  try {
    const trama = JSON.parse(linea) as TramaEntrante;
    id = typeof trama.id === "string" ? trama.id : "";
    const resultado = manejar(trama);
    return {
      id,
      estado: resultado.estado,
      mensaje: resultado.mensaje,
      bits_corregidos: resultado.bitsCorregidos,
      detalle: resultado.detalle,
      ms_procesamiento: performance.now() - inicio,
    };
  } catch (exc) {
    return {
      id,
      estado: "error_no_corregible",
      mensaje: null,
      bits_corregidos: [],
      detalle: { excepcion: exc instanceof Error ? exc.message : String(exc) },
      ms_procesamiento: performance.now() - inicio,
    };
  }
}

// Levanta el servidor TCP. Una conexión puede traer varias líneas NDJSON
// seguidas; se van despachando a medida que se completan.
export function crearServidor(manejar: Manejador): net.Server {
  return net.createServer((socket) => {
    socket.setEncoding("utf-8");
    let buffer = "";

    socket.on("data", (chunk) => {
      buffer += chunk;
      let indice = buffer.indexOf("\n");
      while (indice !== -1) {
        const linea = buffer.slice(0, indice).trim();
        buffer = buffer.slice(indice + 1);
        if (linea) {
          const respuesta = procesarLinea(linea, manejar);
          socket.write(`${JSON.stringify(respuesta)}\n`);
        }
        indice = buffer.indexOf("\n");
      }
    });

    socket.on("error", () => {
      // Conexión cortada por el emisor: no hay nada que responder.
    });
  });
}

// Arranca el servidor y devuelve una promesa que resuelve cuando ya escucha.
export function escuchar(
  manejar: Manejador,
  host: string = HOST_POR_DEFECTO,
  puerto: number = PUERTO_POR_DEFECTO,
): Promise<net.Server> {
  const servidor = crearServidor(manejar);
  return new Promise((resolve, reject) => {
    servidor.once("error", reject);
    servidor.listen(puerto, host, () => {
      servidor.removeListener("error", reject);
      resolve(servidor);
    });
  });
}
