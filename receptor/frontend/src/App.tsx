import { ETIQUETAS_ESTADO, Estado, useHistorialEnVivo } from "./api";
import { RegistroTramas } from "./componentes/RegistroTramas";

const ORDEN_ESTADOS: Estado[] = ["ok", "corregido", "error_detectado", "error_no_corregible"];

export default function App() {
  const { historial, contadores, conectado } = useHistorialEnVivo();
  const total = ORDEN_ESTADOS.reduce((suma, estado) => suma + contadores[estado], 0);

  return (
    <div className="app">
      <header className="encabezado">
        <div>
          <h1>Receptor · Laboratorio 2 — Detección y corrección de errores</h1>
          <p>Arquitectura de capas: transmisión → enlace → presentación → aplicación</p>
        </div>
        <div className="estado-receptor">
          <i className={`punto ${conectado ? "vivo" : "muerto"}`} />
          {conectado ? "conectado en vivo" : "reconectando…"}
        </div>
      </header>

      <div className="tarjeta">
        <h2>
          Resumen <span className="sufijo">{total} trama{total === 1 ? "" : "s"} recibidas</span>
        </h2>
        <div className="metricas">
          {ORDEN_ESTADOS.map((clave) => (
            <div className="metrica" key={clave}>
              <div className="valor">{contadores[clave]}</div>
              <div className="clave">{ETIQUETAS_ESTADO[clave]}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="tarjeta">
        <h2>
          Tramas recibidas <span className="sufijo">últimas primero</span>
        </h2>
        <RegistroTramas historial={historial} />
      </div>
    </div>
  );
}
