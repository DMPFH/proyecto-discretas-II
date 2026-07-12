"""
dmphf.py
========
Núcleo del proyecto: Dynamic Minimal Perfect Hash Function (D-MPHF).

Implementa la fórmula exacta de las diapositivas:

    h1(k) = (a1*k_int + b1) mod p mod n      # posición candidata
    h2(k) = (a2*k_int + b2) mod p mod r      # bucket ("subgrupo")
    hf(k) = ( h1(k) + g[h2(k)] ) mod n       # posición final

Es una variante didáctica del algoritmo "Hash, Displace and Compress"
(CHD) de Belazzougui, Botelho y Dietzfelbinger (2009), que es el
resultado clásico detrás de toda función hash perfecta mínima moderna
(usado en librerías reales como CMPH y BBHash). La extensión "dinámica"
(soporte de inserciones tras la construcción) es la contribución
propia del proyecto: no forma parte del algoritmo CHD original, que es
estrictamente estático.

Arquitectura Servidor/MCU de las diapositivas:
  - build()  representa el trabajo "del Servidor": costoso, offline,
    solo se ejecuta al construir o reconstruir la tabla.
  - lookup() representa el trabajo "del MCU": SOLO dos evaluaciones
    hash, una suma, dos módulos y un acceso a arreglo. Nada de punteros,
    nada de listas -> por eso el acceso es O(1) determinístico y la
    huella de memoria es mínima (ideal para RAM de un microcontrolador).

NOTA IMPORTANTE (para el informe): una función hash perfecta mínima con
0% de desperdicio exacto solo existe, en sentido estricto, para un
conjunto ESTÁTICO de m llaves conocido de antemano (n = m). Para poder
insertar llaves nuevas después de construida la tabla, este proyecto
reserva una pequeña holgura (`slack`) y usa reconstrucción local
amortizada (ver recurrence.py). Con slack = 0 se obtiene el caso
estático clásico (100% de ocupación exacta, igual que en la diapositiva
de comparación); con slack > 0 se obtiene la versión dinámica.
"""

from __future__ import annotations
import math
import random
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

from .modular_arithmetic import key_to_int, is_prime
from .group_theory import AffineMap
from .recurrence import LCG, CapacityGrowth
from .succinct_rank import BitRank

# Primo grande fijo (Mersenne prime 2^61 - 1), universo de codificación
# de llaves. Es primo (verificable con is_prime), y suficientemente
# grande para que la codificación de llaves típicas (enteros de 32/64
# bits, strings cortos) no sufra colisiones sistemáticas antes de
# llegar a las funciones hash universales.
DEFAULT_P = (1 << 61) - 1
assert is_prime(DEFAULT_P), "DEFAULT_P debe ser primo (Mersenne prime 2^61-1)"


class UniversalHash:
    """
    Envoltura de un AffineMap (grupo afín AGL(1, Z_p)) que reduce el
    resultado a un rango [0, range_size) mediante un módulo final.
    Es la familia de hashing universal de Carter-Wegman:
        h(x) = ((a*x + b) mod p) mod range_size
    """

    def __init__(self, p: int, range_size: int, rng: random.Random):
        a = rng.randrange(1, p)
        b = rng.randrange(0, p)
        self.affine = AffineMap(a, b, p)
        self.range_size = range_size

    def __call__(self, k_int: int) -> int:
        return self.affine(k_int) % self.range_size


@dataclass
class BuildStats:
    attempts: int = 0
    n: int = 0
    r: int = 0
    m: int = 0
    build_time_s: float = 0.0


@dataclass
class InsertResult:
    position: int
    local_retries: int
    rebuilt: bool
    new_n: Optional[int] = None


class DMPHFBuildError(RuntimeError):
    pass


