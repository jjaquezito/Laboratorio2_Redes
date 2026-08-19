# -----------------------------------------------------------------------------
# CLI del emisor — ejercita la pila completa sin levantar la interfaz web
# -----------------------------------------------------------------------------
# Enviar un mensaje al receptor (debe estar escuchando en el puerto 5001):
#   python -m app.cli enviar "Hola mundo" --algoritmo hamming --m 8 --error 1/100
#
# Ver la trama capa por capa sin abrir el socket:
#   python -m app.cli enviar "Hola mundo" --algoritmo crc32 --error 0.01 --sin-enviar
#
# Barrido de experimentos y exportación a CSV:
#   python -m app.cli experimentos --repeticiones 200 --salida barrido.csv
#
# La salida colorea la redundancia en verde y los bits volteados en rojo.
# -----------------------------------------------------------------------------

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .capas import aplicacion, enlace, presentacion, transmision
from .experimentos import runner

VERDE = "\033[32m"
ROJO = "\033[31m"
AMARILLO = "\033[33m"
GRIS = "\033[90m"
NEGRITA = "\033[1m"
FIN = "\033[0m"


def _color(texto: str, codigo: str, usar_color: bool) -> str:
    return f"{codigo}{texto}{FIN}" if usar_color else texto


# Dibuja la trama con la redundancia en verde y los bits volteados en rojo.
def pintar_trama(
    trama: str,
    redundancia: set[int],
    volteados: set[int],
    usar_color: bool,
    ancho: int = 72,
) -> str:
    piezas = []
    for indice, bit in enumerate(trama):
        if indice in volteados:
            piezas.append(_color(bit, ROJO + NEGRITA, usar_color))
        elif indice in redundancia:
            piezas.append(_color(bit, VERDE, usar_color))
        else:
            piezas.append(bit)

    lineas = []
    for inicio in range(0, len(trama), ancho):
        etiqueta = _color(f"{inicio:>5} ", GRIS, usar_color)
        lineas.append(etiqueta + "".join(piezas[inicio : inicio + ancho]))
    return "\n".join(lineas)


def comando_enviar(args: argparse.Namespace) -> int:
    usar_color = sys.stdout.isatty() and not args.sin_color
    params = {"m": args.m} if args.algoritmo == "hamming" else {}

    try:
        if args.sin_enviar:
            resultado = aplicacion.preparar_envio(
                args.mensaje, args.algoritmo, params,
                tasa_error=args.error, semilla=args.semilla,
                modo_ruido=args.modo_ruido, parametro_ruido=args.parametro_ruido,
            )
        else:
            resultado = aplicacion.solicitar_mensaje(
                args.mensaje, args.algoritmo, params,
                tasa_error=args.error, semilla=args.semilla,
                modo_ruido=args.modo_ruido, parametro_ruido=args.parametro_ruido,
                host=args.host, puerto=args.puerto,
            )
    except (aplicacion.ErrorAplicacion, enlace.ErrorEnlace,
            presentacion.ErrorPresentacion, ValueError) as exc:
        print(_color(f"error: {exc}", ROJO, usar_color), file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(resultado.a_dict(), ensure_ascii=False, indent=2))
        return 0 if (args.sin_enviar or resultado.enviado) else 1

    etiqueta = runner.etiquetar(resultado.algoritmo, resultado.params)
    print(f"\n{_color('APLICACIÓN', NEGRITA, usar_color)}    mensaje={resultado.mensaje!r}")
    print(f"              algoritmo={etiqueta}  tasa_error={resultado.tasa_error}")
    print(f"\n{_color('PRESENTACIÓN', NEGRITA, usar_color)}  {len(resultado.bits_ascii)} bits ASCII")
    print(pintar_trama(resultado.bits_ascii, set(), set(), usar_color))

    print(
        f"\n{_color('ENLACE', NEGRITA, usar_color)}        {len(resultado.trama_enlace)} bits "
        f"(+{resultado.bits_redundancia} de redundancia, "
        f"overhead {resultado.overhead:.1%})  "
        + _color("redundancia en verde", VERDE, usar_color)
    )
    print(pintar_trama(
        resultado.trama_enlace, set(resultado.posiciones_redundancia), set(), usar_color
    ))

    print(
        f"\n{_color('RUIDO', NEGRITA, usar_color)}         {resultado.bits_volteados} bits volteados  "
        + _color("volteados en rojo", ROJO, usar_color)
    )
    print(pintar_trama(
        resultado.trama_transmitida,
        set(resultado.posiciones_redundancia),
        set(resultado.posiciones_volteadas),
        usar_color,
    ))
    if resultado.posiciones_volteadas:
        print(_color(f"              posiciones: {resultado.posiciones_volteadas}", GRIS, usar_color))

    if args.sin_enviar:
        print(f"\n{_color('TRANSMISIÓN', NEGRITA, usar_color)}   (omitida: --sin-enviar)\n")
        return 0

    print(f"\n{_color('TRANSMISIÓN', NEGRITA, usar_color)}   {args.host}:{args.puerto}")
    if not resultado.enviado:
        print(_color(f"              FALLÓ — {resultado.error_transmision}", ROJO, usar_color) + "\n")
        return 1

    telemetria = resultado.telemetria or {}
    estado = telemetria.get("estado", "sin respuesta")
    colores = {
        "ok": VERDE, "corregido": AMARILLO,
        "error_detectado": ROJO, "error_no_corregible": ROJO,
    }
    print(f"              enviado ({len(resultado.trama_transmitida)} bits)")
    print(f"\n{_color('RECEPTOR', NEGRITA, usar_color)}      estado={_color(estado, colores.get(estado, ''), usar_color)}")
    print(f"              mensaje={telemetria.get('mensaje')!r}")
    if telemetria.get("bits_corregidos"):
        print(f"              bits_corregidos={telemetria['bits_corregidos']}")

    intacto = telemetria.get("mensaje") == resultado.mensaje
    veredicto = (
        _color("✓ el mensaje llegó íntegro", VERDE, usar_color) if intacto
        else _color("✗ el mensaje NO se recuperó", ROJO, usar_color)
    )
    print(f"\n{veredicto}\n")
    return 0 if intacto else 1


