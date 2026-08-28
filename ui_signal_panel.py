"""Panel de señal: métricas, valores para copiar a Quantfury, calculadora de
ganancia/pérdida con position sizing por riesgo, y disparo de alerta a Telegram."""
import pandas as pd
import streamlit as st

import config
import db
import risk_rules
import trading_hours
import account_settings
import performance
from price_format import format_price
from signal_service import get_mean_reversion_signal
from telegram_handler import send_signal_alert, TOKEN, CHAT_ID


def _next_candle_close(interval_hours: float = None) -> pd.Timestamp:
    if interval_hours is None:
        interval_hours = config.get_interval_hours()
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
        status_labels = {
            "confirmada": " ✅ confirmada",
            "en formación": " ⏳ en formación",
            "filtrada_adx": " 🚫 filtrada (ADX bajo)",
            "filtrada_rr": " 🚫 filtrada (riesgo/beneficio pobre)",
        }
        status_tag = status_labels.get(result["status"], "")
    st.subheader(f"{color} {signal}{status_tag}")
    if signal in ("COMPRA", "VENTA") and result["status"] == "en formación":
        st.caption("Apareció en la última vela cerrada. Se confirma si se sostiene en la próxima.")
    if result["status"] == "filtrada_adx":
        st.caption(f"⛔ Cumplió el puntaje de confluencia, pero el ADX ({result['adx']}) está por debajo del mínimo ({config.MIN_ADX_FOR_SIGNAL}) -- mercado sin tendencia clara, alto riesgo de señal falsa. No se ofrece como operable.")
    if result["status"] == "filtrada_rr":
        st.caption(f"⛔ Cumplió el puntaje de confluencia, pero el ratio riesgo/beneficio ({result['rr_ratio']}:1) está por debajo del mínimo ({config.MIN_RR_RATIO}:1). No se ofrece como operable.")

    g1, g2, g3, g4 = st.columns(4)
    g1.metric("RSI 14", result["rsi"], result["rsi_zone"])
    g2.metric("ADX", result["adx"], result["trend_strength"])
    if result.get("stoch_k") is not None:
        g3.metric("Stoch RSI", result["stoch_k"])
    g4.metric("Delta", f"{result['delta_pct']}%", "comprador" if "comprador" in result["delta_state"] else "vendedor" if "vendedor" in result["delta_state"] else "equilibrado")

    extra_bits = [f"MACD {result['macd_state']}", f"PVT {result['pvt_confirm']}", f"DI {result.get('di_direction', '—')}"]
    if result.get("trend_1d"):
        extra_bits.append(f"1D {result['trend_1d']}")
    st.caption(" · ".join(extra_bits))
    if result["trend_strength"] == "lateral/débil":
        st.caption("⚠️ Mercado sin tendencia clara -- las señales de MACD/EMA son menos fiables ahora.")
    if result.get("pattern"):
        st.caption(f"Patrón de velas: envolvente {result['pattern']}")

    if result["support"] or result["resistance"]:
        lvl1, lvl2 = st.columns(2)
        if result["support"]:
            lvl1.metric("Soporte cercano", format_price(result["support"]))
        if result["resistance"]:
            lvl2.metric("Resistencia cercana", format_price(result["resistance"]))
    vp = result.get("volume_profile")
    if vp:
        st.caption(f"📊 Volume Profile: POC {format_price(vp['poc'])} · VAH {format_price(vp['vah'])} · VAL {format_price(vp['val'])}")

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


