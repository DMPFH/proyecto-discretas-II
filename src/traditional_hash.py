"""
traditional_hash.py
====================
Tabla hash clásica con resolución de colisiones por ENCADENAMIENTO
(listas enlazadas), usada como línea base para reproducir exactamente
la tabla comparativa de la diapositiva 2:

    | Característica          | Tradicional            | D-MPHF        |
    |--------------------------|------------------------|---------------|
    | Acceso a memoria         | O(1) prom / O(n) peor  | O(1) determin.|
    | Gestión de colisiones    | Listas enlazadas (RAM) | Biyectividad  |
    | Utilización de slot      | < 70% (factor de carga)| ~100%         |
    | Estructura                | Dinámica con punteros  | Aritmética modular |

Se redimensiona automáticamente cuando el factor de carga supera 0.7,
igual que las implementaciones estándar de tablas hash (Python dict,
Java HashMap, etc.), para que la comparación sea justa y realista.
"""

from __future__ import annotations
from typing import Any, List, Optional


class ChainedHashTable:
    LOAD_FACTOR_THRESHOLD = 0.7

    def __init__(self, initial_capacity: int = 8):
        self.capacity = max(8, initial_capacity)
        self.buckets: List[List[tuple]] = [[] for _ in range(self.capacity)]
        self.count = 0
        self.total_resizes = 0
        self.total_probe_steps = 0  # para medir colisiones acumuladas

    def _hash(self, key: Any) -> int:
        return hash(key) % self.capacity

    def insert(self, key: Any, value: Any = True) -> None:
        idx = self._hash(key)
        bucket = self.buckets[idx]
        for i, (k, _) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return
        bucket.append((key, value))
        self.count += 1
        if self.count / self.capacity > self.LOAD_FACTOR_THRESHOLD:
            self._resize()

    def _resize(self) -> None:
        old_buckets = self.buckets
        self.capacity *= 2
        self.buckets = [[] for _ in range(self.capacity)]
        for bucket in old_buckets:
            for key, value in bucket:
                idx = self._hash(key)
                self.buckets[idx].append((key, value))
        self.total_resizes += 1

    def lookup(self, key: Any) -> Optional[Any]:
        idx = self._hash(key)
        bucket = self.buckets[idx]
        steps = 0
        for k, v in bucket:
            steps += 1
            if k == key:
                self.total_probe_steps += steps
                return v
        self.total_probe_steps += steps
        return None

    def __contains__(self, key: Any) -> bool:
        return self.lookup(key) is not None

    def stats(self) -> dict:
        chain_lengths = [len(b) for b in self.buckets]
        max_chain = max(chain_lengths) if chain_lengths else 0
        used_buckets = sum(1 for c in chain_lengths if c > 0)
        collided_buckets = sum(1 for c in chain_lengths if c > 1)

        # Estimación de memoria (bytes), modelo teórico clásico:
        # cada slot del arreglo de buckets es un puntero (8 bytes en
        # sistemas de 64 bits); cada entrada de la lista enlazada
        # ocupa: puntero al valor "next" + almacenamiento de la llave.
        PTR = 8
        KEY_OVERHEAD = 28  # aproximación de un int/objeto pequeño en CPython
        memoria_bytes = self.capacity * PTR + self.count * (PTR + KEY_OVERHEAD)

        return {
            "m_llaves": self.count,
            "capacidad_buckets": self.capacity,
            "factor_carga": round(self.count / self.capacity, 3),
            "cadena_maxima": max_chain,
            "buckets_con_colision": collided_buckets,
            "buckets_usados_%": round(100 * used_buckets / self.capacity, 2),
            "memoria_teorica_bytes": memoria_bytes,
            "total_resizes": self.total_resizes,
        }
