"""
Crypto Signal Dashboard -- punto de entrada.
"""
import time
import streamlit as st

import config
import db
import performance
import account_settings
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

if "db_initialized" not in st.session_state:
    db.init_db(default_symbols=config.AVAILABLE_SYMBOLS)
    st.session_state.db_initialized = True
init_session_state()

config.INTERVAL = db.get_state("selected_interval", config.INTERVAL)

top_col1, top_col2, top_col3 = st.columns([2.5, 1, 1])
with top_col2:
    st.session_state.refresh_paused = st.checkbox(
        "⏸️ Pausar refresco",
        value=st.session_state.refresh_paused,
        help="Pausa el refresco automático en toda la app -- útil para backtests largos o para leer el historial sin que se recargue solo.",
    )
with top_col3:
    new_notif_value = st.checkbox(
        "🔔 Telegram",
        value=st.session_state.notifications_enabled,
        help="Activa o pausa las alertas de Telegram sin salir de la app -- igual que /start y /stop, pero desde aquí. Se recuerda la próxima vez que abras la app.",
    )
    if new_notif_value != st.session_state.notifications_enabled:
        st.session_state.notifications_enabled = new_notif_value
        db.set_state("notifications_enabled", "1" if new_notif_value else "0")

with st.expander("⚙️ Cuenta (capital, saldo real, apalancamiento)"):
    closed_ops_for_balance = db.get_operation_history(500)
    saved_capital, saved_calc_mode, saved_leverage = account_settings.get_settings()
    saldo_real, pnl_total_realizado = performance.compute_real_balance(closed_ops_for_balance, saved_capital)

    ac1, ac2, ac3 = st.columns(3)
    ac1.metric("Capital inicial", f"${saved_capital:.2f}")
    ac2.metric("Saldo real actual", f"${saldo_real:.2f}", f"{pnl_total_realizado:+.2f}")
    ac3.metric("Modo de cálculo", "Riesgo %" if saved_calc_mode == "risk_pct" else "Apalancamiento fijo")

    with st.form("account_settings_form"):
        new_capital = st.number_input("Capital inicial ($)", min_value=1.0, value=saved_capital, step=10.0,
                                        help="Se usa para calcular tu saldo real (capital inicial + ganancias/pérdidas ya cerradas).")
        new_mode = st.radio(
            "Modo de cálculo por defecto en la calculadora", ["risk_pct", "leverage"],
            format_func=lambda m: "Riesgo % (recomendado)" if m == "risk_pct" else "Apalancamiento fijo",
            index=0 if saved_calc_mode == "risk_pct" else 1, horizontal=True,
        )
        new_leverage = st.number_input("Apalancamiento por defecto (si eliges ese modo)", min_value=1.0, max_value=50.0, value=saved_leverage, step=0.5)
        if st.form_submit_button("💾 Guardar configuración de cuenta"):
            account_settings.set_settings(new_capital, new_mode, new_leverage)
            st.success("Configuración guardada.")
            st.rerun()

open_ops = db.get_open_operations()
refresh_ms = setup_autorefresh(len(open_ops))

process_telegram_commands()
check_open_operations(open_ops)
confirmed_favorites = get_confirmed_favorites_signals(open_ops)
notify_favorites_signals(confirmed_favorites)

with top_col1:
    st.title("📊 Crypto Signal Dashboard")

tab_signal, tab_tracking, tab_favorites, tab_backtest, tab_backup = st.tabs(
    ["📈 Señal", f"📍 Seguimiento ({len(open_ops)})", "⭐ Favoritos", "🧪 Backtest", "💾 Historial/Respaldo"]
)

with tab_tracking:
    if open_ops:
        exposure = performance.build_report([], open_ops)
        e1, e2, e3 = st.columns(3)
        e1.metric("Operaciones abiertas", exposure["open_count"])
        e2.metric("Monto total invertido", f"${exposure['total_invested_open']:.2f}")
        e3.metric("Riesgo total en juego", f"${exposure['total_risk_usd_open']:.2f}")
        st.divider()
    render_operations_panel(open_ops)
    if not open_ops:
        st.info("No tienes operaciones en seguimiento ahora mismo. Acepta una señal confirmada desde la pestaña Señal para empezar a trackearla aquí.")

with tab_favorites:
    render_favorites_panel(confirmed_favorites)

with tab_backtest:
    render_backtest_panel()

with tab_backup:
    render_backup_panel()

with tab_signal:
    col_sel, col_tf, col_info = st.columns([1, 1, 2])
    with col_sel:
        options = config.AVAILABLE_SYMBOLS.copy()
        if st.session_state.symbol not in options:
            options.append(st.session_state.symbol)
        chosen = st.selectbox("Cripto en seguimiento", options, index=options.index(st.session_state.symbol))
        if chosen != st.session_state.symbol:
            set_symbol(chosen)

    with col_tf:
        tf_options = config.AVAILABLE_INTERVALS.copy()
        if config.INTERVAL not in tf_options:
            tf_options.append(config.INTERVAL)
        chosen_tf = st.selectbox("Timeframe", tf_options, index=tf_options.index(config.INTERVAL))
        if chosen_tf != config.INTERVAL:
            config.INTERVAL = chosen_tf
            db.set_state("selected_interval", chosen_tf)
            st.rerun()

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

    col1, col2 = st.tabs(["📋 Análisis", "📊 Gráficos"])
    with col1:
        render_signal_panel(symbol, result, open_ops)
    with col2:
        render_charts(df, symbol)

    st.divider()
    st.caption(
        "⚠️ Herramienta de apoyo técnico, no es asesoría financiera. "
        "Las señales combinan MACD, RSI, PVT, delta, ADX, patrón de velas y niveles de "
        "soporte/resistencia, calculadas solo sobre velas cerradas — no garantizan "
        "resultados. Define siempre tu propia gestión de riesgo."
    )
