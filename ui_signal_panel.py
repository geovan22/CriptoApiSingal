"""Panel de señal: métricas, valores para copiar a Quantfury, calculadora de
ganancia/pérdida con position sizing por riesgo, y disparo de alerta a Telegram."""
import pandas as pd
import streamlit as st

import config
import db
from price_format import format_price
from telegram_handler import send_signal_alert, TOKEN, CHAT_ID


def _next_candle_close(interval_hours: int = 4) -> pd.Timestamp:
    now = pd.Timestamp.now(tz="UTC")
    boundary_hour = ((now.hour // interval_hours) + 1) * interval_hours
    if boundary_hour >= 24:
        return now.normalize() + pd.Timedelta(days=1)
    return now.normalize() + pd.Timedelta(hours=boundary_hour)


def _format_timedelta(td: pd.Timedelta) -> str:
    total_min = int(td.total_seconds() // 60)
    h, m = divmod(total_min, 60)
    return f"{h}h {m}min" if h else f"{m}min"


def _render_signal_metrics(result: dict):
    st.metric("Precio actual", f"${format_price(result['live_price'])}")
    if result["price"] != result["live_price"]:
        st.caption(f"Señal calculada sobre la última vela cerrada (${format_price(result['price'])})")

    signal = result["signal"]
    color = {"COMPRA": "🟢", "VENTA": "🔴", "ESPERA": "🟡"}[signal]
    status_tag = ""
    if signal in ("COMPRA", "VENTA"):
        status_tag = " ✅ confirmada" if result["status"] == "confirmada" else " ⏳ en formación"
    st.subheader(f"{color} {signal}{status_tag}")
    if signal in ("COMPRA", "VENTA") and result["status"] == "en formación":
        st.caption("Apareció en la última vela cerrada. Se confirma si se sostiene en la próxima.")

    st.write(f"**MACD:** {result['macd_state']}")
    st.write(f"**RSI 14:** {result['rsi']} ({result['rsi_zone']})")
    st.write(f"**PVT:** {result['pvt_confirm']}")
    st.write(f"**Delta:** {result['delta_state']} ({result['delta_pct']}%)")
    if result.get("trend_1d"):
        st.write(f"**Tendencia 1D:** {result['trend_1d']}")
    st.write(f"**ADX:** {result['adx']} ({result['trend_strength']})")
    if result["trend_strength"] == "lateral/débil":
        st.caption("⚠️ Mercado sin tendencia clara -- las señales de MACD/EMA son menos fiables ahora.")
    if result.get("pattern"):
        st.write(f"**Patrón de velas:** envolvente {result['pattern']}")
    if result["support"]:
        st.write(f"**Soporte cercano:** {format_price(result['support'])}")
    if result["resistance"]:
        st.write(f"**Resistencia cercana:** {format_price(result['resistance'])}")

    st.markdown("**Razones a favor:**")
    for r in result["reasons"]:
        st.write(f"- {r}")
    if result.get("conflict_reasons"):
        st.markdown("**⚠️ Señales en conflicto (contradicen esta señal):**")
        for r in result["conflict_reasons"]:
            st.write(f"- {r}")


def _render_quantfury_values(result: dict):
    st.markdown("**Valores para Quantfury (toca el ícono de copiar en cada uno):**")
    st.caption("Precio de entrada")
    st.code(f"{format_price(result['entry'])}", language=None)
    stop_note = ""
    if result.get("stop_capped"):
        stop_note = f" (limitado a {config.MAX_STOP_PCT*100:.0f}% máx. de riesgo)"
    elif result.get("stop_widened"):
        stop_note = " (ampliado por volatilidad ATR)"
    st.caption("Stop loss" + stop_note)
    st.code(f"{format_price(result['stop'])}", language=None)
    st.caption("Take profit")
    st.code(f"{format_price(result['tp'])}", language=None)


def _render_accept_operation_button(symbol: str, signal: str, result: dict, open_ops: list):
    open_ops_this_symbol = [o for o in open_ops if o["symbol"] == symbol]
    if open_ops_this_symbol:
        st.info(f"Ya tienes una operación de {symbol} en seguimiento.")
    else:
        if st.button("✅ Aceptar y dar seguimiento a esta operación"):
            db.create_operation(symbol, signal, result["entry"], result["stop"], result["tp"])
            st.success("Operación en seguimiento. Se revisa automáticamente cada refresco.")
            st.rerun()


def _render_calculator(symbol: str, signal: str, result: dict, alert_key: str):
    st.markdown("**Calculadora de ganancia/pérdida**")
    entry, stop, tp = result["entry"], result["stop"], result["tp"]
    stop_distance_pct = abs(entry - stop) / entry if entry else 0

    cap_col, risk_col = st.columns(2)
    with cap_col:
        capital = st.number_input("Capital disponible ($)", min_value=1.0, value=50.0, step=10.0, key="capital_input")
    with risk_col:
        risk_pct = st.number_input(
            "Riesgo por operación (%)", min_value=0.1, max_value=100.0, value=2.0, step=0.5,
            key="risk_pct_input",
            help="% de tu capital que estás dispuesto a perder si toca el stop. 1-2% es lo recomendado en gestión de riesgo profesional.",
        )

    suggested_investment = (capital * risk_pct / 100) / stop_distance_pct if stop_distance_pct > 0 else capital
    suggested_investment = round(suggested_investment, 2)

    investment = st.number_input(
        "Monto a invertir ($)", min_value=1.0, value=suggested_investment, step=10.0,
        key=f"investment_input_{alert_key}",
    )
    max_loss_if_default = capital * risk_pct / 100
    st.caption(
        f"💡 Sugerido para arriesgar {risk_pct:.1f}% de tu capital (${max_loss_if_default:.2f}) "
        f"si toca el stop, según la distancia real de este stop ({stop_distance_pct*100:.2f}%). "
        f"Puedes cambiarlo, pero montos más altos arriesgan más de tu capital real."
    )

    qty = investment / entry

    if signal == "COMPRA":
        profit_usd = qty * (tp - entry)
        loss_usd = qty * (entry - stop)
    else:
        profit_usd = qty * (entry - tp)
        loss_usd = qty * (stop - entry)

    profit_pct = (profit_usd / investment) * 100 if investment else 0
    loss_pct = (loss_usd / investment) * 100 if investment else 0
    implied_leverage = investment / capital if capital else 0
    rr_ratio = (profit_usd / loss_usd) if loss_usd else 0

    pnl_col1, pnl_col2 = st.columns(2)
    with pnl_col1:
        st.metric("Si toca Take Profit", f"+${profit_usd:,.2f}", f"{profit_pct:+.1f}%")
    with pnl_col2:
        st.metric("Si toca Stop Loss", f"-${loss_usd:,.2f}", f"{-loss_pct:.1f}%", delta_color="inverse")

    st.caption(f"Cantidad: {qty:.6f} {symbol.replace('USDT','')} · Ratio riesgo/beneficio: 1:{rr_ratio:.2f}")

    if result.get("low_quality_rr"):
        st.warning(
            f"⚠️ El ratio riesgo/beneficio de esta señal ({result['rr_ratio']}:1) está por debajo "
            f"de lo recomendado (mínimo {config.MIN_RR_RATIO}:1). Aunque el stop ya está limitado, "
            f"el take profit está relativamente cerca -- considera si vale la pena esta operación."
        )

    if implied_leverage > 1:
        st.warning(
            f"⚠️ Este monto implica un apalancamiento aproximado de **{implied_leverage:.1f}x** "
            f"sobre tu capital de ${capital:,.2f}. Verifica siempre el apalancamiento real que usa tu bróker."
        )


def _maybe_send_alert(symbol: str, signal: str, result: dict, alert_key: str):
    if (
        result["status"] == "confirmada"
        and st.session_state.last_alert != alert_key
        and st.session_state.notifications_enabled
        and TOKEN and CHAT_ID
    ):
        ok, info = send_signal_alert(symbol, result)
        if ok:
            st.session_state.last_alert = alert_key
            st.toast(f"Alerta enviada a Telegram ({symbol})")
        else:
            st.warning(f"No se pudo enviar Telegram: {info}")


def render_signal_panel(symbol: str, result: dict, open_ops: list):
    """Panel completo de la columna derecha: métricas, valores, calculadora, alerta."""
    _render_signal_metrics(result)

    signal = result["signal"]
    alert_key = f"{symbol}:{signal}"

    if signal in ("COMPRA", "VENTA"):
        _render_quantfury_values(result)
        _render_accept_operation_button(symbol, signal, result, open_ops)
        _render_calculator(symbol, signal, result, alert_key)
        _maybe_send_alert(symbol, signal, result, alert_key)
    else:
        st.info("Sin señal confirmada — mercado en zona de espera.")
        st.caption(f"Confluencia actual: {result['buy_score']} a favor de compra vs {result['sell_score']} a favor de venta (se necesita ≥3 y mayoría clara).")
        remaining = _next_candle_close() - pd.Timestamp.now(tz="UTC")
        st.caption(f"⏱️ Próxima vela cierra en {_format_timedelta(remaining)} -- el análisis solo cambia al cerrar una vela.")
        st.session_state.last_alert = alert_key
