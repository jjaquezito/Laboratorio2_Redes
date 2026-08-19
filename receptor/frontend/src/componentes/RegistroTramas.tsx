import { Fragment, useState } from "react";
import { ETIQUETAS_ESTADO, RegistroTrama } from "../api";
import { VistaTrama } from "./VistaTrama";

interface Props {
  historial: RegistroTrama[];
}

const FORMATO_HORA = new Intl.DateTimeFormat("es-GT", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
});

export function RegistroTramas({ historial }: Props) {
  const [expandidoId, setExpandidoId] = useState<string | null>(null);

  if (historial.length === 0) {
    return <div className="vacio">Todavía no llega ninguna trama. Envía un mensaje desde el emisor.</div>;
  }

  return (
    <div className="historial">
      {historial.map((registro, indice) => {
        // El id del emisor no es único entre reconexiones de prueba: se compone con la posición.
        const clave = `${registro.id}-${registro.marcaDeTiempo}-${indice}`;
        const expandido = expandidoId === clave;

        return (
          <div key={clave} className="fila-historial" onClick={() => setExpandidoId(expandido ? null : clave)}>
            <div className="resumen">
              <div className="izquierda">
                <span className="hora">{FORMATO_HORA.format(registro.marcaDeTiempo)}</span>
                <span className={`insignia ${registro.estado}`}>
                  <i className="punto" />
                  {ETIQUETAS_ESTADO[registro.estado] ?? registro.estado}
                </span>
                <span className="texto">{registro.mensaje ?? "sin mensaje"}</span>
              </div>
              <span className="hora">{registro.algoritmo}</span>
            </div>

            {expandido && (
              <div className="detalle" onClick={(evento) => evento.stopPropagation()}>
                <dl className="clave-valor">
                  <dt>id</dt>
                  <dd>{registro.id || "—"}</dd>
                  <dt>algoritmo</dt>
                  <dd>
                    {registro.algoritmo}
                    {registro.params.m ? ` (m=${String(registro.params.m)})` : ""}
                  </dd>
                  <dt>longitud original</dt>
                  <dd>{registro.longitudOriginalBits} bits</dd>
                  <dt>trama recibida</dt>
                  <dd>{registro.trama.length} bits</dd>
                  <dt>bits corregidos</dt>
                  <dd>{registro.bitsCorregidos.length ? registro.bitsCorregidos.join(", ") : "ninguno"}</dd>
                  <dt>ms de procesamiento</dt>
                  <dd>{registro.msProcesamiento.toFixed(3)}</dd>
                  {Object.entries(registro.detalle).map(([clave, valor]) => (
                    <Fragment key={clave}>
                      <dt>{clave}</dt>
                      <dd>{Array.isArray(valor) ? valor.join(", ") : String(valor)}</dd>
                    </Fragment>
                  ))}
                </dl>
                <VistaTrama bits={registro.trama} volteados={registro.bitsCorregidos} />
                <div className="leyenda-bits">
                  <span>
                    <i className="muestra bit-volteado" />
                    bit corregido
                  </span>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
