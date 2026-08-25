"""Muestra las operaciones en seguimiento (con progreso)."""
import streamlit as st

import db
from price_format import format_price
from signal_service import get_data_and_signal


def render_operations_panel(open_ops: list):
    if open_ops:
        st.divider()
        st.subheader("📍 Operaciones en seguimiento")
        for op in open_ops:
            try:
                _, op_result = get_data_and_signal(op["symbol"])
                live = op_result["live_price"]
                if op["direction"] == "COMPRA":
                    progress = (live - op["entry"]) / (op["tp"] - op["entry"]) if op["tp"] != op["entry"] else 0
                else:
                    progress = (op["entry"] - live) / (op["entry"] - op["tp"]) if op["entry"] != op["tp"] else 0
                progress = max(0, min(1, progress))
                breakeven_tag = " 🔒 break-even activo" if op.get("breakeven_applied") else ""
                st.write(f"**{op['symbol']} {op['direction']}**{breakeven_tag} · entrada ${format_price(op['entry'])} · precio actual ${format_price(live)}")
                st.progress(progress, text=f"{progress*100:.0f}% hacia el take profit")
            except Exception:
                st.write(f"{op['symbol']} {op['direction']} (no se pudo actualizar precio)")
