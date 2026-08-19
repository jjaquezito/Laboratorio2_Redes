import { useMemo } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { FilaExperimento, colorDeSerie } from "../api";

/* Ejes y rejilla recesivos; el color vive solo en las marcas de datos. */
const EJE = {
  stroke: "var(--eje)",
  tick: { fill: "var(--tinta-mute)", fontSize: 11 },
  tickLine: false,
};
const MARGEN = { top: 8, right: 16, bottom: 4, left: 4 };

interface Serie {
  etiqueta: string;
  color: string;
}

/** Series en orden estable: el color sigue a la entidad, no a su posición. */
function seriesDe(filas: FilaExperimento[]): Serie[] {
  const vistas = new Map<string, Serie>();
  for (const fila of filas) {
    if (!vistas.has(fila.etiqueta)) {
      vistas.set(fila.etiqueta, {
        etiqueta: fila.etiqueta,
        color: colorDeSerie(fila.etiqueta),
      });
    }
  }
  return [...vistas.values()].sort((a, b) => a.etiqueta.localeCompare(b.etiqueta));
}

function Leyenda({ series }: { series: Serie[] }) {
  if (series.length < 2) return null;
  return (
    <div className="leyenda">
      {series.map((serie) => (
        <span key={serie.etiqueta}>
          <i className="llave" style={{ background: serie.color }} />
          {serie.etiqueta}
        </span>
      ))}
    </div>
  );
}

interface PropsTooltip {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string | number;
  formato: (valor: number) => string;
  titulo: (etiqueta: string | number) => string;
}

