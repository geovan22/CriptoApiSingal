"""Gráficos de velas, MACD, RSI, delta y ADX."""
import streamlit as st
import plotly.graph_objects as go


def render_charts(df, symbol: str):
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

    fig_adx = go.Figure()
    fig_adx.add_trace(go.Scatter(x=df["open_time"], y=df["adx14"], name="ADX"))
    fig_adx.add_hline(y=25, line_dash="dash", line_color="gray")
    fig_adx.update_layout(height=150, margin=dict(l=10, r=10, t=10, b=10), title="ADX (fuerza de tendencia, >25 = fuerte)")
    st.plotly_chart(fig_adx, use_container_width=True)
