"""
Recibe comandos que le mandas a tu bot de Telegram y los traduce a acciones
del dashboard. Comandos soportados:

  /start           -> activa las alertas push
  /stop            -> desactiva las alertas push (el dashboard sigue viendo el mercado)
  /status          -> resumen corto: activo/pausado, cripto y señal actual
  /now             -> análisis completo al momento (igual al panel del dashboard)
  /symbol BTCUSDT  -> cambia la cripto que se está siguiendo
"""
import requests


def get_updates(token: str, offset: int = 0, timeout: int = 5):
    """Trae mensajes nuevos enviados al bot desde el último offset procesado."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        r = requests.get(url, params={"offset": offset, "timeout": 0}, timeout=timeout)
        r.raise_for_status()
        data = r.json()
        return data.get("result", [])
    except Exception:
        return []


def parse_commands(updates: list, expected_chat_id: str):
    """
    Devuelve una lista de comandos parseados: [{"cmd": "start", "arg": None}, ...]
    Solo procesa mensajes que vengan de tu propio chat_id (seguridad básica:
    que nadie más pueda controlar tu bot aunque adivine el username).
    """
    commands = []
    max_update_id = None
    for u in updates:
        max_update_id = u["update_id"]
        msg = u.get("message") or u.get("edited_message")
        if not msg:
            continue
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if expected_chat_id and chat_id != str(expected_chat_id):
            continue  # ignorar mensajes de cualquier otro chat
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        parts = text[1:].split()
        cmd = parts[0].lower()
        arg = parts[1].upper() if len(parts) > 1 else None
        commands.append({"cmd": cmd, "arg": arg})
    return commands, max_update_id


def format_status_message(symbol: str, notifications_enabled: bool, result: dict) -> str:
    estado = "🟢 Activas" if notifications_enabled else "🔴 Pausadas"
    signal_emoji = {"COMPRA": "🟢", "VENTA": "🔴", "ESPERA": "🟡"}[result["signal"]]
    lines = [
        f"*Estado de alertas:* {estado}",
        f"*Cripto en seguimiento:* {symbol}",
        f"*Precio:* ${result['price']:,.2f}",
        f"{signal_emoji} *Señal:* {result['signal']}",
        f"MACD: {result['macd_state']} | RSI: {result['rsi']} ({result['rsi_zone']})",
        f"PVT: {result['pvt_confirm']}",
        f"Delta: {result['delta_state']} ({result['delta_pct']}%)",
    ]
    if result["signal"] in ("COMPRA", "VENTA"):
        lines.append(f"Entrada: ${result['entry']:,.2f} | Stop: ${result['stop']:,.2f} | TP: ${result['tp']:,.2f}")
    return "\n".join(lines)
