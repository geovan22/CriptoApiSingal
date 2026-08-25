"""Panel de favoritos y modo escaneo (vive dentro de una pestaña, sin expander propio)."""
import streamlit as st
import db


def render_favorites_panel():
    favorites = db.get_favorites()
    st.write("Favoritos actuales:", ", ".join(favorites) if favorites else "(ninguno)")

    fcol1, fcol2 = st.columns([2, 1])
    with fcol1:
        new_fav = st.text_input("Agregar par (ej. ETHUSDT)", key="new_fav_input")
    with fcol2:
        st.write("")
        st.write("")
        if st.button("Agregar a favoritos") and new_fav:
            sym = new_fav.upper().strip()
            sym = sym if sym.endswith("USDT") else f"{sym}USDT"
            db.add_favorite(sym)
            st.rerun()

    if favorites:
        rm_choice = st.selectbox("Quitar de favoritos", ["(elegir)"] + favorites, key="rm_fav_select")
        if rm_choice != "(elegir)" and st.button("Quitar"):
            db.remove_favorite(rm_choice)
            st.rerun()

    st.session_state.scan_mode = st.checkbox(
        "🔍 Modo escaneo: buscar señal automáticamente solo en favoritos",
        value=st.session_state.scan_mode,
    )
    if st.session_state.scan_mode:
        st.caption(
            "Revisa tus favoritos en cada refresco y cambia automáticamente al primero que tenga "
            "una señal confirmada. Sigue buscando mientras esta pestaña esté abierta."
        )
