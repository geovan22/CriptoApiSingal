"""
Obtención de datos de mercado y señal, con caché para no re-descargar
en cada refresco del dashboard.
"""
import streamlit as st

import config
from data_fetch import get_klines
from indicators import add_all_indicators
from signals import evaluate_signal, get_daily_trend


@st.cache_data(ttl=55, show_spinner=False)
def cached_klines(symbol: str, interval: str, limit: int):
    return get_klines(symbol, interval, limit)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_daily_trend(symbol: str):
    df_1d = cached_klines(symbol, "1d", 100)
    df_1d = add_all_indicators(df_1d)
    return get_daily_trend(df_1d)


def get_data_and_signal(symbol: str):
    """Devuelve (df_con_indicadores, resultado_de_señal) para un símbolo."""
    df = cached_klines(symbol, config.INTERVAL, 300)
    df = add_all_indicators(df)
    try:
        trend_1d = cached_daily_trend(symbol)
    except Exception:
        trend_1d = None
    result = evaluate_signal(df, trend_1d=trend_1d)
    return df, result
