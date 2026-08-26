"""Panel de respaldo, restauración, historial, y desempeño real -- organizado
en pestañas internas (Desempeño / Respaldo / Cierres manuales / Historial)
para no forzar scroll por 4 secciones largas apiladas."""
import io
import csv
import streamlit as st

import config
import db
import performance
import post_close_review


def _render_performance_report():
    st.caption(
        "Medido en 'R' (múltiplos de lo que planeabas arriesgar), como hacen los traders "
        "profesionales -- permite comparar operaciones de distinto tamaño y símbolo en una "
        "sola escala. R = 1 significa 'gané/perdí justo lo que planeaba arriesgar'."
    )

    closed_ops = db.get_operation_history(200)
    open_ops = db.get_open_operations()
    report = performance.build_report(closed_ops, open_ops)

    if report["n_with_r_data"] == 0:
        st.info("Todavía no hay suficientes operaciones cerradas con datos completos para el reporte en R.")
    else:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Win rate", f"{report['win_rate_pct']}%")
        m2.metric("R promedio/operación", f"{report['avg_r']:+.2f}R")
        m3.metric("Ganancia prom.", f"{report['avg_win_r']:+.2f}R")
        m4.metric("Pérdida prom.", f"{report['avg_loss_r']:+.2f}R")
        st.caption(f"PnL total real acumulado: ${report['total_pnl_usd']:+.2f} · {report['n_with_r_data']} de {report['n_closed_total']} operaciones cerradas tenían datos completos para R.")

        if report.get("avg_mfe_r") is not None:
            st.markdown("**Diagnóstico MAE/MFE** (qué tan lejos llegó el precio a favor/en contra)")
            dc1, dc2, dc3 = st.columns(3)
            dc1.metric("MFE promedio", f"{report['avg_mfe_r']:.2f}R", help="Qué tan a favor llegó a estar el precio antes de cerrar, en promedio.")
            dc2.metric("MAE promedio", f"{report['avg_mae_r']:.2f}R", help="Qué tan en contra llegó a estar el precio antes de cerrar, en promedio.")
            if report.get("avg_capture_rate") is not None:
                dc3.metric("Tasa de captura", f"{report['avg_capture_rate']*100:.0f}%", help="Qué % del mejor movimiento posible (MFE) terminaste capturando realmente.")

            if report["avg_mfe_r"] > 0 and report["avg_capture_rate"] is not None and report["avg_capture_rate"] < 0.5:
                st.info("💡 Tu tasa de captura es baja -- el precio suele llegar más lejos a tu favor de lo que terminas ganando.")
            if report["avg_mae_r"] > 0.8:
                st.info("💡 El precio suele acercarse mucho a tu stop antes de recuperarse (MAE alto).")

        if report["equity_curve"]:
            with st.expander("Ver curva de equity (PnL acumulado en $)"):
                import plotly.graph_objects as go
                times = [p["time"] for p in report["equity_curve"]]
                cum = [p["cum_pnl_usd"] for p in report["equity_curve"]]
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=times, y=cum, mode="lines+markers", name="PnL acumulado ($)"))
                fig.add_hline(y=0, line_dash="dash", line_color="gray")
                fig.update_layout(height=250, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)

    if report["open_count"] > 0:
        st.markdown("**Exposición actual (operaciones abiertas)**")
        ec1, ec2 = st.columns(2)
        ec1.metric("Monto total invertido", f"${report['total_invested_open']:.2f}")
        ec2.metric("Riesgo total en juego", f"${report['total_risk_usd_open']:.2f}")
        if report["total_risk_usd_open"] > 0:
            st.caption(
                "Suma del riesgo planeado de TODAS tus operaciones abiertas a la vez. "
                "Si supera ~6-10% de tu capital total, estás arriesgando más de lo recomendado en conjunto."
            )


def _operations_to_csv() -> str:
    all_ops = db.get_open_operations() + db.get_operation_history(1000)
    if not all_ops:
        return ""
    cols = [
        "id", "symbol", "direction", "strategy", "status", "entry", "stop", "initial_stop",
        "tp", "opened_at", "closed_at", "outcome", "close_reason", "close_price", "pnl_pct",
        "investment_amount", "risk_pct_used", "capital_at_entry", "quantity",
        "mfe_price", "mae_price", "breakeven_applied",
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=cols, extrasaction="ignore")
    writer.writeheader()
    for op in all_ops:
        writer.writerow(op)
    return output.getvalue()


