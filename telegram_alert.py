"""
Envío de alertas push a tu Telegram cuando se detecta una señal.
"""
import requests
import time


def send_telegram_message(token: str, chat_id: str, text: str, retries: int = 2, timeout: int = 20):
    if not token or not chat_id:
        return False, "Faltan credenciales de Telegram"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    last_err = None
    for attempt in range(retries + 1):
        try:
            r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=timeout)
            r.raise_for_status()
            return True, "ok"
        except Exception as e:
            last_err = e
            if attempt < retries:
                time.sleep(2)
            continue
    return False, str(last_err)
