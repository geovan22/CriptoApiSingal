"""
Revisa operaciones en seguimiento (cierra solas al tocar TP/stop, avisa si
el análisis se revierte) y el modo escaneo de favoritos.
"""
import streamlit as st

import config
import db
from price_format import format_price
from telegram_alert import send_telegram_message
from signal_service import get_data_and_signal
from app_state import set_symbol
from telegram_handler import send_signal_alert, TOKEN, CHAT_ID


def check_open_operations():
    """
    Para cada operación en seguimiento: si tocó TP o stop, la cierra y
    registra el resultado. Si el análisis ahora confirma la señal
    contraria, manda una alerta de salida temprana (una sola vez).
    """
    for op in db.get_open_operations():
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
        elif hit_stop:
            db.close_operation(op["id"], live_price, "stop")
            if TOKEN and CHAT_ID:
                send_telegram_message(TOKEN, CHAT_ID, f"🛑 *{op['symbol']}* tocó Stop Loss en ${format_price(live_price)}. Operación cerrada en el registro.")
        elif not op["early_warning_sent"]:
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


def run_scan_mode():
    """
    Si el modo escaneo está activo, revisa los favoritos y cambia
    automáticamente al primero que tenga una señal confirmada.
    """
    if not st.session_state.scan_mode:
        return

    favorites = db.get_favorites()
    found = None
    for fav_symbol in favorites:
        try:
            _, fav_result = get_data_and_signal(fav_symbol)
        except Exception:
            continue
        if fav_result["signal"] in ("COMPRA", "VENTA") and fav_result["status"] == "confirmada":
            found = (fav_symbol, fav_result)
            break

    if found:
        fav_symbol, fav_result = found
        set_symbol(fav_symbol)
        alert_key = f"{fav_symbol}:{fav_result['signal']}"
        if st.session_state.last_alert != alert_key and st.session_state.notifications_enabled and TOKEN and CHAT_ID:
            ok, _ = send_signal_alert(fav_symbol, fav_result)
            if ok:
                st.session_state.last_alert = alert_key
