# Laboratorio 2 — Esquemas de detección y corrección de errores

**Universidad del Valle de Guatemala**
Facultad de Ingeniería · Departamento de Ciencias de la Computación
CC3067 Redes · Ciclo 2 de 2026

| Integrante | Carné |
|---|---|
| Joel Antonio Jaquez López | 23369 |
| Jose Pablo Lopez Lopez | 23773 |

---

## ¿De qué se trata este proyecto?

Cuando un mensaje viaja por un cable, por el aire o por una fibra óptica, siempre
existe la posibilidad de que algún bit llegue alterado. Este proyecto implementa
un sistema de transmisión que **simula ese daño y lo enfrenta de dos maneras
distintas**:

- **Detectando** el error, para descartar el mensaje y pedir que se reenvíe.
- **Corrigiendo** el error en el destino, sin necesidad de retransmitir.

El sistema está compuesto por dos aplicaciones independientes que se comunican
por red:

- Un **emisor**, escrito en **Python**, que toma un texto, le agrega información
  de redundancia, le aplica ruido artificial y lo transmite.
- Un **receptor**, escrito en **TypeScript**, que recibe la trama dañada,
  verifica su integridad, la corrige si puede y muestra el mensaje.

Están en lenguajes distintos a propósito: el enunciado lo exige, y eso obliga a
que ambos respeten un contrato común en lugar de compartir código.

---

## Arquitectura de capas

Cada aplicación está organizada en capas, y cada capa ofrece servicios concretos.
El mensaje **desciende** por la pila del emisor y **asciende** por la del
receptor.

```
        EMISOR (Python)                          RECEPTOR (TypeScript)

   APLICACIÓN                                         APLICACIÓN
   solicitar_mensaje                                mostrar_mensaje
        │  "Hola"                                          ▲  "Hola"
        ▼                                                  │
   PRESENTACIÓN                                       PRESENTACIÓN
   codificar_mensaje                                decodificar_mensaje
        │  01001000...                                     ▲
        ▼                                                  │
   ENLACE                                                ENLACE
   calcular_integridad                    verificar_integridad · corregir_mensaje
        │  01001000... + redundancia                       ▲
        ▼                                                  │
   RUIDO                                                   │
   aplicar_ruido                                           │
        │  algunos bits invertidos                         │
        ▼                                                  │
   TRANSMISIÓN  ─────────── TCP · puerto 5001 ────────► TRANSMISIÓN
   enviar_informacion                              recibir_informacion
```

### Qué hace cada capa

| Capa | Responsabilidad |
|---|---|
| **Aplicación** | Pide el texto a enviar, el algoritmo de integridad y la tasa de error. Del otro lado, muestra el mensaje recibido o el error correspondiente. |
| **Presentación** | Traduce el texto a ASCII binario, 8 bits por carácter. La letra `A` se convierte en `01000001`. |
| **Enlace** | Calcula la información de redundancia y la concatena al mensaje. En el receptor, la usa para verificar y, si el algoritmo lo permite, corregir. |
| **Ruido** | Simula el canal no confiable. Existe **solo en el emisor**: invierte cada bit con una probabilidad dada, afectando por igual a los datos y a la redundancia. |
| **Transmisión** | Envía y recibe las tramas por sockets TCP. |

---

## Los dos algoritmos

Ambos están implementados en **los dos lenguajes**, porque el emisor necesita
calcular la redundancia y el receptor necesita interpretarla.

### Hamming(n, m) — corrección de errores

Agrega bits de paridad que permiten **localizar exactamente qué bit se dañó** y
repararlo. El bitstream se divide en bloques de `m` bits y cada bloque recibe `r`
bits de paridad, donde `r` es el menor entero que cumple `m + r + 1 ≤ 2^r`.

Como cada bloque se protege por separado, el esquema corrige **un error por
bloque**, no uno en todo el mensaje.

| m | n | Bits de paridad | Overhead |
|---|---|---|---|
| 4 | 7 | 3 | 42.9 % |
| 8 | 12 | 4 | 33.3 % |
| 11 | 15 | 4 | 26.7 % |
| 16 | 21 | 5 | 23.8 % |

