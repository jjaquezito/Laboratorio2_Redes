// -----------------------------------------------------------------------------
// RECEPTOR — punto de entrada
// -----------------------------------------------------------------------------
// Levanta dos servidores:
//
//   TCP  (puerto 5001) — §1 y §3 del protocolo. Aquí habla el emisor: recibe
//        tramas NDJSON, las verifica/corrige y responde telemetría.
//   HTTP (puerto 3000) — Express sirve el build de React y expone un
//        WebSocket en /ws con el mismo historial en vivo (extensión fuera
//        del enunciado, igual que la telemetría del §3).
//
// Arranque:  npm run dev   (o: node dist/main.js --host 0.0.0.0 --puerto 5001 --puerto-ui 3000)
// -----------------------------------------------------------------------------

import { existsSync } from "node:fs";
import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";

import express from "express";
import { WebSocketServer } from "ws";

import * as aplicacion from "./capas/aplicacion.js";
import * as transmision from "./capas/transmision.js";
import * as estado from "./estado.js";

const PUERTO_UI_POR_DEFECTO = 3000;
const DIRECTORIO_ESTATICO = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "frontend",
  "dist",
);

const VERDE = "\x1b[32m";
const AMARILLO = "\x1b[33m";
const ROJO = "\x1b[31m";
const GRIS = "\x1b[90m";
const FIN = "\x1b[0m";

const COLOR_ESTADO: Record<string, string> = {
  ok: VERDE,
  corregido: AMARILLO,
  error_detectado: ROJO,
  error_no_corregible: ROJO,
};

interface Argumentos {
  host: string;
  puerto: number;
  puertoUi: number;
}

function leerArgumentos(argv: string[]): Argumentos {
  const args: Argumentos = {
    host: transmision.HOST_POR_DEFECTO,
    puerto: transmision.PUERTO_POR_DEFECTO,
    puertoUi: PUERTO_UI_POR_DEFECTO,
  };

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--host" && argv[i + 1]) {
      args.host = argv[i + 1]!;
      i++;
    } else if (argv[i] === "--puerto" && argv[i + 1]) {
      args.puerto = Number(argv[i + 1]);
      i++;
    } else if (argv[i] === "--puerto-ui" && argv[i + 1]) {
      args.puertoUi = Number(argv[i + 1]);
      i++;
    }
  }

  return args;
}

// Sirve el build de React; si no está compilado, un aviso en vez de un 404 opaco.
function crearAppHttp(): express.Express {
  const app = express();

  app.get("/api/historial", (_req, res) => {
    res.json(estado.obtenerSnapshot());
  });

  if (existsSync(DIRECTORIO_ESTATICO)) {
    app.use(express.static(DIRECTORIO_ESTATICO));
    app.get("*", (_req, res) => {
      res.sendFile(path.join(DIRECTORIO_ESTATICO, "index.html"));
    });
  } else {
    app.get("/", (_req, res) => {
      res.json({
        mensaje: "Backend del receptor activo. El frontend no está compilado.",
        compilar: "cd receptor/frontend && npm install && npm run build",
      });
    });
  }

  return app;
}

async function main(): Promise<void> {
  const { host, puerto, puertoUi } = leerArgumentos(process.argv.slice(2));

  const app = crearAppHttp();
  const servidorHttp = http.createServer(app);
  const wss = new WebSocketServer({ server: servidorHttp, path: "/ws" });

  wss.on("connection", (socket) => {
    socket.send(JSON.stringify({ tipo: "snapshot", datos: estado.obtenerSnapshot() }));
  });

  function difundir(registro: estado.RegistroTrama): void {
    const mensaje = JSON.stringify({ tipo: "trama", datos: registro });
    for (const cliente of wss.clients) {
      if (cliente.readyState === cliente.OPEN) cliente.send(mensaje);
    }
  }

  await transmision.escuchar((trama) => {
    const inicio = performance.now();
    const resultado = aplicacion.procesarTrama(trama);
    const msProcesamiento = performance.now() - inicio;

    const registro: estado.RegistroTrama = {
      id: trama.id ?? "",
      algoritmo: trama.algoritmo,
      params: (trama.params ?? {}) as Record<string, unknown>,
      longitudOriginalBits: trama.longitud_original_bits,
      trama: trama.trama,
      estado: resultado.estado,
      mensaje: resultado.mensaje,
      bitsCorregidos: resultado.bitsCorregidos,
      detalle: resultado.detalle,
      msProcesamiento,
      marcaDeTiempo: Date.now(),
    };
    estado.registrar(registro);
    difundir(registro);

    const color = COLOR_ESTADO[resultado.estado] ?? GRIS;
    console.log(
      `${GRIS}${(trama.id ?? "").slice(0, 8)}${FIN} ${color}${resultado.estado.padEnd(20)}${FIN} ${JSON.stringify(resultado.mensaje)}`,
    );

    return resultado;
  }, host, puerto);

  await new Promise<void>((resolve) => servidorHttp.listen(puertoUi, host, resolve));

  console.log(`receptor: datos TCP en ${host}:${puerto} · UI en http://${host}:${puertoUi}`);
}

main().catch((exc) => {
  console.error("no se pudo levantar el receptor:", exc);
  process.exitCode = 1;
});
