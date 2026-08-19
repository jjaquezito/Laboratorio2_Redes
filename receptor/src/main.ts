// -----------------------------------------------------------------------------
// RECEPTOR — punto de entrada
// -----------------------------------------------------------------------------
// Levanta el servidor TCP (§1 y §3 del protocolo) y conecta cada trama
// entrante con la capa de aplicación: ENLACE -> PRESENTACIÓN -> APLICACIÓN.
//
// Arranque:  npm run dev   (o: node dist/main.js --host 0.0.0.0 --puerto 5001)
// -----------------------------------------------------------------------------

import * as aplicacion from "./capas/aplicacion.js";
import * as transmision from "./capas/transmision.js";

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

function leerArgumentos(argv: string[]): { host: string; puerto: number } {
  let host = transmision.HOST_POR_DEFECTO;
  let puerto = transmision.PUERTO_POR_DEFECTO;

  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--host" && argv[i + 1]) {
      host = argv[i + 1]!;
      i++;
    } else if (argv[i] === "--puerto" && argv[i + 1]) {
      puerto = Number(argv[i + 1]);
      i++;
    }
  }

  return { host, puerto };
}

async function main(): Promise<void> {
  const { host, puerto } = leerArgumentos(process.argv.slice(2));

  await transmision.escuchar((trama) => {
    const resultado = aplicacion.procesarTrama(trama);
    const color = COLOR_ESTADO[resultado.estado] ?? GRIS;
    console.log(
      `${GRIS}${(trama.id ?? "").slice(0, 8)}${FIN} ${color}${resultado.estado.padEnd(20)}${FIN} ${JSON.stringify(resultado.mensaje)}`,
    );
    return resultado;
  }, host, puerto);

  console.log(`receptor escuchando en ${host}:${puerto}`);
}

main().catch((exc) => {
  console.error("no se pudo levantar el receptor:", exc);
  process.exitCode = 1;
});
