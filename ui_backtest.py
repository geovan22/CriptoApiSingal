"""Panel de backtest -- prueba el sistema con datos históricos, con resultados persistidos en DB."""
import json
import pandas as pd
import streamlit as st

import config
import db
import backtest
import stats_helper
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


def _render_interpretation(stats: dict, label: str = ""):
    interp = stats_helper.interpret_backtest(stats)
    if interp.get("n_trades", 0) == 0:
        return
    prefix = f"**{label}** — " if label else ""
    st.caption(
        f"{prefix}Win rate observado {interp['win_rate_pct']}% · "
        f"tu win rate REAL probablemente está entre {interp['win_rate_ci_low']}% y "
        f"{interp['win_rate_ci_high']}% (95% de confianza, n={interp['n_trades']})."
    )
    if interp.get("breakeven_win_rate_pct") is not None:
        be = interp["breakeven_win_rate_pct"]
        verdict = interp["verdict"]
        if verdict == "por_encima_equilibrio":
            st.success(f"✅ Con esta muestra, todo el intervalo de confianza queda por ENCIMA del {be}% que necesitas para no perder dinero -- señal alentadora, aunque la muestra sigue siendo chica.")
        elif verdict == "por_debajo_equilibrio":
            st.error(f"🔴 Con esta muestra, todo el intervalo de confianza queda por DEBAJO del {be}% que necesitas para no perder dinero -- señal preocupante.")
        else:
            st.warning(f"⚪ Indeterminado: tu intervalo de confianza cruza el {be}% que necesitas para no perder dinero -- con esta cantidad de datos, NO se puede afirmar si el sistema tiene ventaja o no. Necesitarías ~{interp['required_n_for_10pct_margin']} operaciones para saberlo con más certeza (tienes {interp['n_trades']}).")


