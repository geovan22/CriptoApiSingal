"""
Lógica de señal replicando el marco usado manualmente en el análisis:
- Cruce de MACD (alcista/bajista)               -- peso 1  (derivado del precio)
- Zona de RSI (sobrecompra/sobreventa/neutral)   -- peso 1  (derivado del precio)
- Confirmación de PVT (volumen ponderado)        -- peso 1.5 (volumen real)
- Delta aproximado (compras vs ventas a mercado) -- peso 1.5 (volumen real)
- Proximidad a soporte/resistencia               -- peso 1
- Tendencia diaria (1D) como contexto            -- peso 0.5 (informativo)

Los pesos reflejan la jerarquía de tu guía de trading profesional: el
volumen/order flow (PVT, delta) pesa más que los indicadores derivados
solo del precio (MACD, RSI), que la guía trata con más escepticismo.

IMPORTANTE:
1) La señal se calcula usando solo velas YA CERRADAS. La última vela del
   gráfico está en formación y sus valores cambian en vivo -- evaluarla
   directamente causa señales que aparecen y desaparecen en minutos.
2) Confirmación de 2 velas: una señal solo se marca "confirmada" si se
   sostiene en las dos últimas velas cerradas (no solo en la más reciente).
   Si aparece por primera vez, queda como "en formación" y no dispara
   alerta -- reduce falsas señales de una sola vela.
3) Las razones se separan en "a favor" y "en conflicto" para no mezclar
   señales que apoyan la decisión con las que la contradicen.
"""
import pandas as pd
import numpy as np
from indicators import detect_engulfing

try:
    import config
    MAX_STOP_PCT = getattr(config, "MAX_STOP_PCT", 0.04)
    MIN_RR_RATIO = getattr(config, "MIN_RR_RATIO", 1.0)
except Exception:
    MAX_STOP_PCT = 0.04
    MIN_RR_RATIO = 1.0

WEIGHTS = {
    "macd": 1.0,
    "rsi": 1.0,
    "pvt": 1.5,
    "delta": 1.5,
    "level": 1.0,
    "trend_1d": 0.5,
    "pattern": 0.5,
}


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


def get_daily_trend(df_1d: pd.DataFrame) -> str:
    """
    Tendencia de contexto usando velas diarias: precio de cierre vs EMA 50.
    Se usa como filtro informativo, no como condición obligatoria.
    """
    df = only_closed_candles(df_1d)
    last = df.iloc[-1]
    if pd.isna(last.get("ema50")):
        return "indeterminada"
    return "alcista" if last["close"] > last["ema50"] else "bajista"


