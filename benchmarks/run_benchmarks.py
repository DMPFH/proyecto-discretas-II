"""
run_benchmarks.py
==================
Reproduce, con datos medidos (no inventados), la tabla comparativa de
la diapositiva 2 y la de conclusiones: memoria, tiempo de acceso,
ocupación y comportamiento ante colisiones, para D-MPHF (estático
exacto y dinámico) vs. una tabla hash tradicional con encadenamiento.

Uso:
    python3 benchmarks/run_benchmarks.py
"""

import sys
import os
import time
import random
import statistics as st

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.dmphf import DMPHF
from src.traditional_hash import ChainedHashTable


def timed_lookups(lookup_fn, keys, repeats=3):
    """Mide tiempo promedio y máximo de `repeats` rondas de búsqueda
    sobre TODAS las llaves, en microsegundos por búsqueda."""
    times = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        for k in keys:
            lookup_fn(k)
        t1 = time.perf_counter()
        times.append((t1 - t0) / len(keys) * 1e6)  # us/busqueda
    return st.mean(times), max(times)


def bench_one(m: int):
    print(f"\n{'='*72}\n  N = {m:,} llaves\n{'='*72}")
    keys = [f"iot-device-{i:08d}" for i in range(m)]
    random.Random(0).shuffle(keys)

    # ---------------- D-MPHF: modo estático exacto (0% desperdicio) ----
    d_static = DMPHF(bucket_avg_size=4, seed=1)
    t0 = time.perf_counter()
    d_static.build(keys, exact_minimal=True)
    build_time_static = time.perf_counter() - t0
    avg_us, max_us = timed_lookups(d_static.lookup, keys)
    s_static = d_static.stats()

    # ---------------- D-MPHF: modo dinámico (slack para insertar) -----
    d_dyn = DMPHF(slack=0.15, bucket_avg_size=4, seed=1)
    t0 = time.perf_counter()
    d_dyn.build(keys)
    build_time_dyn = time.perf_counter() - t0
    s_dyn = d_dyn.stats()

    # ---------------- Tabla hash tradicional ---------------------------
    trad = ChainedHashTable()
    t0 = time.perf_counter()
    for k in keys:
        trad.insert(k, True)
    build_time_trad = time.perf_counter() - t0
    avg_us_trad, max_us_trad = timed_lookups(trad.lookup, keys)
    s_trad = trad.stats()

    memoria_dmphf = s_static["memoria_total_bytes(g+bitrank)"]
    memoria_trad = s_trad["memoria_teorica_bytes"]

    print(f"{'Metrica':32s} {'D-MPHF (estatico)':22s} {'D-MPHF (dinamico)':20s} {'Hash tradicional':18s}")
    print("-" * 96)
    print(f"{'Ocupacion (%)':32s} {s_static['ocupacion_%']:<22} {s_dyn['ocupacion_%']:<20} {s_trad['factor_carga']*100:<18.2f}")
    print(f"{'Tiempo construccion (s)':32s} {build_time_static:<22.4f} {build_time_dyn:<20.4f} {build_time_trad:<18.4f}")
    print(f"{'Lookup promedio (us)':32s} {avg_us:<22.4f} {'-':<20} {avg_us_trad:<18.4f}")
    print(f"{'Lookup peor caso (us)':32s} {max_us:<22.4f} {'-':<20} {max_us_trad:<18.4f}")
    print(f"{'Memoria estructura (bytes)':32s} {memoria_dmphf:<22} {'-':<20} {memoria_trad:<18}")
    print(f"{'Cadena maxima (colisiones)':32s} {'0 (biyectivo)':<22} {'0 (biyectivo)':<20} {s_trad['cadena_maxima']:<18}")

    ahorro = 100 * (1 - memoria_dmphf / memoria_trad)
    speedup = avg_us_trad / avg_us if avg_us > 0 else float("nan")
    print(f"\n  -> Ahorro de memoria de D-MPHF vs. tradicional: {ahorro:.1f}%")
    print(f"  -> D-MPHF es {speedup:.2f}x mas rapido en lookup promedio")

    return {
        "m": m, "memoria_dmphf": memoria_dmphf, "memoria_trad": memoria_trad,
        "avg_us_dmphf": avg_us, "avg_us_trad": avg_us_trad,
        "ocupacion_dmphf": s_static["ocupacion_%"], "ocupacion_trad": s_trad["factor_carga"] * 100,
    }


