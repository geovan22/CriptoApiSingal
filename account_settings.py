"""
Configuración de cuenta persistida: capital inicial (para calcular el
saldo real acumulado), y modo de cálculo de la calculadora -- por % de
riesgo (por defecto) o por apalancamiento fijo (tú eliges el apalancamiento
y el monto se calcula directo, en vez de partir de la distancia del stop).
"""
import db


def get_settings():
    initial_capital = float(db.get_state("initial_capital", "50"))
    calc_mode = db.get_state("calc_mode", "risk_pct")  # "risk_pct" | "leverage"
    default_leverage = float(db.get_state("default_leverage", "2.0"))
    return initial_capital, calc_mode, default_leverage


def set_settings(initial_capital: float, calc_mode: str, default_leverage: float):
    db.set_state("initial_capital", str(initial_capital))
    db.set_state("calc_mode", calc_mode)
    db.set_state("default_leverage", str(default_leverage))
