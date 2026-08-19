import { useMemo } from "react";

interface Props {
  bits: string;
  redundancia?: number[];
  volteados?: number[];
}

/**
 * Dibuja una trama bit a bit resaltando la redundancia (aqua) y los bits que el
 * canal volteó (rojo). Es la evidencia visual que pide el enunciado: se ve
 * exactamente qué agregó la capa de enlace y qué destruyó la capa de ruido.
 *
 * Los bits contiguos del mismo tipo se agrupan en un solo <b>, de modo que una
 * trama de 2048 bits genera decenas de nodos y no miles.
 */
export function VistaTrama({ bits, redundancia = [], volteados = [] }: Props) {
  const tramos = useMemo(() => {
    const esRedundancia = new Set(redundancia);
    const esVolteado = new Set(volteados);

    const salida: { clase: string; texto: string }[] = [];
    for (let i = 0; i < bits.length; i += 1) {
      const clase = esVolteado.has(i)
        ? "bit-volteado"
        : esRedundancia.has(i)
          ? "bit-redundancia"
          : "";
      const ultimo = salida[salida.length - 1];
      if (ultimo && ultimo.clase === clase) ultimo.texto += bits[i];
      else salida.push({ clase, texto: bits[i] });
    }
    return salida;
  }, [bits, redundancia, volteados]);

  if (!bits) return <div className="vacio">Sin datos</div>;

  return (
    <div className="bits">
      {tramos.map((tramo, indice) => (
        <b key={indice} className={tramo.clase}>
          {tramo.texto}
        </b>
      ))}
    </div>
  );
}

interface PropsNivel {
  nombre: string;
  meta: string;
  bits: string;
  redundancia?: number[];
  volteados?: number[];
}

/** Un peldaño de la pila, con su etiqueta de capa y su métrica. */
export function NivelPila({ nombre, meta, bits, redundancia, volteados }: PropsNivel) {
  return (
    <div>
      <div className="nivel-etiqueta">
        {nombre}
        <span className="meta">{meta}</span>
      </div>
      <VistaTrama bits={bits} redundancia={redundancia} volteados={volteados} />
    </div>
  );
}
