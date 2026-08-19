# -----------------------------------------------------------------------------
# Backend del EMISOR — FastAPI
# -----------------------------------------------------------------------------
# Expone la pila de capas por HTTP y WebSocket, y sirve el build de React.
#
#   POST /api/enviar        recorre la pila completa y transmite
#   POST /api/experimentos  barrido completo (JSON o CSV)
#   GET  /api/config        algoritmos y valores por defecto
#   GET  /api/estado        ¿hay un receptor escuchando?
#   WS   /ws                envíos y barridos con progreso en vivo
#
# Arranque:  uvicorn app.main:app --port 8000
# -----------------------------------------------------------------------------

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .algoritmos import crc32, hamming
from .capas import aplicacion, enlace, presentacion, ruido, transmision
from .experimentos import runner

DIRECTORIO_ESTATICO = Path(__file__).resolve().parent.parent / "frontend" / "dist"

app = FastAPI(
    title="Emisor — Laboratorio 2 (CC3067 Redes)",
    description="Arquitectura de capas para detección y corrección de errores.",
    version="1.0.0",
)

# Los dev servers de Vite (5173/5174) hablan con este backend en desarrollo.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Modelos
# --------------------------------------------------------------------------- #

class SolicitudEnvio(BaseModel):
    mensaje: str = Field(..., min_length=1, description="Texto ASCII a enviar")
    algoritmo: str = Field("hamming", description="'hamming' o 'crc32'")
    m: int = Field(8, ge=1, le=64, description="Bits de datos por bloque (Hamming)")
    tasa_error: str = Field("0", description="Errores por bit: 0.01, 1/100, 5%")
    semilla: int | None = Field(None, description="Semilla para reproducir el ruido")
    modo_ruido: str = Field("bernoulli", description="bernoulli | exactos | rafaga")
    parametro_ruido: int | None = None
    host: str = transmision.HOST_POR_DEFECTO
    puerto: int = transmision.PUERTO_POR_DEFECTO
    transmitir: bool = Field(True, description="False = solo previsualizar la trama")


class SolicitudExperimentos(BaseModel):
    tamanos: list[int] = Field(default_factory=lambda: list(runner.TAMANOS_POR_DEFECTO))
    bers: list[float] = Field(default_factory=lambda: list(runner.BER_POR_DEFECTO))
    m_hamming: list[int] = Field(default_factory=lambda: [8, 16])
    incluir_crc32: bool = True
    repeticiones: int = Field(runner.REPETICIONES_POR_DEFECTO, ge=1, le=5000)
    semilla: int | None = 2026
    modo: str = Field("local", description="local | socket")
    host: str = transmision.HOST_POR_DEFECTO
    puerto: int = transmision.PUERTO_POR_DEFECTO
    formato: str = Field("json", description="json | csv")

    def configuraciones(self) -> list[tuple[str, dict]]:
        configuraciones: list[tuple[str, dict]] = [
            ("hamming", {"m": m}) for m in self.m_hamming
        ]
        if self.incluir_crc32:
            configuraciones.append(("crc32", {}))
        if not configuraciones:
            raise HTTPException(400, "hay que elegir al menos un algoritmo")
        return configuraciones


# --------------------------------------------------------------------------- #
# Lógica compartida entre REST y WebSocket
# --------------------------------------------------------------------------- #

def _ejecutar_envio(solicitud: SolicitudEnvio) -> dict[str, Any]:
    params = {"m": solicitud.m} if solicitud.algoritmo == "hamming" else {}
    comunes = dict(
        algoritmo=solicitud.algoritmo,
        params=params,
        tasa_error=solicitud.tasa_error,
        semilla=solicitud.semilla,
        modo_ruido=solicitud.modo_ruido,
        parametro_ruido=solicitud.parametro_ruido,
    )
    try:
        if solicitud.transmitir:
            resultado = aplicacion.solicitar_mensaje(
                solicitud.mensaje, host=solicitud.host, puerto=solicitud.puerto,
                **comunes,
            )
        else:
            resultado = aplicacion.preparar_envio(solicitud.mensaje, **comunes)
    except (
        aplicacion.ErrorAplicacion,
        enlace.ErrorEnlace,
        presentacion.ErrorPresentacion,
        ruido.ErrorRuido,
        hamming.ErrorHamming,
        crc32.ErrorCRC32,
    ) as exc:
        raise HTTPException(400, str(exc)) from exc

    datos = resultado.a_dict()
    datos["etiqueta"] = runner.etiquetar(resultado.algoritmo, resultado.params)
    datos["trama_enviada"] = resultado.trama_para_receptor()

    # Veredicto local: permite ver la UI completa aunque el receptor esté caído.
    estado, recuperado = runner.veredicto_local(resultado)
    datos["veredicto_local"] = {"estado": estado, "mensaje": recuperado}
    return datos


def _ejecutar_barrido(
    solicitud: SolicitudExperimentos,
    progreso=None,
) -> list[runner.Agregado]:
    try:
        return list(runner.barrer(
            tamanos=solicitud.tamanos,
            bers=solicitud.bers,
            configuraciones=solicitud.configuraciones(),
            repeticiones=solicitud.repeticiones,
            semilla=solicitud.semilla,
            modo=solicitud.modo,
            host=solicitud.host,
            puerto=solicitud.puerto,
            progreso=progreso,
        ))
    except transmision.ErrorTransmision as exc:
        raise HTTPException(
            503, f"el barrido en modo 'socket' necesita el receptor: {exc}"
        ) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


