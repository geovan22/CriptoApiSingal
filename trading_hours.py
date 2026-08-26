"""
Horario de operación configurable. Restringe cuándo se ofrecen señales
NUEVAS para aceptar y cuándo se mandan alertas de entrada -- NUNCA
restringe el monitoreo de operaciones ya abiertas (esas siguen su curso
sin importar la hora, para no dejarlas sin vigilancia).

Útil para evitar que el sistema te ofrezca (o te avise de) entradas
nuevas cuando no estás disponible para revisarlas -- ej. mientras duermes.
"""
import pandas as pd
import db


def get_settings():
    enabled = db.get_state("trading_hours_enabled", "0") == "1"
    start = int(db.get_state("trading_hours_start", "0"))
    end = int(db.get_state("trading_hours_end", "24"))
    offset = float(db.get_state("trading_hours_utc_offset", "0"))
    return enabled, start, end, offset


def set_settings(enabled: bool, start: int, end: int, offset: float):
    db.set_state("trading_hours_enabled", "1" if enabled else "0")
    db.set_state("trading_hours_start", str(start))
    db.set_state("trading_hours_end", str(end))
    db.set_state("trading_hours_utc_offset", str(offset))


def is_within_trading_hours() -> tuple[bool, str]:
    """
    Devuelve (permitido, mensaje). Si el horario no está activado,
    siempre permite. Soporta rangos que cruzan medianoche (ej. 22 a 6).
    """
    enabled, start, end, offset = get_settings()
    if not enabled:
        return True, ""

    now_utc = pd.Timestamp.now(tz="UTC")
    local_hour = (now_utc.hour + offset) % 24

    if start <= end:
        within = start <= local_hour < end
    else:
        within = local_hour >= start or local_hour < end

    if within:
        return True, ""
    return False, (
        f"⏰ Fuera de tu horario configurado ({start:02.0f}:00–{end:02.0f}:00, hora local). "
        f"No se ofrece para aceptar ni se envían alertas de entradas nuevas -- las operaciones "
        f"ya abiertas se siguen vigilando normalmente."
    )
