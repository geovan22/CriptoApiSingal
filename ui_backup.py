"""Panel de respaldo y restauración de datos (favoritos, historial, estado)."""
import streamlit as st

import config
import db


def render_backup_panel():
    with st.expander("💾 Respaldo de datos (favoritos, historial, estado)"):
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
