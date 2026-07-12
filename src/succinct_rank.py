"""
succinct_rank.py
=================
Estructura auxiliar para el paso de "Compresión" (la C de CHD:
Compress-Hash-Displace) que permite pasar de una construcción con
holgura (n' > m, fácil y rápida de encontrar) a una función hash
perfecta mínima EXACTA (n = m, "0% de desperdicio" literal, como
promete la diapositiva de comparación).

Idea: si `occupied` es el bitmap de tamaño n' con exactamente m bits en
1 (las posiciones realmente usadas), entonces

    compress(pos) = rank(pos) = #{ i < pos : occupied[i] == 1 }

es una biyección estricta y creciente entre las m posiciones ocupadas
de [0, n') y el rango denso [0, m). Aplicar `rank` como paso final del
hash da acceso O(1) real a un rango de tamaño EXACTAMENTE m.

Implementación: bitmap empaquetado a 1 bit/slot + tabla de rangos
acumulados por bloques de 64 bits (técnica clásica "rank por bloques",
la misma idea de fondo que estructuras succintas como rank9), de forma
que rank(pos) se calcula en tiempo O(1) amortizado (una lectura de
tabla + a lo sumo 64 operaciones de bits, es decir, O(1) real ya que
64 es una constante fija, no depende de n).
"""

from __future__ import annotations
from array import array


class BitRank:
    BLOCK = 64

    def __init__(self, n: int):
        self.n = n
        self.bits = bytearray((n + 7) // 8)
        self._built = False
        self.block_rank: array = array("I")

    def set_bit(self, i: int) -> None:
        self.bits[i >> 3] |= (1 << (i & 7))

    def get_bit(self, i: int) -> int:
        return (self.bits[i >> 3] >> (i & 7)) & 1

    def build(self) -> None:
        """Precalcula el rank acumulado al inicio de cada bloque."""
        n_blocks = (self.n + self.BLOCK - 1) // self.BLOCK + 1
        self.block_rank = array("I", [0]) * 0  # reset
        self.block_rank = array("I", [0] * n_blocks)
        acc = 0
        for blk in range(n_blocks - 1):
            self.block_rank[blk] = acc
            start = blk * self.BLOCK
            end = min(start + self.BLOCK, self.n)
            for i in range(start, end):
                acc += self.get_bit(i)
        self.block_rank[n_blocks - 1] = acc
        self.total_ones = acc
        self._built = True

    def rank(self, pos: int) -> int:
        """#bits en 1 dentro de [0, pos). Requiere build() previo."""
        if not self._built:
            raise RuntimeError("Llame a build() antes de rank()")
        blk = pos // self.BLOCK
        r = self.block_rank[blk]
        start = blk * self.BLOCK
        for i in range(start, pos):
            r += self.get_bit(i)
        return r

    def total_bytes(self) -> int:
        import sys
        return len(self.bits) + sys.getsizeof(self.block_rank)
