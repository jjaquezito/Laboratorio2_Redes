# Emisor — Laboratorio 2 (CC3067 Redes)

Lado **emisor** de la arquitectura de capas para detección y corrección de
errores. Escrito en **Python**; el receptor va en **TypeScript** (el enunciado
exige lenguajes distintos).

El contrato entre ambos lados es [`../shared/PROTOCOLO.md`](../shared/PROTOCOLO.md).
Si el emisor y el receptor no coinciden bit a bit con ese documento, nada funciona.

---

## Puesta en marcha

```bash
cd emisor
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Frontend (una sola vez)
cd frontend && npm install && npm run build && cd ..

# Levantar la UI en http://localhost:8000
uvicorn app.main:app --port 8000
```

Para desarrollo del frontend con recarga en caliente:

```bash
cd frontend && npm run dev      # http://localhost:5173, delega /api y /ws al 8000
```

---

## Uso por línea de comandos

No requiere el frontend. Sirve para verificar la pila completa y para depurar.

```bash
# ¿Hay un receptor escuchando?
python -m app.cli estado

# Enviar un mensaje por la pila completa
python -m app.cli enviar "Hola mundo" --algoritmo hamming --m 8 --error 1/100

# Ver la trama capa por capa sin abrir el socket
python -m app.cli enviar "Hola mundo" --algoritmo crc32 --error 0.01 --sin-enviar

# Inyectar errores dirigidos (útil para el informe)
python -m app.cli enviar "Redes" --algoritmo hamming --modo-ruido exactos   --parametro-ruido 1
python -m app.cli enviar "Redes" --algoritmo crc32   --modo-ruido rafaga    --parametro-ruido 8

# Barrido de experimentos -> CSV
python -m app.cli experimentos --repeticiones 200 --salida ../docs/resultados/barrido.csv
```

La salida colorea la **redundancia en verde** y los **bits volteados por el ruido
en rojo**, en cada nivel de la pila.

### Receptor de prueba

Andamio de desarrollo para ejercitar el emisor sin depender del receptor real:

```bash
python -m tools.receptor_de_prueba --puerto 5001
```

> No es la entrega: el receptor del laboratorio es el de TypeScript.

---

## Arquitectura

```
app/
├── capas/
│   ├── aplicacion.py     solicitar_mensaje — orquesta el descenso por la pila
│   ├── presentacion.py   codificar_mensaje / decodificar_mensaje (ASCII 8 bits)
│   ├── enlace.py         calcular_integridad — concatena la redundancia
│   ├── ruido.py          aplicar_ruido — canal Bernoulli (solo emisor)
│   └── transmision.py    enviar_informacion — TCP + NDJSON al puerto 5001
├── algoritmos/
│   ├── hamming.py        Hamming(n,m) genérico por bloques — CORRECCIÓN
│   └── crc32.py          CRC-32 IEEE 802.3 — DETECCIÓN
├── experimentos/runner.py  barridos y métricas para el informe
├── main.py               FastAPI: REST + WebSocket + sirve el build de React
└── cli.py                interfaz de línea de comandos
```

`enlace.verificar_integridad` es un **espejo local del receptor**: en producción
esa lógica corre en TypeScript, y aquí existe para poder cerrar el lazo en los
tests y correr experimentos sin levantar el receptor.

### Algoritmos

| | Hamming(n, m) | CRC-32 IEEE 802.3 |
|---|---|---|
| Tipo | Corrección | Detección |
| Redundancia | `r` bits por bloque de `m` (`m+r+1 ≤ 2^r`) | 32 bits fijos |
| Capacidad | Corrige 1 bit **por bloque** | Detecta; no corrige |
| Overhead | Constante con el tamaño (33 % con m=8) | Se amortiza al crecer el mensaje |
| Punto débil | ≥ 2 errores en un bloque: "corrige" mal en silencio | No recupera nada |

Valores de referencia: `m=4 → n=7` · `m=8 → n=12` · `m=11 → n=15` · `m=16 → n=21`.

---

## Pruebas

```bash
python -m pytest tests -q
```

La suite cubre:

- `CRC32("123456789") == 0xCBF43926` (vector canónico obligatorio) y coincidencia
  con `zlib.crc32` como oráculo independiente.
- Hamming con `m=8` produce `n=12`; se inyecta 1 error en **cada una** de las `n`
  posiciones de un bloque y las `n` se corrigen (para m = 4, 8, 11 y 16).
- CRC-32 detecta el 100 % de las ráfagas de hasta 32 bits.
- Los **vectores dorados** de [`../shared/vectores.json`](../shared/vectores.json):
  los mismos casos que debe leer la suite de `vitest` del receptor.
- El contrato de trama: las posiciones de los bits volteados **nunca** viajan al
  receptor, y el ruido alcanza también a la redundancia.
- 50 envíos con `p = 0` sobre un socket real → 50/50 íntegros.

### Regenerar los vectores dorados

```bash
python -m tools.gen_vectores
```

> `shared/vectores.json` es un artefacto **compartido con el receptor**: si se
> regenera y cambia, el receptor deja de coincidir. Regenerarlo solo al
> modificar un algoritmo a propósito.