### CRC-32 IEEE 802.3 — detección de errores

Calcula un valor de 32 bits a partir del mensaje y lo anexa al final. El receptor
lo recalcula y lo compara: si no coinciden, la trama viene dañada.

**No corrige.** Solo distingue una trama íntegra de una corrupta, pero lo hace
con una fiabilidad muy alta: detecta el 100 % de las ráfagas de hasta 32 bits
consecutivos.

Usa el polinomio estándar `0x04C11DB7`, y se valida contra el vector canónico
`CRC32("123456789") = 0xCBF43926`.

---

## Estructura del repositorio

```
Lab_2/
├── emisor/                  Aplicación en Python
│   ├── app/
│   │   ├── capas/           Las cinco capas del emisor
│   │   ├── algoritmos/      hamming.py y crc32.py
│   │   ├── experimentos/    Barridos de métricas
│   │   ├── main.py          Servidor FastAPI
│   │   └── cli.py           Interfaz de línea de comandos
│   ├── frontend/            Interfaz web (React + Vite)
│   ├── tests/               165 pruebas
│   └── tools/               Generador de vectores y receptor de prueba
│
├── receptor/                Aplicación en TypeScript
│   ├── src/
│   │   ├── capas/           Las capas del receptor
│   │   ├── algoritmos/      hamming.ts y crc32.ts
│   │   └── main.ts          Servidor TCP + Express
│   ├── frontend/            Interfaz web (React + Vite)
│   └── tests/               97 pruebas
│
├── shared/                  Archivos compartidos por ambos lados
│   ├── PROTOCOLO.md         El contrato de trama
│   └── vectores.json        Casos de referencia cross-lenguaje
│
├── Informe/                 Reporte en PDF
└── docker-compose.yml
```

### Los archivos compartidos

`shared/` es la parte más importante para que las dos aplicaciones se entiendan.

**`PROTOCOLO.md`** define el formato exacto de las tramas: qué campos viajan, cómo
se codifica el texto, cómo se calculan los bits de paridad y el CRC. Si los dos
lados no coinciden bit a bit con ese documento, nada funciona.

**`vectores.json`** contiene 30 casos que asocian un mensaje y una configuración
con la trama exacta que ambos extremos deben producir. Las pruebas de Python y
las de TypeScript leen el mismo archivo, de modo que cualquier discrepancia entre
las dos implementaciones hace fallar una prueba en vez de aparecer durante una
demostración.

---

## Cómo ejecutar el proyecto

Se necesitan **dos terminales**, una para cada aplicación. Levanta primero el
receptor: el emisor no tiene a quién enviarle si no está escuchando.

### Terminal 1 — Receptor

```bash
cd receptor

# Solo la primera vez
npm install
cd frontend && npm install && npm run build && cd ..

# Levantar
npx tsx src/main.ts --puerto 5001 --puerto-ui 3000
```

Queda escuchando tramas en el puerto **5001** y sirve su interfaz en
**http://localhost:3000**

### Terminal 2 — Emisor

```bash
cd emisor

# Solo la primera vez
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..

# Levantar
uvicorn app.main:app --port 8000
```

Su interfaz queda en **http://localhost:8000**

Si todo salió bien, en la esquina superior derecha del emisor verás un indicador
verde que dice *"Receptor 127.0.0.1:5001 · escuchando"*.

### Con Docker

Alternativamente, ambas aplicaciones pueden levantarse juntas:

```bash
docker compose up --build
```

Esto expone el emisor en `localhost:8000` y el receptor en `localhost:3000`.

---

## Cómo usar la aplicación

La interfaz del emisor tiene dos pestañas.

### Pestaña "Enviar"

Transmite **un mensaje** y muestra qué le ocurre en cada capa.

1. Escribe el texto (solo caracteres ASCII, del 0 al 127).
2. Elige el algoritmo: Hamming o CRC-32.
3. Si elegiste Hamming, selecciona el tamaño de bloque `m`.
4. Define cómo se dañará la trama:
   - **Bernoulli** — cada bit se invierte con una probabilidad dada. Es el modelo
     del enunciado. Acepta `0.01`, `1/100` o `5 %`.
   - **k errores exactos** — invierte exactamente esa cantidad de bits.
   - **Ráfaga contigua** — daña un tramo consecutivo.
