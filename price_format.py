"""
Formato de precios con precisión dinámica.

Un formato fijo de 2 decimales funciona para BTC ($78,758.00) pero borra
toda la información útil en criptos baratas: 0.1152 y 0.1201 redondean
ambos a "0.12" con 2 decimales, haciendo que entrada/stop/TP se vean
idénticos aunque no lo sean. Aquí se ajustan los decimales según la
magnitud del precio.
"""


def price_decimals(price: float) -> int:
    price = abs(price)
    if price >= 100:
        return 2
    elif price >= 1:
        return 4
    elif price >= 0.01:
        return 5
    elif price >= 0.0001:
        return 6
    else:
        return 8


def format_price(price: float, with_commas: bool = True) -> str:
    if price is None:
        return "-"
    d = price_decimals(price)
    if with_commas:
        return f"{price:,.{d}f}"
    return f"{price:.{d}f}"
