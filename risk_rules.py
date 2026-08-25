"""
Reglas de disciplina que no son parte del análisis técnico en sí, pero
protegen contra errores de comportamiento comunes -- en este caso,
"revenge trading": volver a entrar de inmediato en el mismo símbolo y
misma dirección justo después de que un stop-loss demostró que la lectura
estaba equivocada en ese momento.
"""
import pandas as pd

import config
import db


def _interval_hours() -> float:
    interval = config.INTERVAL
    if interval.endswith("h"):
        return float(interval[:-1])
    if interval.endswith("d"):
        return float(interval[:-1]) * 24
    if interval.endswith("m"):
        return float(interval[:-1]) / 60
    return 4.0


def check_cooldown(symbol: str, direction: str) -> tuple[bool, str]:
    """
    Devuelve (en_cooldown, mensaje). Si el último cierre de este símbolo
    en esta misma dirección fue por stop-loss y todavía no pasaron
    config.COOLDOWN_CANDLES velas, está en enfriamiento.
    """
    history = db.get_operation_history(50)
    matches = [
        h for h in history
        if h["symbol"] == symbol and h["direction"] == direction and h["outcome"] == "stop"
    ]
    if not matches:
        return False, ""

    last = matches[0]  # get_operation_history ya viene ordenado por closed_at DESC
    try:
        closed_at = pd.Timestamp(last["closed_at"])
        if closed_at.tzinfo is None:
            closed_at = closed_at.tz_localize("UTC")
    except Exception:
        return False, ""

    now = pd.Timestamp.now(tz="UTC")
    hours_since = (now - closed_at).total_seconds() / 3600
    cooldown_hours = config.COOLDOWN_CANDLES * _interval_hours()

    if hours_since < cooldown_hours:
        remaining = cooldown_hours - hours_since
        return True, (
            f"⏸️ En enfriamiento: {symbol} {direction} tuvo un stop-loss hace "
            f"{hours_since:.1f}h. Se recomienda esperar {remaining:.1f}h más "
            f"antes de reentrar en la misma dirección (evita repetir el mismo error)."
        )
    return False, ""
