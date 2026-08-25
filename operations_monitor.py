"""
Revisa operaciones en seguimiento (cierra solas al tocar TP/stop, avisa si
el análisis se revierte) y la watchlist de favoritos (solo informativa).
"""
import streamlit as st

import config
import db
import risk_rules
from price_format import format_price
from telegram_alert import send_telegram_message
from signal_service import get_data_and_signal
from telegram_handler import send_signal_alert, TOKEN, CHAT_ID


def check_open_operations(open_ops: list):
    """
    Para cada operación en seguimiento: si tocó TP o stop, la cierra y
    registra el resultado. Si alcanzó 1x su riesgo original a favor, mueve
    el stop a break-even (ya no puede perder). Si el análisis ahora
    confirma la señal contraria, manda una alerta de salida temprana.
    """
    for op in open_ops:
        try:
            _, op_result = get_data_and_signal(op["symbol"])
        except Exception:
            continue
        live_price = op_result["live_price"]

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

        # --- Break-even automático: si ya ganó 1x su riesgo original, el
        # stop se mueve al precio de entrada -- de aquí en adelante la
        # operación no puede terminar en pérdida. ---
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

        # --- Alerta de reversión ---
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


def get_confirmed_favorites_signals() -> list:
    """
    Revisa TODOS los favoritos y devuelve solo los que tienen una señal
    CONFIRMADA (COMPRA o VENTA, sin advertencias, sin estar en formación,
    sin estar filtrada por ADX/R:B). Es puramente informativo -- no cambia
    el símbolo en seguimiento ni navega a ningún lado. El usuario decide
    manualmente cuál revisar a fondo.
    """
    results = []
    for fav_symbol in db.get_favorites():
        try:
            _, fav_result = get_data_and_signal(fav_symbol)
        except Exception:
            continue
        if fav_result["signal"] in ("COMPRA", "VENTA") and fav_result["status"] == "confirmada":
            results.append({"symbol": fav_symbol, "signal": fav_result["signal"], "result": fav_result})
    return results


def notify_favorites_signals(confirmed_list: list):
    """
    Si el usuario activó las notificaciones de favoritos, manda una alerta
    de Telegram por cada señal nueva de la lista (sin repetir la misma
    mientras siga vigente). No cambia el símbolo en seguimiento.
    """
    if not st.session_state.get("notify_favorites") or not (TOKEN and CHAT_ID) or not st.session_state.notifications_enabled:
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
