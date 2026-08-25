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
#
# Nota: esto es una lista de las criptos MÁS LÍQUIDAS y con mayor volumen
# en Binance -- no una promesa de rentabilidad (ninguna cripto lo es).
# Mayor liquidez importa para esta herramienta porque hace que los niveles
# de soporte/resistencia, delta y PVT sean más confiables (spreads más
# ajustados, menos manipulación de precio por operadores pequeños).
AVAILABLE_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT",
    "LTCUSDT", "TRXUSDT", "TONUSDT", "NEARUSDT", "SUIUSDT",
    "APTUSDT", "ARBUSDT", "OPUSDT", "POLUSDT", "BCHUSDT",
]

# Temporalidad (4h: buen balance entre calidad de señal y ruido,
# consistente con el análisis manual que ya veníamos haciendo en el chat)
INTERVAL = "4h"

# Cada cuánto se refresca el dashboard (segundos)
REFRESH_SECONDS = 60

# --- Telegram: se lee de secrets/env, nunca hardcodeado aquí ---
TELEGRAM_TOKEN = _get_secret("TELEGRAM_TOKEN", os.getenv("TELEGRAM_TOKEN", ""))
TELEGRAM_CHAT_ID = _get_secret("TELEGRAM_CHAT_ID", os.getenv("TELEGRAM_CHAT_ID", ""))

# --- Turso (base de datos persistente, opcional) ---
# Si se dejan vacíos, db.py usa un archivo SQLite local automáticamente.
# Ver instrucciones de configuración al inicio de db.py.
TURSO_DATABASE_URL = _get_secret("TURSO_DATABASE_URL", os.getenv("TURSO_DATABASE_URL", ""))
TURSO_AUTH_TOKEN = _get_secret("TURSO_AUTH_TOKEN", os.getenv("TURSO_AUTH_TOKEN", ""))