def bench_insercion_dinamica():
    print(f"\n{'='*72}\n  Comportamiento dinamico: efecto dominó al insertar\n{'='*72}")
    d = DMPHF(slack=0.10, bucket_avg_size=4, seed=5, growth_factor=1.4)
    base = [f"sensor-{i}" for i in range(2000)]
    d.build(base)
    print(f"Construccion inicial: m={d.m}, n={d.n}, ocupacion={d.stats()['ocupacion_%']}%")

    rnd = random.Random(2)
    nuevas = [f"sensor-{i}" for i in range(2000, 6000)]
    rnd.shuffle(nuevas)

    retries_hist = {}
    checkpoints = []
    for i, k in enumerate(nuevas, 1):
        r = d.insert(k)
        retries_hist[r.local_retries] = retries_hist.get(r.local_retries, 0) + 1
        if i % 1000 == 0:
            checkpoints.append((i, d.n, d.stats()["ocupacion_%"], d.total_rebuilds))

    print("\nProgreso cada 1000 inserciones (insertadas, n_actual, ocupacion%, reconstrucciones_acumuladas):")
    for cp in checkpoints:
        print(f"  {cp}")

    print(f"\nHistograma de reintentos locales por insercion: {retries_hist}")
    print(f"Total de reconstrucciones completas: {d.total_rebuilds}")
    print(f"Costo amortizado ~ {d.total_rebuilds}/{len(nuevas)} = "
          f"{d.total_rebuilds/len(nuevas)*100:.3f}% de las inserciones dispararon reconstruccion completa")

    # Verificacion final de integridad
    todas = base + nuevas
    posiciones = [d.lookup(k) for k in todas]
    assert all(p is not None for p in posiciones)
    assert len(set(posiciones)) == len(todas)
    print(f"\nIntegridad verificada: {len(todas)} llaves, todas unicas y recuperables.")


def plot_summary(resultados, output_path="benchmarks/comparacion_memoria.png"):
    """Genera una gráfica de barras (memoria D-MPHF vs. tradicional, y
    ocupación) a partir de los resultados medidos. Requiere matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")  # no requiere entorno gráfico
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n[aviso] matplotlib no está instalado; se omite la gráfica "
              "(pip install matplotlib).")
        return

    ns = [r["m"] for r in resultados]
    mem_dmphf = [r["memoria_dmphf"] for r in resultados]
    mem_trad = [r["memoria_trad"] for r in resultados]
    ocup_dmphf = [r["ocupacion_dmphf"] for r in resultados]
    ocup_trad = [r["ocupacion_trad"] for r in resultados]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    x = range(len(ns))
    width = 0.35
    ax1.bar([i - width/2 for i in x], mem_dmphf, width, label="D-MPHF")
    ax1.bar([i + width/2 for i in x], mem_trad, width, label="Tradicional")
    ax1.set_yscale("log")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels([f"{n:,}" for n in ns])
    ax1.set_xlabel("Número de llaves (m)")
    ax1.set_ylabel("Memoria (bytes, escala log)")
    ax1.set_title("Memoria de la estructura")
    ax1.legend()

    ax2.bar([i - width/2 for i in x], ocup_dmphf, width, label="D-MPHF")
    ax2.bar([i + width/2 for i in x], ocup_trad, width, label="Tradicional")
    ax2.set_xticks(list(x))
    ax2.set_xticklabels([f"{n:,}" for n in ns])
    ax2.set_xlabel("Número de llaves (m)")
    ax2.set_ylabel("Ocupación (%)")
    ax2.set_title("Ocupación de la tabla")
    ax2.legend()

    fig.suptitle("D-MPHF vs. Tabla Hash Tradicional (datos medidos)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    print(f"\n[grafica] Guardada en: {output_path}")


if __name__ == "__main__":
    resultados = []
    for m in (200, 2000, 20000):
        resultados.append(bench_one(m))

    bench_insercion_dinamica()
    plot_summary(resultados)

    print(f"\n{'='*72}\n  Resumen (para graficar / incluir en el informe)\n{'='*72}")
    print(f"{'N':>8} {'Mem D-MPHF':>12} {'Mem Tradic.':>12} {'Ahorro %':>10} {'Ocup D-MPHF':>12} {'Ocup Trad':>10}")
    for r in resultados:
        ahorro = 100 * (1 - r["memoria_dmphf"] / r["memoria_trad"])
        print(f"{r['m']:>8} {r['memoria_dmphf']:>12} {r['memoria_trad']:>12} {ahorro:>9.1f}% "
              f"{r['ocupacion_dmphf']:>11.1f}% {r['ocupacion_trad']:>9.1f}%")