class DMPHF:
    """Función Hash Perfecta Mínima (Dinámica)."""

    def __init__(
        self,
        slack: float = 0.0,
        bucket_avg_size: float = 3.0,
        seed: Optional[int] = None,
        p: int = DEFAULT_P,
        max_global_retries: int = 60,
        max_local_lcg_tries: int = 40,
        growth_factor: float = 1.5,
    ):
        if not (0.0 <= slack < 1.0):
            raise ValueError("slack debe estar en [0, 1)")
        self.slack = slack
        self.bucket_avg_size = bucket_avg_size
        self.p = p
        self.max_global_retries = max_global_retries
        self.max_local_lcg_tries = max_local_lcg_tries
        self.growth_factor = growth_factor
        self._master_rng = random.Random(seed)

        # Estado tras build():
        self.n = 0
        self.r = 0
        self.h1: Optional[UniversalHash] = None
        self.h2: Optional[UniversalHash] = None
        self.g: List[int] = []
        self.occupied: bytearray = bytearray()
        self.keys_at_position: List[Any] = []
        self.buckets: List[List[tuple]] = []  # bucket -> [(key, k_int, h1v), ...]
        self.next_free_ptr = 0
        self.m = 0

        self.build_stats = BuildStats()
        self.total_local_retries = 0
        self.total_rebuilds = 0
        self.insert_trace: List[InsertResult] = []

        # Estado del paso de compresión (n exacto = m, ver succinct_rank.py)
        self.compressed = False
        self.n_working = 0
        self.bitrank: Optional[BitRank] = None

    # ------------------------------------------------------------------
    # Construcción (offline, "Servidor")
    # ------------------------------------------------------------------

    def build(self, keys: Iterable[Any], exact_minimal: bool = False,
              working_gamma: float = 1.23) -> None:
        """
        Construye la D-MPHF.

        exact_minimal=False (default): construcción "dinámica". Usa
            n = ceil(m / (1 - slack)); soporta insert() directamente.
        exact_minimal=True: construcción "estática exacta". Internamente
            sobre-provisiona con n' = ceil(m * working_gamma) para que
            la búsqueda de desplazamientos converja rápido, y luego
            aplica el paso de COMPRESIÓN (succinct_rank.BitRank) para
            que el rango final expuesto al usuario sea EXACTAMENTE
            n = m (0% de desperdicio literal). insert() sigue
            funcionando: descomprime automáticamente en la primera
            inserción (ver decompress_to_dynamic()).
        """
        import time

        t0 = time.perf_counter()
        keys = list(dict.fromkeys(keys))  # elimina duplicados, preserva orden
        m = len(keys)
        if m == 0:
            raise ValueError("No se puede construir una D-MPHF sin llaves")

        if exact_minimal:
            n = max(1, math.ceil(m * working_gamma))
        else:
            n = max(1, math.ceil(m / (1.0 - self.slack))) if self.slack > 0 else m
        r = max(1, round(m / self.bucket_avg_size))

        attempts_at_this_n = 0
        total_attempts = 0
        max_total_attempts = self.max_global_retries * 8

        while True:
            total_attempts += 1
            ok = self._try_build_once(keys, n, r)
            if ok:
                break
            attempts_at_this_n += 1
            if attempts_at_this_n >= self.max_global_retries:
                if total_attempts >= max_total_attempts:
                    raise DMPHFBuildError(
                        f"No fue posible construir la D-MPHF tras "
                        f"{total_attempts} intentos con m={m}. "
                        f"Sugerencia: aumente `slack` o reduzca "
                        f"`bucket_avg_size`."
                    )
                n = math.ceil(n * 1.07) + 1
                attempts_at_this_n = 0

        if exact_minimal:
            self._compress()

        self.build_stats = BuildStats(
            attempts=total_attempts, n=self.n, r=self.r, m=m,
            build_time_s=time.perf_counter() - t0,
        )

    def _compress(self) -> None:
        """
        Paso de COMPRESIÓN de CHD: colapsa las m posiciones ocupadas de
        un rango disperso [0, n') a un rango denso [0, m) mediante una
        estructura de rank succinta. Después de esto, self.n == self.m
        exactamente (0% de desperdicio real, no aproximado).
        """
        n_working = self.n
        bitrank = BitRank(n_working)
        for pos in range(n_working):
            if self.occupied[pos]:
                bitrank.set_bit(pos)
        bitrank.build()
        assert bitrank.total_ones == self.m, "Inconsistencia en el conteo de ocupación"

        compact_keys: List[Any] = [None] * self.m
        running = 0
        for pos in range(n_working):
            if self.occupied[pos]:
                compact_keys[running] = self.keys_at_position[pos]
                running += 1

        self.n_working = n_working
        self.n = self.m
        self.keys_at_position = compact_keys
        self.bitrank = bitrank
        self.compressed = True

    def decompress_to_dynamic(self) -> None:
        """
        Revierte el paso de compresión para volver a habilitar insert().
        No requiere reconstrucción: h1, h2, g, buckets y el bitmap
        `occupied` (en el espacio de trabajo n_working) siguen siendo
        válidos; solo hace falta reexpandir `keys_at_position` al rango
        disperso [0, n_working) usando la misma estructura de rank.
        """
        if not self.compressed:
            return
        n_working = self.n_working
        full_keys: List[Any] = [None] * n_working
        running = 0
        for pos in range(n_working):
            if self.occupied[pos]:
                full_keys[pos] = self.keys_at_position[running]
                running += 1
        self.keys_at_position = full_keys
        self.n = n_working
        self.compressed = False
        self.bitrank = None

    def _try_build_once(self, keys: List[Any], n: int, r: int) -> bool:
        rng = self._master_rng
        h1 = UniversalHash(self.p, n, rng)
        h2 = UniversalHash(self.p, r, rng)

        buckets: List[List[tuple]] = [[] for _ in range(r)]
        for key in keys:
            k_int = key_to_int(key, self.p)
            h1v = h1(k_int)
            b = h2(k_int)
            buckets[b].append((key, k_int, h1v))

        # Colisión fatal: dos llaves del mismo bucket con igual h1v
        # nunca pueden separarse por traslación -> descartar intento.
        for bucket in buckets:
            seen_h1 = set()
            for _, _, h1v in bucket:
                if h1v in seen_h1:
                    return False
                seen_h1.add(h1v)

        occupied = bytearray(n)
        g = [0] * r
        keys_at_position: List[Any] = [None] * n
        next_free_ptr = 0

        # Procesar buckets de mayor a menor tamaño (heurística CHD:
        # minimiza el costo esperado total de búsqueda).
        order = sorted(range(r), key=lambda b: -len(buckets[b]))

        for b in order:
            bucket = buckets[b]
            if not bucket:
                continue

            if len(bucket) == 1:
                # Bucket singleton: basta un slot libre cualquiera.
                # Cursor amortizado O(n) total (nunca retrocede).
                while next_free_ptr < n and occupied[next_free_ptr]:
                    next_free_ptr += 1
                if next_free_ptr >= n:
                    return False
                key, k_int, h1v = bucket[0]
                pos = next_free_ptr
                d = (pos - h1v) % n
                occupied[pos] = 1
                keys_at_position[pos] = key
                g[b] = d
                continue

            d = self._search_displacement(
                [h1v for _, _, h1v in bucket], occupied, n, b
            )
            if d is None:
                return False
            g[b] = d
            for key, k_int, h1v in bucket:
                pos = (h1v + d) % n
                occupied[pos] = 1
                keys_at_position[pos] = key

        # Éxito: confirmar estado
        self.n, self.r = n, r
        self.h1, self.h2, self.g = h1, h2, g
        self.occupied = occupied
        self.keys_at_position = keys_at_position
        self.buckets = buckets
        self.next_free_ptr = next_free_ptr
        self.m = len(keys)
        return True

    def _search_displacement(self, h1_vals, occupied, n, bucket_id) -> Optional[int]:
        tried = set()
        candidates: List[int] = []

        lcg_seed = (bucket_id * 2654435761 + 1) % n if n > 1 else 0
        lcg = LCG(seed=lcg_seed, m=n)
        for _ in range(min(self.max_local_lcg_tries, n)):
            d = next(lcg)
            if d not in tried:
                tried.add(d)
                candidates.append(d)

        for d in candidates:
            positions = [(h1v + d) % n for h1v in h1_vals]
            if len(set(positions)) == len(positions) and all(
                not occupied[p] for p in positions
            ):
                return d

        # Fallback: barrido completo (garantiza completitud si existe
        # una solución para este n).
        for d in range(n):
            if d in tried:
                continue
            positions = [(h1v + d) % n for h1v in h1_vals]
            if len(set(positions)) == len(positions) and all(
                not occupied[p] for p in positions
            ):
                return d
        return None

    # ------------------------------------------------------------------
    # Búsqueda O(1) ("MCU")
    # ------------------------------------------------------------------

    def _position_for(self, key: Any) -> int:
        k_int = key_to_int(key, self.p)
        b = self.h2(k_int)
        return (self.h1(k_int) + self.g[b]) % self.n

    def lookup(self, key: Any) -> Optional[int]:
        """
        Devuelve la posición de `key` en [0, n) si pertenece al
        conjunto construido, o None si no pertenece.

        IMPORTANTE (propiedad fundamental de las MPHF): la fórmula
        hf(k) SIEMPRE devuelve un entero en [0, n), incluso para llaves
        que nunca formaron parte del conjunto original. Por eso es
        indispensable el paso de verificación (comparar la llave
        almacenada en esa posición); sin él, una MPHF usada como
        "tabla hash de propósito general" reportaría falsos positivos.
        """
        k_int = key_to_int(key, self.p)
        b = self.h2(k_int)

        if not self.compressed:
            pos = (self.h1(k_int) + self.g[b]) % self.n
            if self.keys_at_position[pos] == key:
                return pos
            return None

        # Modo comprimido: primero ubicar en el espacio de trabajo
        # disperso [0, n_working), luego comprimir con rank() al
        # rango denso [0, m).
        working_pos = (self.h1(k_int) + self.g[b]) % self.n_working
        if self.bitrank.get_bit(working_pos) == 0:
            return None
        pos = self.bitrank.rank(working_pos)
        if self.keys_at_position[pos] == key:
            return pos
        return None

    def __contains__(self, key: Any) -> bool:
        return self.lookup(key) is not None

    # ------------------------------------------------------------------
    # Inserción dinámica ("efecto dominó")
    # ------------------------------------------------------------------

    def insert(self, key: Any) -> InsertResult:
        if self.compressed:
            # Insertar sobre una tabla "estática exacta" requiere volver
            # al espacio de trabajo disperso; no cuesta una reconstrucción
            # completa, solo reexpandir el mapeo (ver decompress_to_dynamic).
            self.decompress_to_dynamic()

        if key in self:
            pos = self._position_for(key)
            return InsertResult(position=pos, local_retries=0, rebuilt=False)

        k_int = key_to_int(key, self.p)
        h1v = self.h1(k_int)
        b = self.h2(k_int)
        pos = (h1v + self.g[b]) % self.n

        if not self.occupied[pos]:
            # Caso feliz: slot libre, inserción directa O(1), sin
            # reacomodo.
            self.occupied[pos] = 1
            self.keys_at_position[pos] = key
            self.buckets[b].append((key, k_int, h1v))
            self.m += 1
            result = InsertResult(position=pos, local_retries=0, rebuilt=False)
            self.insert_trace.append(result)
            return result

        # Colisión -> "efecto dominó": liberar el bucket completo y
        # buscar una nueva traslación que acomode a TODOS sus miembros
        # (incluida la llave nueva).
        old_bucket = self.buckets[b]
        old_positions = [(h1val + self.g[b]) % self.n for _, _, h1val in old_bucket]
        for p in old_positions:
            self.occupied[p] = 0
            self.keys_at_position[p] = None

        trial_bucket = old_bucket + [(key, k_int, h1v)]
        h1_vals = [h1val for _, _, h1val in trial_bucket]

        if len(set(h1_vals)) != len(h1_vals):
            # Colisión fatal de h1 dentro del bucket: ninguna traslación
            # puede separarlos. Se restaura el estado anterior y se
            # escala a reconstrucción completa.
            for kk, kint, h1val in old_bucket:
                pp = (h1val + self.g[b]) % self.n
                self.occupied[pp] = 1
                self.keys_at_position[pp] = kk
            return self._rebuild_with_growth(key)

        d = self._search_displacement(h1_vals, self.occupied, self.n, b)
        self.total_local_retries += 1

        if d is not None:
            self.g[b] = d
            for kk, kint, h1val in trial_bucket:
                pp = (h1val + d) % self.n
                self.occupied[pp] = 1
                self.keys_at_position[pp] = kk
            self.buckets[b] = trial_bucket
            self.m += 1
            pos = (h1v + d) % self.n
            result = InsertResult(position=pos, local_retries=1, rebuilt=False)
            self.insert_trace.append(result)
            return result

        # Reacomodo local imposible (bucket/tabla demasiado llenos):
        # restaurar y escalar a reconstrucción completa.
        for kk, kint, h1val in old_bucket:
            pp = (h1val + self.g[b]) % self.n
            self.occupied[pp] = 1
            self.keys_at_position[pp] = kk
        return self._rebuild_with_growth(key)

    def _rebuild_with_growth(self, new_key: Any) -> InsertResult:
        growth = CapacityGrowth(n0=self.n, growth_factor=self.growth_factor)
        new_n_target = growth.grow()

        all_keys = [k for k in self.keys_at_position if k is not None] + [new_key]

        rebuilt = DMPHF(
            slack=self.slack,
            bucket_avg_size=self.bucket_avg_size,
            seed=self._master_rng.randrange(0, 1 << 30),
            p=self.p,
            max_global_retries=self.max_global_retries,
            max_local_lcg_tries=self.max_local_lcg_tries,
            growth_factor=self.growth_factor,
        )
        # Aseguramos que la nueva construcción tenga al menos new_n_target
        # de espacio, ajustando el slack efectivo si hace falta.
        m_new = len(all_keys)
        effective_slack = max(self.slack, 1 - m_new / new_n_target)
        rebuilt.slack = min(effective_slack, 0.5)
        rebuilt.build(all_keys)

        # Preservar los contadores/historial acumulados de ESTA instancia;
        # solo se reemplaza el estado estructural (h1,h2,g,ocupacion,...)
        # por el de la reconstrucción.
        preserved_rebuilds = self.total_rebuilds + 1
        preserved_local_retries = self.total_local_retries
        preserved_trace = self.insert_trace

        self.__dict__.update(rebuilt.__dict__)

        self.total_rebuilds = preserved_rebuilds
        self.total_local_retries = preserved_local_retries
        self.insert_trace = preserved_trace

        pos = self._position_for(new_key)
        result = InsertResult(
            position=pos, local_retries=0, rebuilt=True, new_n=self.n
        )
        self.insert_trace.append(result)
        return result

    # ------------------------------------------------------------------
    # Estadísticas / memoria
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        import sys

        max_disp = max(self.g) if self.g else 0
        bits_per_g = max(1, math.ceil(math.log2(max_disp + 1)))
        theoretical_bits = self.r * bits_per_g
        theoretical_bytes = math.ceil(theoretical_bits / 8)

        python_bytes = (
            sys.getsizeof(self.g)
            + sum(sys.getsizeof(x) for x in self.g)
        )

        result = {
            "m_llaves": self.m,
            "n_slots (externo)": self.n,
            "r_buckets": self.r,
            "ocupacion_%": round(100 * self.m / self.n, 3) if self.n else 0,
            "bits_por_desplazamiento": bits_per_g,
            "memoria_teorica_bytes(g)": theoretical_bytes,
            "memoria_python_bytes(g)": python_bytes,
            "intentos_construccion": self.build_stats.attempts,
            "tiempo_construccion_s": round(self.build_stats.build_time_s, 6),
            "total_reconstrucciones": self.total_rebuilds,
            "total_reintentos_locales": self.total_local_retries,
            "modo": "estatico_exacto (comprimido)" if self.compressed else "dinamico",
        }

        if self.compressed:
            result["n_working (espacio disperso interno)"] = self.n_working
            result["memoria_bitrank_bytes"] = self.bitrank.total_bytes()
            result["memoria_total_bytes(g+bitrank)"] = (
                theoretical_bytes + self.bitrank.total_bytes()
            )

        return result
