"""
Configuración editable. No pongas aquí tus credenciales de Binance --
esta app solo usa el endpoint PÚBLICO de precios, no las necesita.

IMPORTANTE SOBRE SEGURIDAD:
El token de Telegram NUNCA se guarda en este archivo (que sí se sube a git).
Se lee de dos lugares posibles, en este orden:
  1. st.secrets (cuando corre en Streamlit Community Cloud -- lo configuras
     en la web de Streamlit, nunca queda en el repositorio)
  2. Variables de entorno TELEGRAM_TOKEN / TELEGRAM_CHAT_ID (cuando corres
     local, ej. con Termux), cargadas desde un archivo .env que está en
     .gitignore y por lo tanto NUNCA se sube a git.
"""
import os

def _get_secret(key: str, default: str = "") -> str:
    try:
        import streamlit as st
        if key in st.secrets:
            return st.secrets[key]
    except Exception:
        pass
    return default

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Cripto que se sigue por defecto al abrir la app (cambiable después desde
# la web o con /symbol en Telegram, sin necesidad de tocar este archivo)
DEFAULT_SYMBOL = "BTCUSDT"

# Opciones sugeridas en el selector de la web (puedes escribir cualquier
# otro par de Binance manualmente, no está limitado a esta lista).
AVAILABLE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "TRXUSDT", "TONUSDT", "NEARUSDT", "SUIUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "POLUSDT", "BCHUSDT",
    "ATOMUSDT", "ICPUSDT", "FILUSDT", "INJUSDT", "RENDERUSDT",
    "SHIBUSDT", "PEPEUSDT",
]

# Temporalidad por defecto (el usuario puede cambiarla desde la UI --
# ver AVAILABLE_INTERVALS y get_interval_hours() abajo -- y queda guardada
# en la base de datos para la próxima vez que abra la app).
INTERVAL = "4h"

# Timeframes disponibles para seleccionar en la UI (formato Binance)
AVAILABLE_INTERVALS = ["15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"]


def get_interval_hours() -> float:
    """Convierte el INTERVAL actual (ej. '4h', '1d', '15m') a horas."""
    s = INTERVAL
    if s.endswith("m"):
        return float(s[:-1]) / 60
    if s.endswith("h"):
        return float(s[:-1])
    if s.endswith("d"):
        return float(s[:-1]) * 24
    return 4.0

# Velas de "enfriamiento" tras un stop-loss antes de volver a permitir
# señal en el MISMO símbolo y MISMA dirección.
COOLDOWN_CANDLES = 2

# ADX mínimo para permitir que una señal se confirme.
MIN_ADX_FOR_SIGNAL = 20

# Modo reversión a la media: disponible para BACKTEST siempre, pero
# pausado para uso en vivo hasta que muestre resultados razonables.
ENABLE_MEAN_REVERSION_LIVE = False

# --- Gestión de riesgo ---
MAX_STOP_PCT = 0.10
MIN_RR_RATIO = 1.0

# Cada cuánto se refresca el dashboard (segundos)
REFRESH_SECONDS = 60

# --- Telegram: se lee de secrets/env, nunca hardcodeado aquí ---
TELEGRAM_TOKEN = _get_secret("TELEGRAM_TOKEN", os.getenv("TELEGRAM_TOKEN", ""))
TELEGRAM_CHAT_ID = _get_secret("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))

# --- Turso (base de datos persistente, opcional) ---
TURSO_DATABASE_URL = _get_secret("TURSO_DATABASE_URL", os.getenv("TURSO_DATABASE_URL", ""))
TURSO_AUTH_TOKEN = _get_secret("TURSO_AUTH_TOKEN", os.getenv("TURSO_AUTH_TOKEN", ""))
