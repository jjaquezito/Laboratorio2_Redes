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
# Conexión reutilizable para enviar muchas tramas seguidas.
#
# `enviar_informacion` abre y cierra un socket por mensaje, lo que es lo más
# simple para un envío suelto pero no escala: cada cierre deja el puerto local en
# TIME_WAIT durante segundos y un barrido de decenas de miles de envíos agota el
# rango efímero del sistema (en macOS, 49152-65535) con "Can't assign requested
# address". NDJSON está pensado para multiplexar tramas sobre una sola conexión,
# así que la suite de experimentos usa esta clase.
#
# Si el receptor se reinicia a mitad del barrido, el siguiente envío reconecta
# de forma transparente en lugar de abortar.
class Conexion:
    def __init__(
        self,
        host: str = HOST_POR_DEFECTO,
        puerto: int = PUERTO_POR_DEFECTO,
        timeout: float = TIMEOUT_POR_DEFECTO,
    ) -> None:
        self.host = host
        self.puerto = puerto
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._buffer = bytearray()

    def __enter__(self) -> "Conexion":
        self.abrir()
        return self

    def __exit__(self, *_excepcion: object) -> None:
        self.cerrar()

    def abrir(self) -> None:
        self.cerrar()
        try:
            self._sock = socket.create_connection(
                (self.host, self.puerto), timeout=self.timeout
            )
        except ConnectionRefusedError as exc:
            raise ErrorTransmision(
                f"no hay ningún receptor escuchando en {self.host}:{self.puerto}. "
                "Levanta el receptor antes de enviar."
            ) from exc
        except OSError as exc:
            raise ErrorTransmision(
                f"fallo de red contra {self.host}:{self.puerto}: {exc}"
            ) from exc
        self._buffer.clear()

    def cerrar(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        self._buffer.clear()

    # Lee una línea NDJSON del buffer, rellenándolo desde el socket si hace falta.
    def _leer_linea(self) -> str | None:
        assert self._sock is not None
        while b"\n" not in self._buffer:
            try:
                trozo = self._sock.recv(4096)
            except socket.timeout:
                return None
            if not trozo:
                return None
            self._buffer.extend(trozo)
        linea, _, resto = self._buffer.partition(b"\n")
        self._buffer = bytearray(resto)
        return linea.decode("utf-8")

    def enviar(
        self, trama_json: dict[str, Any], esperar_telemetria: bool = True
    ) -> Telemetria | None:
        linea = (
            json.dumps(trama_json, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")

        for intento in (1, 2):
            if self._sock is None:
                self.abrir()
            try:
                self._sock.sendall(linea)  # type: ignore[union-attr]
                if not esperar_telemetria:
                    return None
                respuesta = self._leer_linea()
                if respuesta is None:
                    raise ConnectionResetError("el receptor cerró la conexión")
                return Telemetria.desde_json(json.loads(respuesta))
            except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                # El receptor se reinició: reconectar y reintentar una sola vez.
                self.cerrar()
                if intento == 2:
                    raise ErrorTransmision(
                        f"el receptor en {self.host}:{self.puerto} cerró la conexión"
                    ) from None
            except socket.timeout as exc:
                self.cerrar()
                raise ErrorTransmision(
                    f"tiempo de espera agotado ({self.timeout}s) hablando con "
                    f"{self.host}:{self.puerto}"
                ) from exc
            except json.JSONDecodeError as exc:
                self.cerrar()
                raise ErrorTransmision(
                    "el receptor respondió algo que no es JSON"
                ) from exc

        return None


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