def _render_accept_operation_button(symbol: str, signal: str, result: dict, open_ops: list, calc: dict):
    open_ops_this_symbol = [o for o in open_ops if o["symbol"] == symbol]
    if open_ops_this_symbol:
        st.caption(f"Ya tienes {len(open_ops_this_symbol)} operación(es) de {symbol} en seguimiento -- puedes agregar otra más si quieres.")

    if result["status"] != "confirmada":
        st.caption("No disponible para seguimiento hasta que la señal esté confirmada (no filtrada ni en formación).")
        return

    within_hours, hours_msg = trading_hours.is_within_trading_hours()
    if not within_hours:
        st.warning(hours_msg)
        return

    in_cooldown, cooldown_msg = risk_rules.check_cooldown(symbol, signal)
    if in_cooldown:
        st.warning(cooldown_msg)
        return

    confirm_key = f"confirm_dup_{symbol}_{signal}"

    if st.button("✅ Aceptar y dar seguimiento a esta operación", key=f"accept_btn_{symbol}_{signal}"):
        duplicate = db.find_recent_similar_operation(symbol, signal, result["entry"], result["stop"])
        if duplicate:
            st.session_state[confirm_key] = True
            st.rerun()
        else:
            db.create_operation(
                symbol, signal, result["entry"], result["stop"], result["tp"],
                investment_amount=calc.get("investment"),
                risk_pct_used=calc.get("risk_pct"),
                capital_at_entry=calc.get("capital"),
                quantity=calc.get("qty"),
            )
            st.success("Operación en seguimiento (con el monto, riesgo y cantidad de la calculadora ya guardados). Se revisa automáticamente cada refresco.")
            st.rerun()

    if st.session_state.get(confirm_key):
        st.warning(
            f"⚠️ Ya abriste una operación casi idéntica de {symbol} hace menos de 2 minutos "
            f"(entrada y stop prácticamente iguales) -- ¿fue un doble clic accidental, o de verdad "
            f"quieres agregar otra posición igual?"
        )
        dc1, dc2 = st.columns(2)
        with dc1:
            if st.button("Sí, agregar de todas formas", key=f"confirm_yes_{symbol}_{signal}"):
                db.create_operation(
                    symbol, signal, result["entry"], result["stop"], result["tp"],
                    investment_amount=calc.get("investment"),
                    risk_pct_used=calc.get("risk_pct"),
                    capital_at_entry=calc.get("capital"),
                    quantity=calc.get("qty"),
                )
                st.session_state[confirm_key] = False
                st.success("Operación en seguimiento.")
                st.rerun()
        with dc2:
            if st.button("No, cancelar", key=f"confirm_no_{symbol}_{signal}"):
                st.session_state[confirm_key] = False
                st.rerun()