def _score_last_closed(df: pd.DataFrame, trend_1d: str = None):
    """
    Calcula el puntaje de confluencia y las razones para la ÚLTIMA vela
    cerrada de df (df ya debe venir filtrado con only_closed_candles).
    Devuelve (signal, buy_score, sell_score, buy_reasons, sell_reasons, extras)
    """
    last = df.iloc[-1]
    prev = df.iloc[-2]

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

    delta_sum = df["delta"].tail(3).sum()
    delta_pct = delta_sum / df["volume"].tail(3).sum() if df["volume"].tail(3).sum() else 0
    if delta_pct > 0.08:
        delta_state = "comprador (delta positivo)"
    elif delta_pct < -0.08:
        delta_state = "vendedor (delta negativo)"
    else:
        delta_state = "equilibrado"

    # ADX: fuerza de tendencia (no direccional). No suma puntos a favor/en
    # contra directamente -- se usa para avisar cuando el mercado está
    # lateral y las señales de MACD/EMA son menos fiables en ese contexto.
    adx_val = last.get("adx14", 0)
    if adx_val >= 25:
        trend_strength = "fuerte"
    elif adx_val >= 20:
        trend_strength = "moderada"
    else:
        trend_strength = "lateral/débil"

    atr_val = last.get("atr14", None)

    # Patrón de velas envolvente (clásico, del ebook de patrones)
    pattern = detect_engulfing(df)

    supports, resistances = find_swing_levels(df)
    price = last["close"]
    near_support = nearest_level(price, supports, above=False)
    near_resistance = nearest_level(price, resistances, above=True)

    buy_score = 0.0
    sell_score = 0.0
    buy_reasons = []
    sell_reasons = []

    # MACD (peso 1)
    if macd_state == "alcista":
        buy_score += WEIGHTS["macd"]
        buy_reasons.append("MACD en fase alcista")
    else:
        sell_score += WEIGHTS["macd"]
        sell_reasons.append("MACD en fase bajista")

    # RSI (peso 1)
    if rsi_zone == "sobreventa":
        buy_score += WEIGHTS["rsi"]
        buy_reasons.append("RSI en sobreventa (<30)")
    elif rsi_zone == "sobrecompra":
        sell_score += WEIGHTS["rsi"]
        sell_reasons.append("RSI en sobrecompra (>70)")

    # PVT (peso 1.5 -- volumen real, pesa más que MACD/RSI)
    if "confirma alcista" in pvt_confirm:
        buy_score += WEIGHTS["pvt"]
        buy_reasons.append("PVT confirma presión compradora")
    elif "confirma bajista" in pvt_confirm:
        sell_score += WEIGHTS["pvt"]
        sell_reasons.append("PVT confirma presión vendedora")
    elif "diverge" in pvt_confirm and price_slope > 0:
        sell_score += WEIGHTS["pvt"] * 0.5
        sell_reasons.append("Divergencia bajista PVT/precio")
    elif "diverge" in pvt_confirm and price_slope < 0:
        buy_score += WEIGHTS["pvt"] * 0.5
        buy_reasons.append("Divergencia alcista PVT/precio")

    # Delta (peso 1.5 -- volumen real)
    if "comprador" in delta_state:
        buy_score += WEIGHTS["delta"]
        buy_reasons.append("Delta comprador en últimas velas cerradas")
    elif "vendedor" in delta_state:
        sell_score += WEIGHTS["delta"]
        sell_reasons.append("Delta vendedor en últimas velas cerradas")

    # Soporte/Resistencia (peso 1)
    if near_support and abs(price - near_support) / price < 0.006:
        buy_score += WEIGHTS["level"]
        buy_reasons.append(f"Precio cerca de soporte {near_support}")
    if near_resistance and abs(near_resistance - price) / price < 0.006:
        sell_score += WEIGHTS["level"]
        sell_reasons.append(f"Precio cerca de resistencia {near_resistance}")

    # Tendencia diaria (peso 0.5 -- contexto, no obligatorio)
    if trend_1d == "alcista":
        buy_score += WEIGHTS["trend_1d"]
        buy_reasons.append("Tendencia diaria (1D) alcista")
    elif trend_1d == "bajista":
        sell_score += WEIGHTS["trend_1d"]
        sell_reasons.append("Tendencia diaria (1D) bajista")

    # Patrón de velas envolvente (peso 0.5)
    if pattern == "alcista":
        buy_score += WEIGHTS["pattern"]
        buy_reasons.append("Patrón envolvente alcista (2 últimas velas)")
    elif pattern == "bajista":
        sell_score += WEIGHTS["pattern"]
        sell_reasons.append("Patrón envolvente bajista (2 últimas velas)")

    if buy_score >= 3 and buy_score > sell_score:
        signal = "COMPRA"
    elif sell_score >= 3 and sell_score > buy_score:
        signal = "VENTA"
    else:
        signal = "ESPERA"

    extras = {
        "price": price,
        "macd_state": macd_state,
        "rsi": round(rsi_val, 2),
        "rsi_zone": rsi_zone,
        "pvt_confirm": pvt_confirm,
        "delta_state": delta_state,
        "delta_pct": round(delta_pct * 100, 1),
        "support": near_support,
        "resistance": near_resistance,
        "adx": round(adx_val, 1),
        "trend_strength": trend_strength,
        "atr": atr_val,
        "pattern": pattern,
    }
    return signal, buy_score, sell_score, buy_reasons, sell_reasons, extras


