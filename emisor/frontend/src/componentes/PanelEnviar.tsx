import { useEffect, useMemo, useState } from "react";
import {
  Config,
  ETIQUETAS_ESTADO,
  Estado,
  PeticionEnvio,
  ResultadoEnvio,
  enviar,
} from "../api";
import { NivelPila } from "./VistaTrama";

interface Props {
  config: Config;
  receptorActivo: boolean;
  onDestino: (host: string, puerto: number) => void;
}

const pct = (x: number) => `${(x * 100).toFixed(1)} %`;

/**
 * Pestaña "Enviar": el servicio `solicitar_mensaje` de la capa de aplicación.
 * Muestra la trama en cada capa (ASCII -> +redundancia -> post-ruido) y el
 * veredicto que devolvió el receptor.
 */
export function PanelEnviar({ config, receptorActivo, onDestino }: Props) {
  const [mensaje, setMensaje] = useState("Hola mundo");
  const [algoritmo, setAlgoritmo] = useState("hamming");
  const [m, setM] = useState(config.defaults.m);
  const [tasaError, setTasaError] = useState(config.defaults.tasa_error);
  const [modoRuido, setModoRuido] = useState("bernoulli");
  const [parametroRuido, setParametroRuido] = useState(1);
  const [semilla, setSemilla] = useState("");
  const [host, setHost] = useState(config.defaults.host);
  const [puerto, setPuerto] = useState(config.defaults.puerto);

  const [resultado, setResultado] = useState<ResultadoEnvio | null>(null);
  const [historial, setHistorial] = useState<ResultadoEnvio[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => onDestino(host, puerto), [host, puerto, onDestino]);

  const infoHamming = config.algoritmos.find((a) => a.nombre === "hamming");
  const dimension = infoHamming?.m_sugeridos?.find((d) => d.m === m);

  const peticion = (transmitir: boolean): PeticionEnvio => ({
    mensaje,
    algoritmo,
    m,
    tasa_error: tasaError,
    semilla: semilla.trim() === "" ? null : Number(semilla),
    modo_ruido: modoRuido,
    parametro_ruido: modoRuido === "bernoulli" ? null : parametroRuido,
    host,
    puerto,
    transmitir,
  });

  async function ejecutar(transmitir: boolean) {
    setOcupado(true);
    setError(null);
    try {
      const datos = await enviar(peticion(transmitir));
      setResultado(datos);
      setHistorial((previo) => [datos, ...previo].slice(0, 40));
    } catch (excepcion) {
      setError(excepcion instanceof Error ? excepcion.message : String(excepcion));
    } finally {
      setOcupado(false);
    }
  }

  // Si el receptor no respondió, se muestra el veredicto calculado localmente
  // para que la UI siga siendo útil (queda marcado como tal).
  const veredicto = resultado?.telemetria ?? null;
  const estado: Estado | null = veredicto
    ? veredicto.estado
    : (resultado?.veredicto_local.estado ?? null);
  const textoRecuperado = veredicto
    ? veredicto.mensaje
    : (resultado?.veredicto_local.mensaje ?? null);
  const intacto = textoRecuperado === resultado?.mensaje;

  const bitsCorregidos = useMemo(
    () => veredicto?.bits_corregidos ?? [],
    [veredicto],
  );

  return (
    <>
      <div className="tarjeta">
        <h2>Aplicación · solicitar_mensaje</h2>
        <div className="campos">
          <div className="campo ancho">
            <label htmlFor="mensaje">Mensaje (solo ASCII 0–127)</label>
            <textarea
              id="mensaje"
              value={mensaje}
              onChange={(e) => setMensaje(e.target.value)}
              placeholder="Escribe el texto a transmitir…"
            />
            <span className="pista">
              {mensaje.length} caracteres · {mensaje.length * 8} bits ASCII
            </span>
          </div>

          <div className="campo">
            <label htmlFor="algoritmo">Algoritmo de integridad</label>
            <select
              id="algoritmo"
              value={algoritmo}
              onChange={(e) => setAlgoritmo(e.target.value)}
            >
              {config.algoritmos.map((a) => (
                <option key={a.nombre} value={a.nombre}>
                  {a.titulo} · {a.tipo === "correccion" ? "corrección" : "detección"}
                </option>
              ))}
            </select>
            <span className="pista">
              {config.algoritmos.find((a) => a.nombre === algoritmo)?.descripcion}
            </span>
          </div>

          {algoritmo === "hamming" && (
            <div className="campo">
              <label htmlFor="m">Bits de datos por bloque (m)</label>
              <select id="m" value={m} onChange={(e) => setM(Number(e.target.value))}>
                {infoHamming?.m_sugeridos?.map((d) => (
                  <option key={d.m} value={d.m}>
                    Hamming({d.n},{d.m}) · m={d.m}
                  </option>
                ))}
              </select>
              <span className="pista">
                {dimension
                  ? `r=${dimension.r} bits de paridad · overhead ${pct(
                      dimension.r / dimension.n,
                    )}`
                  : ""}
              </span>
            </div>
          )}

          <div className="campo">
            <label htmlFor="modo-ruido">Modo de ruido</label>
            <select
              id="modo-ruido"
              value={modoRuido}
              onChange={(e) => setModoRuido(e.target.value)}
            >
              <option value="bernoulli">Bernoulli</option>
              <option value="exactos">k errores exactos</option>
              <option value="rafaga">Ráfaga contigua</option>
            </select>
          </div>

          {modoRuido === "bernoulli" ? (
            <div className="campo">
              <label htmlFor="tasa">Tasa de error (por bit)</label>
              <input
                id="tasa"
                value={tasaError}
                onChange={(e) => setTasaError(e.target.value)}
                placeholder="0.01 o 1/100"
              />
              <span className="pista">Acepta 0.01, 1/100 o 5 %</span>
            </div>
          ) : (
            <div className="campo">
              <label htmlFor="param">
                {modoRuido === "exactos" ? "Cantidad de bits" : "Longitud de ráfaga"}
              </label>
              <input
                id="param"
                type="number"
                min={1}
                value={parametroRuido}
                onChange={(e) => setParametroRuido(Number(e.target.value))}
              />
            </div>
          )}

          <div className="campo">
            <label htmlFor="semilla">Semilla (opcional)</label>
            <input
              id="semilla"
              value={semilla}
              onChange={(e) => setSemilla(e.target.value)}
              placeholder="vacío = aleatorio"
            />
            <span className="pista">Fíjala para reproducir un experimento</span>
          </div>

          <div className="campo">
            <label htmlFor="host">Receptor</label>
            <input id="host" value={host} onChange={(e) => setHost(e.target.value)} />
          </div>

          <div className="campo">
            <label htmlFor="puerto">Puerto</label>
            <input
              id="puerto"
              type="number"
              value={puerto}
              onChange={(e) => setPuerto(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="acciones">
          <button
            className="boton"
            onClick={() => ejecutar(true)}
            disabled={ocupado || !mensaje}
          >
            {ocupado ? "Enviando…" : "Enviar al receptor"}
          </button>
          <button
            className="boton secundario"
            onClick={() => ejecutar(false)}
            disabled={ocupado || !mensaje}
          >
            Solo previsualizar trama
          </button>
          {!receptorActivo && (
            <span className="pista">
              El receptor no responde: la previsualización sigue funcionando.
            </span>
          )}
        </div>

        {error && (
          <div className="aviso-error" style={{ marginTop: 14 }}>
            {error}
          </div>
        )}
      </div>

      {resultado && (
        <div className="columnas">
          <div className="tarjeta">
            <h2>
              Trama capa por capa
              <span className="sufijo">{resultado.etiqueta}</span>
            </h2>

            <div className="pila">
              <NivelPila
                nombre="Presentación"
                meta={`${resultado.bits_ascii.length} bits · ASCII 8 bits/carácter, MSB primero`}
                bits={resultado.bits_ascii}
              />
              <NivelPila
                nombre="Enlace"
                meta={`${resultado.trama_enlace.length} bits · +${resultado.bits_redundancia} de redundancia · overhead ${pct(resultado.overhead)}`}
                bits={resultado.trama_enlace}
                redundancia={resultado.posiciones_redundancia}
              />
              <NivelPila
                nombre="Ruido"
                meta={`${resultado.bits_volteados} bit(s) volteados · p = ${resultado.tasa_error}`}
                bits={resultado.trama_transmitida}
                redundancia={resultado.posiciones_redundancia}
                volteados={resultado.posiciones_volteadas}
              />
              {bitsCorregidos.length > 0 && (
                <NivelPila
                  nombre="Receptor · corrección"
                  meta={`${bitsCorregidos.length} bit(s) corregidos por el receptor`}
                  bits={resultado.trama_transmitida}
                  redundancia={resultado.posiciones_redundancia}
                  volteados={bitsCorregidos}
                />
              )}
            </div>

            <div className="leyenda-bits">
              <span>
                <i className="muestra" style={{ background: "var(--tinta-2)" }} />
                Datos
              </span>
              <span>
                <i className="muestra" style={{ background: "var(--serie-3)" }} />
                Redundancia
              </span>
              <span>
                <i className="muestra" style={{ background: "var(--critico)" }} />
                Volteado por el ruido
              </span>
            </div>
          </div>

          <div>
            <div className="tarjeta">
              <h2>Veredicto del receptor</h2>

              {!resultado.enviado && resultado.error_transmision ? (
                <>
                  <div className="aviso-error">{resultado.error_transmision}</div>
                  <p className="pista" style={{ marginTop: 12 }}>
                    Lo de abajo es la verificación calculada <b>localmente</b> por el
                    emisor, no la del receptor.
                  </p>
                </>
              ) : null}

              {estado && (
                <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                  <span className={`insignia ${estado}`}>
                    <i className="punto" />
                    {ETIQUETAS_ESTADO[estado]}
                  </span>
                  <span className="pista">
                    {intacto ? "el mensaje llegó íntegro" : "el mensaje NO se recuperó"}
                  </span>
                </div>
              )}

              <div className="campo" style={{ marginTop: 14 }}>
                <label>Mensaje recibido</label>
                <div className="bits" style={{ maxHeight: 110 }}>
                  {textoRecuperado === null ? "— (no entregado)" : textoRecuperado}
                </div>
              </div>

              <div className="metricas">
                <div className="metrica">
                  <div className="valor">{resultado.trama_transmitida.length}</div>
                  <div className="clave">bits transmitidos</div>
                </div>
                <div className="metrica">
                  <div className="valor">{resultado.bits_volteados}</div>
                  <div className="clave">bits volteados</div>
                </div>
                <div className="metrica">
                  <div className="valor">{pct(resultado.overhead)}</div>
                  <div className="clave">overhead</div>
                </div>
                <div className="metrica">
                  <div className="valor">{resultado.ms_emision.toFixed(2)} ms</div>
                  <div className="clave">emisión</div>
                </div>
              </div>
            </div>

            <div className="tarjeta">
              <h2>
                Historial
                <span className="sufijo">{historial.length} envío(s)</span>
              </h2>
              {historial.length === 0 ? (
                <div className="vacio">Aún no hay envíos</div>
              ) : (
                <div className="historial">
                  {historial.map((item) => {
                    const est =
                      item.telemetria?.estado ?? item.veredicto_local.estado;
                    return (
                      <button
                        key={item.id}
                        className="fila-historial"
                        onClick={() => setResultado(item)}
                      >
                        <span className="texto">{item.mensaje}</span>
                        <span className={`insignia ${est}`}>
                          <i className="punto" />
                          {ETIQUETAS_ESTADO[est]}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