def _render_calculator(symbol: str, signal: str, result: dict, alert_key: str) -> dict:
    st.markdown("**Calculadora de ganancia/pérdida**")
    entry, stop, tp = result["entry"], result["stop"], result["tp"]
    stop_distance_pct = abs(entry - stop) / entry if entry else 0

    saved_capital, saved_calc_mode, saved_leverage = account_settings.get_settings()
    closed_ops = db.get_operation_history(500)
    real_balance, _ = performance.compute_real_balance(closed_ops, saved_capital)

    cap_col, mode_col = st.columns(2)
    with cap_col:
        capital = st.number_input(
            "Capital disponible ($)", min_value=1.0, value=real_balance, step=10.0, key="capital_input",
            help="Por defecto es tu saldo real (capital inicial + ganancias/pérdidas ya cerradas) -- configúralo en '⚙️ Cuenta' arriba.",
        )
    with mode_col:
        calc_mode = st.radio(
            "Modo de cálculo", ["risk_pct", "leverage"],
            format_func=lambda m: "Riesgo %" if m == "risk_pct" else "Apalancamiento fijo",
            index=0 if saved_calc_mode == "risk_pct" else 1, horizontal=True, key=f"calc_mode_{alert_key}",
        )

    if calc_mode == "risk_pct":
        risk_pct = st.number_input(
            "Riesgo por operación (%)", min_value=0.1, max_value=100.0, value=2.0, step=0.5,
            key="risk_pct_input",
            help="% de tu capital que estás dispuesto a perder si toca el stop. 1-2% es lo recomendado en gestión de riesgo profesional.",
        )
        suggested_investment = (capital * risk_pct / 100) / stop_distance_pct if stop_distance_pct > 0 else capital
        suggested_investment = round(suggested_investment, 2)
        max_loss_if_default = capital * risk_pct / 100
        st.metric("💡 Monto recomendado", f"${suggested_investment:.2f}", help=f"Para arriesgar {risk_pct:.1f}% de tu capital (${max_loss_if_default:.2f}) según la distancia real de este stop ({stop_distance_pct*100:.2f}%).")
    else:
        leverage_chosen = st.number_input("Apalancamiento deseado", min_value=1.0, max_value=50.0, value=saved_leverage, step=0.5, key="leverage_input")
        suggested_investment = round(capital * leverage_chosen, 2)
        implied_risk_pct = (suggested_investment * stop_distance_pct / capital * 100) if capital else 0
        risk_pct = implied_risk_pct
        st.metric("💡 Monto según apalancamiento", f"${suggested_investment:.2f}", help=f"Capital × {leverage_chosen:.1f}x. Esto implica arriesgar ~{implied_risk_pct:.1f}% de tu capital si toca el stop.")
        if implied_risk_pct > 5:
            st.warning(f"⚠️ Con {leverage_chosen:.1f}x y este stop, arriesgarías ~{implied_risk_pct:.1f}% de tu capital -- bastante por encima del 1-2% recomendado.")

    use_custom = st.checkbox("✏️ Usar un monto distinto al recomendado", key=f"custom_toggle_{alert_key}")
    if use_custom:
        investment = st.number_input(
            "Monto a invertir ($)", min_value=1.0, value=suggested_investment, step=10.0,
            key=f"custom_investment_{alert_key}",
        )
    else:
        investment = suggested_investment
        st.caption(f"Se usará el monto: ${investment:.2f}")

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

    lev_col1, lev_col2 = st.columns(2)
    with lev_col1:
        st.metric("Monto a invertir (final)", f"${investment:.2f}")
    with lev_col2:
        st.metric("Apalancamiento implícito", f"{implied_leverage:.1f}x")

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

    return {"capital": capital, "risk_pct": risk_pct, "investment": investment, "qty": qty}


def _maybe_send_alert(symbol: str, signal: str, result: dict, alert_key: str):
    if (
        result["status"] == "confirmada"
        and st.session_state.last_alert != alert_key
        and st.session_state.notifications_enabled
        and TOKEN and CHAT_ID
    ):
        within_hours, _ = trading_hours.is_within_trading_hours()
        if not within_hours:
            return
        in_cooldown, _ = risk_rules.check_cooldown(symbol, signal)
        if in_cooldown:
            return
        ok, info = send_signal_alert(symbol, result)
        if ok:
            st.session_state.last_alert = alert_key
            st.toast(f"Alerta enviada a Telegram ({symbol})")
        else:
            st.warning(f"No se pudo enviar Telegram: {info}")


