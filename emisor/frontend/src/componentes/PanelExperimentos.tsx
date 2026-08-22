import { useState } from "react";
import {
  Config,
  FilaExperimento,
  PeticionExperimentos,
  correrExperimentos,
  descargarCsv,
} from "../api";
import { Graficas, TablaResultados } from "./Graficas";

interface Props {
  config: Config;
  receptorActivo: boolean;
  host: string;
  puerto: number;
}

const numeros = (texto: string): number[] =>
  texto
    .split(/[,\s]+/)
    .map((pieza) => Number(pieza))
    .filter((valor) => Number.isFinite(valor));

/**
 * Pestaña "Experimentos": barrido sobre tamaño de mensaje × BER × algoritmo,
 * con las cuatro gráficas y la exportación a CSV que pide el informe.
 */
export function PanelExperimentos({ config, receptorActivo, host, puerto }: Props) {
  const [tamanos, setTamanos] = useState(config.defaults.tamanos.join(", "));
  const [bers, setBers] = useState(config.defaults.bers.join(", "));
  const [mHamming, setMHamming] = useState("8, 16");
  const [incluirCrc32, setIncluirCrc32] = useState(true);
  const [repeticiones, setRepeticiones] = useState(config.defaults.repeticiones);
  const [semilla, setSemilla] = useState("2026");
  const [modo, setModo] = useState("local");

  const [filas, setFilas] = useState<FilaExperimento[]>([]);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const peticion = (): PeticionExperimentos => ({
    tamanos: numeros(tamanos),
    bers: numeros(bers),
    m_hamming: numeros(mHamming),
    incluir_crc32: incluirCrc32,
    repeticiones,
    semilla: semilla.trim() === "" ? null : Number(semilla),
    modo,
    host,
    puerto,
  });

  const celdas =
    numeros(tamanos).length *
    numeros(bers).length *
    (numeros(mHamming).length + (incluirCrc32 ? 1 : 0));

  async function correr() {
    setOcupado(true);
    setError(null);
    try {
      const datos = await correrExperimentos(peticion());
      setFilas(datos.filas);
    } catch (excepcion) {
      setError(excepcion instanceof Error ? excepcion.message : String(excepcion));
    } finally {
      setOcupado(false);
    }
  }

  async function exportar() {
    try {
      await descargarCsv(peticion());
    } catch (excepcion) {
      setError(excepcion instanceof Error ? excepcion.message : String(excepcion));
    }
  }

  return (
    <>
      <div className="tarjeta">
        <h2>
          Barrido
          <span className="sufijo">
            {celdas} celdas × {repeticiones} repeticiones ={" "}
            {(celdas * repeticiones).toLocaleString("es")} envíos
          </span>
        </h2>

        <div className="campos">
          <div className="campo">
            <label htmlFor="tamanos">Tamaños de mensaje (bits)</label>
            <input
              id="tamanos"
              value={tamanos}
              onChange={(e) => setTamanos(e.target.value)}
            />
            <span className="pista">Múltiplos de 8</span>
          </div>

          <div className="campo">
            <label htmlFor="bers">Tasas de error (BER)</label>
            <input id="bers" value={bers} onChange={(e) => setBers(e.target.value)} />
          </div>

          <div className="campo">
            <label htmlFor="m-hamming">Valores de m (Hamming)</label>
            <input
              id="m-hamming"
              value={mHamming}
              onChange={(e) => setMHamming(e.target.value)}
            />
          </div>

          <div className="campo">
            <label htmlFor="repeticiones">Repeticiones por celda</label>
            <input
              id="repeticiones"
              type="number"
              min={1}
              max={5000}
              value={repeticiones}
              onChange={(e) => setRepeticiones(Number(e.target.value))}
            />
          </div>

          <div className="campo">
            <label htmlFor="semilla-exp">Semilla</label>
            <input
              id="semilla-exp"
              value={semilla}
              onChange={(e) => setSemilla(e.target.value)}
            />
            <span className="pista">Fija = barrido reproducible</span>
          </div>

          <div className="campo">
            <label htmlFor="modo">Modo</label>
            <select id="modo" value={modo} onChange={(e) => setModo(e.target.value)}>
              <option value="local">Local (sin receptor)</option>
              <option value="socket" disabled={!receptorActivo}>
                Socket real {receptorActivo ? "" : "— receptor caído"}
              </option>
            </select>
            <span className="pista">
              {modo === "socket"
                ? "Cada envío viaja por TCP al receptor"
                : "Verifica con el espejo local del receptor"}
            </span>
          </div>

          <div className="campo">
            <label htmlFor="crc32">Incluir CRC-32</label>
            <div style={{ display: "flex", alignItems: "center", gap: 8, height: 34 }}>
              <input
                id="crc32"
                type="checkbox"
                style={{ width: 16, height: 16 }}
                checked={incluirCrc32}
                onChange={(e) => setIncluirCrc32(e.target.checked)}
              />
              <span className="pista">Algoritmo de detección</span>
            </div>
          </div>
        </div>

        <div className="acciones">
          <button className="boton" onClick={correr} disabled={ocupado || celdas === 0}>
            {ocupado ? "Corriendo barrido…" : "Correr barrido"}
          </button>
          <button
            className="boton secundario"
            onClick={exportar}
            disabled={ocupado || celdas === 0}
          >
            Exportar CSV
          </button>
        </div>

        {ocupado && (
          <div className="barra-progreso">
            <div style={{ width: "100%", opacity: 0.5 }} />
          </div>
        )}

        {error && (
          <div className="aviso-error" style={{ marginTop: 14 }}>
            {error}
          </div>
        )}
      </div>

      {filas.length > 0 ? (
        <>
          <Graficas filas={filas} />
          <div className="tarjeta">
            <h2>
              Resultados
              <span className="sufijo">{filas.length} filas</span>
            </h2>
            <TablaResultados filas={filas} />
          </div>
        </>
      ) : (
        !ocupado && (
          <div className="tarjeta">
            <div className="vacio">
              Aún no hay resultados. Al ejecutar el barrido aparecerán aquí las
              cuatro gráficas y la tabla de datos.
            </div>
          </div>
        )
      )}
    </>
  );
}