def render_backtest_panel():
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

            st.markdown("**📐 Interpretación estadística**")
            _render_interpretation(bt_stats)

            confluence = backtest.summarize_by_confluence(bt_trades)
            if confluence:
                st.markdown("**Desglose por nivel de confluencia** (¿más razones a favor = mejor resultado?)")
                for label, stats_c in confluence.items():
                    st.write(f"- {label}: {stats_c['n_trades']} operaciones · win rate {stats_c['win_rate']}% · PnL prom. {stats_c['avg_pnl_pct']:+.2f}%")

            with st.expander("Ver todas las operaciones simuladas"):
                for t in bt_trades:
                    emoji = "🟢" if t["pnl_pct"] > 0 else "🔴"
                    st.write(
                        f"{emoji} {t['entry_time'].strftime('%Y-%m-%d %H:%M')} {t['direction']} "
                        f"@ {format_price(t['entry'])} → {t['outcome']} @ {format_price(t['close_price'])} "
                        f"({t['pnl_pct']:+.2f}%, {t['bars_held']} velas)"
                    )

    st.divider()
    st.markdown("### 📊 Análisis combinado (todos los símbolos)")
    st.caption(
        "Corre el backtest en varios símbolos a la vez y junta TODAS las operaciones en una "
        "sola muestra -- llega mucho más rápido al mínimo de ~100 operaciones que hace falta "
        "para conclusiones confiables, en vez de esperar semanas con un solo símbolo. "
        "Nota: las criptos suelen moverse correlacionadas entre sí, así que esto no es una "
        "muestra perfectamente independiente -- pero sigue siendo mejor que ver un símbolo solo."
    )
    multi_symbols = st.multiselect(
        "Símbolos a incluir", config.AVAILABLE_SYMBOLS,
        default=config.AVAILABLE_SYMBOLS[:8], key="multi_symbols",
    )
    multi_limit = st.slider("Velas históricas por símbolo", 300, 1000, 700, step=50, key="multi_limit")
    run_multi = st.button(f"📊 Analizar {len(multi_symbols)} símbolos combinados")

    if run_multi and multi_symbols:
        progress_bar = st.progress(0.0)
        status_text = st.empty()

        def _update_progress(symbol, i, total):
            status_text.text(f"Analizando {symbol}... ({i + 1}/{total})")
            progress_bar.progress((i + 1) / total)

        try:
            all_trades, per_symbol, pooled_stats, errors = backtest.run_multi_symbol_backtest(
                multi_symbols, config.INTERVAL, limit=multi_limit, progress_callback=_update_progress
            )
            st.session_state["multi_result"] = (all_trades, per_symbol, pooled_stats, errors)
        except Exception as e:
            st.error(f"No se pudo correr el análisis combinado: {e}")
        finally:
            status_text.empty()
            progress_bar.empty()

    if "multi_result" in st.session_state:
        all_trades, per_symbol, pooled_stats, errors = st.session_state["multi_result"]

        if errors:
            st.warning(f"No se pudieron analizar {len(errors)} símbolo(s): {', '.join(errors.keys())}")

        if pooled_stats.get("n_trades", 0) == 0:
            st.warning("Ningún símbolo generó operaciones confirmadas en este rango.")
        else:
            st.write(f"**Resultado combinado: {pooled_stats['n_trades']} operaciones de {len(per_symbol)} símbolos**")
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Win rate", f"{pooled_stats['win_rate']}%")
            m2.metric("Expectativa/operación", f"{pooled_stats['expectancy_pct']:+.2f}%")
            m3.metric("Profit factor", pooled_stats['profit_factor'] if pooled_stats['profit_factor'] else "∞")
            m4.metric("Drawdown máx.", f"{pooled_stats['max_drawdown_pct']:.2f}%")

            st.markdown("**📐 Interpretación estadística (muestra combinada)**")
            _render_interpretation(pooled_stats)

            with st.expander(f"Ver desglose por símbolo ({len(per_symbol)})"):
                for sym, s in sorted(per_symbol.items(), key=lambda kv: kv[1].get("n_trades", 0), reverse=True):
                    if s.get("n_trades", 0) == 0:
                        st.write(f"- {sym}: sin operaciones")
                    else:
                        emoji = "🟢" if s["expectancy_pct"] > 0 else "🔴"
                        st.write(f"{emoji} **{sym}**: {s['n_trades']} op. · win rate {s['win_rate']}% · expectativa {s['expectancy_pct']:+.2f}%")

    st.divider()
    st.markdown("### 🔬 Validación fuera de muestra (walk-forward)")
    st.caption(
        "Divide el histórico en dos partes cronológicas: la primera mitad (train) es la que hemos "
        "estado mirando para ajustar el sistema; la segunda (test) NUNCA se usó para decidir nada. "
        "Si el sistema tiene una ventaja real -- y no solo quedó ajustado al tramo que ya vimos -- "
        "los resultados de test no deberían verse muy distintos a los de train."
    )
    oos_col1, oos_col2 = st.columns([2, 1])
    with oos_col1:
        oos_symbol = st.selectbox("Símbolo a validar", config.AVAILABLE_SYMBOLS, key="oos_symbol")
    with oos_col2:
        st.write("")
        st.write("")
        run_oos = st.button("🔬 Correr validación fuera de muestra")

    if run_oos:
        try:
            with st.spinner(f"Validando {oos_symbol} (train/test)..."):
                oos_result = backtest.run_out_of_sample_validation(oos_symbol, config.INTERVAL, total_limit=1400)
            st.session_state["oos_result"] = (oos_symbol, oos_result)
        except Exception as e:
            st.error(f"No se pudo correr la validación: {e}")

    if "oos_result" in st.session_state:
        oos_sym, oos_data = st.session_state["oos_result"]
        train_trades, train_stats = oos_data["train"]
        test_trades, test_stats = oos_data["test"]

        st.write(f"**{oos_sym}** · corte en {oos_data['split_time'].strftime('%Y-%m-%d %H:%M')}")

        oc1, oc2 = st.columns(2)
        with oc1:
            st.markdown("**TRAIN** (ya observado)")
            if train_stats.get("n_trades", 0) == 0:
                st.caption("Sin operaciones en este tramo.")
            else:
                st.metric("Win rate", f"{train_stats['win_rate']}%")
                st.metric("Expectativa/op.", f"{train_stats['expectancy_pct']:+.2f}%")
                st.caption(f"{train_stats['n_trades']} operaciones · PF {train_stats['profit_factor'] or '∞'}")
                _render_interpretation(train_stats)
        with oc2:
            st.markdown("**TEST** (fuera de muestra)")
            if test_stats.get("n_trades", 0) == 0:
                st.caption("Sin operaciones en este tramo.")
            else:
                st.metric("Win rate", f"{test_stats['win_rate']}%")
                st.metric("Expectativa/op.", f"{test_stats['expectancy_pct']:+.2f}%")
                st.caption(f"{test_stats['n_trades']} operaciones · PF {test_stats['profit_factor'] or '∞'}")
                _render_interpretation(test_stats)

        if train_stats.get("n_trades", 0) >= 5 and test_stats.get("n_trades", 0) >= 5:
            train_exp = train_stats["expectancy_pct"]
            test_exp = test_stats["expectancy_pct"]
            if train_exp <= 0 and test_exp <= 0:
                st.error(
                    "⚠️ El sistema perdió dinero en AMBOS tramos (train y test) -- no es un problema de "
                    "sobreajuste, es que no muestra ventaja estadística en este periodo reciente para "
                    f"este símbolo. Expectativa train {train_exp:+.2f}% / test {test_exp:+.2f}%."
                )
            elif test_exp < 0 and train_exp > 0:
                st.error(
                    "⚠️ El sistema fue rentable en el tramo que ya observamos (train) pero perdió dinero "
                    "en el tramo nunca visto (test) -- señal clásica de sobreajuste. Los parámetros "
                    "actuales podrían estar ajustados al ruido del tramo que miramos, no a una ventaja real."
                )
            elif train_exp <= 0 and test_exp > 0:
                st.info(
                    "ℹ️ Train fue negativo pero test resultó positivo -- con muestras tan chicas esto es "
                    "más probable que sea variación normal que una mejora real. No es evidencia sólida "
                    "en ningún sentido todavía."
                )
            elif test_exp < train_exp * 0.3:
                st.warning(
                    "⚠️ El rendimiento en test es considerablemente más débil que en train -- vale la "
                    "pena tomar los resultados de train con cautela y no seguir ajustando parámetros "
                    "mirando solo ese tramo."
                )
            else:
                st.success("✅ El desempeño en test es razonablemente consistente con train -- buena señal de que no es puro sobreajuste.")
        else:
            st.info("Pocas operaciones en alguno de los dos tramos para sacar una conclusión firme -- prueba con más velas (total_limit) si quieres más muestra.")
