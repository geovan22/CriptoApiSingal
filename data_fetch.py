"""
Descarga de velas (klines) desde la API PÚBLICA de Binance.
No requiere API key ni secret -- los datos de mercado son públicos.

Si tu red/país bloquea api.binance.com, se prueba automáticamente con
endpoints alternativos (data-api.binance.vision, binance.us).
"""
import requests
import pandas as pd

ENDPOINTS = [
    "https://api.binance.com/api/v3/klines",
    "https://data-api.binance.vision/api/v3/klines",
    "https://api.binance.us/api/v3/klines",
]

COLUMNS = [
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "n_trades",
    "taker_buy_base", "taker_buy_quote", "ignore",
]


def get_klines(symbol: str = "BTCUSDT", interval: str = "4h", limit: int = 300) -> pd.DataFrame:
    """
    symbol: p.ej. 'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BCHUSDT'
    interval: '1m','5m','15m','1h','4h','1d', etc (formato Binance)
    """
    params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
    last_err = None
    for url in ENDPOINTS:
        try:
            resp = requests.get(url, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            df = pd.DataFrame(data, columns=COLUMNS)
            for col in ["open", "high", "low", "close", "volume", "taker_buy_base"]:
                df[col] = df[col].astype(float)
            df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
            df["close_time"] = pd.to_datetime(df["close_time"], unit="ms")
            # Aproximación de delta: volumen comprador (taker buy) vs vendedor
            df["buy_vol"] = df["taker_buy_base"]
            df["sell_vol"] = df["volume"] - df["taker_buy_base"]
            df["delta"] = df["buy_vol"] - df["sell_vol"]
            return df[[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "buy_vol", "sell_vol", "delta",
            ]]
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"No se pudo obtener datos de ningún endpoint de Binance: {last_err}")
