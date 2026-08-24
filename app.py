import time
import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

import config
from data_fetch import get_klines
from indicators import add_all_indicators
from signals import evaluate_signal
from telegram_alert import send_telegram_message
from telegram_bot import get_updates, parse_commands, format_status_message, format_help_message

st.set_page_config(page_title="Crypto Signal Dashboard", layout="wide")
st_autorefresh(interval=config.REFRESH_SECONDS * 1000, key="refresh")

# --- Estado persistente durante la sesión ---
if "symbol" not in st.session_state:
    st.session_state.symbol = config.DEFAULT_SYMBOL
if "notifications_enabled" not in st.session_state:
    st.session_state.notifications_enabled = True
if "telegram_offset" not in st.session_state:
    st.session_state.telegram_offset = 0
if "last_alert" not in st.session_state:
    st.session_state.last_alert = None

TOKEN = config.TELEGRAM_TOKEN
CHAT_ID = config.TELEGRAM_CHAT_ID


def get_data_and_signal(symbol: str):
    df = get_klines(symbol, config.INTERVAL, limit=300)
    df = add_all_indicators(df)
    result = evaluate_signal(df)
    return df, result


# --- Procesar comandos pendientes de Telegram (/start /stop /status /now /symbol) ---
if TOKEN and CHAT_ID:
    updates = get_updates(TOKEN, offset=st.session_state.telegram_offset)
    commands, max_update_id = parse_commands(updates, CHAT_ID)
    if max_update_id is not None:
        st.session_state.telegram_offset = max_update_id + 1

    for c in commands:
        cmd, arg = c["cmd"], c["arg"]

        if cmd == "start":
            st.session_state.notifications_enabled = True
            send_telegram_message(TOKEN, CHAT_ID, "🟢 Alertas activadas.")

        elif cmd == "stop":
            st.session_state.notifications_enabled = False
            send_telegram_message(TOKEN, CHAT_ID, "🔴 Alertas pausadas. El dashboard sigue vigilando el mercado, pero no te va a interrumpir.")

        elif cmd == "help":
            send_telegram_message(TOKEN, CHAT_ID, format_help_message())

        elif cmd == "symbol" and arg:
            symbol = arg if arg.endswith("USDT") else f"{arg}USDT"
            try:
                get_klines(symbol, config.INTERVAL, limit=5)  # validar que el par existe
                st.session_state.symbol = symbol
                send_telegram_message(TOKEN, CHAT_ID, f"✅ Ahora siguiendo *{symbol}*.")
            except Exception:
                send_telegram_message(TOKEN, CHAT_ID, f"⚠️ No encontré el par *{symbol}* en Binance. Verifica el nombre (ej. /symbol ETHUSDT).")

        elif cmd in ("status", "now"):
            try:
                _, result = get_data_and_signal(st.session_state.symbol)
                extra = "\n\n(análisis al momento)" if cmd == "now" else ""
                msg = format_status_message(st.session_state.symbol, st.session_state.notifications_enabled, result) + extra
                send_telegram_message(TOKEN, CHAT_ID, msg)
            except Exception as e:
                send_telegram_message(TOKEN, CHAT_ID, f"⚠️ No pude obtener datos ahora mismo: {e}")

# --- UI ---
st.title("📊 Crypto Signal Dashboard")

col_sel, col_info = st.columns([1, 2])
with col_sel:
    options = config.AVAILABLE_SYMBOLS.copy()
    if st.session_state.symbol not in options:
        options.append(st.session_state.symbol)
    chosen = st.selectbox("Cripto en seguimiento", options, index=options.index(st.session_state.symbol))
    if chosen != st.session_state.symbol:
        st.session_state.symbol = chosen

with col_info:
    estado = "🟢 Activas" if st.session_state.notifications_enabled else "🔴 Pausadas"
    st.caption(
        f"Alertas Telegram: {estado} · Timeframe {config.INTERVAL} · "
        f"Refresco cada {config.REFRESH_SECONDS}s · Última actualización: {time.strftime('%H:%M:%S')}"
    )
    st.caption("Comandos por Telegram: /start /stop /status /now /symbol PAR")

symbol = st.session_state.symbol

try:
    df, result = get_data_and_signal(symbol)
