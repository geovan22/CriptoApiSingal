"""Panel de respaldo, restauración, historial, y desempeño real (vive dentro de una pestaña)."""
import streamlit as st

import config
import db
import performance


def _render_performance_report():
    st.markdown("### 📈 Desempeño real (dinero de verdad, no backtest)")
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
                st.info("💡 Tu tasa de captura es baja -- el precio suele llegar más lejos a tu favor de lo que terminas ganando. Podría valer la pena un take profit más ambicioso o un trailing stop, una vez tengas más operaciones para confirmarlo.")
            if report["avg_mae_r"] > 0.8:
                st.info("💡 El precio suele acercarse mucho a tu stop antes de recuperarse (MAE alto) -- si esto se repite con más datos, podría indicar que el stop está algo apretado para la volatilidad real.")

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
                "Suma del riesgo planeado (capital × % de riesgo) de TODAS tus operaciones abiertas a la vez. "
                "Si esta suma supera ~6-10% de tu capital total, estás arriesgando más de lo recomendado en conjunto, "
                "aunque cada operación individual se vea conservadora."
            )


def render_backup_panel():
    _render_performance_report()

    st.divider()
    db_mode = "☁️ Turso (persistente en la nube)" if config.TURSO_DATABASE_URL else "💻 Local (puede perderse si Streamlit Cloud reinicia el contenedor)"
    st.caption(f"Modo de base de datos: **{db_mode}**")
    if not config.TURSO_DATABASE_URL:
        st.caption(
            "El disco de Streamlit Cloud puede reiniciarse. Descarga un respaldo de vez en cuando "
            "para no perder tus favoritos ni tu historial de operaciones, o configura Turso "
            "(gratis) para que sea permanente -- ver instrucciones al inicio de db.py."
        )
    st.download_button("Descargar respaldo (JSON)", db.export_backup(), file_name="crypto_dashboard_backup.json")
    uploaded = st.file_uploader("Restaurar desde respaldo", type="json", key="restore_upload")
    if uploaded and st.button("Restaurar"):
        db.import_backup(uploaded.read().decode("utf-8"))
        st.success("Respaldo restaurado.")
        st.rerun()

    st.divider()
    history = db.get_operation_history(15)
    if history:
        wins = sum(1 for h in history if h["pnl_pct"] and h["pnl_pct"] > 0)
        st.write(f"**Historial** -- {wins}/{len(history)} operaciones ganadoras (últimas {len(history)})")
        for h in history:
            emoji = "🟢" if h["pnl_pct"] and h["pnl_pct"] > 0 else "🔴"
            reason = h.get("close_reason") or h["outcome"]
            st.write(f"{emoji} {h['symbol']} {h['direction']} · {reason} · {h['pnl_pct']:+.2f}%")
    else:
        st.caption("Todavía no hay operaciones cerradas en el historial.")
