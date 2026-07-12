"""
group_theory.py
================
Módulo 1 del proyecto: Grupos y Estructuras Algebraicas.

Formaliza dos ideas de las diapositivas:

1. Cada función hash "universal" h(k) = (a*k + b) mod p es un elemento
   del GRUPO AFÍN  AGL(1, Z_p) = { x -> a*x + b (mod p) : a in Z_p*, b in Z_p }.
   Este grupo actúa sobre el conjunto Z_p mediante la composición usual
   de funciones, y cada elemento (a != 0, p primo) es una BIYECCIÓN de
   Z_p en sí mismo (demostrado con el inverso modular de a).

2. La resolución de colisiones por desplazamiento (g[bucket]) es una
   ACCIÓN DEL GRUPO CÍCLICO (Z_n, +) sobre el conjunto de posiciones
   {0, ..., n-1} por traslación: t_d(x) = (x + d) mod n.
   Cada bucket recibe un elemento t_d distinto que "permuta" sus
   posiciones candidatas hasta lograr inyectividad global -> esto es
   exactamente la "permutación local (grupo simétrico)" que describen
   las diapositivas, restringida al subgrupo cíclico generado por la
   traslación.

Ninguna de estas funciones es necesaria para que el algoritmo corra;
existen para que el proyecto pueda EXPLICAR, con lenguaje de teoría de
grupos, por qué el método funciona (requisito de "comprensión
conceptual" del enunciado).
"""

from __future__ import annotations
from typing import Callable
from .modular_arithmetic import mod_inverse, extended_gcd


class AffineMap:
    """
    Un elemento x -> (a*x + b) mod p del grupo afín AGL(1, Z_p).

    Se comporta como una biyección de Z_p en Z_p cuando p es primo y
    a no es congruente con 0 mod p (lo cual se verifica al construirlo).
    """

    def __init__(self, a: int, b: int, p: int):
        if p < 2:
            raise ValueError("p debe ser >= 2")
        a = a % p
        if a == 0:
            raise ValueError("a no puede ser 0 mod p: no sería biyectiva")
        self.a, self.b, self.p = a, b % p, p

    def __call__(self, x: int) -> int:
        return (self.a * x + self.b) % self.p

    def inverse(self) -> "AffineMap":
        """
        Elemento inverso en el grupo AGL(1, Z_p):
        si f(x) = a*x + b, entonces f^{-1}(y) = a^{-1}*(y - b).
        Se calcula con el inverso modular (Euclides Extendido, Módulo 2).
        """
        a_inv = mod_inverse(self.a, self.p)
        b_inv = (-a_inv * self.b) % self.p
        return AffineMap(a_inv, b_inv, self.p)

    def is_bijection_on_verify(self, sample_size: int = 200) -> bool:
        """
        Verificación empírica (no exhaustiva si p es grande) de que
        f(f^{-1}(y)) == y para una muestra de puntos. Sirve como prueba
        de sanidad rápida en los tests.
        """
        inv = self.inverse()
        import random
        for _ in range(sample_size):
            y = random.randrange(0, self.p)
            if self(inv(y)) != y:
                return False
        return True

    def __repr__(self):
        return f"AffineMap(x -> {self.a}*x + {self.b} mod {self.p})"


class CyclicTranslation:
    """
    Elemento t_d(x) = (x + d) mod n del grupo cíclico (Z_n, +),
    usado para desplazar (permutar) las posiciones candidatas de un
    bucket completo durante la resolución de colisiones.
    """

    def __init__(self, d: int, n: int):
        self.d = d % n
        self.n = n

    def __call__(self, x: int) -> int:
        return (x + self.d) % self.n

    def order(self) -> int:
        """
        Orden del elemento en el grupo cíclico (Z_n, +):
        el menor k > 0 tal que k*d ≡ 0 (mod n), que por teoría de grupos
        elemental es  n / gcd(d, n).
        """
        if self.d == 0:
            return 1
        g, _, _ = extended_gcd(self.d, self.n)
        return self.n // g

    def generates_full_group(self) -> bool:
        """True si <t_d> = Z_n completo, es decir gcd(d, n) == 1."""
        return self.order() == self.n


def verify_injective_on_set(f: Callable[[int], int], domain: list) -> bool:
    """Utilidad genérica: ¿f es inyectiva restringida a `domain`?"""
    seen = set()
    for x in domain:
        y = f(x)
        if y in seen:
            return False
        seen.add(y)
    return True