def comando_experimentos(args: argparse.Namespace) -> int:
    configuraciones = [
        ("hamming", {"m": m}) for m in args.m_hamming
    ] + ([("crc32", {})] if args.crc32 else [])

    def progreso(hechas: int, total: int) -> None:
        print(f"\r  {hechas}/{total} celdas", end="", file=sys.stderr, flush=True)

    agregados = list(runner.barrer(
        tamanos=args.tamanos, bers=args.bers, configuraciones=configuraciones,
        repeticiones=args.repeticiones, semilla=args.semilla,
        modo=args.modo, host=args.host, puerto=args.puerto, progreso=progreso,
    ))
    print(file=sys.stderr)

    csv = runner.a_csv(agregados)
    if args.salida:
        destino = Path(args.salida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(csv, encoding="utf-8")
        print(f"{len(agregados)} filas -> {destino}")
    else:
        print(csv, end="")
    return 0


def comando_estado(args: argparse.Namespace) -> int:
    vivo = transmision.probar_conexion(args.host, args.puerto)
    print(f"receptor {args.host}:{args.puerto}: {'escuchando' if vivo else 'sin respuesta'}")
    return 0 if vivo else 1


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="emisor",
        description="Emisor del Laboratorio 2 (CC3067 Redes) — capas, ruido y envío.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    def agregar_destino(p: argparse.ArgumentParser) -> None:
        p.add_argument("--host", default=transmision.HOST_POR_DEFECTO)
        p.add_argument("--puerto", type=int, default=transmision.PUERTO_POR_DEFECTO)

    enviar = sub.add_parser("enviar", help="envía un mensaje por la pila completa")
    enviar.add_argument("mensaje")
    enviar.add_argument("--algoritmo", choices=enlace.ALGORITMOS, default="hamming")
    enviar.add_argument("--m", type=int, default=8, help="bits de datos por bloque Hamming")
    enviar.add_argument("--error", default="0", help="tasa de error: 0.01, 1/100, 5%%")
    enviar.add_argument("--semilla", type=int, default=None)
    enviar.add_argument("--modo-ruido", choices=("bernoulli", "exactos", "rafaga"), default="bernoulli")
    enviar.add_argument("--parametro-ruido", type=int, default=None)
    enviar.add_argument("--sin-enviar", action="store_true", help="no abre el socket")
    enviar.add_argument("--json", action="store_true")
    enviar.add_argument("--sin-color", action="store_true")
    agregar_destino(enviar)
    enviar.set_defaults(func=comando_enviar)

    exp = sub.add_parser("experimentos", help="barrido de métricas y exportación CSV")
    exp.add_argument("--tamanos", type=int, nargs="+", default=list(runner.TAMANOS_POR_DEFECTO))
    exp.add_argument("--bers", type=float, nargs="+", default=list(runner.BER_POR_DEFECTO))
    exp.add_argument("--m-hamming", type=int, nargs="+", default=[8, 16])
    exp.add_argument("--sin-crc32", dest="crc32", action="store_false")
    exp.add_argument("--repeticiones", type=int, default=runner.REPETICIONES_POR_DEFECTO)
    exp.add_argument("--semilla", type=int, default=2026)
    exp.add_argument("--modo", choices=("local", "socket"), default="local")
    exp.add_argument("--salida", default=None, help="ruta del CSV; por defecto stdout")
    agregar_destino(exp)
    exp.set_defaults(func=comando_experimentos)

    estado = sub.add_parser("estado", help="¿hay un receptor escuchando?")
    agregar_destino(estado)
    estado.set_defaults(func=comando_estado)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
