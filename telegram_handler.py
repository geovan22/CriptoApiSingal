"""
Procesa los comandos pendientes que el usuario le mandó al bot de Telegram
(/start, /stop, /help, /favorites, /operations, /symbol, /status, /now).
"""
import streamlit as st

import config
import db
from data_fetch import get_klines
from price_format import format_price
from telegram_alert import send_telegram_message
from telegram_bot import get_updates, parse_commands, format_status_message, format_help_message
from app_state import set_symbol
from signal_service import get_data_and_signal

TOKEN = config.TELEGRAM_TOKEN
CHAT_ID = config.TELEGRAM_CHAT_ID


def send_signal_alert(symbol: str, result: dict):
    msg = (
        f"*{result['signal']}* señal CONFIRMADA en *{symbol}* ({config.INTERVAL})\n"
        f"Precio: ${format_price(result['price'])}\n"
        f"Entrada: ${format_price(result['entry'])}\n"
        f"Stop: ${format_price(result['stop'])}\n"
        f"TP: ${format_price(result['tp'])}\n"
        f"A favor: {', '.join(result['reasons'])}\n"
        + (f"En conflicto: {', '.join(result['conflict_reasons'])}" if result['conflict_reasons'] else "")
    )
    return send_telegram_message(TOKEN, CHAT_ID, msg)


def process_telegram_commands():
    """Revisa y ejecuta cualquier comando nuevo recibido por Telegram."""
    if not (TOKEN and CHAT_ID):
        return

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

        elif cmd == "favorites":
            favs = db.get_favorites()
            send_telegram_message(TOKEN, CHAT_ID, "*Favoritos:*\n" + ("\n".join(f"- {s}" for s in favs) if favs else "(ninguno)"))

        elif cmd == "operations":
            ops = db.get_open_operations()
            if not ops:
                send_telegram_message(TOKEN, CHAT_ID, "No hay operaciones en seguimiento.")
            else:
                lines = [f"{o['symbol']} {o['direction']} | entrada {format_price(o['entry'])} | stop {format_price(o['stop'])} | tp {format_price(o['tp'])}" for o in ops]
                send_telegram_message(TOKEN, CHAT_ID, "*Operaciones en seguimiento:*\n" + "\n".join(lines))

        elif cmd == "symbol" and arg:
            symbol = arg if arg.endswith("USDT") else f"{arg}USDT"
            try:
                get_klines(symbol, config.INTERVAL, limit=5)
                set_symbol(symbol)
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
