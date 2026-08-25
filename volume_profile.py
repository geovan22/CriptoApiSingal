"""
Volume Profile -- muestra en qué precios se negoció más volumen REAL,
a diferencia de find_swing_levels() (en signals.py) que solo mira máximos
y mínimos visuales. Un nivel de Volume Profile refleja dónde el mercado
de verdad "aceptó" el precio (mucha negociación), mientras que zonas de
bajo volumen tienden a romperse rápido (el precio "pasó de largo").

Metodología (estándar en trading profesional, distribución proporcional
por solapamiento -- más precisa que asignar todo el volumen al cierre):
  1. Se divide el rango de precio de las últimas N velas en bins.
  2. El volumen de cada vela se reparte entre los bins que toca su rango
     (high-low), proporcional a cuánto se solapan.
  3. POC (Point of Control) = el bin con más volumen acumulado.
  4. Value Area = rango de bins alrededor del POC que concentra ~70% del
     volumen total (VAH = límite superior, VAL = límite inferior).
"""
import numpy as np
import pandas as pd


def compute_volume_profile(df: pd.DataFrame, lookback: int = 120, bins: int = 24, value_area_pct: float = 0.70):
    """
    Devuelve {"poc": float, "vah": float, "val": float} o None si no hay
    suficientes datos. Usa velas ya cerradas de `df` (el caller debe pasar
    solo velas cerradas).
    """
    sub = df.tail(lookback)
    if len(sub) < 10:
        return None

    lows = sub["low"].values.astype(float)
    highs = sub["high"].values.astype(float)
    vols = sub["volume"].values.astype(float)

    lo_all, hi_all = lows.min(), highs.max()
    if hi_all <= lo_all:
        return None

    edges = np.linspace(lo_all, hi_all, bins + 1)
    ranges = np.maximum(highs - lows, 1e-9)  # evitar división por cero en velas doji

    bin_volumes = np.zeros(bins)
    for i in range(bins):
        b_lo, b_hi = edges[i], edges[i + 1]
        overlap = np.maximum(0.0, np.minimum(highs, b_hi) - np.maximum(lows, b_lo))
        bin_volumes[i] = np.sum(vols * overlap / ranges)

    if bin_volumes.sum() <= 0:
        return None

    poc_idx = int(np.argmax(bin_volumes))
    poc_price = (edges[poc_idx] + edges[poc_idx + 1]) / 2

    total = bin_volumes.sum()
    target = total * value_area_pct
    lo_i = hi_i = poc_idx
    cum = bin_volumes[poc_idx]

    while cum < target and (lo_i > 0 or hi_i < bins - 1):
        left_vol = bin_volumes[lo_i - 1] if lo_i > 0 else -1
        right_vol = bin_volumes[hi_i + 1] if hi_i < bins - 1 else -1
        if right_vol >= left_vol and hi_i < bins - 1:
            hi_i += 1
            cum += bin_volumes[hi_i]
        elif lo_i > 0:
            lo_i -= 1
            cum += bin_volumes[lo_i]
        else:
            break

    return {
        "poc": round(float(poc_price), 6),
        "vah": round(float(edges[hi_i + 1]), 6),
        "val": round(float(edges[lo_i]), 6),
    }