except Exception as e:
    st.error(f"Error obteniendo datos de {symbol}: {e}")
    st.stop()

col1, col2 = st.columns([3, 1])

with col1:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["open_time"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name=symbol,
    ))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema50"], name="EMA 50", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema200"], name="EMA 200", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["bb_upper"], name="BB Superior", line=dict(width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["bb_lower"], name="BB Inferior", line=dict(width=1, dash="dot")))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    fig_macd = go.Figure()
    fig_macd.add_trace(go.Bar(x=df["open_time"], y=df["macd_hist"], name="Histograma"))
    fig_macd.add_trace(go.Scatter(x=df["open_time"], y=df["macd"], name="MACD"))
    fig_macd.add_trace(go.Scatter(x=df["open_time"], y=df["macd_signal"], name="Señal"))
    fig_macd.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_macd, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        fig_rsi = go.Figure()
        fig_rsi.add_trace(go.Scatter(x=df["open_time"], y=df["rsi14"], name="RSI 14"))
        fig_rsi.add_hline(y=70, line_dash="dash", line_color="red")
        fig_rsi.add_hline(y=30, line_dash="dash", line_color="green")
        fig_rsi.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_rsi, use_container_width=True)
    with c2:
        fig_delta = go.Figure()
        colors = ["#22c55e" if v >= 0 else "#ef4444" for v in df["delta"].tail(60)]
        fig_delta.add_trace(go.Bar(x=df["open_time"].tail(60), y=df["delta"].tail(60), marker_color=colors, name="Delta"))
        fig_delta.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10), title="Delta (compra - venta)")
        st.plotly_chart(fig_delta, use_container_width=True)

with col2:
    st.metric("Precio actual", f"${result['live_price']:,.2f}")
    if result["price"] != result["live_price"]:
        st.caption(f"Señal calculada sobre la última vela cerrada (${result['price']:,.2f})")

    signal = result["signal"]
    color = {"COMPRA": "🟢", "VENTA": "🔴", "ESPERA": "🟡"}[signal]
    st.subheader(f"{color} {signal}")

    st.write(f"**MACD:** {result['macd_state']}")
    st.write(f"**RSI 14:** {result['rsi']} ({result['rsi_zone']})")
    st.write(f"**PVT:** {result['pvt_confirm']}")
    st.write(f"**Delta:** {result['delta_state']} ({result['delta_pct']}%)")
    if result["support"]:
        st.write(f"**Soporte cercano:** {result['support']:,.2f}")
    if result["resistance"]:
        st.write(f"**Resistencia cercana:** {result['resistance']:,.2f}")

    st.markdown("**Razones:**")
    for r in result["reasons"]:
        st.write(f"- {r}")

    alert_key = f"{symbol}:{signal}"
    if signal in ("COMPRA", "VENTA"):
        st.success(
            f"Entrada: ${result['entry']:,.2f}\n\n"
            f"Stop loss: ${result['stop']:,.2f}\n\n"
            f"Take profit: ${result['tp']:,.2f}"
        )
        if st.session_state.last_alert != alert_key and st.session_state.notifications_enabled and TOKEN and CHAT_ID:
            msg = (
                f"*{signal}* señal en *{symbol}* ({config.INTERVAL})\n"
                f"Precio: ${result['price']:,.2f}\n"
                f"Entrada: ${result['entry']:,.2f}\n"
                f"Stop: ${result['stop']:,.2f}\n"
                f"TP: ${result['tp']:,.2f}\n"
                f"Razones: {', '.join(result['reasons'])}"
            )
            ok, info = send_telegram_message(TOKEN, CHAT_ID, msg)
            if ok:
                st.session_state.last_alert = alert_key
                st.toast(f"Alerta enviada a Telegram ({symbol})")
            else:
                st.warning(f"No se pudo enviar Telegram: {info}")
    else:
        st.info("Sin señal confirmada — mercado en zona de espera.")
        st.session_state.last_alert = alert_key

st.divider()
st.caption(
    "⚠️ Herramienta de apoyo técnico, no es asesoría financiera. "
    "Las señales combinan MACD, RSI, PVT, delta aproximado y niveles de "
    "soporte/resistencia, calculadas solo sobre velas cerradas — no garantizan "
    "resultados. Define siempre tu propia gestión de riesgo."
)
