"""
modular_arithmetic.py
======================
Módulo 2 del proyecto: Teoría de Números y Criptografía.

Contiene las primitivas de aritmética modular sobre las que se construye
toda la D-MPHF:

  - Algoritmo de Euclides Extendido -> inverso modular.
  - Test de primalidad (Miller-Rabin) y búsqueda del siguiente primo.
  - Codificación determinística de llaves (int/str/bytes) a Z_p mediante
    la regla de Horner, evaluada en aritmética modular.

Todas las funciones son puras (sin estado) y están escritas para ser
citables y explicables en el informe: cada una corresponde a un
resultado clásico de teoría de números.
"""

from __future__ import annotations
import random
from typing import Tuple


# ---------------------------------------------------------------------------
# 1. Algoritmo de Euclides Extendido e inverso modular
# ---------------------------------------------------------------------------

def extended_gcd(a: int, b: int) -> Tuple[int, int, int]:
    """
    Devuelve (g, x, y) tales que a*x + b*y = g = gcd(a, b).

    Implementación iterativa (evita recursión profunda para enteros grandes,
    relevante si p se escoge del orden de 2^61 como en este proyecto).
    """
    old_r, r = a, b
    old_s, s = 1, 0
    old_t, t = 0, 1

    while r != 0:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
        old_t, t = t, old_t - q * t

    return old_r, old_s, old_t


def mod_inverse(a: int, p: int) -> int:
    """
    Inverso multiplicativo de a en Z_p, es decir, a^{-1} tal que
    (a * a^{-1}) mod p == 1.

    Existe si y solo si gcd(a, p) == 1 (garantizado automáticamente si p
    es primo y a no es múltiplo de p, que es el caso de uso en este
    proyecto: p siempre se elige primo).
    """
    a = a % p
    g, x, _ = extended_gcd(a, p)
    if g != 1:
        raise ValueError(
            f"No existe inverso modular: gcd({a}, {p}) = {g} != 1"
        )
    return x % p


# ---------------------------------------------------------------------------
# 2. Primalidad (Miller-Rabin determinístico para el rango usado aquí)
# ---------------------------------------------------------------------------

def is_prime(n: int, k: int = 20) -> bool:
    """
    Test de primalidad de Miller-Rabin (probabilístico, error < 4^-k).
    Con k=20 la probabilidad de falso positivo es despreciable
    (< 10^-12), suficiente para elegir el módulo p de la función hash.
    """
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31):
        if n == p:
            return True
        if n % p == 0:
            return False

    # n - 1 = 2^r * d
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1

    for _ in range(k):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def next_prime(n: int) -> int:
    """Menor primo >= n."""
    if n <= 2:
        return 2
    candidate = n if n % 2 == 1 else n + 1
    while not is_prime(candidate):
        candidate += 2
    return candidate


# ---------------------------------------------------------------------------
# 3. Codificación de llaves a Z_p (regla de Horner, en aritmética modular)
# ---------------------------------------------------------------------------

_HORNER_BASE = 257  # > 256 (rango de un byte), reduce colisiones triviales


def key_to_int(key, p: int) -> int:
    """
    Codifica una llave arbitraria (int, str o bytes) como un elemento de
    Z_p, de forma determinística y reproducible entre ejecuciones.

    - Si `key` es int: se reduce directamente mod p.
    - Si es str/bytes: se evalúa como un polinomio en la base 257 usando
      la regla de Horner, reduciendo mod p en cada paso (para no generar
      enteros gigantes y para que el resultado ya viva en Z_p):

          k_int = ( ( (c0*B + c1)*B + c2 )*B + ... ) mod p

    Esta codificación es la que garantiza que TODA la información de la
    llave pasa por aritmética modular antes de llegar a las funciones
    hash universales h1, h2.
    """
    if isinstance(key, bool):
        raise TypeError("No se aceptan booleanos como llave (ambiguo con int).")

    if isinstance(key, int):
        return key % p

    if isinstance(key, str):
        data = key.encode("utf-8")
    elif isinstance(key, bytes):
        data = key
    else:
        # Cualquier otro tipo: usar su representación textual estable
        data = repr(key).encode("utf-8")

    acc = 0
    for byte in data:
        acc = (acc * _HORNER_BASE + byte) % p
    return acc
