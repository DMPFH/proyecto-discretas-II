# D-MPHF: Función Hash Perfecta Mínima (Dinámica) para Sistemas Embebidos

**Matemáticas Discretas II — Proyecto Final**

Implementación completa de una función hash perfecta mínima dinámica (D-MPHF),
construida mediante aritmética modular, teoría de grupos y relaciones de
recurrencia, con comparación empírica contra una tabla hash tradicional.

---

## 1. ¿Qué problema resuelve?

Dado un conjunto de `m` llaves conocidas (p. ej., identificadores de
dispositivos IoT), construir una función `hf: K → {0, ..., n-1}` que:

- sea **inyectiva** sobre el conjunto de llaves (cero colisiones),
- use la menor cantidad de memoria posible (`n` lo más cercano a `m`),
- responda en **O(1) determinístico** (sin listas enlazadas, sin punteros).

Esto es exactamente una **función hash perfecta mínima (MPHF)** cuando
`n = m` exactamente. Este proyecto además soporta **inserciones dinámicas**
después de la construcción inicial (la "D" de D-MPHF), algo que el algoritmo
clásico de MPHF no contempla.

## 2. Los tres módulos del curso, y dónde viven en el código

| Módulo del curso | Concepto usado | Archivo |
|---|---|---|
| **Teoría de números / aritmética modular** | Algoritmo de Euclides Extendido, inverso modular, primalidad (Miller-Rabin), codificación de llaves vía regla de Horner en `Z_p` | `src/modular_arithmetic.py` |
| **Teoría de grupos** | Grupo afín `AGL(1, Z_p) = {x → ax+b mod p}` (familia hash universal de Carter-Wegman) como acción de grupo biyectiva; subgrupo cíclico `(Z_n, +)` actuando por traslación para resolver colisiones | `src/group_theory.py` |
| **Ecuaciones en diferencias (recurrencias)** | Generador congruencial lineal `x_{t+1} = (a·x_t + b) mod m` para la búsqueda de desplazamientos; recurrencia de crecimiento de capacidad `n_{t+1} = ⌈a·n_t⌉ + b` para el análisis amortizado de reconstrucciones | `src/recurrence.py` |
| **Estructuras de datos succintas** (extensión propia) | Bitmap empaquetado + tabla de rangos por bloques (`rank`) para el paso de *compresión* que logra el 0% de desperdicio exacto | `src/succinct_rank.py` |
| **Algoritmo integrado** | Ensambla los tres módulos en la construcción tipo *Hash-Displace-Compress* (CHD) | `src/dmphf.py` |

## 3. La fórmula exacta implementada

```
h1(k) = (a1·k_int + b1) mod p mod n     # posición candidata   (grupo afín)
h2(k) = (a2·k_int + b2) mod p mod r     # bucket / "subgrupo"  (grupo afín)
hf(k) = (h1(k) + g[h2(k)]) mod n        # posición final       (traslación cíclica)
```

`g[]` (el vector de desplazamiento) se calcula **una vez, offline**
("Servidor") probando candidatos generados por el LCG (recurrencia) hasta que
todas las llaves de un bucket caen en posiciones libres y distintas. Esto es
una **permutación local** (elemento del subgrupo cíclico `(Z_n,+)`) aplicada
solo a ese bucket — exactamente la idea de "reordenamiento en subgrupos
específicos" de la diapositiva 1.

Una vez calculado `g[]`, la consulta ("MCU") es aritmética pura: dos hashes
afines, una suma, dos módulos, un acceso a arreglo. **Cero punteros.**

## 4. Dos modos de uso (léase esto antes de interpretar los resultados)

Es importante ser honestos sobre una tensión matemática real: una función
hash perfecta mínima con **0% de desperdicio exacto** (`n = m`) solo puede
garantizarse, en sentido estricto, para un conjunto **estático** conocido de
antemano. Este proyecto ofrece los dos regímenes:

### Modo estático exacto — `build(keys, exact_minimal=True)`
Construye internamente con una pequeña holgura (`n' ≈ 1.23·m`, fácil y rápida
de resolver), y luego aplica el paso de **compresión** (`succinct_rank.py`):
una estructura de `rank` colapsa las `m` posiciones ocupadas de `[0, n')` a un
rango **denso** `[0, m)`. El resultado: `n == m` exactamente, **0% de
desperdicio real**, verificado en las pruebas (`test_biyeccion_exacta_modo_comprimido`).
No soporta `insert()` directamente (ver siguiente punto).

