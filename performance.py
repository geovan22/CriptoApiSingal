"""
Reporte de desempeño con DINERO REAL (no backtest) -- usa las operaciones
que de verdad aceptaste y cerraste, con los datos que la calculadora ya
guarda (monto, riesgo%, cantidad, MAE/MFE).

Metodología: medir en "R" (múltiplos del riesgo original), no en dólares
ni en %. Es la práctica estándar profesional -- permite comparar
operaciones de distinto tamaño y distinto símbolo en una sola escala.
R = 1 significa "gané/perdí exactamente lo que planeaba arriesgar".

MAE (Maximum Adverse Excursion) / MFE (Maximum Favorable Excursion):
qué tan en contra y a favor llegó a moverse el precio durante la
operación. Diagnostican si el stop es muy ancho/estrecho y si el TP
se queda corto o si sales demasiado pronto (Sweeney, 1996).
"""


def _risk_distance(op: dict):
    """Distancia de precio que se planeaba arriesgar (entry vs stop inicial)."""
    initial_stop = op.get("initial_stop") or op.get("stop")
    if initial_stop is None:
        return None
    dist = abs(op["entry"] - initial_stop)
    return dist if dist > 0 else None


def compute_trade_metrics(op: dict) -> dict:
    """
    Calcula R-multiple final, MFE en R, MAE en R, y tasa de captura para
    UNA operación (abierta o cerrada). Si falta información (operaciones
    viejas creadas antes de este sistema, o datos raros), devuelve None
    en lo que no se pueda calcular -- nunca revienta el reporte completo.
    """
    empty = {"r_final": None, "mfe_r": None, "mae_r": None, "capture_rate": None, "pnl_usd": None}
    try:
        risk_dist = _risk_distance(op)
        direction = op.get("direction")
        entry = op.get("entry")
        if entry is None or direction not in ("COMPRA", "VENTA"):
            return empty

        close_price = op.get("close_price")
        live_price = op.get("_live_price")
        ref_price = close_price if close_price is not None else live_price

        r_final = None
        if risk_dist and ref_price is not None:
            price_move = (ref_price - entry) if direction == "COMPRA" else (entry - ref_price)
            r_final = price_move / risk_dist

        mfe_r = mae_r = capture_rate = None
        if risk_dist:
            mfe_price = op.get("mfe_price")
            mae_price = op.get("mae_price")
            if mfe_price is not None:
                mfe_move = (mfe_price - entry) if direction == "COMPRA" else (entry - mfe_price)
                mfe_r = max(0.0, mfe_move / risk_dist)
            if mae_price is not None:
                mae_move = (entry - mae_price) if direction == "COMPRA" else (mae_price - entry)
                mae_r = max(0.0, mae_move / risk_dist)
            if mfe_r and mfe_r > 0 and r_final is not None:
                capture_rate = r_final / mfe_r

        pnl_usd = None
        if op.get("quantity") and ref_price is not None:
            qty = op["quantity"]
            pnl_usd = qty * (ref_price - entry) if direction == "COMPRA" else qty * (entry - ref_price)

        return {
            "r_final": round(r_final, 2) if r_final is not None else None,
            "mfe_r": round(mfe_r, 2) if mfe_r is not None else None,
            "mae_r": round(mae_r, 2) if mae_r is not None else None,
            "capture_rate": round(capture_rate, 2) if capture_rate is not None else None,
            "pnl_usd": round(pnl_usd, 2) if pnl_usd is not None else None,
        }
    except Exception:
        return empty


def build_report(closed_ops: list, open_ops: list) -> dict:
    """
    Reporte completo de desempeño real: métricas en R sobre las cerradas,
    diagnóstico de MAE/MFE promedio, curva de equity en $, y exposición
    de riesgo actual sobre las abiertas.
    """
    closed_with_r = []
    for op in closed_ops:
        m = compute_trade_metrics(op)
        if m["r_final"] is not None:
            closed_with_r.append({**op, **m})

    n = len(closed_with_r)
    report = {
        "n_with_r_data": n,
        "n_closed_total": len(closed_ops),
    }

    if n > 0:
        wins = [t for t in closed_with_r if t["r_final"] > 0]
        losses = [t for t in closed_with_r if t["r_final"] <= 0]
        report["win_rate_pct"] = round(len(wins) / n * 100, 1)
        report["avg_r"] = round(sum(t["r_final"] for t in closed_with_r) / n, 2)
        report["avg_win_r"] = round(sum(t["r_final"] for t in wins) / len(wins), 2) if wins else 0.0
        report["avg_loss_r"] = round(sum(t["r_final"] for t in losses) / len(losses), 2) if losses else 0.0
        report["total_pnl_usd"] = round(sum(t["pnl_usd"] for t in closed_with_r if t["pnl_usd"] is not None), 2)

        mfe_vals = [t["mfe_r"] for t in closed_with_r if t["mfe_r"] is not None]
        mae_vals = [t["mae_r"] for t in closed_with_r if t["mae_r"] is not None]
        capture_vals = [t["capture_rate"] for t in closed_with_r if t["capture_rate"] is not None]
        report["avg_mfe_r"] = round(sum(mfe_vals) / len(mfe_vals), 2) if mfe_vals else None
        report["avg_mae_r"] = round(sum(mae_vals) / len(mae_vals), 2) if mae_vals else None
        report["avg_capture_rate"] = round(sum(capture_vals) / len(capture_vals), 2) if capture_vals else None

        dated = sorted(
            [t for t in closed_with_r if t["pnl_usd"] is not None],
            key=lambda t: t.get("closed_at") or "",
        )
        cum = 0.0
        equity_curve = []
        for t in dated:
            cum += t["pnl_usd"]
            equity_curve.append({"time": t.get("closed_at"), "cum_pnl_usd": round(cum, 2)})
        report["equity_curve"] = equity_curve
    else:
        report["equity_curve"] = []

    total_invested = sum(o.get("investment_amount") or 0 for o in open_ops)
    total_risk_usd = sum(
        (o.get("capital_at_entry") or 0) * (o.get("risk_pct_used") or 0) / 100 for o in open_ops
    )
    report["open_count"] = len(open_ops)
    report["total_invested_open"] = round(total_invested, 2)
    report["total_risk_usd_open"] = round(total_risk_usd, 2)

    return report
