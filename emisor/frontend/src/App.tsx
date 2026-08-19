import { useCallback, useEffect, useState } from "react";
import { Config, obtenerConfig, obtenerEstado } from "./api";
import { PanelEnviar } from "./componentes/PanelEnviar";
import { PanelExperimentos } from "./componentes/PanelExperimentos";

type Pestana = "enviar" | "experimentos";

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [fallo, setFallo] = useState<string | null>(null);
  const [pestana, setPestana] = useState<Pestana>("enviar");
  const [receptorActivo, setReceptorActivo] = useState(false);
  const [destino, setDestino] = useState({ host: "127.0.0.1", puerto: 5001 });

  useEffect(() => {
    obtenerConfig()
      .then((datos) => {
        setConfig(datos);
        setDestino({ host: datos.defaults.host, puerto: datos.defaults.puerto });
      })
      .catch((excepcion) => setFallo(String(excepcion)));
  }, []);

  // Sondeo del receptor: el indicador del encabezado debe reflejar la realidad
  // aunque Jose reinicie su proceso a mitad de una demo.
  useEffect(() => {
    let vigente = true;
    const sondear = () =>
      obtenerEstado(destino.host, destino.puerto)
        .then((datos) => vigente && setReceptorActivo(datos.receptor_activo))
        .catch(() => vigente && setReceptorActivo(false));

    sondear();
    const temporizador = window.setInterval(sondear, 3000);
    return () => {
      vigente = false;
      window.clearInterval(temporizador);
    };
  }, [destino]);

  const alCambiarDestino = useCallback(
    (host: string, puerto: number) => setDestino({ host, puerto }),
    [],
  );

  if (fallo) {
    return (
      <div className="app">
        <div className="aviso-error">No se pudo contactar el backend: {fallo}</div>
      </div>
    );
  }

  if (!config) {
    return (
      <div className="app">
        <div className="vacio">Cargando…</div>
      </div>
    );
  }

  return (
    <div className="app">
      <header className="encabezado">
        <div>
          <h1>Emisor · Laboratorio 2 — Detección y corrección de errores</h1>
          <p>
            Arquitectura de capas: aplicación → presentación → enlace → ruido →
            transmisión
          </p>
        </div>
        <div className="estado-receptor">
          <i className={`punto ${receptorActivo ? "vivo" : "muerto"}`} />
          Receptor {destino.host}:{destino.puerto} ·{" "}
          {receptorActivo ? "escuchando" : "sin respuesta"}
        </div>
      </header>

      <nav className="pestanas" role="tablist">
        <button
          role="tab"
          aria-selected={pestana === "enviar"}
          onClick={() => setPestana("enviar")}
        >
          Enviar
        </button>
        <button
          role="tab"
          aria-selected={pestana === "experimentos"}
          onClick={() => setPestana("experimentos")}
        >
          Experimentos
        </button>
      </nav>

      {pestana === "enviar" ? (
        <PanelEnviar
          config={config}
          receptorActivo={receptorActivo}
          onDestino={alCambiarDestino}
        />
      ) : (
        <PanelExperimentos
          config={config}
          receptorActivo={receptorActivo}
          host={destino.host}
          puerto={destino.puerto}
        />
      )}
    </div>
  );
}