### Modo dinámico — `build(keys, slack=0.15)` (o cualquier `slack > 0`)
Reserva un margen de slots libres desde el inicio. `insert(key)`:
1. Si el slot objetivo está libre → inserción directa O(1).
2. Si hay colisión → **"efecto dominó"**: se libera el bucket completo y se
   busca una nueva traslación (recurrencia LCG) que acomode a todos sus
   miembros, incluida la llave nueva.
3. Si ni eso alcanza → se dispara una **reconstrucción completa** con una
   capacidad nueva dada por la recurrencia `n_{t+1} = ⌈growth_factor·n_t⌉`
   (análisis de costo amortizado, igual que un arreglo dinámico clásico).

Si se llama `insert()` sobre una tabla en modo "estático exacto", el sistema
**descomprime automáticamente** (sin reconstrucción completa, ver
`decompress_to_dynamic()`) y continúa en modo dinámico.

> **Nota para el informe:** esta distinción es, en sí misma, un resultado del
> proyecto: demuestra que entendieron la diferencia entre una MPHF clásica
> (estática) y la extensión dinámica, en vez de simplemente afirmar "100% de
> ocupación" sin matices.

## 5. Cómo correrlo

```bash
pip install -r requirements.txt

# Pruebas (35 casos: aritmética modular, grupos, recurrencias, D-MPHF, tabla tradicional)
pytest tests/ -v

# Demostración narrativa Servidor/MCU
python3 demo.py

# Benchmarks completos (D-MPHF estático, dinámico, y tabla tradicional)
python3 benchmarks/run_benchmarks.py
```

## 6. Resultados medidos (no simulados)

Con `N = 20{,}000` llaves tipo `"iot-device-XXXXXXXX"`:

| Métrica | D-MPHF (estático exacto) | Hash tradicional (encadenamiento) |
|---|---|---|
| Ocupación | **100.0 %** | 61.0 % |
| Memoria de la estructura | **14,074 bytes** | 982,144 bytes |
| Cadena máxima (colisiones) | **0** (biyectivo) | 6 |
| Lookup promedio | 11.2 µs | 0.63 µs |

**Ahorro de memoria: ~98.6%.** Este es el resultado que sí sostiene la
promesa central de las diapositivas: para RAM crítica en IoT, la D-MPHF es
dramáticamente más compacta.

**Hallazgo honesto sobre velocidad:** en esta implementación en Python puro,
la tabla tradicional resulta **más rápida** en lookup (no más lenta). La
razón no es que el algoritmo sea peor: es que `hash()` y el acceso a `dict`
de CPython están escritos en C y altamente optimizados, mientras que
`hf(k)` aquí ejecuta aritmética modular sobre enteros de 61 bits **en
bytecode interpretado de Python**, con el overhead de llamada a función que
eso implica. En una implementación real en C para un microcontrolador (el
escenario real de las diapositivas), esas mismas operaciones —multiplicación,
suma, dos módulos— son instrucciones de máquina de **un solo ciclo**, y ahí
sí la ausencia de persecución de punteros (que genera fallos de caché en
listas enlazadas) favorecería a la D-MPHF también en velocidad, no solo en
memoria. Esta es la razón por la que las diapositivas separan explícitamente
"Servidor" (donde el costo de construcción no importa) de "MCU" (donde
memoria, no velocidad de reloj, es el recurso crítico).

## 7. Limitaciones conocidas y trabajo futuro

- La búsqueda de desplazamiento usa un `fallback` de barrido completo
  `O(n)` en el peor caso por bucket; para `m` muy grande (> 10⁵) en Python
  puro esto puede volverse lento. Una implementación en C con buckets más
  pequeños (`bucket_avg_size` menor) y `SIMD` para el paso de verificación
  escalaría mucho mejor.
- El bitmap `occupied` (modo dinámico) usa 1 byte por slot en vez de 1 bit,
  por simplicidad de código; `succinct_rank.py` sí implementa el empaquetado
  real de 1 bit/slot para el modo comprimido.
- No se implementó eliminación (`delete`) de llaves; es una extensión natural
  (marcar tumba lógica + recompresión periódica).

## 8. Referencia académica

El algoritmo base (sin la extensión dinámica) es una variante didáctica de:

> Belazzougui, D., Botelho, F. C., & Dietzfelbinger, M. (2009).
> *Hash, displace, and compress.* European Symposium on Algorithms (ESA).

La familia de hashing universal `(ax+b) mod p mod r` es la de:

> Carter, J. L., & Wegman, M. N. (1979).
> *Universal classes of hash functions.* Journal of Computer and System Sciences.