def render_backup_panel():
    tab1, tab2, tab3, tab4 = st.tabs(["📈 Desempeño", "💾 Respaldo", "🔍 Cierres manuales", "📜 Historial"])

    with tab1:
        _render_performance_report()

    with tab2:
        db_mode = "☁️ Turso (persistente en la nube)" if config.TURSO_DATABASE_URL else "💻 Local (puede perderse si Streamlit Cloud reinicia el contenedor)"
        st.caption(f"Modo de base de datos: **{db_mode}**")
        if not config.TURSO_DATABASE_URL:
            st.caption(
                "El disco de Streamlit Cloud puede reiniciarse. Descarga un respaldo de vez en cuando, "
                "o configura Turso (gratis) para que sea permanente."
            )
        st.download_button("Descargar respaldo (JSON)", db.export_backup(), file_name="crypto_dashboard_backup.json")
        csv_data = _operations_to_csv()
        if csv_data:
            st.download_button(
                "📄 Descargar operaciones (CSV, para Excel/Sheets)", csv_data,
                file_name="operaciones.csv", mime="text/csv",
            )
        uploaded = st.file_uploader("Restaurar desde respaldo", type="json", key="restore_upload")
        if uploaded and st.button("Restaurar"):
            db.import_backup(uploaded.read().decode("utf-8"))
            st.success("Respaldo restaurado.")
            st.rerun()

    with tab3:
        st.caption(
            "Para cada operación que cerraste tú mismo, simula qué habría pasado si la hubieras "
            "dejado correr -- para saber si tus cierres manuales están ayudando o quitándole ganancia al sistema."
        )
        if st.button("🔬 Analizar mis cierres manuales"):
            with st.spinner("Simulando qué hubiera pasado..."):
                closed_ops = db.get_operation_history(200)
                reviews = post_close_review.review_manual_closes(closed_ops)
            st.session_state["manual_review"] = reviews

        if "manual_review" in st.session_state:
            reviews = st.session_state["manual_review"]
            if not reviews:
                st.info("No hay operaciones cerradas manualmente para analizar todavía.")
            else:
                better, worse, same = 0, 0, 0
                for r in reviews:
                    actual = r["actual_pnl_pct"] or 0
                    sim = r["sim_pnl_pct"]
                    diff = actual - sim
                    if abs(diff) < 0.1:
                        same += 1
                        tag = "⚪ Similar"
                    elif diff > 0:
                        better += 1
                        tag = "✅ Cerrar manual fue MEJOR"
                    else:
                        worse += 1
                        tag = "🔴 Cerrar manual fue PEOR"

                    outcome_label = {"tp": "habría tocado TP", "stop": "habría tocado stop", "sigue_abierta": "seguiría abierta hoy"}[r["sim_outcome"]]
                    with st.container(border=True):
                        st.write(f"**{r['symbol']} {r['direction']}** -- {tag}")
                        st.caption(f"Real: {actual:+.2f}% · Si no la tocabas: {outcome_label} con {sim:+.2f}% ({r['sim_bars']} velas después)")

                st.caption(f"Resumen: {better} veces mejor cerrar manual, {worse} veces peor, {same} similar -- de {len(reviews)} operaciones analizadas.")

    with tab4:
        history = db.get_operation_history(15)
        if history:
            wins = sum(1 for h in history if h["pnl_pct"] and h["pnl_pct"] > 0)
            st.caption(f"{wins}/{len(history)} operaciones ganadoras (últimas {len(history)})")
            for h in history:
                is_win = h["pnl_pct"] and h["pnl_pct"] > 0
                color = "#16a34a" if is_win else "#dc2626"
                emoji = "🟢" if is_win else "🔴"
                reason = h.get("close_reason") or h["outcome"]
                with st.container(border=True):
                    st.markdown(f"<span style='color:{color}; font-weight:700;'>{emoji} {h['symbol']} {h['direction']}</span>", unsafe_allow_html=True)
                    st.caption(f"{reason} · {h['pnl_pct']:+.2f}%")
        else:
            st.caption("Todavía no hay operaciones cerradas en el historial.")
