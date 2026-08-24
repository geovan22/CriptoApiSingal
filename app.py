import time
import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

import config
from data_fetch import get_klines
from indicators import add_all_indicators
from signals import evaluate_signal
from telegram_alert import send_telegram_message

st.set_page_config(page_title="Crypto Signal Dashboard", layout="wide")

# --- Auto-refresh ---
st_autorefresh(interval=config.REFRESH_SECONDS * 1000, key="refresh")

st.title("📊 Crypto Signal Dashboard")
st.caption(
    f"Datos públicos de Binance · Timeframe {config.INTERVAL} · "
    f"Refresco cada {config.REFRESH_SECONDS}s · "
    f"Última actualización: {time.strftime('%H:%M:%S')}"
)

# Estado para no repetir la misma alerta de Telegram en cada refresco
if "last_alert" not in st.session_state:
    st.session_state.last_alert = {}

tabs = st.tabs(config.SYMBOLS)

for symbol, tab in zip(config.SYMBOLS, tabs):
    with tab:
        try:
            df = get_klines(symbol, config.INTERVAL, limit=300)
            df = add_all_indicators(df)
            result = evaluate_signal(df)
        except Exception as e:
            st.error(f"Error obteniendo datos de {symbol}: {e}")
            continue

        col1, col2 = st.columns([3, 1])

        # --- Gráfico de velas + EMAs + BB ---
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

            # MACD
            fig_macd = go.Figure()
            fig_macd.add_trace(go.Bar(x=df["open_time"], y=df["macd_hist"], name="Histograma"))
            fig_macd.add_trace(go.Scatter(x=df["open_time"], y=df["macd"], name="MACD"))
            fig_macd.add_trace(go.Scatter(x=df["open_time"], y=df["macd_signal"], name="Señal"))
            fig_macd.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig_macd, use_container_width=True)

            # RSI + PVT
            c1, c2 = st.columns(2)
            with c1:
                fig_rsi = go.Figure()
                fig_rsi.add_trace(go.Scatter(x=df["open_time"], y=df["rsi14"], name="RSI 14"))
                fig_rsi.add_hline(y=70, line_dash="dash", line_color="red")
                fig_rsi.add_hline(y=30, line_dash="dash", line_color="green")
                fig_rsi.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_rsi, use_container_width=True)
            with c2:
                fig_pvt = go.Figure()
                fig_pvt.add_trace(go.Scatter(x=df["open_time"], y=df["pvt"], name="PVT"))
                fig_pvt.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig_pvt, use_container_width=True)

        # --- Panel de señal ---
        with col2:
            price = result["price"]
            st.metric("Precio actual", f"${price:,.2f}")

            signal = result["signal"]
            color = {"COMPRA": "🟢", "VENTA": "🔴", "ESPERA": "🟡"}[signal]
            st.subheader(f"{color} {signal}")

            st.write(f"**MACD:** {result['macd_state']}")
            st.write(f"**RSI 14:** {result['rsi']} ({result['rsi_zone']})")
            st.write(f"**PVT:** {result['pvt_confirm']}")
            if result["support"]:
                st.write(f"**Soporte cercano:** {result['support']:,.2f}")
            if result["resistance"]:
                st.write(f"**Resistencia cercana:** {result['resistance']:,.2f}")

            st.markdown("**Razones:**")
            for r in result["reasons"]:
                st.write(f"- {r}")

            if signal in ("COMPRA", "VENTA"):
                st.success(
                    f"Entrada: ${result['entry']:,.2f}\n\n"
                    f"Stop loss: ${result['stop']:,.2f}\n\n"
                    f"Take profit: ${result['tp']:,.2f}"
                )

                # Enviar alerta de Telegram solo si la señal cambió respecto al último aviso
                last = st.session_state.last_alert.get(symbol)
                if last != signal and config.TELEGRAM_TOKEN and config.TELEGRAM_CHAT_ID:
                    msg = (
                        f"*{signal}* señal en *{symbol}* ({config.INTERVAL})\n"
                        f"Precio: ${price:,.2f}\n"
                        f"Entrada: ${result['entry']:,.2f}\n"
                        f"Stop: ${result['stop']:,.2f}\n"
                        f"TP: ${result['tp']:,.2f}\n"
                        f"Razones: {', '.join(result['reasons'])}"
                    )
                    ok, info = send_telegram_message(config.TELEGRAM_TOKEN, config.TELEGRAM_CHAT_ID, msg)
                    if ok:
                        st.session_state.last_alert[symbol] = signal
                        st.toast(f"Alerta enviada a Telegram ({symbol})")
                    else:
                        st.warning(f"No se pudo enviar Telegram: {info}")
            else:
                st.info("Sin señal confirmada — mercado en zona de espera.")
                st.session_state.last_alert[symbol] = "ESPERA"

st.divider()
st.caption(
    "⚠️ Herramienta de apoyo técnico, no es asesoría financiera. "
    "Las señales combinan MACD, RSI, PVT y niveles de soporte/resistencia, "
    "replicando el marco de análisis manual — no garantizan resultados. "
    "Define siempre tu propia gestión de riesgo."
)
