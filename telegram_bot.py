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
from price_format import format_price


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
    status_tag = ""
    if result["signal"] in ("COMPRA", "VENTA"):
        status_labels = {
            "confirmada": " (✅ confirmada)",
            "en formación": " (⏳ en formación)",
            "filtrada_adx": " (🚫 filtrada: ADX bajo, mercado sin tendencia)",
            "filtrada_rr": " (🚫 filtrada: riesgo/beneficio pobre)",
        }
        status_tag = status_labels.get(result.get("status"), "")
    lines = [
        f"*Estado de alertas:* {estado}",
        f"*Cripto en seguimiento:* {symbol}",
        f"*Precio:* ${format_price(result['price'])}",
        f"{signal_emoji} *Señal:* {result['signal']}{status_tag}",
        f"MACD: {result['macd_state']} | RSI: {result['rsi']} ({result['rsi_zone']})",
        f"PVT: {result['pvt_confirm']}",
        f"Delta: {result['delta_state']} ({result['delta_pct']}%)",
    ]
    if result.get("trend_1d"):
        lines.append(f"Tendencia 1D: {result['trend_1d']}")
    if result["signal"] in ("COMPRA", "VENTA"):
        lines.append(f"Entrada: ${format_price(result['entry'])} | Stop: ${format_price(result['stop'])} | TP: ${format_price(result['tp'])}")
        if result.get("rr_ratio") is not None:
            lines.append(f"Ratio riesgo/beneficio: 1:{result['rr_ratio']}")
        if result.get("status") != "confirmada":
            lines.append("⚠️ No operable todavía -- revisa el motivo arriba antes de considerar esta señal.")
        if result.get("reasons"):
            lines.append(f"✅ A favor: {', '.join(result['reasons'])}")
        if result.get("conflict_reasons"):
            lines.append(f"⚠️ En conflicto: {', '.join(result['conflict_reasons'])}")
    return "\n".join(lines)


def format_help_message() -> str:
    return (
        "*Comandos disponibles*\n\n"
        "🟢 /start\n"
        "Activa las alertas push. Cuando el dashboard detecte una señal de "
        "COMPRA o VENTA, te llega el aviso aquí con entrada, stop y take profit.\n\n"
        "🔴 /stop\n"
        "Pausa las alertas. El dashboard sigue vigilando el mercado igual, "
        "solo deja de mandarte mensajes hasta que uses /start de nuevo.\n\n"
        "ℹ️ /status\n"
        "Resumen corto: si las alertas están activas o pausadas, qué cripto "
        "estás siguiendo y cuál es la señal actual (COMPRA/VENTA/ESPERA).\n\n"
        "🔍 /now\n"
        "Igual que /status pero con el detalle completo del análisis al momento "
        "(MACD, RSI, PVT, delta, soporte/resistencia) -- úsalo cuando quieras ver "
        "cómo está el mercado ahora mismo sin abrir el dashboard.\n\n"
        "🔄 /symbol PAR\n"
        "Cambia la cripto en seguimiento. El PAR va en formato Binance.\n"
        "Ejemplo: `/symbol ETHUSDT` o `/symbol SOL` (el USDT se agrega solo si lo omites).\n\n"
        "⭐ /favorites\n"
        "Muestra tu lista de favoritos (los que usa el modo escaneo).\n\n"
        "📍 /operations\n"
        "Muestra tus operaciones en seguimiento (entrada, stop, TP de cada una).\n\n"
        "❓ /help\n"
        "Muestra este mensaje."
    )