function TooltipPersonalizado({
  active,
  payload,
  label,
  formato,
  titulo,
}: PropsTooltip) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="cabecera">{titulo(label ?? "")}</div>
      {payload.map((punto) => (
        <div key={punto.name} className="linea">
          <i className="llave" style={{ background: punto.color }} />
          {punto.name}
          <span className="num">
            {punto.value === null || punto.value === undefined
              ? "—"
              : formato(punto.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

interface PropsGrafica {
  titulo: string;
  subtitulo: string;
  filas: FilaExperimento[];
  /** Dimensión del eje X. */
  eje: "ber_nominal" | "bits_mensaje";
  /** Métrica del eje Y. */
  metrica: keyof FilaExperimento;
  formatoY: (valor: number) => string;
  etiquetaX: string;
  dominioY?: [number, number | "auto"];
}

function GraficaLineas({
  titulo,
  subtitulo,
  filas,
  eje,
  metrica,
  formatoY,
  etiquetaX,
  dominioY,
}: PropsGrafica) {
  const series = useMemo(() => seriesDe(filas), [filas]);

  // El eje X es categórico y no logarítmico: el barrido incluye BER = 0, que
  // una escala log no puede representar. Los valores van igualmente espaciados
  // y rotulados con su valor real, lo que se indica en el subtítulo.
  const datos = useMemo(() => {
    const claves = [...new Set(filas.map((f) => f[eje] as number))].sort(
      (a, b) => a - b,
    );
    return claves.map((clave) => {
      const punto: Record<string, number | string | null> = { x: clave };
      for (const serie of series) {
        const coincidencias = filas.filter(
          (f) => f[eje] === clave && f.etiqueta === serie.etiqueta,
        );
        punto[serie.etiqueta] = coincidencias.length
          ? coincidencias.reduce((suma, f) => suma + (f[metrica] as number), 0) /
            coincidencias.length
          : null;
      }
      return punto;
    });
  }, [filas, series, eje, metrica]);

  if (!filas.length) return null;

  const formatoX = (valor: number) =>
    eje === "ber_nominal"
      ? valor === 0
        ? "0"
        : `${valor}`
      : `${valor}`;

  return (
    <div className="tarjeta">
      <h3 className="grafica-titulo">{titulo}</h3>
      <p className="grafica-sub">{subtitulo}</p>
      <Leyenda series={series} />
      <ResponsiveContainer width="100%" height={252}>
        <LineChart data={datos} margin={MARGEN}>
          <CartesianGrid stroke="var(--rejilla)" vertical={false} />
          <XAxis
            dataKey="x"
            type="category"
            tickFormatter={formatoX}
            label={{
              value: etiquetaX,
              position: "insideBottom",
              offset: -2,
              fill: "var(--tinta-mute)",
              fontSize: 11,
            }}
            height={42}
            {...EJE}
          />
          <YAxis
            tickFormatter={formatoY}
            domain={dominioY ?? ["auto", "auto"]}
            width={56}
            axisLine={false}
            {...EJE}
          />
          <Tooltip
            cursor={{ stroke: "var(--eje)", strokeWidth: 1 }}
            content={
              <TooltipPersonalizado
                formato={formatoY}
                titulo={(valor) => `${etiquetaX}: ${formatoX(Number(valor))}`}
              />
            }
          />
          {series.map((serie) => (
            <Line
              key={serie.etiqueta}
              type="monotone"
              dataKey={serie.etiqueta}
              name={serie.etiqueta}
              stroke={serie.color}
              strokeWidth={2}
              dot={{ r: 4, strokeWidth: 2, fill: "var(--superficie)" }}
              activeDot={{ r: 5, strokeWidth: 2, fill: "var(--superficie)" }}
              connectNulls
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

const pct = (valor: number) => `${(valor * 100).toFixed(0)} %`;
const pct1 = (valor: number) => `${(valor * 100).toFixed(1)} %`;
const ms = (valor: number) => `${valor.toFixed(3)} ms`;

/** Las cuatro gráficas del informe. */
export function Graficas({ filas }: { filas: FilaExperimento[] }) {
  // Para las gráficas frente al BER se fija el tamaño más grande del barrido:
  // mezclar tamaños en una sola curva promediaría cosas incomparables.
  const tamanoMayor = useMemo(
    () => Math.max(...filas.map((f) => f.bits_mensaje)),
    [filas],
  );
  const porBer = useMemo(
    () => filas.filter((f) => f.bits_mensaje === tamanoMayor),
    [filas, tamanoMayor],
  );
  // Para las gráficas frente al tamaño se fija el BER más alto del barrido.
  const berMayor = useMemo(
    () => Math.max(...filas.map((f) => f.ber_nominal)),
    [filas],
  );
  const porTamano = useMemo(
    () => filas.filter((f) => f.ber_nominal === berMayor),
    [filas, berMayor],
  );

  if (!filas.length) return null;

  return (
    <div className="rejilla-graficas">
      <GraficaLineas
        titulo="1 · Tasa de entrega correcta vs BER"
        subtitulo={`Mensajes de ${tamanoMayor} bits. Eje X categórico: el barrido incluye BER = 0, que una escala logarítmica no admite.`}
        filas={porBer}
        eje="ber_nominal"
        metrica="tasa_entrega"
        formatoY={pct}
        etiquetaX="BER (errores por bit)"
        dominioY={[0, 1]}
      />
      <GraficaLineas
        titulo="2 · Errores no detectados vs BER"
        subtitulo="Fracción de mensajes corruptos que el receptor dio por buenos. Es el fallo silencioso: cuanto más bajo, mejor."
        filas={porBer}
        eje="ber_nominal"
        metrica="tasa_falsos_negativos"
        formatoY={pct1}
        etiquetaX="BER (errores por bit)"
        dominioY={[0, "auto"]}
      />
      <GraficaLineas
        titulo="3 · Overhead vs tamaño del mensaje"
        subtitulo="CRC-32 amortiza sus 32 bits fijos; Hamming paga r bits por cada bloque de m, así que su costo no baja."
        filas={porTamano}
        eje="bits_mensaje"
        metrica="overhead"
        formatoY={pct}
        etiquetaX="Bits del mensaje"
        dominioY={[0, 1]}
      />
      <GraficaLineas
        titulo="4 · Latencia de cómputo vs tamaño del mensaje"
        subtitulo="Tiempo medio de la pila del emisor (codificar + calcular integridad + aplicar ruido)."
        filas={porTamano}
        eje="bits_mensaje"
        metrica="ms_emision_medio"
        formatoY={ms}
        etiquetaX="Bits del mensaje"
      />
    </div>
  );
}

/** Vista de tabla: relieve exigido por el WARN de contraste y ruta al informe. */
export function TablaResultados({ filas }: { filas: FilaExperimento[] }) {
  if (!filas.length) return null;
  return (
    <div className="envoltura-tabla">
      <table>
        <thead>
          <tr>
            <th>Configuración</th>
            <th>Bits</th>
            <th>BER</th>
            <th>Overhead</th>
            <th>Entrega</th>
            <th>No detectados</th>
            <th>Mis-corrección</th>
            <th>Emisión</th>
          </tr>
        </thead>
        <tbody>
          {filas.map((fila, indice) => (
            <tr key={indice}>
              <td>
                <i
                  className="punto-serie"
                  style={{ background: colorDeSerie(fila.etiqueta) }}
                />
                {fila.etiqueta}
              </td>
              <td>{fila.bits_mensaje}</td>
              <td>{fila.ber_nominal}</td>
              <td>{pct1(fila.overhead)}</td>
              <td>{pct1(fila.tasa_entrega)}</td>
              <td>{pct1(fila.tasa_falsos_negativos)}</td>
              <td>{fila.mis_correcciones}</td>
              <td>{fila.ms_emision_medio.toFixed(3)} ms</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
