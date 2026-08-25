"""
Inicialización del estado de sesión, la base de datos, y el intervalo
de refresco automático (dinámico según si hay operaciones abiertas,
y pausable manualmente).
"""
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import config
import db


def init_session_state():
    if "symbol" not in st.session_state:
        st.session_state.symbol = db.get_state("last_symbol", config.DEFAULT_SYMBOL)
    if "notifications_enabled" not in st.session_state:
        st.session_state.notifications_enabled = True
    if "telegram_offset" not in st.session_state:
        st.session_state.telegram_offset = 0
    if "last_alert" not in st.session_state:
        st.session_state.last_alert = None
    if "scan_mode" not in st.session_state:
        st.session_state.scan_mode = False
    if "refresh_paused" not in st.session_state:
        st.session_state.refresh_paused = False


def set_symbol(new_symbol: str):
    st.session_state.symbol = new_symbol
    db.set_state("last_symbol", new_symbol)


def setup_autorefresh() -> tuple[int, int]:
    """
    Configura el auto-refresco dinámico. Devuelve (refresh_ms, open_ops_count)
    para que la UI pueda mostrar el estado actual.

    - Si hay operaciones en seguimiento: cada 20s (para detectar TP/stop rápido)
    - Si no: cada REFRESH_SECONDS (60s por defecto)
    - Se puede pausar manualmente (ej. mientras se corre un backtest largo,
      para que el refresco no interrumpa el cálculo a la mitad).
    """
    open_ops_count = len(db.get_open_operations())
    if st.session_state.refresh_paused:
        refresh_ms = 3_600_000  # efectivamente pausado (1h)
    else:
        refresh_ms = 20_000 if open_ops_count > 0 else config.REFRESH_SECONDS * 1000
    st_autorefresh(interval=refresh_ms, key="refresh")
    return refresh_ms, open_ops_count