def evaluate_signal(df_full: pd.DataFrame, trend_1d: str = None) -> dict:
    """
    df_full: DataFrame con indicadores ya calculados (incluye la vela en curso).
    trend_1d: 'alcista' | 'bajista' | None -- contexto opcional del timeframe diario.

    Devuelve un diccionario con el diagnóstico completo. La señal solo se
    marca como "status": "confirmada" si se sostiene en las últimas 2 velas
    cerradas; si es la primera vez que aparece, queda "en formación" y no
    debería disparar una alerta todavía.
    """
    live_price = df_full.iloc[-1]["close"]
    df = only_closed_candles(df_full)

    signal, buy_score, sell_score, buy_reasons, sell_reasons, extras = _score_last_closed(df, trend_1d)

    # Confirmación de 2 velas: repetir el cálculo excluyendo la última vela cerrada
    prev_signal = "ESPERA"
    if len(df) > 60:  # margen para que find_swing_levels tenga suficiente historia
        prev_signal, *_ = _score_last_closed(df.iloc[:-1], trend_1d)

    if signal in ("COMPRA", "VENTA") and signal == prev_signal:
        status = "confirmada"
    elif signal in ("COMPRA", "VENTA"):
        status = "en formación"
    else:
        status = "n/a"

    reasons = buy_reasons if signal == "COMPRA" else sell_reasons if signal == "VENTA" else []
    conflict_reasons = sell_reasons if signal == "COMPRA" else buy_reasons if signal == "VENTA" else []

    price = extras["price"]
    near_support = extras["support"]
    near_resistance = extras["resistance"]
    atr_val = extras["atr"]

    entry = stop = tp = None
    stop_widened = False
    stop_capped = False
    if signal == "COMPRA":
        entry = price
        stop = near_support * 0.997 if near_support else price * 0.98
        tp = near_resistance if near_resistance else price * 1.03
        if atr_val and (entry - stop) < atr_val:
            stop = entry - atr_val
            stop_widened = True
        max_stop_distance = entry * MAX_STOP_PCT
        if (entry - stop) > max_stop_distance:
            stop = entry - max_stop_distance
            stop_capped = True
            stop_widened = False
    elif signal == "VENTA":
        entry = price
        stop = near_resistance * 1.003 if near_resistance else price * 1.02
        tp = near_support if near_support else price * 0.97
        if atr_val and (stop - entry) < atr_val:
            stop = entry + atr_val
            stop_widened = True
        max_stop_distance = entry * MAX_STOP_PCT
        if (stop - entry) > max_stop_distance:
            stop = entry + max_stop_distance
            stop_capped = True
            stop_widened = False

    rr_ratio = None
    low_quality_rr = False
    if entry is not None and stop is not None and tp is not None:
        risk = abs(entry - stop)
        reward = abs(tp - entry)
        if risk > 0:
            rr_ratio = reward / risk
            low_quality_rr = rr_ratio < MIN_RR_RATIO

    return {
        "signal": signal,
        "status": status,
        "price": price,
        "live_price": live_price,
        "candle_time": df.iloc[-1]["open_time"],
        "macd_state": extras["macd_state"],
        "rsi": extras["rsi"],
        "rsi_zone": extras["rsi_zone"],
        "pvt_confirm": extras["pvt_confirm"],
        "delta_state": extras["delta_state"],
        "delta_pct": extras["delta_pct"],
        "trend_1d": trend_1d,
        "adx": extras["adx"],
        "trend_strength": extras["trend_strength"],
        "pattern": extras["pattern"],
        "support": near_support,
        "resistance": near_resistance,
        "buy_score": round(buy_score, 2),
        "sell_score": round(sell_score, 2),
        "reasons": reasons,
        "conflict_reasons": conflict_reasons,
        "entry": entry,
        "stop": stop,
        "tp": tp,
        "stop_widened": stop_widened,
        "stop_capped": stop_capped,
        "rr_ratio": round(rr_ratio, 2) if rr_ratio is not None else None,
        "low_quality_rr": low_quality_rr,
    }
