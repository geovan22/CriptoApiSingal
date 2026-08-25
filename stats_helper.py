"""
Herramienta de interpretación estadística para los resultados del backtest.

La pregunta que responde: "¿este número (win rate, expectativa) es una
ventaja real, o podría ser pura casualidad con esta cantidad de datos?"

Referencias (prácticas estándar en validación de sistemas de trading):
- Mínimo ~30 operaciones para empezar a aplicar estadística con sentido
  (teorema del límite central). 100+ para conclusiones confiables.
- Intervalo de confianza de Wilson para el win rate: más preciso que la
  aproximación normal simple cuando hay pocas operaciones.
- "Win rate de equilibrio": el % de aciertos mínimo necesario para no
  perder dinero, dado el tamaño promedio de tus ganancias vs pérdidas.
  Si tu intervalo de confianza del win rate real INCLUYE ese número, no
  se puede afirmar con confianza que el sistema sea rentable ni que no
  lo sea -- hacen falta más datos.
"""
import math


def wilson_interval(wins: int, n: int, confidence: float = 0.95):
    """Intervalo de confianza de Wilson para una proporción (win rate)."""
    if n <= 0:
        return 0.0, 0.0
    z = 1.96 if confidence == 0.95 else 2.576  # 95% o 99%
    phat = wins / n
    denom = 1 + z ** 2 / n
    center = phat + z ** 2 / (2 * n)
    margin = z * math.sqrt((phat * (1 - phat) + z ** 2 / (4 * n)) / n)
    low = (center - margin) / denom
    high = (center + margin) / denom
    return max(0.0, low), min(1.0, high)


def breakeven_win_rate(avg_win_pct: float, avg_loss_pct: float):
    """
    % de aciertos mínimo necesario para no perder dinero, dado el tamaño
    promedio de ganancia vs pérdida. Ej.: si ganas en promedio 2% y
    pierdes en promedio 1%, necesitas acertar al menos 33% de las veces
    para no perder (no 50%, porque tus ganancias son más grandes).
    """
    aw = abs(avg_win_pct)
    al = abs(avg_loss_pct)
    if aw + al == 0:
        return None
    return al / (aw + al)


def required_n_for_margin(p: float = 0.5, margin: float = 0.10, confidence: float = 0.95):
    """Cuántas operaciones hacen falta para que el margen de error sea +-margin."""
    z = 1.96 if confidence == 0.95 else 2.576
    p = min(max(p, 0.01), 0.99)
    return math.ceil((z ** 2 * p * (1 - p)) / (margin ** 2))


def interpret_backtest(stats: dict) -> dict:
    """
    Devuelve un diagnóstico completo a partir de las stats que ya produce
    backtest.summarize_trades(): intervalo de confianza del win rate real,
    win rate de equilibrio, si el resultado es estadísticamente distinguible
    de "no tiene ventaja", y cuántas operaciones harían falta para saberlo
    con más certeza.
    """
    n = stats.get("n_trades", 0)
    if n == 0:
        return {"n_trades": 0, "enough_for_inference": False}

    win_rate_pct = stats["win_rate"]
    wins = round(win_rate_pct / 100 * n)
    ci_low, ci_high = wilson_interval(wins, n)

    be = breakeven_win_rate(stats.get("avg_win_pct", 0), stats.get("avg_loss_pct", 0))
    be_inside_ci = be is not None and ci_low <= be <= ci_high

    if be is not None:
        if ci_low > be:
            verdict = "por_encima_equilibrio"  # todo el intervalo por encima del breakeven -> señal alentadora
        elif ci_high < be:
            verdict = "por_debajo_equilibrio"  # todo el intervalo por debajo -> señal preocupante
        else:
            verdict = "indeterminado"  # el intervalo cruza el breakeven -> no se puede afirmar nada todavía
    else:
        verdict = "sin_datos"

    required_n = required_n_for_margin(p=win_rate_pct / 100, margin=0.10)

    return {
        "n_trades": n,
        "enough_for_inference": n >= 30,
        "win_rate_pct": win_rate_pct,
        "win_rate_ci_low": round(ci_low * 100, 1),
        "win_rate_ci_high": round(ci_high * 100, 1),
        "breakeven_win_rate_pct": round(be * 100, 1) if be is not None else None,
        "be_inside_ci": be_inside_ci,
        "verdict": verdict,
        "required_n_for_10pct_margin": required_n,
    }
