"""
Lógica de señal replicando el marco usado manualmente en el análisis:
- Cruce de MACD (alcista/bajista)
- Zona de RSI (sobrecompra/sobreventa/neutral)
- Confirmación de PVT (¿el volumen ponderado confirma el movimiento del precio?)
- Proximidad a soporte/resistencia (swing highs/lows recientes)

Una señal solo se marca como "confirmada" cuando varias condiciones coinciden
(confluencia), igual que hicimos capturas a capturas en el chat. Esto es
apoyo a la decisión, no garantía de resultado -- siempre defina su propio
stop y tamaño de posición.
"""
import pandas as pd
import numpy as np


def find_swing_levels(df: pd.DataFrame, lookback: int = 60, order: int = 3):
    """Encuentra soportes y resistencias como máximos/mínimos locales recientes."""
    highs, lows = [], []
    sub = df.tail(lookback).reset_index(drop=True)
    for i in range(order, len(sub) - order):
        window_h = sub["high"].iloc[i - order:i + order + 1]
        window_l = sub["low"].iloc[i - order:i + order + 1]
        if sub["high"].iloc[i] == window_h.max():
            highs.append(sub["high"].iloc[i])
        if sub["low"].iloc[i] == window_l.min():
            lows.append(sub["low"].iloc[i])
    resistances = sorted(set(round(h, 2) for h in highs), reverse=True)
    supports = sorted(set(round(l, 2) for l in lows), reverse=True)
    return supports, resistances


def nearest_level(price: float, levels: list, above: bool):
    candidates = [l for l in levels if (l > price if above else l < price)]
    if not candidates:
        return None
    return min(candidates) if above else max(candidates)


def evaluate_signal(df: pd.DataFrame) -> dict:
    """
    Devuelve un diccionario con el diagnóstico completo:
    señal ('COMPRA','VENTA','ESPERA'), razones, y niveles sugeridos.
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

    macd_bullish_cross = prev["macd"] <= prev["macd_signal"] and last["macd"] > last["macd_signal"]
    macd_bearish_cross = prev["macd"] >= prev["macd_signal"] and last["macd"] < last["macd_signal"]
    macd_state = "alcista" if last["macd"] > last["macd_signal"] else "bajista"

    rsi_val = last["rsi14"]
    if rsi_val >= 70:
        rsi_zone = "sobrecompra"
    elif rsi_val <= 30:
        rsi_zone = "sobreventa"
    else:
        rsi_zone = "neutral"

    # PVT: comparar pendiente reciente (10 velas) vs precio
    pvt_slope = df["pvt"].tail(10).diff().mean()
    price_slope = df["close"].tail(10).diff().mean()
    if pvt_slope > 0 and price_slope > 0:
        pvt_confirm = "confirma alcista"
    elif pvt_slope < 0 and price_slope < 0:
        pvt_confirm = "confirma bajista"
    elif pvt_slope <= 0 and price_slope > 0:
        pvt_confirm = "diverge (precio sube, volumen no confirma)"
    elif pvt_slope >= 0 and price_slope < 0:
        pvt_confirm = "diverge (precio baja, volumen no confirma caída)"
    else:
        pvt_confirm = "plano"

    supports, resistances = find_swing_levels(df)
    price = last["close"]
    near_support = nearest_level(price, supports, above=False)
    near_resistance = nearest_level(price, resistances, above=True)

    # --- Lógica de confluencia (igual que en el análisis manual) ---
    buy_score = 0
    sell_score = 0
    reasons = []

    if macd_state == "alcista":
        buy_score += 1
        reasons.append("MACD en fase alcista")
    else:
        sell_score += 1
        reasons.append("MACD en fase bajista")

    if rsi_zone == "sobreventa":
        buy_score += 1
        reasons.append("RSI en sobreventa (<30)")
    elif rsi_zone == "sobrecompra":
        sell_score += 1
        reasons.append("RSI en sobrecompra (>70)")

    if "confirma alcista" in pvt_confirm:
        buy_score += 1
        reasons.append("PVT confirma presión compradora")
    elif "confirma bajista" in pvt_confirm:
        sell_score += 1
        reasons.append("PVT confirma presión vendedora")
    elif "diverge" in pvt_confirm and price_slope > 0:
        sell_score += 0.5
        reasons.append("Divergencia bajista PVT/precio")
    elif "diverge" in pvt_confirm and price_slope < 0:
        buy_score += 0.5
        reasons.append("Divergencia alcista PVT/precio")

    # Proximidad a soporte/resistencia (dentro de 0.6%)
    if near_support and abs(price - near_support) / price < 0.006:
        buy_score += 1
        reasons.append(f"Precio cerca de soporte {near_support}")
    if near_resistance and abs(near_resistance - price) / price < 0.006:
        sell_score += 1
        reasons.append(f"Precio cerca de resistencia {near_resistance}")

    if buy_score >= 3 and buy_score > sell_score:
        signal = "COMPRA"
    elif sell_score >= 3 and sell_score > buy_score:
        signal = "VENTA"
    else:
        signal = "ESPERA"

    entry = stop = tp = None
    if signal == "COMPRA":
        entry = price
        stop = near_support * 0.997 if near_support else price * 0.98
        tp = near_resistance if near_resistance else price * 1.03
    elif signal == "VENTA":
        entry = price
        stop = near_resistance * 1.003 if near_resistance else price * 1.02
        tp = near_support if near_support else price * 0.97

    return {
        "signal": signal,
        "price": price,
        "macd_state": macd_state,
        "macd_bullish_cross": macd_bullish_cross,
        "macd_bearish_cross": macd_bearish_cross,
        "rsi": round(rsi_val, 2),
        "rsi_zone": rsi_zone,
        "pvt_confirm": pvt_confirm,
        "support": near_support,
        "resistance": near_resistance,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "reasons": reasons,
        "entry": entry,
        "stop": stop,
        "tp": tp,
    }
