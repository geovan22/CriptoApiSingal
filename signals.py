"""
Lógica de señal replicando el marco usado manualmente en el análisis:
- Cruce de MACD (alcista/bajista)
- Zona de RSI (sobrecompra/sobreventa/neutral)
- Confirmación de PVT (¿el volumen ponderado confirma el movimiento del precio?)
- Delta aproximado (compras vs ventas a mercado dentro de cada vela)
- Proximidad a soporte/resistencia (swing highs/lows recientes)

IMPORTANTE: la señal se calcula usando solo velas YA CERRADAS. La última vela
del gráfico está en formación y sus valores cambian en vivo -- evaluarla
directamente causa señales que aparecen y desaparecen en minutos. Por eso
aquí se descarta si close_time todavía no pasó.

Una señal solo se marca como "confirmada" cuando varias condiciones coinciden
(confluencia). Esto es apoyo a la decisión, no garantía de resultado.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timezone


def only_closed_candles(df: pd.DataFrame) -> pd.DataFrame:
    """Descarta la última vela si todavía está en formación."""
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    if df.iloc[-1]["close_time"] > now:
        return df.iloc[:-1].copy()
    return df


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


def evaluate_signal(df_full: pd.DataFrame) -> dict:
    """
    df_full: DataFrame con indicadores ya calculados (incluye la vela en curso).
    Devuelve un diccionario con el diagnóstico completo, calculado SOLO con
    velas cerradas para evitar señales que parpadean.
    """
    live_price = df_full.iloc[-1]["close"]
    df = only_closed_candles(df_full)

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

    # --- Delta aproximado (buy vs sell volume real de las últimas velas cerradas) ---
    delta_sum = df["delta"].tail(3).sum()
    delta_pct = delta_sum / df["volume"].tail(3).sum() if df["volume"].tail(3).sum() else 0
    if delta_pct > 0.08:
        delta_state = "comprador (delta positivo)"
    elif delta_pct < -0.08:
        delta_state = "vendedor (delta negativo)"
    else:
        delta_state = "equilibrado"

    supports, resistances = find_swing_levels(df)
    price = last["close"]
    near_support = nearest_level(price, supports, above=False)
    near_resistance = nearest_level(price, resistances, above=True)

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

    if "comprador" in delta_state:
        buy_score += 1
        reasons.append("Delta comprador en últimas velas cerradas")
    elif "vendedor" in delta_state:
        sell_score += 1
        reasons.append("Delta vendedor en últimas velas cerradas")

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
        "live_price": live_price,
        "candle_time": last["open_time"],
        "macd_state": macd_state,
        "macd_bullish_cross": macd_bullish_cross,
        "macd_bearish_cross": macd_bearish_cross,
        "rsi": round(rsi_val, 2),
        "rsi_zone": rsi_zone,
        "pvt_confirm": pvt_confirm,
        "delta_state": delta_state,
        "delta_pct": round(delta_pct * 100, 1),
        "support": near_support,
        "resistance": near_resistance,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "reasons": reasons,
        "entry": entry,
        "stop": stop,
        "tp": tp,
    }
