"""
Panel de favoritos -- watchlist pasiva. Muestra SOLO las señales
confirmadas (sin advertencias, sin "en formación", sin filtradas) de cada
favorito. No cambia el símbolo en seguimiento ni navega solo -- el usuario
decide manualmente cuál revisar a fondo con el botón "Ver detalle".
"""
import streamlit as st
import db
from app_state import set_symbol


def _render_watchlist(confirmed_list: list):
    if not confirmed_list:
        st.info("Ningún favorito tiene una señal confirmada en este momento. Esta lista solo muestra COMPRA/VENTA limpias -- sin advertencias, sin filtradas, sin en formación.")
        return

    for item in confirmed_list:
        symbol, signal, result = item["symbol"], item["signal"], item["result"]
        is_buy = signal == "COMPRA"
        color = "#16a34a" if is_buy else "#dc2626"
        emoji = "🟢" if is_buy else "🔴"

        with st.container(border=True):
            c1, c2, c3 = st.columns([2, 2, 1])
            with c1:
                st.markdown(f"**{symbol}**")
                st.caption(f"Precio: ${result['price']:.6g}")
            with c2:
                st.markdown(f"<span style='color:{color}; font-weight:600; font-size:1.05em;'>{emoji} {signal}</span>", unsafe_allow_html=True)
                st.caption(f"R:B 1:{result.get('rr_ratio', '—')}")
            with c3:
                if st.button("Ver detalle", key=f"ver_{symbol}"):
                    set_symbol(symbol)
                    st.session_state["_jump_to_signal_tab"] = True
                    st.rerun()


def render_favorites_panel(confirmed_list: list):
    st.markdown("#### ⭐ Watchlist -- solo señales confirmadas")
    st.caption(
        "Se revisan todos tus favoritos automáticamente. Solo aparecen aquí los que tienen "
        "COMPRA o VENTA ✅ confirmada, sin advertencias -- nada en formación, nada filtrado por "
        "ADX o riesgo/beneficio. Tú decides cuál revisar a fondo, nada cambia solo."
    )
    _render_watchlist(confirmed_list)

    st.divider()
    with st.expander("⚙️ Administrar favoritos y notificaciones"):
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

        st.session_state.notify_favorites = st.checkbox(
            "🔔 Avisar por Telegram cuando un favorito tenga una señal confirmada nueva",
            value=st.session_state.get("notify_favorites", False),
            help="Solo notifica -- nunca cambia el símbolo en seguimiento ni navega por ti.",
        )
