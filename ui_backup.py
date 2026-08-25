"""Panel de respaldo, restauración e historial (vive dentro de una pestaña)."""
import streamlit as st

import config
import db


def render_backup_panel():
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
            st.write(f"{emoji} {h['symbol']} {h['direction']} · {h['outcome']} · {h['pnl_pct']:+.2f}%")
    else:
        st.caption("Todavía no hay operaciones cerradas en el historial.")