# --------------------------------------------------------------------------- #
# REST
# --------------------------------------------------------------------------- #

# Todo lo que la UI necesita para armar los formularios.
@app.get("/api/config")
def obtener_config() -> dict[str, Any]:
    return {
        "algoritmos": [
            {
                "nombre": hamming.NOMBRE,
                "titulo": "Hamming(n, m)",
                "tipo": hamming.TIPO,
                "descripcion": "Corrige 1 bit por bloque de n bits.",
                "m_sugeridos": [
                    {"m": m, "n": hamming.dimensiones(m)[0], "r": hamming.dimensiones(m)[1]}
                    for m in hamming.M_SUGERIDOS
                ],
            },
            {
                "nombre": crc32.NOMBRE,
                "titulo": "CRC-32 IEEE 802.3",
                "tipo": crc32.TIPO,
                "descripcion": "Detecta errores; no corrige. 32 bits fijos.",
                "polinomio": f"0x{crc32.POLINOMIO:08X}",
            },
        ],
        "defaults": {
            "m": 8,
            "tasa_error": "0.01",
            "host": transmision.HOST_POR_DEFECTO,
            "puerto": transmision.PUERTO_POR_DEFECTO,
            "tamanos": list(runner.TAMANOS_POR_DEFECTO),
            "bers": list(runner.BER_POR_DEFECTO),
            "repeticiones": runner.REPETICIONES_POR_DEFECTO,
        },
        "modos_ruido": ["bernoulli", "exactos", "rafaga"],
        "estados": list(runner.ESTADOS),
    }


@app.get("/api/estado")
def obtener_estado(
    host: str = transmision.HOST_POR_DEFECTO,
    puerto: int = transmision.PUERTO_POR_DEFECTO,
) -> dict[str, Any]:
    return {
        "receptor_activo": transmision.probar_conexion(host, puerto),
        "host": host,
        "puerto": puerto,
    }


# Servicio `solicitar_mensaje`: recorre la pila completa del emisor.
@app.post("/api/enviar")
async def enviar(solicitud: SolicitudEnvio) -> dict[str, Any]:
    return await asyncio.to_thread(_ejecutar_envio, solicitud)


# Barrido completo. Devuelve JSON para las gráficas o CSV para el informe.
@app.post("/api/experimentos")
async def experimentos(solicitud: SolicitudExperimentos):
    agregados = await asyncio.to_thread(_ejecutar_barrido, solicitud)
    if solicitud.formato == "csv":
        return PlainTextResponse(
            runner.a_csv(agregados),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="barrido.csv"'},
        )
    return {"filas": [a.a_fila() for a in agregados], "total": len(agregados)}


# --------------------------------------------------------------------------- #
# WebSocket
# --------------------------------------------------------------------------- #

# Canal en vivo: envíos y barridos con barra de progreso.
@app.websocket("/ws")
async def websocket(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            peticion = json.loads(await ws.receive_text())
            accion = peticion.get("accion")

            if accion == "enviar":
                try:
                    datos = await asyncio.to_thread(
                        _ejecutar_envio, SolicitudEnvio(**peticion.get("datos", {}))
                    )
                    await ws.send_json({"tipo": "envio", "datos": datos})
                except HTTPException as exc:
                    await ws.send_json({"tipo": "error", "mensaje": exc.detail})

            elif accion == "experimentos":
                solicitud = SolicitudExperimentos(**peticion.get("datos", {}))
                bucle = asyncio.get_running_loop()
                cola: asyncio.Queue = asyncio.Queue()

                def progreso(hechas: int, total: int) -> None:
                    bucle.call_soon_threadsafe(cola.put_nowait, (hechas, total))

                tarea = asyncio.create_task(
                    asyncio.to_thread(_ejecutar_barrido, solicitud, progreso)
                )
                while not tarea.done():
                    try:
                        hechas, total = await asyncio.wait_for(cola.get(), timeout=0.25)
                        await ws.send_json(
                            {"tipo": "progreso", "hechas": hechas, "total": total}
                        )
                    except asyncio.TimeoutError:
                        pass

                try:
                    agregados = await tarea
                    await ws.send_json({
                        "tipo": "experimentos",
                        "filas": [a.a_fila() for a in agregados],
                    })
                except HTTPException as exc:
                    await ws.send_json({"tipo": "error", "mensaje": exc.detail})

            else:
                await ws.send_json(
                    {"tipo": "error", "mensaje": f"acción desconocida: {accion!r}"}
                )

    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 — no tumbar el socket por un fallo puntual
        try:
            await ws.send_json({"tipo": "error", "mensaje": str(exc)})
        except Exception:
            pass


# --------------------------------------------------------------------------- #
# Frontend (build de React). Se monta al final para no tapar /api ni /ws.
# --------------------------------------------------------------------------- #

if DIRECTORIO_ESTATICO.is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=DIRECTORIO_ESTATICO / "assets"),
        name="assets",
    )

    @app.get("/{ruta:path}")
    def spa(ruta: str) -> FileResponse:
        archivo = DIRECTORIO_ESTATICO / ruta
        if ruta and archivo.is_file():
            return FileResponse(archivo)
        return FileResponse(DIRECTORIO_ESTATICO / "index.html")

else:

    @app.get("/")
    def sin_frontend() -> dict[str, str]:
        return {
            "mensaje": "Backend del emisor activo. El frontend no está compilado.",
            "compilar": "cd emisor/frontend && npm install && npm run build",
            "docs": "/docs",
        }