5. Opcionalmente fija una **semilla**, para que el ruido sea reproducible.
6. Presiona **Enviar al receptor**.

Debajo aparece la trama en cada nivel de la pila, bit por bit: la redundancia que
agregó la capa de enlace se resalta en verde y los bits que el ruido invirtió, en
rojo. A la derecha se muestra el veredicto del receptor.

El botón **Solo previsualizar trama** hace todo el cálculo sin abrir el socket,
útil si el receptor no está disponible.

### Pestaña "Experimentos"

Ejecuta miles de transmisiones automáticas variando el tamaño del mensaje, la
tasa de error y el algoritmo, y genera las cuatro gráficas del informe.

El selector **Modo** determina si los envíos viajan de verdad:

- **Local** — verifica dentro del propio emisor. Es rápido y no requiere que el
  receptor esté corriendo.
- **Socket real** — cada trama viaja por TCP y el veredicto lo da el receptor.

### La interfaz del receptor

Muestra en vivo cada trama que llega, con contadores por estado y el detalle de
cada una: la trama recibida, el síndrome o los CRC comparados, los bits
corregidos y el mensaje decodificado.

### Los cuatro resultados posibles

| Estado | Significado |
|---|---|
| **Íntegro** | La trama llegó sin daño. |
| **Corregido** | Llegó dañada y Hamming la reparó. Se entrega el mensaje. |
| **Error detectado** | CRC-32 detectó corrupción. No hay corrección posible, no se entrega mensaje. |
| **Error no corregible** | Hamming encontró más errores de los que puede reparar en un bloque. No se entrega mensaje. |

---

## Línea de comandos

El emisor también funciona sin interfaz gráfica:

```bash
cd emisor
source .venv/bin/activate

# ¿Hay un receptor escuchando?
python -m app.cli estado

# Enviar un mensaje
python -m app.cli enviar "Hola mundo" --algoritmo hamming --m 8 --error 1/100

# Ver la trama capa por capa sin abrir el socket
python -m app.cli enviar "Hola mundo" --algoritmo crc32 --error 0.01 --sin-enviar

# Inyectar errores dirigidos
python -m app.cli enviar "Redes" --algoritmo hamming --modo-ruido exactos --parametro-ruido 1
python -m app.cli enviar "Redes" --algoritmo crc32 --modo-ruido rafaga --parametro-ruido 8

# Barrido de experimentos exportado a CSV
python -m app.cli experimentos --repeticiones 200 --salida resultados.csv
```

---

## Pruebas

```bash
# Emisor — 165 pruebas
cd emisor && source .venv/bin/activate && python -m pytest tests -q

# Receptor — 97 pruebas
cd receptor && npm test
```

Ambas suites verifican, entre otras cosas:

- El vector canónico `CRC32("123456789") = 0xCBF43926`.
- Que Hamming corrija un error inyectado en **cada una** de las posiciones de un
  bloque, para los cuatro valores de `m`.
- Que CRC-32 detecte el 100 % de las ráfagas de hasta 32 bits.
- Los 30 vectores de referencia de `shared/vectores.json`, que garantizan que
  Python y TypeScript producen exactamente las mismas tramas.

---

## Nota sobre la simulación del ruido

La capa de ruido vive del lado del emisor, lo cual puede parecer contraintuitivo:
en la realidad, el daño ocurre en el medio de transmisión, no en quien envía.

Se implementó así porque emisor y receptor corren en la misma computadora, donde
no hay interferencia real que observar. La capa de ruido **simula** ese medio
imperfecto justo antes de transmitir, lo que permite estudiar el comportamiento
de los algoritmos bajo condiciones controladas y reproducibles.

El emisor conoce las posiciones exactas de los bits que invirtió, pero **nunca se
las envía al receptor**: solo viajan la trama dañada y el nombre del algoritmo.
De esta manera, el veredicto del receptor se obtiene únicamente a partir de la
información de redundancia, sin ninguna ventaja artificial.
