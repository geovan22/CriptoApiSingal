"""Muestra las operaciones en seguimiento (con progreso, datos de la
calculadora guardados, y botón para finalizar manualmente) y el historial."""
import streamlit as st

import db
from price_format import format_price
from signal_service import get_data_and_signal


def render_operations_panel(open_ops: list):
    if open_ops:
        st.divider()
        st.subheader(f"📍 Operaciones en seguimiento ({len(open_ops)})")
        for op in open_ops:
            with st.container(border=True):
                try:
                    _, op_result = get_data_and_signal(op["symbol"])
                    live = op_result["live_price"]
                    if op["direction"] == "COMPRA":
                        progress = (live - op["entry"]) / (op["tp"] - op["entry"]) if op["tp"] != op["entry"] else 0
                    else:
                        progress = (op["entry"] - live) / (op["entry"] - op["tp"]) if op["entry"] != op["tp"] else 0
                    progress = max(0, min(1, progress))
                    breakeven_tag = " 🔒 break-even activo" if op.get("breakeven_applied") else ""

                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.write(f"**{op['symbol']} {op['direction']}**{breakeven_tag} · entrada ${format_price(op['entry'])} · precio actual ${format_price(live)}")
                        if op.get("investment_amount"):
                            st.caption(
                                f"Monto invertido: ${op['investment_amount']:.2f} · "
                                f"Riesgo usado: {op.get('risk_pct_used', '—')}% · "
                                f"Capital al entrar: ${op.get('capital_at_entry', '—')} · "
                                f"Cantidad: {op.get('quantity', 0):.6f}"
                            )
                        st.progress(progress, text=f"{progress*100:.0f}% hacia el take profit")
                    with c2:
                        st.write("")
                        if st.button("🏁 Finalizar", key=f"finish_{op['id']}"):
                            db.close_operation(op["id"], live, "manual", close_reason="manual")
                            st.success(f"{op['symbol']} finalizada manualmente en ${format_price(live)}.")
                            st.rerun()
                except Exception:
                    st.write(f"{op['symbol']} {op['direction']} (no se pudo actualizar precio)")

    history = db.get_operation_history(15)
    if history:
        with st.expander(f"📜 Historial ({len(history)} operaciones cerradas recientes)"):
            wins = sum(1 for h in history if h["pnl_pct"] and h["pnl_pct"] > 0)
            st.caption(f"{wins}/{len(history)} operaciones ganadoras en este historial")
            for h in history:
                emoji = "🟢" if h["pnl_pct"] and h["pnl_pct"] > 0 else "🔴"
                reason = h.get("close_reason") or h["outcome"]
                st.write(f"{emoji} {h['symbol']} {h['direction']} · {reason} · {h['pnl_pct']:+.2f}%")
