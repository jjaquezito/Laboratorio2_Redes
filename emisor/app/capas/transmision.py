# -----------------------------------------------------------------------------
# Capa de TRANSMISIÓN — servicio enviar_informacion
# Especificación: shared/PROTOCOLO.md §1 y §3
# -----------------------------------------------------------------------------
# Canal  : TCP con NDJSON — un objeto JSON por línea, terminado en \n, UTF-8
# Puerto : 5001 por defecto
# Sesión : una conexión por mensaje, para que el receptor pueda reiniciarse sin
#          dejar al emisor en un estado inválido
#
# El receptor responde por el mismo socket con un objeto de telemetría (§3).
# Esa respuesta es una extensión fuera del enunciado: alimenta la UI y la suite
# de experimentos. El flujo obligatorio del laboratorio sigue siendo
# unidireccional, así que esperarla nunca condiciona el éxito del envío.
# -----------------------------------------------------------------------------

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from typing import Any

# En Docker Compose, RECEPTOR_HOST=receptor; en desarrollo local cae en localhost.
HOST_POR_DEFECTO = os.environ.get("RECEPTOR_HOST", "127.0.0.1")
PUERTO_POR_DEFECTO = int(os.environ.get("RECEPTOR_PUERTO", "5001"))
TIMEOUT_POR_DEFECTO = 5.0


# No se pudo establecer o sostener la conexión con el receptor.
class ErrorTransmision(OSError):
    pass


# Respuesta del receptor (§3 del protocolo).
@dataclass
class Telemetria:

    id: str
    estado: str
    mensaje: str | None = None
    bits_corregidos: list[int] = field(default_factory=list)
    detalle: dict[str, Any] = field(default_factory=dict)
    ms_procesamiento: float | None = None

    @classmethod
    def desde_json(cls, crudo: dict[str, Any]) -> "Telemetria":
        return cls(
            id=crudo.get("id", ""),
            estado=crudo.get("estado", "desconocido"),
            mensaje=crudo.get("mensaje"),
            bits_corregidos=crudo.get("bits_corregidos") or [],
            detalle=crudo.get("detalle") or {},
            ms_procesamiento=crudo.get("ms_procesamiento"),
        )


# Lee una línea NDJSON del socket. Devuelve ``None`` si el par cierra.
def _leer_linea(sock: socket.socket) -> str | None:
    buffer = bytearray()
    while True:
        try:
            trozo = sock.recv(4096)
        except socket.timeout:
            return None
        if not trozo:
            return None
        buffer.extend(trozo)
        if b"\n" in buffer:
            linea, _, _ = buffer.partition(b"\n")
            return linea.decode("utf-8")


# Abre el socket, envía una línea NDJSON y opcionalmente lee la respuesta.
# Una conexión por mensaje: así el receptor puede reiniciarse sin dejar al
# emisor en un estado inválido.
def enviar_informacion(
    trama_json: dict[str, Any],
    host: str = HOST_POR_DEFECTO,
    puerto: int = PUERTO_POR_DEFECTO,
    timeout: float = TIMEOUT_POR_DEFECTO,
    esperar_telemetria: bool = True,
) -> Telemetria | None:
    linea = json.dumps(trama_json, ensure_ascii=False, separators=(",", ":")) + "\n"

    try:
        with socket.create_connection((host, puerto), timeout=timeout) as sock:
            sock.sendall(linea.encode("utf-8"))
            if not esperar_telemetria:
                return None

            respuesta = _leer_linea(sock)
            if respuesta is None:
                return None
            try:
                return Telemetria.desde_json(json.loads(respuesta))
            except json.JSONDecodeError as exc:
                raise ErrorTransmision(
                    f"el receptor respondió algo que no es JSON: {respuesta[:120]!r}"
                ) from exc

    except ConnectionRefusedError as exc:
        raise ErrorTransmision(
            f"no hay ningún receptor escuchando en {host}:{puerto}. "
            "Levanta el receptor antes de enviar."
        ) from exc
    except socket.timeout as exc:
        raise ErrorTransmision(
            f"tiempo de espera agotado ({timeout}s) hablando con {host}:{puerto}"
        ) from exc
    except OSError as exc:
        raise ErrorTransmision(f"fallo de red contra {host}:{puerto}: {exc}") from exc


# ``True`` si hay un receptor escuchando. La UI lo usa como indicador.
def probar_conexion(
    host: str = HOST_POR_DEFECTO,
    puerto: int = PUERTO_POR_DEFECTO,
    timeout: float = 1.0,
) -> bool:
    try:
        with socket.create_connection((host, puerto), timeout=timeout):
            return True
    except OSError:
        return False
