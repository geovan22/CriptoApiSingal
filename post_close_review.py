"""
Simulación "¿qué hubiera pasado?" para operaciones que cerraste
MANUALMENTE. Responde: si no hubieras intervenido, ¿habría tocado tu
take profit, tu stop, o seguiría abierta? Compara eso contra lo que
realmente hiciste, para ir calibrando si tus cierres manuales están
ayudando o quitándole ganancia al sistema.
"""
import pandas as pd

from data_fetch import get_klines


def _fetch_forward(symbol: str, interval: str, start_time, max_calls: int = 3) -> pd.DataFrame:
    """Trae velas desde start_time hasta ahora, paginando si hace falta."""
    frames = []
    cursor = start_time
    for _ in range(max_calls):
        chunk = get_klines(symbol, interval, limit=1000, start_time=cursor)
        if chunk.empty:
            break
        frames.append(chunk)
        if len(chunk) < 1000:
            break
        cursor = chunk.iloc[-1]["close_time"]
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset="open_time").reset_index(drop=True)
    return df


def simulate_forward(symbol: str, direction: str, entry: float, stop: float, tp: float,
                      start_time, interval: str = "4h") -> dict:
    """
    Simula vela por vela desde start_time qué habría pasado si nunca
    hubieras tocado la operación. Devuelve 'tp', 'stop', o 'sigue_abierta'.
    """
    try:
        df = _fetch_forward(symbol, interval, start_time)
    except Exception as e:
        return {"error": str(e)}

    if df.empty:
        return {"error": "No se pudieron obtener velas para simular."}

    for i, candle in df.iterrows():
        hit_tp = (direction == "COMPRA" and candle["high"] >= tp) or \
                 (direction == "VENTA" and candle["low"] <= tp)
        hit_stop = (direction == "COMPRA" and candle["low"] <= stop) or \
                   (direction == "VENTA" and candle["high"] >= stop)

        if hit_stop:
            pnl_pct = ((stop - entry) / entry * 100) if direction == "COMPRA" else ((entry - stop) / entry * 100)
            return {"outcome": "stop", "close_price": stop, "close_time": candle["open_time"], "bars": i + 1, "pnl_pct": pnl_pct}
        if hit_tp:
            pnl_pct = ((tp - entry) / entry * 100) if direction == "COMPRA" else ((entry - tp) / entry * 100)
            return {"outcome": "tp", "close_price": tp, "close_time": candle["open_time"], "bars": i + 1, "pnl_pct": pnl_pct}

    last_price = df.iloc[-1]["close"]
    pnl_pct = ((last_price - entry) / entry * 100) if direction == "COMPRA" else ((entry - last_price) / entry * 100)
    return {"outcome": "sigue_abierta", "close_price": last_price, "close_time": df.iloc[-1]["open_time"], "bars": len(df), "pnl_pct": pnl_pct}


def review_manual_closes(closed_ops: list) -> list:
    """Para cada operación cerrada manualmente, compara realidad vs simulación."""
    reviews = []
    for op in closed_ops:
        if op.get("close_reason") != "manual":
            continue
        sim = simulate_forward(
            op["symbol"], op["direction"], op["entry"],
            op.get("initial_stop") or op["stop"], op["tp"],
            start_time=op["opened_at"],
        )
        if "error" in sim:
            continue
        reviews.append({
            "symbol": op["symbol"],
            "direction": op["direction"],
            "actual_pnl_pct": op.get("pnl_pct"),
            "actual_close_price": op.get("close_price"),
            "sim_outcome": sim["outcome"],
            "sim_pnl_pct": sim["pnl_pct"],
            "sim_close_time": sim["close_time"],
            "sim_bars": sim["bars"],
        })
    return reviews
