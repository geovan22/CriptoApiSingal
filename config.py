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

# Velas de "enfriamiento" tras un stop-loss antes de volver a permitir
# señal en el MISMO símbolo y MISMA dirección. Práctica estándar en
# trading algorítmico para evitar "revenge trading" automatizado --
# reentrar de inmediato en la misma trampa que acaba de fallar.
# 2 velas de 4h = 8 horas de espera tras un stop.
COOLDOWN_CANDLES = 2

# ADX mínimo para permitir que una señal se confirme. Investigación estándar
# de trading algorítmico: por debajo de 20, el mercado está lateral/sin
# tendencia clara y los indicadores de momentum (MACD) dan señales falsas
# ("whipsaws") con más frecuencia. Antes esto solo se mostraba como aviso;
# ahora bloquea la confirmación -- el ADX actúa como "portero", no como
# un dato más que suma puntos.
MIN_ADX_FOR_SIGNAL = 20

# --- Gestión de riesgo ---
# Distancia máxima permitida para el stop loss, como % del precio de entrada.
#
# IMPORTANTE: esto es una RED DE SEGURIDAD EXTREMA, no el control principal
# de riesgo. El control principal es el "Riesgo por operación (%)" de la
# calculadora, que ajusta cuánto DINERO inviertes según qué tan lejos esté
# el stop -- eso ya limita tu pérdida en dólares sin importar el % de precio.
#
# Antes este valor estaba en 4%, forzando el mismo stop apretado para BTC
# (lento) y para altcoins volátiles (POL, NEAR). El backtest mostró que
# eso perjudicaba a BTC: sacaba operaciones por ruido normal antes de que
# el movimiento se desarrollara (profit factor cayó de 1.58 a 0.99). Con
# el position sizing por riesgo ya activo, un stop más lejano solo reduce
# el monto invertido -- no hace falta forzarlo a estar cerca.
MAX_STOP_PCT = 0.10

# Ratio riesgo/beneficio mínimo aceptable. Si después de aplicar el tope
# de arriba el TP queda muy cerca comparado con el riesgo, la señal se
# marca como de baja calidad en vez de "confirmada" sin más.
MIN_RR_RATIO = 1.0

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
