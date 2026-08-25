"""
Cálculo de indicadores técnicos usados en el análisis manual del chat:
EMA 50/200, Bollinger Bands, MACD, RSI 14, Stoch RSI, PVT (Price Volume Trend).
Todo implementado con pandas/numpy puro, sin dependencias pesadas.
"""
import pandas as pd
import numpy as np


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def bollinger_bands(close: pd.Series, length: int = 20, std_mult: float = 2.0):
    mid = close.rolling(length).mean()
    std = close.rolling(length).std()
    upper = mid + std_mult * std
    lower = mid - std_mult * std
    return upper, mid, lower


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(close, fast)
    ema_slow = ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    out = 100 - (100 / (1 + rs))
    return out.fillna(50)


def stoch_rsi(close: pd.Series, rsi_len: int = 14, stoch_len: int = 14, k: int = 3, d: int = 3):
    r = rsi(close, rsi_len)
    min_r = r.rolling(stoch_len).min()
    max_r = r.rolling(stoch_len).max()
    stoch = ((r - min_r) / (max_r - min_r).replace(0, np.nan)) * 100
    k_line = stoch.rolling(k).mean()
    d_line = k_line.rolling(d).mean()
    return k_line.fillna(50), d_line.fillna(50)


def pvt(close: pd.Series, volume: pd.Series) -> pd.Series:
    pct_change = close.pct_change().fillna(0)
    pvt_raw = (pct_change * volume).cumsum()
    return pvt_raw


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Average True Range -- mide la volatilidad reciente en unidades de precio."""
    tr = true_range(df)
    return tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()


def adx(df: pd.DataFrame, length: int = 14):
    """
    ADX (Average Directional Index, Wilder) -- mide qué tan FUERTE es la
    tendencia, sin importar la dirección. No es un indicador de compra/venta
    por sí solo: sirve para saber si vale la pena confiar en MACD/EMA en
    este momento (tendencia real) o si el mercado está lateral (ADX < 20),
    donde los cruces de medias suelen dar señales falsas.
    Devuelve (adx, plus_di, minus_di).
    """
    high, low = df["high"], df["low"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm = pd.Series(plus_dm, index=df.index)
    minus_dm = pd.Series(minus_dm, index=df.index)

    tr = true_range(df)
    tr_smooth = tr.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    plus_dm_smooth = plus_dm.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    minus_dm_smooth = minus_dm.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()

    plus_di = 100 * (plus_dm_smooth / tr_smooth.replace(0, np.nan))
    minus_di = 100 * (minus_dm_smooth / tr_smooth.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_val = dx.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    return adx_val.fillna(0), plus_di.fillna(0), minus_di.fillna(0)


def detect_engulfing(df: pd.DataFrame) -> str:
    """
    Patrón de velas envolventes (clásico, del ebook de patrones de gráfico):
    compara las 2 últimas velas de df. Devuelve 'alcista', 'bajista', o None.
    """
    if len(df) < 2:
        return None
    prev, last = df.iloc[-2], df.iloc[-1]
    prev_bearish = prev["close"] < prev["open"]
    prev_bullish = prev["close"] > prev["open"]
    last_bullish = last["close"] > last["open"]
    last_bearish = last["close"] < last["open"]

    if prev_bearish and last_bullish and last["open"] <= prev["close"] and last["close"] >= prev["open"]:
        return "alcista"
    if prev_bullish and last_bearish and last["open"] >= prev["close"] and last["close"] <= prev["open"]:
        return "bajista"
    return None


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """df debe tener columnas: open, high, low, close, volume"""
    df = df.copy()
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)
    df["bb_upper"], df["bb_mid"], df["bb_lower"] = bollinger_bands(df["close"], 20, 2.0)
    df["macd"], df["macd_signal"], df["macd_hist"] = macd(df["close"])
    df["rsi14"] = rsi(df["close"], 14)
    df["stoch_k"], df["stoch_d"] = stoch_rsi(df["close"])
    df["pvt"] = pvt(df["close"], df["volume"])
    df["atr14"] = atr(df, 14)
    df["adx14"], df["plus_di"], df["minus_di"] = adx(df, 14)
    return df
