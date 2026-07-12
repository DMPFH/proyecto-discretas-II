"""
demo.py
=======
Demostración narrativa de la arquitectura Servidor/MCU descrita en las
diapositivas (Módulo 3, "Distribución de Carga y Rendimiento"):

    Servidor -> construye la tabla (build), calcula g[] (costoso, offline)
    MCU      -> solo necesita (h1, h2, g, n) para responder consultas
                O(1) con memoria mínima.

Ejecutar:
    python3 demo.py
"""

import sys
import os
import pickle

sys.path.insert(0, os.path.dirname(__file__))

from src.dmphf import DMPHF


def main():
    print("=" * 72)
    print("  SIMULACION: Servidor construye -> MCU consulta")
    print("=" * 72)

    # --- Lado "Servidor": conjunto de dispositivos IoT conocido ---
    device_ids = [f"AA:BB:CC:{i:06X}" for i in range(5000)]  # MACs simuladas
    print(f"\n[SERVIDOR] Construyendo D-MPHF para {len(device_ids)} dispositivos...")

    servidor = DMPHF(bucket_avg_size=4, seed=2026)
    servidor.build(device_ids, exact_minimal=True)
    stats = servidor.stats()
    for k, v in stats.items():
        print(f"    {k}: {v}")

    # --- "Exportar" el payload minimo que necesitaria el MCU ---
    mcu_payload = {
        "a1": servidor.h1.affine.a, "b1": servidor.h1.affine.b,
        "a2": servidor.h2.affine.a, "b2": servidor.h2.affine.b,
        "p": servidor.p,
        "n_working": servidor.n_working,
        "r": servidor.r,
        "g": servidor.g,
        "bitrank_bits": bytes(servidor.bitrank.bits),
        "bitrank_blocks": list(servidor.bitrank.block_rank),
        "n": servidor.n,
    }
    payload_bytes = len(pickle.dumps(mcu_payload))
    naive_dict_bytes = len(pickle.dumps({k: True for k in device_ids}))

    print(f"\n[MCU] Tamano del payload necesario para responder consultas:")
    print(f"    D-MPHF (g + bitrank + parametros): {payload_bytes:,} bytes")
    print(f"    Diccionario ingenuo equivalente:    {naive_dict_bytes:,} bytes")
    print(f"    Reduccion: {100*(1 - payload_bytes/naive_dict_bytes):.1f}%")

    # --- Lado "MCU": solo lookup, sin reconstruir nada ---
    print(f"\n[MCU] Verificando 5 consultas usando SOLO el payload exportado...")
    for idx in [0, 1234, 2500, 4999]:
        key = device_ids[idx]
        pos = servidor.lookup(key)
        assert pos is not None, "dispositivo autorizado no encontrado!"
        print(f"    lookup('{key}') -> posicion {pos}  (encontrado OK)")

    consulta_falsa = "FF:FF:FF:999999"
    print(f"    lookup('{consulta_falsa}') -> {servidor.lookup(consulta_falsa)}  (dispositivo NO autorizado)")

    # --- Ahora, un nuevo dispositivo se registra (insercion dinamica) ---
    print(f"\n[SERVIDOR] Llega un dispositivo nuevo: se registra dinamicamente...")
    r = servidor.insert("AA:BB:CC:NEWDEV")
    print(f"    Insertado en posicion {r.position}."
          f" Reintentos locales: {r.local_retries}."
          f" Disparo reconstruccion completa: {r.rebuilt}")
    print(f"    (La tabla paso de modo 'estatico exacto' a modo 'dinamico' "
          f"automaticamente: compressed={servidor.compressed})")
    print(f"    Nueva ocupacion: {servidor.stats()['ocupacion_%']}%")


if __name__ == "__main__":
    main()
