"""
Backtesting -- corre la lógica EXACTA de evaluate_signal() sobre datos
históricos, vela por vela, sin look-ahead.

LIMITACIÓN CONOCIDA: la tendencia diaria (1D) que en vivo se calcula con
velas reales de 1 día, aquí se aproxima con EMA200 del propio timeframe
(4h) para no requerir una segunda descarga por cada vela evaluada.
"""
import numpy as np
from data_fetch import get_klines
from indicators import add_all_indicators
from signals import evaluate_signal, evaluate_mean_reversion


def _trend_from_ema200(df):
    return np.where(df["close"] > df["ema200"], "alcista", "bajista")


def _simulate(df, symbol: str, warmup: int, strategy: str = "trend"):
    """
    strategy: "trend" (sistema principal, con tendencia 1D) o
    "mean_reversion" (Bollinger Bands, solo activo en ADX bajo).
    """
    trend_arr = _trend_from_ema200(df) if strategy == "trend" else None
    trades = []
    open_trade = None
    i = warmup

    while i < len(df):
        if open_trade is None:
            window = df.iloc[:i + 1]
            if strategy == "mean_reversion":
                result = evaluate_mean_reversion(window)
                if not result.get("active"):
                    i += 1
                    continue
            else:
                result = evaluate_signal(window, trend_1d=trend_arr[i])

            if result["signal"] in ("COMPRA", "VENTA") and result["status"] == "confirmada":
                entry_score = result.get("buy_score") if result["signal"] == "COMPRA" else result.get("sell_score")
                open_trade = {
                    "symbol": symbol,
                    "direction": result["signal"],
                    "entry": result["entry"],
                    "stop": result["stop"],
                    "tp": result["tp"],
                    "entry_index": i,
                    "entry_time": df.iloc[i]["open_time"],
                    "entry_score": entry_score,
                }
            i += 1
        else:
            candle = df.iloc[i]
            hit_tp = (open_trade["direction"] == "COMPRA" and candle["high"] >= open_trade["tp"]) or \
                     (open_trade["direction"] == "VENTA" and candle["low"] <= open_trade["tp"])
            hit_stop = (open_trade["direction"] == "COMPRA" and candle["low"] <= open_trade["stop"]) or \
                       (open_trade["direction"] == "VENTA" and candle["high"] >= open_trade["stop"])

            outcome = close_price = None
            if hit_stop:
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


def run_backtest(symbol: str, interval: str = "4h", limit: int = 1000, warmup: int = 210, strategy: str = "trend"):
    raw = get_klines(symbol, interval, limit)
    df = add_all_indicators(raw)
    if len(df) < warmup + 5:
        raise ValueError(f"No hay suficientes velas ({len(df)}) para un backtest confiable (mínimo {warmup + 5}).")
    return _simulate(df, symbol, warmup, strategy=strategy)


def run_multi_symbol_backtest(symbols: list, interval: str = "4h", limit: int = 700,
                               warmup: int = 210, progress_callback=None, strategy: str = "trend"):
    all_trades = []
    per_symbol_stats = {}
    errors = {}

    for i, symbol in enumerate(symbols):
        if progress_callback:
            progress_callback(symbol, i, len(symbols))
        try:
            trades, stats = run_backtest(symbol, interval, limit, warmup, strategy=strategy)
            per_symbol_stats[symbol] = stats
            all_trades.extend(trades)
        except Exception as e:
            errors[symbol] = str(e)

    pooled_stats = summarize_trades(all_trades)
    return all_trades, per_symbol_stats, pooled_stats, errors


def run_out_of_sample_validation(symbol: str, interval: str = "4h", total_limit: int = 1400,
                                  split_ratio: float = 0.6, train_warmup: int = 210, test_buffer: int = 150,
                                  strategy: str = "trend"):
    raw = get_klines(symbol, interval, total_limit)
    df = add_all_indicators(raw)
    n = len(df)
    mid = int(n * split_ratio)

    if mid < train_warmup + 20 or (n - mid) < 20:
        raise ValueError(f"No hay suficientes velas ({n}) para dividir en train/test de forma confiable.")

    train_df = df.iloc[:mid].reset_index(drop=True)
    test_start = max(0, mid - test_buffer)
    test_df = df.iloc[test_start:].reset_index(drop=True)
    test_warmup = min(test_buffer, len(test_df) - 10)

    train_trades, train_stats = _simulate(train_df, symbol, warmup=train_warmup, strategy=strategy)
    test_trades, test_stats = _simulate(test_df, symbol, warmup=test_warmup, strategy=strategy)

    return {
        "train": (train_trades, train_stats),
        "test": (test_trades, test_stats),
        "split_time": df.iloc[mid]["open_time"],
    }


def summarize_by_confluence(trades: list) -> dict:
    buckets = {"3.0 - 3.9 (mínimo)": [], "4.0 - 4.9": [], "5.0+": []}
    for t in trades:
        score = t.get("entry_score")
        if score is None:
            continue
        if score < 4:
            buckets["3.0 - 3.9 (mínimo)"].append(t)
        elif score < 5:
            buckets["4.0 - 4.9"].append(t)
        else:
            buckets["5.0+"].append(t)

    out = {}
    for label, ts in buckets.items():
        if not ts:
            continue
        wins = sum(1 for t in ts if t["pnl_pct"] > 0)
        out[label] = {
            "n_trades": len(ts),
            "win_rate": round(wins / len(ts) * 100, 1),
            "avg_pnl_pct": round(sum(t["pnl_pct"] for t in ts) / len(ts), 2),
        }
    return out


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

    trades_sorted = sorted(trades, key=lambda t: t["entry_time"])
    cum = np.cumsum([t["pnl_pct"] for t in trades_sorted])
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
