"""
recurrence.py
=============
Módulo 3 del proyecto: Ecuaciones en Diferencias.

Dos usos concretos de la recurrencia de primer orden  x_{t+1} = a*x_t + b
que aparece en las diapositivas:

1. LCG (Linear Congruential Generator): genera, de forma determinística
   y reproducible, la SECUENCIA DE CANDIDATOS de desplazamiento que se
   prueban al resolver una colisión de bucket. No es aleatoriedad real:
   es la órbita de la recurrencia x_{t+1} = (a*x_t + b) mod m, cuyo
   período y distribución se analizan con teoría de números clásica
   (Hull-Dobell).

2. CapacityGrowth: modela el "efecto dominó" de crecimiento de la tabla
   cuando las inserciones dinámicas agotan la holgura (slack) inicial.
   La capacidad sigue la recurrencia  n_{t+1} = ceil(a * n_t) + b,
   análoga al análisis amortizado de un arreglo dinámico, y permite
   predecir cuántas reconstrucciones completas ocurrirán tras m
   inserciones (análisis de costo amortizado).
"""

from __future__ import annotations
from math import gcd, ceil
from typing import Iterator


class LCG:
    """
    Generador congruencial lineal:  x_{t+1} = (a*x_t + b) mod m.

    Usado como generador de la SECUENCIA DE PRUEBA de desplazamientos
    g[bucket] en la construcción de la D-MPHF. Se eligen a, b que
    satisfacen el teorema de Hull-Dobell para garantizar período
    completo m (recorre TODOS los residuos antes de repetirse), lo cual
    evita ciclos cortos que harían fallar la búsqueda de desplazamiento.

    Teorema de Hull-Dobell: el LCG tiene período completo m si y solo si
      (i)   gcd(b, m) = 1
      (ii)  (a - 1) es divisible por cada primo que divide a m
      (iii) si 4 | m, entonces 4 | (a - 1)
    Para simplificar y garantizar (i)-(iii) sin factorizar m en cada
    llamada, se usa la construcción estándar a = 1 + 4*k (impar,
    ≡ 1 mod 4) y b coprimo con m, que satisface Hull-Dobell para
    cualquier m potencia de 2, y en la práctica da período largo /
    buena dispersión para m arbitrario (suficiente para este uso: no
    necesitamos criptografía, solo una órbita reproducible y bien
    distribuida).
    """

    def __init__(self, seed: int, m: int, a: int = None, b: int = None):
        if m <= 0:
            raise ValueError("m debe ser positivo")
        self.m = m
        self.a = a if a is not None else self._default_a(m)
        self.b = b if b is not None else self._default_b(seed, m)
        self.state = seed % m

    @staticmethod
    def _default_a(m: int) -> int:
        # a ≡ 1 (mod 4), impar -> buen comportamiento para m potencia de 2
        # y aceptable en general.
        return 2862933555777941757 % m if m > 4 else 3

    @staticmethod
    def _default_b(seed: int, m: int) -> int:
        b = (1442695040888963407 + seed) % m
        # Forzar gcd(b, m) = 1 (condición de Hull-Dobell) incrementando
        # si hace falta.
        while gcd(b, m) != 1 and m > 1:
            b = (b + 1) % m
        return b if b != 0 else 1

    def __iter__(self) -> Iterator[int]:
        return self

    def __next__(self) -> int:
        self.state = (self.a * self.state + self.b) % self.m
        return self.state

    def take(self, k: int) -> list:
        return [next(self) for _ in range(k)]


class CapacityGrowth:
    """
    Modela el crecimiento de la capacidad n de la tabla bajo la
    recurrencia de primer orden:

        n_{t+1} = ceil(growth_factor * n_t) + margin

    Se usa para decidir el nuevo tamaño de tabla cuando una inserción
    dinámica agota la holgura disponible y es necesario reconstruir
    (rehash) la D-MPHF completa. Un growth_factor > 1 (p. ej. 1.5)
    produce, igual que en un arreglo dinámico clásico, un costo
    AMORTIZADO O(1) por inserción a pesar de que cada reconstrucción
    individual cueste O(n).
    """

    def __init__(self, n0: int, growth_factor: float = 1.5, margin: int = 1):
        if growth_factor <= 1.0:
            raise ValueError("growth_factor debe ser > 1 para amortizar")
        self.n = n0
        self.growth_factor = growth_factor
        self.margin = margin
        self.history = [n0]

    def grow(self) -> int:
        self.n = ceil(self.growth_factor * self.n) + self.margin
        self.history.append(self.n)
        return self.n

    def amortized_cost_estimate(self, total_insertions: int) -> float:
        """
        Estimación clásica de costo amortizado total de reconstrucciones
        tras `total_insertions` inserciones, usando la suma geométrica
        de la recurrencia (serie geométrica de razón growth_factor):

            costo_total ~ n0 * (growth_factor / (growth_factor - 1))

        Dividido entre el número de inserciones da el costo amortizado
        por inserción (tiende a una constante, independiente de n).
        """
        r = self.growth_factor
        total_rebuild_cost = self.n * (r / (r - 1))
        return total_rebuild_cost / max(total_insertions, 1)