def _render_mean_reversion_panel(symbol: str, open_ops: list):
    mr = get_mean_reversion_signal(symbol)
    if not mr.get("active"):
        return

    st.divider()
    st.markdown("### 🔄 Modo alternativo: reversión a la media")
    st.caption(
        f"Mercado lateral (ADX {mr['adx']}) -- el sistema de tendencia no opera aquí. "
        "Esta es una estrategia distinta y separada, basada en Bollinger Bands + vela de "
        "rechazo, validada para este tipo de régimen específicamente."
    )

    signal = mr.get("signal", "ESPERA")
    if signal == "ESPERA":
        st.info("Sin rechazo confirmado en las bandas todavía.")
        return

    color = "🟢" if signal == "COMPRA" else "🔴"
    status_labels = {"confirmada": " ✅ confirmada", "filtrada_rr": " 🚫 filtrada (riesgo/beneficio pobre)"}
    st.subheader(f"{color} {signal}{status_labels.get(mr['status'], '')}")
    st.caption(f"Banda inferior {format_price(mr['bb_lower'])} · media {format_price(mr['bb_mid'])} · superior {format_price(mr['bb_upper'])}")

    if mr["status"] != "confirmada":
        if mr["status"] == "filtrada_rr":
            st.caption(f"⛔ R:B ({mr.get('rr_ratio')}:1) por debajo del mínimo ({config.MIN_RR_RATIO}:1). No se ofrece como operable.")
        return

    st.code(f"Entrada: {format_price(mr['entry'])}", language=None)
    st.code(f"Stop: {format_price(mr['stop'])}", language=None)
    st.code(f"Take profit: {format_price(mr['tp'])}", language=None)
    st.caption(f"Ratio riesgo/beneficio: 1:{mr['rr_ratio']}")

    if not getattr(config, "ENABLE_MEAN_REVERSION_LIVE", False):
        st.warning(
            "⏸️ Este modo está pausado para uso en vivo -- los primeros backtests dieron "
            "resultados negativos consistentes (9/9 operaciones perdedoras). Los valores de "
            "arriba son de referencia. Sigue disponible para probar en la pestaña Backtest."
        )
        return

    open_ops_this_symbol = [o for o in open_ops if o["symbol"] == symbol]
    if open_ops_this_symbol:
        st.caption(f"Ya tienes {len(open_ops_this_symbol)} operación(es) de {symbol} en seguimiento.")

    within_hours, hours_msg = trading_hours.is_within_trading_hours()
    if not within_hours:
        st.warning(hours_msg)
        return

    in_cooldown, cooldown_msg = risk_rules.check_cooldown(symbol, signal)
    if in_cooldown:
        st.warning(cooldown_msg)
        return

    mr_capital = st.number_input("Capital disponible ($)", min_value=1.0, value=50.0, step=10.0, key=f"mr_capital_{symbol}")
    mr_risk_pct = st.number_input("Riesgo por operación (%)", min_value=0.1, max_value=100.0, value=2.0, step=0.5, key=f"mr_risk_{symbol}")
    stop_dist_pct = abs(mr["entry"] - mr["stop"]) / mr["entry"] if mr["entry"] else 0
    suggested = round((mr_capital * mr_risk_pct / 100) / stop_dist_pct, 2) if stop_dist_pct > 0 else mr_capital
    mr_investment = st.number_input("Monto a invertir ($)", min_value=1.0, value=suggested, step=10.0, key=f"mr_inv_{symbol}")
    mr_qty = mr_investment / mr["entry"]

    if st.button("✅ Aceptar reversión a la media", key=f"mr_accept_{symbol}"):
        db.create_operation(
            symbol, signal, mr["entry"], mr["stop"], mr["tp"],
            investment_amount=mr_investment, risk_pct_used=mr_risk_pct,
            capital_at_entry=mr_capital, quantity=mr_qty, strategy="mean_reversion",
        )
        st.success("Operación de reversión a la media en seguimiento (marcada por separado en el historial).")
        st.rerun()


def render_signal_panel(symbol: str, result: dict, open_ops: list):
    """Panel completo de la columna derecha: métricas, valores, calculadora, alerta."""
    _render_signal_metrics(result)

    signal = result["signal"]
    alert_key = f"{symbol}:{signal}"

    if signal in ("COMPRA", "VENTA"):
        _render_quantfury_values(result)
        calc = _render_calculator(symbol, signal, result, alert_key)
        _render_accept_operation_button(symbol, signal, result, open_ops, calc)
        _maybe_send_alert(symbol, signal, result, alert_key)
    else:
        st.info("Sin señal confirmada — mercado en zona de espera.")
        st.caption(f"Confluencia actual: {result['buy_score']} a favor de compra vs {result['sell_score']} a favor de venta (se necesita ≥3 y mayoría clara).")
        remaining = _next_candle_close() - pd.Timestamp.now(tz="UTC")
        st.caption(f"⏱️ Próxima vela cierra en {_format_timedelta(remaining)} -- el análisis solo cambia al cerrar una vela.")
        st.session_state.last_alert = alert_key

    _render_mean_reversion_panel(symbol, open_ops)
