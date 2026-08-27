"""Muestra las operaciones en seguimiento (ordenadas por cercanía al TP,
con progreso, datos de la calculadora, y botón para finalizar) y el
historial (con tarjetas y filtro por estrategia)."""
import pandas as pd
import streamlit as st

import config
import db
from price_format import format_price
from signal_service import get_data_and_signal

CLOSE_REASON_LABELS = {
    "tp": "🎯 Take Profit",
    "stop": "🛑 Stop Loss",
    "manual": "✋ Manual",
    "manual_tras_alerta": "✋⚠️ Manual (tras alerta de reversión)",
}

STRATEGY_LABELS = {
    "trend": "📈 Tendencia",
    "mean_reversion": "🔄 Reversión a la media",
}


def _next_candle_close(interval_hours: float = None) -> pd.Timestamp:
    if interval_hours is None:
        interval_hours = config.get_interval_hours()
    now = pd.Timestamp.now(tz="UTC")
    boundary_hour = ((now.hour // interval_hours) + 1) * interval_hours
    if boundary_hour >= 24:
        return now.normalize() + pd.Timedelta(days=1)
    return now.normalize() + pd.Timedelta(hours=boundary_hour)


def _format_timedelta(td: pd.Timedelta) -> str:
    total_min = int(td.total_seconds() // 60)
    h, m = divmod(total_min, 60)
    return f"{h}h {m}min" if h else f"{m}min"


def _compute_progress(op: dict, live: float) -> float:
    if op["direction"] == "COMPRA":
        progress = (live - op["entry"]) / (op["tp"] - op["entry"]) if op["tp"] != op["entry"] else 0
    else:
        progress = (op["entry"] - live) / (op["entry"] - op["tp"]) if op["entry"] != op["tp"] else 0
    return max(0, min(1, progress))


def render_operations_panel(open_ops: list):
    if open_ops:
        st.divider()
        st.subheader(f"📍 Operaciones en seguimiento ({len(open_ops)})")
        remaining = _next_candle_close() - pd.Timestamp.now(tz="UTC")
        st.caption(f"⏱️ Próxima vela cierra en {_format_timedelta(remaining)} -- el análisis solo cambia al cerrar una vela.")

        enriched = []
        for op in open_ops:
            try:
                _, op_result = get_data_and_signal(op["symbol"])
                live = op_result["live_price"]
                progress = _compute_progress(op, live)
                enriched.append((op, live, progress))
            except Exception:
                enriched.append((op, None, -1))
        enriched.sort(key=lambda t: t[2], reverse=True)

        for op, live, progress in enriched:
            with st.container(border=True):
                if live is None:
                    st.write(f"{op['symbol']} {op['direction']} (no se pudo actualizar precio)")
                    continue

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
                    leverage = (op["investment_amount"] / op["capital_at_entry"]) if op.get("capital_at_entry") else None
                    leverage_str = f" · Apalancamiento: {leverage:.1f}x" if leverage else ""
                    st.caption(
                        f"Monto invertido: ${op['investment_amount']:.2f} · "
                        f"Riesgo usado: {op.get('risk_pct_used', '—')}% · "
                        f"Capital al entrar: ${op.get('capital_at_entry', '—')} · "
                        f"Cantidad: {op.get('quantity', 0):.6f}{leverage_str}"
                    )
                st.progress(progress, text=f"{progress*100:.0f}% hacia el take profit")

                with st.expander("✏️ Editar monto/riesgo (corrige el registro para análisis)"):
                    ec1, ec2, ec3 = st.columns(3)
                    with ec1:
                        edit_capital = st.number_input(
                            "Capital ($)", min_value=1.0,
                            value=float(op.get("capital_at_entry") or 50.0), step=10.0, key=f"edit_cap_{op['id']}",
                        )
                    with ec2:
                        edit_risk = st.number_input(
                            "Riesgo (%)", min_value=0.1, max_value=100.0,
                            value=float(op.get("risk_pct_used") or 2.0), step=0.5, key=f"edit_risk_{op['id']}",
                        )
                    with ec3:
                        edit_investment = st.number_input(
                            "Monto invertido ($)", min_value=1.0,
                            value=float(op.get("investment_amount") or 50.0), step=10.0, key=f"edit_inv_{op['id']}",
                        )
                    if st.button("💾 Guardar cambios", key=f"save_edit_{op['id']}"):
                        new_qty = edit_investment / op["entry"]
                        db.update_operation_investment(op["id"], edit_investment, edit_risk, edit_capital, new_qty)
                        st.success("Datos actualizados.")
                        st.rerun()

                if st.button("🏁 Finalizar", key=f"finish_{op['id']}"):
                    reason = "manual_tras_alerta" if op.get("early_warning_sent") else "manual"
                    db.close_operation(op["id"], live, "manual", close_reason=reason)
                    st.success(f"{op['symbol']} finalizada manualmente en ${format_price(live)}.")
                    st.rerun()

    history = db.get_operation_history(50)
    if history:
        with st.expander(f"📜 Historial ({len(history)} operaciones cerradas recientes)"):
            strategies_present = sorted({h.get("strategy", "trend") for h in history})
            filter_options = ["Todas"] + [STRATEGY_LABELS.get(s, s) for s in strategies_present]
            chosen_filter = st.selectbox("Filtrar por estrategia", filter_options, key="history_strategy_filter")

            filtered = history
            if chosen_filter != "Todas":
                target_strategy = next((s for s in strategies_present if STRATEGY_LABELS.get(s, s) == chosen_filter), None)
                filtered = [h for h in history if h.get("strategy", "trend") == target_strategy]

            wins = sum(1 for h in filtered if h["pnl_pct"] and h["pnl_pct"] > 0)
            st.caption(f"{wins}/{len(filtered)} operaciones ganadoras" + (f" (de {len(history)} en total)" if chosen_filter != "Todas" else ""))

            for h in filtered[:15]:
                is_win = h["pnl_pct"] and h["pnl_pct"] > 0
                color = "#16a34a" if is_win else "#dc2626"
                emoji = "🟢" if is_win else "🔴"
                reason_label = CLOSE_REASON_LABELS.get(h.get("close_reason") or h["outcome"], h.get("close_reason") or h["outcome"])
                strategy_label = STRATEGY_LABELS.get(h.get("strategy", "trend"), h.get("strategy", "trend"))
                with st.container(border=True):
                    st.markdown(
                        f"<span style='color:{color}; font-weight:700;'>{emoji} {h['symbol']} {h['direction']}</span> "
                        f"· {strategy_label}",
                        unsafe_allow_html=True,
                    )
                    st.caption(f"{reason_label} · {h['pnl_pct']:+.2f}%")
