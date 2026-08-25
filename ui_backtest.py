"""Panel de backtest -- prueba el sistema con datos históricos, con resultados persistidos en DB."""
import json
import pandas as pd
import streamlit as st

import config
import db
import backtest
from price_format import format_price


def _save_result_to_db(bt_symbol, trades, stats):
    serializable_trades = [
        {**t, "entry_time": t["entry_time"].isoformat(), "exit_time": t["exit_time"].isoformat()}
        for t in trades
    ]
    db.set_state("bt_result", json.dumps({"symbol": bt_symbol, "trades": serializable_trades, "stats": stats}))


def _load_result_from_db():
    saved = db.get_state("bt_result")
    if not saved:
        return None
    try:
        data = json.loads(saved)
        restored_trades = [
            {**t, "entry_time": pd.Timestamp(t["entry_time"]), "exit_time": pd.Timestamp(t["exit_time"])}
            for t in data["trades"]
        ]
        return data["symbol"], restored_trades, data["stats"]
    except Exception:
        return None


def render_backtest_panel():
    with st.expander("🧪 Backtest (probar el sistema con datos históricos)"):
        st.caption(
            "Corre la lógica exacta de señales sobre velas pasadas, sin trampas -- cada decisión "
            "usa solo datos disponibles hasta ese momento. Sirve para ver si el sistema tiene "
            "ventaja estadística real antes de confiar en él con dinero en vivo."
        )
        st.session_state.refresh_paused = st.checkbox(
            "⏸️ Pausar refresco automático mientras uso esta sección",
            value=st.session_state.refresh_paused,
            help="Si tienes operaciones en seguimiento, el refresco cada 20s puede interrumpir un "
                 "backtest a la mitad antes de que termine. Actívalo antes de correr uno largo.",
        )
        bt_col1, bt_col2, bt_col3 = st.columns([1.5, 1, 1])
        with bt_col1:
            bt_symbol = st.selectbox("Símbolo a probar", config.AVAILABLE_SYMBOLS, key="bt_symbol")
        with bt_col2:
            bt_limit = st.slider("Velas históricas", 300, 1000, 700, step=50, key="bt_limit")
        with bt_col3:
            st.write("")
            st.write("")
            run_bt = st.button("▶️ Correr backtest")

        if run_bt:
            try:
                with st.spinner(f"Simulando {bt_limit} velas de {bt_symbol}..."):
                    trades, stats = backtest.run_backtest(bt_symbol, config.INTERVAL, limit=bt_limit)
                st.session_state["bt_result"] = (bt_symbol, trades, stats)
                _save_result_to_db(bt_symbol, trades, stats)
            except Exception as e:
                st.error(f"No se pudo correr el backtest: {e}")

        if "bt_result" not in st.session_state:
            restored = _load_result_from_db()
            if restored:
                st.session_state["bt_result"] = restored

        if "bt_result" in st.session_state:
            bt_sym, bt_trades, bt_stats = st.session_state["bt_result"]
            if bt_stats.get("n_trades", 0) == 0:
                st.warning(f"El sistema no generó ninguna operación confirmada para {bt_sym} en ese rango.")
            else:
                st.write(f"**Resultados para {bt_sym}** ({bt_stats['candles_used']} velas, "
                          f"{bt_stats['n_trades']} operaciones: {bt_stats['compra_count']} compras, "
                          f"{bt_stats['venta_count']} ventas)")
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Win rate", f"{bt_stats['win_rate']}%")
                m2.metric("Expectativa/operación", f"{bt_stats['expectancy_pct']:+.2f}%")
                m3.metric("Profit factor", bt_stats['profit_factor'] if bt_stats['profit_factor'] else "∞")
                m4.metric("Drawdown máx.", f"{bt_stats['max_drawdown_pct']:.2f}%")
                st.caption(
                    f"Ganancia prom.: {bt_stats['avg_win_pct']:+.2f}% · Pérdida prom.: {bt_stats['avg_loss_pct']:+.2f}% · "
                    f"PnL total acumulado: {bt_stats['total_pnl_pct']:+.2f}% · Velas promedio por operación: {bt_stats['avg_bars_held']}"
                )
                if bt_stats["n_trades"] < 20:
                    st.info("Con menos de 20 operaciones la muestra es chica -- prueba con más velas históricas antes de sacar conclusiones firmes.")
                with st.expander("Ver todas las operaciones simuladas"):
                    for t in bt_trades:
                        emoji = "🟢" if t["pnl_pct"] > 0 else "🔴"
                        st.write(
                            f"{emoji} {t['entry_time'].strftime('%Y-%m-%d %H:%M')} {t['direction']} "
                            f"@ {format_price(t['entry'])} → {t['outcome']} @ {format_price(t['close_price'])} "
                            f"({t['pnl_pct']:+.2f}%, {t['bars_held']} velas)"
                        )
