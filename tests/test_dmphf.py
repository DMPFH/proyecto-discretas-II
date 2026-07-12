"""
tests/test_dmphf.py
====================
Batería de pruebas del proyecto. Corre con:

    pytest -v

Cubre los tres módulos matemáticos por separado y luego el sistema
integrado (D-MPHF), incluyendo el caso dinámico con inserciones.
"""

import math
import random
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.modular_arithmetic import extended_gcd, mod_inverse, is_prime, next_prime, key_to_int
from src.group_theory import AffineMap, CyclicTranslation
from src.recurrence import LCG, CapacityGrowth
from src.dmphf import DMPHF, DMPHFBuildError
from src.traditional_hash import ChainedHashTable


# ---------------------------------------------------------------------
# Módulo 2: aritmética modular
# ---------------------------------------------------------------------

class TestModularArithmetic:

    @pytest.mark.parametrize("a,p", [(3, 7), (10, 17), (123456, 1000003), (2, 2**61 - 1)])
    def test_mod_inverse_correctness(self, a, p):
        inv = mod_inverse(a, p)
        assert (a * inv) % p == 1

    def test_mod_inverse_no_existe(self):
        with pytest.raises(ValueError):
            mod_inverse(4, 8)  # gcd(4,8)=4 != 1

    def test_extended_gcd_bezout_identity(self):
        for a, b in [(240, 46), (17, 5), (0, 9), (9, 0), (270, 192)]:
            g, x, y = extended_gcd(a, b)
            assert a * x + b * y == g
            assert g == math.gcd(a, b)

    def test_is_prime_conocidos(self):
        primos = [2, 3, 5, 7, 11, 13, 97, 7919, (1 << 61) - 1]
        no_primos = [1, 0, 4, 6, 100, 7920, (1 << 61) - 3]
        for p in primos:
            assert is_prime(p), f"{p} deberia ser primo"
        for n in no_primos:
            assert not is_prime(n), f"{n} NO deberia ser primo"

    def test_next_prime(self):
        assert next_prime(14) == 17
        assert next_prime(2) == 2
        assert is_prime(next_prime(10**6))

    def test_key_to_int_determinista(self):
        p = next_prime(10**9)
        assert key_to_int("hola-mundo", p) == key_to_int("hola-mundo", p)
        assert key_to_int(42, p) == 42
        # Distintas llaves deberian (con altisima probabilidad) mapear distinto
        assert key_to_int("clave-A", p) != key_to_int("clave-B", p)


# ---------------------------------------------------------------------
# Módulo 1: teoría de grupos
# ---------------------------------------------------------------------

class TestGroupTheory:

    def test_affine_map_es_biyeccion(self):
        p = 97
        f = AffineMap(a=5, b=13, p=p)
        assert f.is_bijection_on_verify()
        imagenes = {f(x) for x in range(p)}
        assert len(imagenes) == p  # biyeccion sobre TODO Z_p

    def test_affine_map_rechaza_a_cero(self):
        with pytest.raises(ValueError):
            AffineMap(a=0, b=3, p=11)

    def test_affine_inverse_compone_identidad(self):
        f = AffineMap(a=41, b=17, p=101)
        f_inv = f.inverse()
        for x in range(101):
            assert f_inv(f(x)) == x
            assert f(f_inv(x)) == x

    def test_cyclic_translation_order_divides_n(self):
        n = 60
        for d in range(1, n):
            t = CyclicTranslation(d, n)
            order = t.order()
            assert n % order == 0
            # aplicar la traslacion `order` veces regresa al origen
            x = 0
            for _ in range(order):
                x = t(x)
            assert x == 0

    def test_cyclic_translation_generador_completo(self):
        n = 17  # primo -> todo d != 0 genera el grupo completo
        for d in range(1, n):
            t = CyclicTranslation(d, n)
            assert t.generates_full_group()


# ---------------------------------------------------------------------
# Módulo 3: relaciones de recurrencia
# ---------------------------------------------------------------------

class TestRecurrence:

    def test_lcg_reproducible(self):
        a = LCG(seed=123, m=1000)
        b = LCG(seed=123, m=1000)
        assert a.take(50) == b.take(50)

    def test_lcg_en_rango(self):
        lcg = LCG(seed=7, m=257)
        for x in lcg.take(500):
            assert 0 <= x < 257

    def test_capacity_growth_recurrencia(self):
        g = CapacityGrowth(n0=100, growth_factor=1.5, margin=0)
        vals = [g.grow() for _ in range(5)]
        # cada termino debe ser >= growth_factor * anterior (por el ceil)
        prev = 100
        for v in vals:
            assert v >= 1.5 * prev - 1
            prev = v

    def test_capacity_growth_amortized_estimate_decrece(self):
        g = CapacityGrowth(n0=1000, growth_factor=2.0)
        c10 = g.amortized_cost_estimate(10)
        c1000 = g.amortized_cost_estimate(1000)
        assert c1000 < c10  # costo amortizado por insercion baja al escalar


