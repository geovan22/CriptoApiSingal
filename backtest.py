"""
Backtesting -- corre la lógica EXACTA de evaluate_signal() sobre datos
históricos, vela por vela, sin look-ahead (cada decisión solo usa datos
disponibles hasta ese momento). Esto existe porque ajustar pesos/reglas
basándose en el resultado de una sola operación real es sobreajuste --
antes de confiar en el sistema en vivo, hay que ver cómo se habría
comportado en cientos de operaciones pasadas.

Los indicadores se calculan UNA sola vez sobre todo el histórico (son
causales: EMA/RSI/MACD/ADX en la fila i solo dependen de filas <= i), y
luego se revela una ventana creciente vela por vela -- rápido y sin fuga
de información del futuro.

LIMITACIÓN CONOCIDA: la tendencia diaria (1D) que en vivo se calcula con
velas reales de 1 día, aquí se aproxima con EMA200 del propio timeframe
(4h) para no requerir una segunda descarga por cada vela evaluada. Es una
simplificación razonable pero no idéntica al comportamiento en vivo.
"""
import numpy as np
from data_fetch import get_klines
from indicators import add_all_indicators
from signals import evaluate_signal


def _trend_from_ema200(df):
    return np.where(df["close"] > df["ema200"], "alcista", "bajista")


def run_backtest(symbol: str, interval: str = "4h", limit: int = 1000, warmup: int = 210):
    """
    Devuelve (trades: list[dict], stats: dict).
    warmup: velas iniciales que se saltan para dar tiempo a que EMA200/ADX
    se estabilicen antes de empezar a operar (con menos datos, los
    indicadores de largo plazo son poco confiables).
    """
    raw = get_klines(symbol, interval, limit)
    df = add_all_indicators(raw)
    if len(df) < warmup + 5:
        raise ValueError(f"No hay suficientes velas ({len(df)}) para un backtest confiable (mínimo {warmup + 5}).")

    trend_arr = _trend_from_ema200(df)

    trades = []
    open_trade = None
    i = warmup

    while i < len(df):
        if open_trade is None:
            window = df.iloc[:i + 1]
            result = evaluate_signal(window, trend_1d=trend_arr[i])
            if result["signal"] in ("COMPRA", "VENTA") and result["status"] == "confirmada":
                open_trade = {
                    "symbol": symbol,
                    "direction": result["signal"],
                    "entry": result["entry"],
                    "stop": result["stop"],
                    "tp": result["tp"],
                    "entry_index": i,
                    "entry_time": df.iloc[i]["open_time"],
                }
            i += 1
        else:
            candle = df.iloc[i]
            hit_tp = (open_trade["direction"] == "COMPRA" and candle["high"] >= open_trade["tp"]) or \
                     (open_trade["direction"] == "VENTA" and candle["low"] <= open_trade["tp"])
            hit_stop = (open_trade["direction"] == "COMPRA" and candle["low"] <= open_trade["stop"]) or \
                       (open_trade["direction"] == "VENTA" and candle["high"] >= open_trade["stop"])

            outcome = close_price = None
            if hit_stop:  # si ambos se tocan en la misma vela: conservador, se asume stop primero
                outcome, close_price = "stop", open_trade["stop"]
            elif hit_tp:
                outcome, close_price = "tp", open_trade["tp"]

            if outcome:
                if open_trade["direction"] == "COMPRA":
                    pnl_pct = (close_price - open_trade["entry"]) / open_trade["entry"] * 100
                else:
                    pnl_pct = (open_trade["entry"] - close_price) / open_trade["entry"] * 100
                trades.append({
                    **open_trade,
                    "outcome": outcome,
                    "close_price": close_price,
                    "exit_time": candle["open_time"],
                    "bars_held": i - open_trade["entry_index"],
                    "pnl_pct": pnl_pct,
                })
                open_trade = None
            i += 1

    stats = summarize_trades(trades)
    stats["open_at_end"] = open_trade is not None
    stats["candles_used"] = len(df)
    return trades, stats


def summarize_trades(trades: list) -> dict:
    if not trades:
        return {"n_trades": 0}
    n = len(trades)
    wins = [t for t in trades if t["pnl_pct"] > 0]
    losses = [t for t in trades if t["pnl_pct"] <= 0]
    win_rate = len(wins) / n * 100
    avg_win = float(np.mean([t["pnl_pct"] for t in wins])) if wins else 0.0
    avg_loss = float(np.mean([t["pnl_pct"] for t in losses])) if losses else 0.0
    total_pnl = sum(t["pnl_pct"] for t in trades)
    expectancy = total_pnl / n

    sum_losses = sum(t["pnl_pct"] for t in losses)
    profit_factor = (sum(t["pnl_pct"] for t in wins) / abs(sum_losses)) if losses and sum_losses != 0 else None

    cum = np.cumsum([t["pnl_pct"] for t in trades])
    peak = np.maximum.accumulate(cum)
    drawdown = cum - peak
    max_drawdown = float(drawdown.min()) if len(drawdown) else 0.0

    avg_bars_held = float(np.mean([t["bars_held"] for t in trades]))

    return {
        "n_trades": n,
        "win_rate": round(win_rate, 1),
        "avg_win_pct": round(avg_win, 2),
        "avg_loss_pct": round(avg_loss, 2),
        "expectancy_pct": round(expectancy, 3),
        "profit_factor": round(profit_factor, 2) if profit_factor is not None else None,
        "total_pnl_pct": round(total_pnl, 2),
        "max_drawdown_pct": round(max_drawdown, 2),
        "avg_bars_held": round(avg_bars_held, 1),
        "compra_count": sum(1 for t in trades if t["direction"] == "COMPRA"),
        "venta_count": sum(1 for t in trades if t["direction"] == "VENTA"),
    }
