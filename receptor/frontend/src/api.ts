/** Cliente del backend del receptor (Express + ws) y tipos del historial en vivo. */

import { useEffect, useRef, useState } from "react";

export type Estado = "ok" | "corregido" | "error_detectado" | "error_no_corregible";

export const ETIQUETAS_ESTADO: Record<Estado, string> = {
  ok: "Íntegro",
  corregido: "Corregido",
  error_detectado: "Error detectado",
  error_no_corregible: "Error no corregible",
};

export interface RegistroTrama {
  id: string;
  algoritmo: string;
  params: Record<string, unknown>;
  longitudOriginalBits: number;
  trama: string;
  estado: Estado;
  mensaje: string | null;
  bitsCorregidos: number[];
  detalle: Record<string, unknown>;
  msProcesamiento: number;
  marcaDeTiempo: number;
}

export type Contadores = Record<Estado, number>;

export interface Snapshot {
  historial: RegistroTrama[];
  contadores: Contadores;
}

type Mensaje = { tipo: "snapshot"; datos: Snapshot } | { tipo: "trama"; datos: RegistroTrama };

const CONTADORES_VACIOS: Contadores = { ok: 0, corregido: 0, error_detectado: 0, error_no_corregible: 0 };
const MAXIMO_HISTORIAL_UI = 200;

function urlWebSocket(): string {
  const protocolo = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocolo}//${window.location.host}/ws`;
}

/** Mantiene el historial y los contadores sincronizados con el backend por WebSocket. */
export function useHistorialEnVivo(): {
  historial: RegistroTrama[];
  contadores: Contadores;
  conectado: boolean;
} {
  const [historial, setHistorial] = useState<RegistroTrama[]>([]);
  const [contadores, setContadores] = useState<Contadores>(CONTADORES_VACIOS);
  const [conectado, setConectado] = useState(false);
  const reintentoRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    let socket: WebSocket;
    let cancelado = false;

    function conectar(): void {
      socket = new WebSocket(urlWebSocket());

      socket.onopen = () => setConectado(true);
      socket.onclose = () => {
        setConectado(false);
        if (!cancelado) reintentoRef.current = window.setTimeout(conectar, 2000);
      };
      socket.onerror = () => socket.close();

      socket.onmessage = (evento) => {
        const mensaje = JSON.parse(evento.data) as Mensaje;
        if (mensaje.tipo === "snapshot") {
          setHistorial(mensaje.datos.historial);
          setContadores(mensaje.datos.contadores);
        } else {
          setHistorial((previo) => [mensaje.datos, ...previo].slice(0, MAXIMO_HISTORIAL_UI));
          setContadores((previo) => ({ ...previo, [mensaje.datos.estado]: previo[mensaje.datos.estado] + 1 }));
        }
      };
    }

    conectar();
    return () => {
      cancelado = true;
      window.clearTimeout(reintentoRef.current);
      socket?.close();
    };
  }, []);

  return { historial, contadores, conectado };
}
