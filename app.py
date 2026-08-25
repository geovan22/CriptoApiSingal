"""
Crypto Signal Dashboard -- punto de entrada.

La lógica está repartida en módulos por responsabilidad para que sea
mantenible:
  app_state.py         - sesión, DB init, refresco dinámico
  signal_service.py     - caché de datos + cálculo de señal
  telegram_handler.py   - comandos entrantes de Telegram
  operations_monitor.py - cierre automático de operaciones, modo escaneo
  ui_favorites.py        - panel de favoritos
  ui_backtest.py          - panel de backtest
  ui_backup.py            - panel de respaldo
  ui_charts.py            - gráficos
  ui_signal_panel.py      - panel de señal + calculadora
  ui_operations.py        - operaciones en seguimiento + historial
"""
import time
import streamlit as st

import config
import db
from app_state import init_session_state, setup_autorefresh, set_symbol
from signal_service import get_data_and_signal
from telegram_handler import process_telegram_commands
from operations_monitor import check_open_operations, run_scan_mode
from ui_favorites import render_favorites_panel
from ui_backtest import render_backtest_panel
from ui_backup import render_backup_panel
from ui_charts import render_charts
from ui_signal_panel import render_signal_panel
from ui_operations import render_operations_panel

st.set_page_config(page_title="Crypto Signal Dashboard", layout="wide")

db.init_db(default_symbols=config.AVAILABLE_SYMBOLS)
init_session_state()
refresh_ms, open_ops_count = setup_autorefresh()

# --- Procesos de fondo (corren en cada refresco) ---
process_telegram_commands()
check_open_operations()
run_scan_mode()

# --- UI ---
st.title("📊 Crypto Signal Dashboard")

render_favorites_panel()
render_backtest_panel()
render_backup_panel()

col_sel, col_info = st.columns([1, 2])
with col_sel:
    options = config.AVAILABLE_SYMBOLS.copy()
    if st.session_state.symbol not in options:
        options.append(st.session_state.symbol)
    chosen = st.selectbox(
        "Cripto en seguimiento", options, index=options.index(st.session_state.symbol),
        disabled=st.session_state.scan_mode,
    )
    if chosen != st.session_state.symbol and not st.session_state.scan_mode:
        set_symbol(chosen)

with col_info:
    estado = "🟢 Activas" if st.session_state.notifications_enabled else "🔴 Pausadas"
    st.caption(
        f"Alertas Telegram: {estado} · Timeframe {config.INTERVAL} · "
        f"Refresco cada {refresh_ms // 1000}s{' (acelerado, hay operaciones abiertas)' if open_ops_count else ''} · "
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
    render_signal_panel(symbol, result)

render_operations_panel()

st.divider()
st.caption(
    "⚠️ Herramienta de apoyo técnico, no es asesoría financiera. "
    "Las señales combinan MACD, RSI, PVT, delta, ADX, patrón de velas y niveles de "
    "soporte/resistencia, calculadas solo sobre velas cerradas — no garantizan "
    "resultados. Define siempre tu propia gestión de riesgo."
)
