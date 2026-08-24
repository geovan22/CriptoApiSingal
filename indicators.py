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
    return df
