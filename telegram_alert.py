"""
Envío de alertas push a tu Telegram cuando se detecta una señal.

CÓMO OBTENER TUS CREDENCIALES (gratis, 2 minutos):
1. En Telegram, busca el bot @BotFather y envíale /newbot
2. Sigue las instrucciones (nombre del bot) y te dará un TOKEN
3. Busca tu bot recién creado y envíale cualquier mensaje (ej. "hola")
4. Abre en el navegador: https://api.telegram.org/bot<TU_TOKEN>/getUpdates
5. Busca "chat":{"id": ...} en la respuesta -- ese número es tu CHAT_ID

Guarda ambos valores como variables de entorno TELEGRAM_TOKEN y TELEGRAM_CHAT_ID
(o pégalos directamente en config.py).
"""
import requests


def send_telegram_message(token: str, chat_id: str, text: str):
    if not token or not chat_id:
        return False, "Faltan credenciales de Telegram"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}, timeout=10)
        r.raise_for_status()
        return True, "ok"
    except Exception as e:
        return False, str(e)
