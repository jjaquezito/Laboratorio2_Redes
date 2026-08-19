# Receptor de PRUEBA — andamio de desarrollo, no es la entrega.

from __future__ import annotations

import argparse
import json
import socketserver
import time

from app.capas import enlace, presentacion

VERDE, AMARILLO, ROJO, GRIS, FIN = "\033[32m", "\033[33m", "\033[31m", "\033[90m", "\033[0m"
COLOR_ESTADO = {
    "ok": VERDE,
    "corregido": AMARILLO,
    "error_detectado": ROJO,
    "error_no_corregible": ROJO,
}


# Una línea NDJSON por conexión (§1 del protocolo).
class Manejador(socketserver.StreamRequestHandler):

    def handle(self) -> None:
        for linea in self.rfile:
            linea = linea.strip()
            if not linea:
                continue
            inicio = time.perf_counter()

            try:
                trama = json.loads(linea)
                # ENLACE: verificar integridad y, si se puede, corregir.
                verificado = enlace.verificar_integridad(
                    trama["trama"], trama["algoritmo"], trama.get("params") or {}
                )
                # PRESENTACIÓN: decodificar solo si la trama es confiable.
                mensaje = (
                    presentacion.decodificar_mensaje(
                        verificado["bits"], trama["longitud_original_bits"]
                    )
                    if verificado["bits"] is not None
                    else None
                )
                respuesta = {
                    "id": trama.get("id", ""),
                    "estado": verificado["estado"],
                    "mensaje": mensaje,
                    "bits_corregidos": verificado["bits_corregidos"],
                    "detalle": verificado["detalle"],
                    "ms_procesamiento": (time.perf_counter() - inicio) * 1000,
                }
            except Exception as exc:  # noqa: BLE001 — un stub no debe caerse
                respuesta = {
                    "id": "",
                    "estado": "error_no_corregible",
                    "mensaje": None,
                    "bits_corregidos": [],
                    "detalle": {"excepcion": str(exc)},
                    "ms_procesamiento": (time.perf_counter() - inicio) * 1000,
                }

            estado = respuesta["estado"]
            color = COLOR_ESTADO.get(estado, GRIS)
            print(
                f"{GRIS}{respuesta['id'][:8]}{FIN} "
                f"{color}{estado:<20}{FIN} {respuesta['mensaje']!r}",
                flush=True,
            )

            self.wfile.write(
                (json.dumps(respuesta, ensure_ascii=False) + "\n").encode("utf-8")
            )


class Servidor(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Receptor de prueba (andamio de desarrollo, no es la entrega)."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--puerto", type=int, default=5001)
    args = parser.parse_args()

    with Servidor((args.host, args.puerto), Manejador) as servidor:
        print(
            f"receptor de PRUEBA escuchando en {args.host}:{args.puerto}\n"
            f"{GRIS}(andamio de desarrollo: el receptor real va en TypeScript){FIN}",
            flush=True,
        )
        try:
            servidor.serve_forever()
        except KeyboardInterrupt:
            print("\ndetenido")


if __name__ == "__main__":
    main()
