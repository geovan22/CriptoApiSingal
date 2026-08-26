"""Muestra las operaciones en seguimiento (con progreso, datos de la
calculadora guardados, y botón para finalizar manualmente) y el historial."""
import streamlit as st

import db
from price_format import format_price
from signal_service import get_data_and_signal

CLOSE_REASON_LABELS = {
    "tp": "🎯 Take Profit",
    "stop": "🛑 Stop Loss",
    "manual": "✋ Manual",
    "manual_tras_alerta": "✋⚠️ Manual (tras alerta de reversión)",
}


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

                    is_buy = op["direction"] == "COMPRA"
                    color = "#16a34a" if is_buy else "#dc2626"
                    emoji = "🟢" if is_buy else "🔴"
                    badges = []
                    if op.get("breakeven_applied"):
                        badges.append("🔒 Break-even")
                    if op.get("early_warning_sent"):
                        badges.append("⚠️ Alerta de reversión activa")
                    if op.get("strategy") == "mean_reversion":
                        badges.append("🔄 Reversión a la media")
                    badges_str = (" · " + " · ".join(badges)) if badges else ""
                    st.markdown(
                        f"<span style='color:{color}; font-weight:700; font-size:1.1em;'>"
                        f"{emoji} {op['symbol']} {op['direction']}</span>{badges_str}",
                        unsafe_allow_html=True,
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Entrada", format_price(op["entry"]))
                    m2.metric("Stop", format_price(op["stop"]))
                    m3.metric("Take Profit", format_price(op["tp"]))
                    m4.metric("Precio actual", format_price(live))

                    if op.get("investment_amount"):
                        st.caption(
                            f"Monto invertido: ${op['investment_amount']:.2f} · "
                            f"Riesgo usado: {op.get('risk_pct_used', '—')}% · "
                            f"Capital al entrar: ${op.get('capital_at_entry', '—')} · "
                            f"Cantidad: {op.get('quantity', 0):.6f}"
                        )
                    st.progress(progress, text=f"{progress*100:.0f}% hacia el take profit")

                    if st.button("🏁 Finalizar", key=f"finish_{op['id']}"):
                        reason = "manual_tras_alerta" if op.get("early_warning_sent") else "manual"
                        db.close_operation(op["id"], live, "manual", close_reason=reason)
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
                reason_label = CLOSE_REASON_LABELS.get(h.get("close_reason") or h["outcome"], h.get("close_reason") or h["outcome"])
                st.write(f"{emoji} {h['symbol']} {h['direction']} · {reason_label} · {h['pnl_pct']:+.2f}%")
