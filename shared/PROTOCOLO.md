# Contrato de trama — Laboratorio 2 Redes

Documento normativo compartido entre el **emisor (Python)** y el **receptor (TypeScript)**.
Si los dos lados no coinciden bit a bit con lo aquí descrito, nada funciona.

## 1. Canal

TCP, **NDJSON**: un objeto JSON por línea, terminado en `\n`, codificado en UTF-8.
Puerto de datos por defecto: **5001**.

## 2. Emisor → Receptor (trama de datos)

```json
{
  "id": "3f9a1c2e-…",
  "algoritmo": "hamming" | "crc32",
  "params": { "m": 8 },
  "longitud_original_bits": 88,
  "trama": "0100100001…"
}
```

| Campo | Descripción |
|---|---|
| `id` | UUID v4. El emisor lo usa para cruzar la respuesta con la verdad-terreno que guardó localmente. |
| `algoritmo` | `"hamming"` (corrección) o `"crc32"` (detección). |
| `params` | `{"m": <int>}` para Hamming (bits de datos por bloque). `{}` para CRC-32. |
| `longitud_original_bits` | Longitud del mensaje en bits **antes** de padding y redundancia. Siempre múltiplo de 8. |
| `trama` | Cadena de `'0'`/`'1'`. Payload + redundancia, **ya con ruido aplicado**. |

**Regla de oro:** `trama` es lo único sometido a ruido. El header es señalización fuera de banda
(en un enlace real el esquema de integridad se negocia a priori). El emisor **nunca** envía las
posiciones de los bits que volteó — eso lo guarda localmente y lo cruza por `id`.

## 3. Receptor → Emisor (telemetría)

Extensión fuera del enunciado: alimenta la UI y la suite de experimentos.
El flujo obligatorio del laboratorio sigue siendo unidireccional.

```json
{
  "id": "3f9a1c2e-…",
  "estado": "ok" | "corregido" | "error_detectado" | "error_no_corregible",
  "mensaje": "Hola mundo",
  "bits_corregidos": [5, 27],
  "detalle": { "sindromes": [0, 5], "crc_rx": "1010…", "crc_calc": "1010…" },
  "ms_procesamiento": 0.12
}
```

| `estado` | Significado |
|---|---|
| `ok` | Verificación limpia, sin correcciones. |
| `corregido` | Hamming detectó y corrigió ≥1 bit. Se entrega el mensaje. |
| `error_detectado` | CRC-32 detectó corrupción. No hay corrección posible; no se entrega mensaje. |
| `error_no_corregible` | Hamming vio un síndrome fuera de rango (≥2 errores en un bloque). |

`mensaje` es `null` cuando el estado es `error_detectado` o `error_no_corregible`.

## 4. Capa de presentación

ASCII de **8 bits por carácter**, MSB primero. `'A'` → `01000001`.
El emisor rechaza caracteres fuera del rango ASCII (0–127) con un error explícito.

## 5. Hamming(n, m) — corrección

- `r` = mínimo entero con `m + r + 1 ≤ 2^r`; `n = m + r`.
- Posiciones **indexadas desde 1**. Los bits de paridad ocupan las potencias de 2 (1, 2, 4, 8, …);
  los de datos llenan el resto en orden.
- El bit de paridad en la posición `2^i` cubre toda posición `j` con `j & 2^i ≠ 0` (incluyéndose a sí
  mismo). **Paridad par**: el XOR de las posiciones cubiertas debe dar 0.
- **Modo por bloques**: el bitstream se parte en bloques de `m` bits; el último se rellena con ceros.
  Cada bloque se codifica por separado. `longitud_original_bits` permite descartar el padding.
- Decodificación: `sindrome` = XOR de los índices `j` cuyo bit vale 1.
  `0` → intacto · `1..n` → voltear ese bit y marcar `corregido` · `>n` → `error_no_corregible`.

Valores de referencia: `m=4 → n=7` · `m=8 → n=12` · `m=11 → n=15` · `m=16 → n=21`.

## 6. CRC-32 IEEE 802.3 — detección

- Polinomio `0x04C11DB7` (forma reflejada `0xEDB88320`), `init = 0xFFFFFFFF`,
  reflect in/out, `xorout = 0xFFFFFFFF`.
- **Vector canónico obligatorio:** `CRC32("123456789") = 0xCBF43926`. Ambos lenguajes lo verifican.
- Padding: si el mensaje tiene menos de 32 bits, se rellena con ceros a la derecha hasta 32.
- Trama = `bits_de_datos (ya con padding) + 32 bits de CRC`, MSB primero.
- Verificación: el receptor recalcula el CRC sobre los bits de datos recibidos y lo compara contra
  los últimos 32 bits. CRC-32 no corrige.

## 7. Capa de ruido (solo emisor)

`aplicar_ruido(bits, p)` — cada bit se voltea de forma independiente con probabilidad `p`
(Bernoulli). Afecta por igual al payload y a la redundancia. Semilla opcional para reproducir
experimentos.

## 8. Vectores dorados

`shared/vectores.json` contiene casos `{mensaje, algoritmo, params, trama_esperada}`.
Los tests de **ambos** lenguajes los leen del mismo archivo. Es la defensa contra el bug clásico
de este laboratorio: dos implementaciones en lenguajes distintos que no producen lo mismo.