# ---------------------------------------------------------------------
# Sistema integrado: D-MPHF
# ---------------------------------------------------------------------

class TestDMPHFEstatico:

    @pytest.mark.parametrize("m", [1, 2, 10, 137, 1000])
    def test_biyeccion_exacta_modo_comprimido(self, m):
        keys = [f"key-{i}" for i in range(m)]
        d = DMPHF(bucket_avg_size=3, seed=1)
        d.build(keys, exact_minimal=True)

        assert d.n == m  # 0% desperdicio EXACTO
        posiciones = [d.lookup(k) for k in keys]
        assert all(p is not None for p in posiciones)
        assert sorted(posiciones) == list(range(m))

    def test_llave_ausente_devuelve_none(self):
        keys = [f"k{i}" for i in range(300)]
        d = DMPHF(bucket_avg_size=3, seed=2)
        d.build(keys, exact_minimal=True)
        for ausente in ["no-existe", "k99999", "otra-llave-rara"]:
            assert d.lookup(ausente) is None

    def test_llaves_enteras_y_string_mezcladas(self):
        keys = list(range(100)) + [f"s{i}" for i in range(100)]
        d = DMPHF(bucket_avg_size=3, seed=5)
        d.build(keys, exact_minimal=True)
        posiciones = [d.lookup(k) for k in keys]
        assert all(p is not None for p in posiciones)
        assert len(set(posiciones)) == len(keys)

    def test_duplicados_se_eliminan(self):
        keys = [1, 2, 3, 2, 1, 4]
        d = DMPHF(bucket_avg_size=2, seed=9)
        d.build(keys, exact_minimal=True)
        assert d.m == 4  # {1,2,3,4}


class TestDMPHFDinamico:

    def test_insercion_simple_sin_colision(self):
        d = DMPHF(slack=0.3, bucket_avg_size=3, seed=3)
        d.build([f"a{i}" for i in range(50)])
        r = d.insert("nueva-llave")
        assert r.position is not None
        assert d.lookup("nueva-llave") == r.position

    def test_insercion_masiva_preserva_integridad(self):
        random.seed(0)
        base = [f"dev-{i}" for i in range(300)]
        d = DMPHF(slack=0.2, bucket_avg_size=3, seed=42)
        d.build(base)

        nuevas = [f"dev-{i}" for i in range(300, 900)]
        random.shuffle(nuevas)
        for k in nuevas:
            d.insert(k)

        todas = base + nuevas
        posiciones = [d.lookup(k) for k in todas]
        assert all(p is not None for p in posiciones), "Se perdio alguna llave"
        assert len(set(posiciones)) == len(todas), "Colision tras insertar"

    def test_insertar_llave_ya_existente_es_idempotente(self):
        d = DMPHF(slack=0.2, bucket_avg_size=3, seed=4)
        keys = [f"x{i}" for i in range(80)]
        d.build(keys)
        pos_antes = d.lookup("x5")
        d.insert("x5")
        assert d.lookup("x5") == pos_antes
        assert d.m == 80  # no crecio

    def test_reconstruccion_completa_se_registra(self):
        d = DMPHF(slack=0.02, bucket_avg_size=3, seed=6, growth_factor=1.3)
        d.build([f"y{i}" for i in range(50)])
        for i in range(50, 400):
            d.insert(f"y{i}")
        assert d.total_rebuilds >= 1
        # Consistencia tras reconstrucciones
        for i in range(400):
            assert d.lookup(f"y{i}") is not None

    def test_descompresion_automatica_al_insertar(self):
        d = DMPHF(bucket_avg_size=3, seed=8)
        keys = [f"z{i}" for i in range(150)]
        d.build(keys, exact_minimal=True)
        assert d.compressed
        d.insert("z-nueva")
        assert not d.compressed
        for k in keys + ["z-nueva"]:
            assert d.lookup(k) is not None


class TestDMPHFErrores:

    def test_build_vacio_lanza_error(self):
        d = DMPHF()
        with pytest.raises(ValueError):
            d.build([])

    def test_slack_invalido(self):
        with pytest.raises(ValueError):
            DMPHF(slack=1.5)
        with pytest.raises(ValueError):
            DMPHF(slack=-0.1)


# ---------------------------------------------------------------------
# Linea base: tabla hash tradicional (para asegurarnos de comparar
# contra algo correcto en los benchmarks)
# ---------------------------------------------------------------------

class TestChainedHashTable:

    def test_insercion_y_busqueda_basica(self):
        t = ChainedHashTable()
        for i in range(200):
            t.insert(f"k{i}", i)
        for i in range(200):
            assert t.lookup(f"k{i}") == i
        assert t.lookup("no-existe") is None

    def test_resize_automatico(self):
        t = ChainedHashTable(initial_capacity=8)
        for i in range(1000):
            t.insert(i, i)
        assert t.total_resizes > 0
        assert t.stats()["factor_carga"] <= 0.75  # justo despues de resize
        for i in range(1000):
            assert t.lookup(i) == i
