"""
Crypto Signal Dashboard -- punto de entrada.

La lógica está repartida en módulos por responsabilidad:
  app_state.py         - sesión, DB init, refresco dinámico
  signal_service.py     - caché de datos + cálculo de señal
  telegram_handler.py   - comandos entrantes de Telegram
  operations_monitor.py - cierre automático, break-even, watchlist favoritos
  ui_favorites.py        - panel de favoritos (watchlist pasiva)
  ui_backtest.py          - panel de backtest
  ui_backup.py            - panel de respaldo + historial
  ui_charts.py            - gráficos
  ui_signal_panel.py      - panel de señal + calculadora
  ui_operations.py        - operaciones en seguimiento

UI organizada en pestañas: la pestaña "Señal" (la más usada) es la
primera y no requiere abrir nada. Favoritos es una watchlist pasiva --
solo lista señales confirmadas, nunca cambia el símbolo en seguimiento
por su cuenta; el usuario elige manualmente cuál revisar a fondo.
"""
import time
import streamlit as st

import config
import db
from app_state import init_session_state, setup_autorefresh, set_symbol
from signal_service import get_data_and_signal
from telegram_handler import process_telegram_commands
from operations_monitor import check_open_operations, get_confirmed_favorites_signals, notify_favorites_signals
from ui_favorites import render_favorites_panel
from ui_backtest import render_backtest_panel
from ui_backup import render_backup_panel
from ui_charts import render_charts
from ui_signal_panel import render_signal_panel
from ui_operations import render_operations_panel

st.set_page_config(page_title="Crypto Signal Dashboard", layout="wide", page_icon="📊")

# --- Estilo moderno: tarjetas mas limpias, botones y metricas con mas aire ---
st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.07);
        border-radius: 10px;
        padding: 10px 14px;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-radius: 12px;
    }
    button[kind="secondary"], button[kind="primary"] {
        border-radius: 8px;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 4px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0 0;
        padding: 8px 16px;
    }
</style>
""", unsafe_allow_html=True)

db.init_db(default_symbols=config.AVAILABLE_SYMBOLS)
init_session_state()

# Una sola consulta de operaciones abiertas por refresco, compartida por
# todos los módulos que la necesitan.
open_ops = db.get_open_operations()
refresh_ms = setup_autorefresh(len(open_ops))

# --- Procesos de fondo (corren en cada refresco) ---
process_telegram_commands()
check_open_operations(open_ops)
confirmed_favorites = get_confirmed_favorites_signals()
notify_favorites_signals(confirmed_favorites)

# --- UI ---
st.title("📊 Crypto Signal Dashboard")

tab_signal, tab_favorites, tab_backtest, tab_backup = st.tabs(
    ["📈 Señal", "⭐ Favoritos", "🧪 Backtest", "💾 Historial/Respaldo"]
)

with tab_favorites:
    render_favorites_panel(confirmed_favorites)

with tab_backtest:
    render_backtest_panel()

with tab_backup:
    render_backup_panel()

with tab_signal:
    col_sel, col_info = st.columns([1, 2])
    with col_sel:
        options = config.AVAILABLE_SYMBOLS.copy()
        if st.session_state.symbol not in options:
            options.append(st.session_state.symbol)
        chosen = st.selectbox("Cripto en seguimiento", options, index=options.index(st.session_state.symbol))
        if chosen != st.session_state.symbol:
            set_symbol(chosen)

    with col_info:
        estado = "🟢 Activas" if st.session_state.notifications_enabled else "🔴 Pausadas"
        st.caption(
            f"Alertas Telegram: {estado} · Timeframe {config.INTERVAL} · "
            f"Refresco cada {refresh_ms // 1000}s{' (acelerado, hay operaciones abiertas)' if open_ops else ''} · "
            f"Última actualización: {time.strftime('%H:%M:%S')}"
        )
        st.caption("Comandos por Telegram: /start /stop /status /now /symbol PAR /favorites /operations")

    symbol = st.session_state.symbol

    try:
        with st.spinner(f"Cargando datos de {symbol}..."):
            df, result = get_data_and_signal(symbol)
    except Exception as e:
        st.error(f"Error obteniendo datos de {symbol}: {e}")
        st.stop()

    col1, col2 = st.columns([3, 1])
    with col1:
        render_charts(df, symbol)
    with col2:
        render_signal_panel(symbol, result, open_ops)

    render_operations_panel(open_ops)

    st.divider()
    st.caption(
        "⚠️ Herramienta de apoyo técnico, no es asesoría financiera. "
        "Las señales combinan MACD, RSI, PVT, delta, ADX, patrón de velas y niveles de "
        "soporte/resistencia, calculadas solo sobre velas cerradas — no garantizan "
        "resultados. Define siempre tu propia gestión de riesgo."
    )
