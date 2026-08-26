"""
Revisa operaciones en seguimiento (cierra solas al tocar TP/stop, avisa si
el análisis se revierte) y la watchlist de favoritos.
"""
import streamlit as st

import config
import db
import risk_rules
import trading_hours
from price_format import format_price
from telegram_alert import send_telegram_message
from signal_service import get_data_and_signal
from telegram_handler import send_signal_alert, TOKEN, CHAT_ID


def check_open_operations(open_ops: list):
    for op in open_ops:
        try:
            _, op_result = get_data_and_signal(op["symbol"])
        except Exception:
            continue
        live_price = op_result["live_price"]

        prev_mfe = op.get("mfe_price") or op["entry"]
        prev_mae = op.get("mae_price") or op["entry"]
        if op["direction"] == "COMPRA":
            new_mfe = max(prev_mfe, live_price)
            new_mae = min(prev_mae, live_price)
        else:
            new_mfe = min(prev_mfe, live_price)
            new_mae = max(prev_mae, live_price)
        if new_mfe != prev_mfe or new_mae != prev_mae:
            db.update_mae_mfe(op["id"], new_mfe, new_mae)

        hit_tp = (op["direction"] == "COMPRA" and live_price >= op["tp"]) or \
                 (op["direction"] == "VENTA" and live_price <= op["tp"])
        hit_stop = (op["direction"] == "COMPRA" and live_price <= op["stop"]) or \
                   (op["direction"] == "VENTA" and live_price >= op["stop"])

        if hit_tp:
            db.close_operation(op["id"], live_price, "tp")
            if TOKEN and CHAT_ID:
                send_telegram_message(TOKEN, CHAT_ID, f"🎯 *{op['symbol']}* tocó Take Profit en ${format_price(live_price)}. Operación cerrada en el registro.")
            continue

        if hit_stop:
            db.close_operation(op["id"], live_price, "stop")
            if TOKEN and CHAT_ID:
                send_telegram_message(TOKEN, CHAT_ID, f"🛑 *{op['symbol']}* tocó Stop Loss en ${format_price(live_price)}. Operación cerrada en el registro.")
            continue

        if not op.get("breakeven_applied"):
            risk_ref = op.get("initial_stop") or op["stop"]
            risk_distance = abs(op["entry"] - risk_ref)
            if risk_distance > 0:
                profit_distance = (live_price - op["entry"]) if op["direction"] == "COMPRA" else (op["entry"] - live_price)
                if profit_distance >= risk_distance:
                    db.apply_breakeven(op["id"], op["entry"])
                    if TOKEN and CHAT_ID:
                        send_telegram_message(
                            TOKEN, CHAT_ID,
                            f"🔒 *{op['symbol']}*: alcanzó 1x su riesgo original a favor. "
                            f"Stop movido a punto de entrada (${format_price(op['entry'])}) -- "
                            f"esta operación ya no puede terminar en pérdida."
                        )

        if not op["early_warning_sent"]:
            opposite = "VENTA" if op["direction"] == "COMPRA" else "COMPRA"
            if op_result["signal"] == opposite and op_result["status"] == "confirmada":
                db.mark_early_warning_sent(op["id"])
                if TOKEN and CHAT_ID:
                    send_telegram_message(
                        TOKEN, CHAT_ID,
                        f"⚠️ *{op['symbol']}*: el análisis ahora confirma señal de *{opposite}*, "
                        f"contraria a tu operación de {op['direction']} abierta en ${format_price(op['entry'])}. "
                        f"Precio actual: ${format_price(live_price)}. Considera evaluar salir manualmente en Quantfury "
                        f"para reducir la pérdida potencial."
                    )


def get_confirmed_favorites_signals(open_ops: list = None) -> list:
    symbols_in_tracking = {op["symbol"] for op in (open_ops or [])}
    results = []
    for fav_symbol in db.get_favorites():
        if fav_symbol in symbols_in_tracking:
            continue
        try:
            _, fav_result = get_data_and_signal(fav_symbol)
        except Exception:
            continue
        if fav_result["signal"] in ("COMPRA", "VENTA") and fav_result["status"] == "confirmada":
            results.append({"symbol": fav_symbol, "signal": fav_result["signal"], "result": fav_result})
    return results


def notify_favorites_signals(confirmed_list: list):
    if not st.session_state.get("notify_favorites") or not (TOKEN and CHAT_ID) or not st.session_state.notifications_enabled:
        return
    within_hours, _ = trading_hours.is_within_trading_hours()
    if not within_hours:
        return
    if "sent_favorite_alerts" not in st.session_state:
        st.session_state.sent_favorite_alerts = set()

    for item in confirmed_list:
        alert_key = f"{item['symbol']}:{item['signal']}"
        if alert_key in st.session_state.sent_favorite_alerts:
            continue
        in_cooldown, _ = risk_rules.check_cooldown(item["symbol"], item["signal"])
        if in_cooldown:
            continue
        ok, _ = send_signal_alert(item["symbol"], item["result"])
        if ok:
            st.session_state.sent_favorite_alerts.add(alert_key)
