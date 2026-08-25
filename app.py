import time
import streamlit as st
import plotly.graph_objects as go
from streamlit_autorefresh import st_autorefresh

import config
import db
import backtest
from price_format import format_price
from data_fetch import get_klines
from indicators import add_all_indicators
from signals import evaluate_signal, get_daily_trend
from telegram_alert import send_telegram_message
from telegram_bot import get_updates, parse_commands, format_status_message, format_help_message

st.set_page_config(page_title="Crypto Signal Dashboard", layout="wide")

db.init_db(default_symbols=config.AVAILABLE_SYMBOLS)

# --- Estado persistente durante la sesión ---
if "symbol" not in st.session_state:
    st.session_state.symbol = db.get_state("last_symbol", config.DEFAULT_SYMBOL)
if "notifications_enabled" not in st.session_state:
    st.session_state.notifications_enabled = True
if "telegram_offset" not in st.session_state:
    st.session_state.telegram_offset = 0
if "last_alert" not in st.session_state:
    st.session_state.last_alert = None
if "scan_mode" not in st.session_state:
    st.session_state.scan_mode = False

TOKEN = config.TELEGRAM_TOKEN
CHAT_ID = config.TELEGRAM_CHAT_ID

# Refresco dinámico: si hay operaciones en seguimiento, revisa cada 20s;
# si no, cada REFRESH_SECONDS (60s por defecto) para no gastar de más.
_open_ops_count = len(db.get_open_operations())
_refresh_ms = 20_000 if _open_ops_count > 0 else config.REFRESH_SECONDS * 1000
st_autorefresh(interval=_refresh_ms, key="refresh")


@st.cache_data(ttl=55, show_spinner=False)
def cached_klines(symbol: str, interval: str, limit: int):
    return get_klines(symbol, interval, limit)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_daily_trend(symbol: str):
    df_1d = cached_klines(symbol, "1d", 100)
    df_1d = add_all_indicators(df_1d)
    return get_daily_trend(df_1d)


def get_data_and_signal(symbol: str):
    df = cached_klines(symbol, config.INTERVAL, 300)
    df = add_all_indicators(df)
    try:
        trend_1d = cached_daily_trend(symbol)
    except Exception:
        trend_1d = None
    result = evaluate_signal(df, trend_1d=trend_1d)
    return df, result


def set_symbol(new_symbol: str):
    st.session_state.symbol = new_symbol
    db.set_state("last_symbol", new_symbol)


def send_signal_alert(symbol, result):
    msg = (
        f"*{result['signal']}* señal CONFIRMADA en *{symbol}* ({config.INTERVAL})\n"
        f"Precio: ${format_price(result['price'])}\n"
        f"Entrada: ${format_price(result['entry'])}\n"
        f"Stop: ${format_price(result['stop'])}\n"
        f"TP: ${format_price(result['tp'])}\n"
        f"A favor: {', '.join(result['reasons'])}\n"
        + (f"En conflicto: {', '.join(result['conflict_reasons'])}" if result['conflict_reasons'] else "")
    )
    return send_telegram_message(TOKEN, CHAT_ID, msg)


# --- Procesar comandos de Telegram ---
if TOKEN and CHAT_ID:
    updates = get_updates(TOKEN, offset=st.session_state.telegram_offset)
    commands, max_update_id = parse_commands(updates, CHAT_ID)
    if max_update_id is not None:
        st.session_state.telegram_offset = max_update_id + 1

    for c in commands:
        cmd, arg = c["cmd"], c["arg"]

        if cmd == "start":
            st.session_state.notifications_enabled = True
            send_telegram_message(TOKEN, CHAT_ID, "🟢 Alertas activadas.")

        elif cmd == "stop":
            st.session_state.notifications_enabled = False
            send_telegram_message(TOKEN, CHAT_ID, "🔴 Alertas pausadas. El dashboard sigue vigilando el mercado, pero no te va a interrumpir.")

        elif cmd == "help":
            send_telegram_message(TOKEN, CHAT_ID, format_help_message())

        elif cmd == "favorites":
            favs = db.get_favorites()
            send_telegram_message(TOKEN, CHAT_ID, "*Favoritos:*\n" + ("\n".join(f"- {s}" for s in favs) if favs else "(ninguno)"))

        elif cmd == "operations":
            ops = db.get_open_operations()
            if not ops:
                send_telegram_message(TOKEN, CHAT_ID, "No hay operaciones en seguimiento.")
            else:
                lines = [f"{o['symbol']} {o['direction']} | entrada {format_price(o['entry'])} | stop {format_price(o['stop'])} | tp {format_price(o['tp'])}" for o in ops]
                send_telegram_message(TOKEN, CHAT_ID, "*Operaciones en seguimiento:*\n" + "\n".join(lines))

        elif cmd == "symbol" and arg:
            symbol = arg if arg.endswith("USDT") else f"{arg}USDT"
            try:
                get_klines(symbol, config.INTERVAL, limit=5)
                set_symbol(symbol)
                send_telegram_message(TOKEN, CHAT_ID, f"✅ Ahora siguiendo *{symbol}*.")
            except Exception:
                send_telegram_message(TOKEN, CHAT_ID, f"⚠️ No encontré el par *{symbol}* en Binance. Verifica el nombre (ej. /symbol ETHUSDT).")

        elif cmd in ("status", "now"):
            try:
                _, result = get_data_and_signal(st.session_state.symbol)
                extra = "\n\n(análisis al momento)" if cmd == "now" else ""
                msg = format_status_message(st.session_state.symbol, st.session_state.notifications_enabled, result) + extra
                send_telegram_message(TOKEN, CHAT_ID, msg)
            except Exception as e:
                send_telegram_message(TOKEN, CHAT_ID, f"⚠️ No pude obtener datos ahora mismo: {e}")

# --- Revisar operaciones en seguimiento: cierre automático + alerta de salida temprana ---
for op in db.get_open_operations():
    try:
        _, op_result = get_data_and_signal(op["symbol"])
    except Exception:
        continue
    live_price = op_result["live_price"]

    hit_tp = (op["direction"] == "COMPRA" and live_price >= op["tp"]) or \
             (op["direction"] == "VENTA" and live_price <= op["tp"])
    hit_stop = (op["direction"] == "COMPRA" and live_price <= op["stop"]) or \
               (op["direction"] == "VENTA" and live_price >= op["stop"])

    if hit_tp:
        db.close_operation(op["id"], live_price, "tp")
        if TOKEN and CHAT_ID:
            send_telegram_message(TOKEN, CHAT_ID, f"🎯 *{op['symbol']}* tocó Take Profit en ${format_price(live_price)}. Operación cerrada en el registro.")
    elif hit_stop:
        db.close_operation(op["id"], live_price, "stop")
        if TOKEN and CHAT_ID:
            send_telegram_message(TOKEN, CHAT_ID, f"🛑 *{op['symbol']}* tocó Stop Loss en ${format_price(live_price)}. Operación cerrada en el registro.")
    elif not op["early_warning_sent"]:
        opposite = "VENTA" if op["direction"] == "COMPRA" else "COMPRA"
        if op_result["signal"] == opposite and op_result["status"] == "confirmada":
            db.mark_early_warning_sent(op["id"])
            if TOKEN and CHAT_ID:
                send_telegram_message(
                    TOKEN, CHAT_ID,
                    f"⚠️ *{op['symbol']}*: el análisis ahora confirma señal de *{opposite}*, "
                    f"contraria a tu operación de {op['direction']} abierta en ${format_price(op['entry'])}. "
                    f"Precio actual: ${format_price(live_price)}. Considera evaluar salir manualmente en Quantfury "
                    f"para reducir la pérdida potencial."
                )

# --- Modo escaneo de favoritos ---
if st.session_state.scan_mode:
    favorites = db.get_favorites()
    found = None
    for fav_symbol in favorites:
        try:
            _, fav_result = get_data_and_signal(fav_symbol)
        except Exception:
            continue
        if fav_result["signal"] in ("COMPRA", "VENTA") and fav_result["status"] == "confirmada":
            found = (fav_symbol, fav_result)
            break
    if found:
        fav_symbol, fav_result = found
        set_symbol(fav_symbol)
        alert_key = f"{fav_symbol}:{fav_result['signal']}"
        if st.session_state.last_alert != alert_key and st.session_state.notifications_enabled and TOKEN and CHAT_ID:
            ok, _ = send_signal_alert(fav_symbol, fav_result)
            if ok:
                st.session_state.last_alert = alert_key

# --- UI ---
st.title("📊 Crypto Signal Dashboard")

with st.expander("⭐ Favoritos y modo escaneo"):
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

with st.expander("🧪 Backtest (probar el sistema con datos históricos)"):
    st.caption(
        "Corre la lógica exacta de señales sobre velas pasadas, sin trampas -- cada decisión "
        "usa solo datos disponibles hasta ese momento. Sirve para ver si el sistema tiene "
        "ventaja estadística real antes de confiar en él con dinero en vivo."
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
        except Exception as e:
            st.error(f"No se pudo correr el backtest: {e}")

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

col_sel, col_info = st.columns([1, 2])
with col_sel:
    options = config.AVAILABLE_SYMBOLS.copy()
    if st.session_state.symbol not in options:
        options.append(st.session_state.symbol)
    chosen = st.selectbox(
        "Cripto en seguimiento", options, index=options.index(st.session_state.symbol),
        disabled=st.session_state.scan_mode,
    )
    if chosen != st.session_state.symbol and not st.session_state.scan_mode:
        set_symbol(chosen)

with col_info:
    estado = "🟢 Activas" if st.session_state.notifications_enabled else "🔴 Pausadas"
    st.caption(
        f"Alertas Telegram: {estado} · Timeframe {config.INTERVAL} · "
        f"Refresco cada {_refresh_ms // 1000}s{' (acelerado, hay operaciones abiertas)' if _open_ops_count else ''} · "
        f"Última actualización: {time.strftime('%H:%M:%S')}"
    )
    st.caption("Comandos por Telegram: /start /stop /status /now /symbol PAR /favorites /operations")

symbol = st.session_state.symbol

try:
    with st.spinner(f"Cargando datos de {symbol}..."):
        df, result = get_data_and_signal(symbol)
except Exception as e:
    st.error(f"Error obteniendo datos de {symbol}: {e}")
    st.stop()

col1, col2 = st.columns([3, 1])

with col1:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["open_time"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"], name=symbol,
    ))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema50"], name="EMA 50", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["ema200"], name="EMA 200", line=dict(width=1)))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["bb_upper"], name="BB Superior", line=dict(width=1, dash="dot")))
    fig.add_trace(go.Scatter(x=df["open_time"], y=df["bb_lower"], name="BB Inferior", line=dict(width=1, dash="dot")))
    fig.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), xaxis_rangeslider_visible=False)
    st.plotly_chart(fig, use_container_width=True)

    fig_macd = go.Figure()
    fig_macd.add_trace(go.Bar(x=df["open_time"], y=df["macd_hist"], name="Histograma"))
    fig_macd.add_trace(go.Scatter(x=df["open_time"], y=df["macd"], name="MACD"))
    fig_macd.add_trace(go.Scatter(x=df["open_time"], y=df["macd_signal"], name="Señal"))
    fig_macd.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_macd, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        fig_rsi = go.Figure()
        fig_rsi.add_trace(go.Scatter(x=df["open_time"], y=df["rsi14"], name="RSI 14"))
        fig_rsi.add_hline(y=70, line_dash="dash", line_color="red")
        fig_rsi.add_hline(y=30, line_dash="dash", line_color="green")
        fig_rsi.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_rsi, use_container_width=True)
    with c2:
        fig_delta = go.Figure()
        colors = ["#22c55e" if v >= 0 else "#ef4444" for v in df["delta"].tail(60)]
        fig_delta.add_trace(go.Bar(x=df["open_time"].tail(60), y=df["delta"].tail(60), marker_color=colors, name="Delta"))
        fig_delta.update_layout(height=180, margin=dict(l=10, r=10, t=10, b=10), title="Delta (compra - venta)")
        st.plotly_chart(fig_delta, use_container_width=True)

    fig_adx = go.Figure()
    fig_adx.add_trace(go.Scatter(x=df["open_time"], y=df["adx14"], name="ADX"))
    fig_adx.add_hline(y=25, line_dash="dash", line_color="gray")
    fig_adx.update_layout(height=150, margin=dict(l=10, r=10, t=10, b=10), title="ADX (fuerza de tendencia, >25 = fuerte)")
    st.plotly_chart(fig_adx, use_container_width=True)

with col2:
    st.metric("Precio actual", f"${format_price(result['live_price'])}")
    if result["price"] != result["live_price"]:
        st.caption(f"Señal calculada sobre la última vela cerrada (${format_price(result['price'])})")

    signal = result["signal"]
    color = {"COMPRA": "🟢", "VENTA": "🔴", "ESPERA": "🟡"}[signal]
    status_tag = ""
    if signal in ("COMPRA", "VENTA"):
        status_tag = " ✅ confirmada" if result["status"] == "confirmada" else " ⏳ en formación"
    st.subheader(f"{color} {signal}{status_tag}")
    if signal in ("COMPRA", "VENTA") and result["status"] == "en formación":
        st.caption("Apareció en la última vela cerrada. Se confirma si se sostiene en la próxima.")

    st.write(f"**MACD:** {result['macd_state']}")
    st.write(f"**RSI 14:** {result['rsi']} ({result['rsi_zone']})")
    st.write(f"**PVT:** {result['pvt_confirm']}")
    st.write(f"**Delta:** {result['delta_state']} ({result['delta_pct']}%)")
    if result.get("trend_1d"):
        st.write(f"**Tendencia 1D:** {result['trend_1d']}")
    st.write(f"**ADX:** {result['adx']} ({result['trend_strength']})")
    if result["trend_strength"] == "lateral/débil":
        st.caption("⚠️ Mercado sin tendencia clara -- las señales de MACD/EMA son menos fiables ahora.")
    if result.get("pattern"):
        st.write(f"**Patrón de velas:** envolvente {result['pattern']}")
    if result["support"]:
        st.write(f"**Soporte cercano:** {format_price(result['support'])}")
    if result["resistance"]:
        st.write(f"**Resistencia cercana:** {format_price(result['resistance'])}")

    st.markdown("**Razones a favor:**")
    for r in result["reasons"]:
        st.write(f"- {r}")
    if result.get("conflict_reasons"):
        st.markdown("**⚠️ Señales en conflicto (contradicen esta señal):**")
        for r in result["conflict_reasons"]:
            st.write(f"- {r}")

    alert_key = f"{symbol}:{signal}"
    if signal in ("COMPRA", "VENTA"):
        st.markdown("**Valores para Quantfury (toca el ícono de copiar en cada uno):**")
        st.caption("Precio de entrada")
        st.code(f"{format_price(result['entry'])}", language=None)
        stop_note = ""
        if result.get("stop_capped"):
            stop_note = f" (limitado a {config.MAX_STOP_PCT*100:.0f}% máx. de riesgo)"
        elif result.get("stop_widened"):
            stop_note = " (ampliado por volatilidad ATR)"
        st.caption("Stop loss" + stop_note)
        st.code(f"{format_price(result['stop'])}", language=None)
        st.caption("Take profit")
        st.code(f"{format_price(result['tp'])}", language=None)

        open_ops_this_symbol = [o for o in db.get_open_operations() if o["symbol"] == symbol]
        if open_ops_this_symbol:
            st.info(f"Ya tienes una operación de {symbol} en seguimiento.")
        else:
            if st.button("✅ Aceptar y dar seguimiento a esta operación"):
                db.create_operation(symbol, signal, result["entry"], result["stop"], result["tp"])
                st.success("Operación en seguimiento. Se revisa automáticamente cada refresco.")
                st.rerun()

        st.markdown("**Calculadora de ganancia/pérdida**")
        cap_col, inv_col = st.columns(2)
        with cap_col:
            capital = st.number_input("Capital disponible ($)", min_value=1.0, value=50.0, step=10.0, key="capital_input")
        with inv_col:
            investment = st.number_input("Monto a invertir ($)", min_value=1.0, value=500.0, step=50.0, key="investment_input")

        entry, stop, tp = result["entry"], result["stop"], result["tp"]
        qty = investment / entry

        if signal == "COMPRA":
            profit_usd = qty * (tp - entry)
            loss_usd = qty * (entry - stop)
        else:
            profit_usd = qty * (entry - tp)
            loss_usd = qty * (stop - entry)

        profit_pct = (profit_usd / investment) * 100 if investment else 0
        loss_pct = (loss_usd / investment) * 100 if investment else 0
        implied_leverage = investment / capital if capital else 0
        rr_ratio = (profit_usd / loss_usd) if loss_usd else 0

        pnl_col1, pnl_col2 = st.columns(2)
        with pnl_col1:
            st.metric("Si toca Take Profit", f"+${profit_usd:,.2f}", f"{profit_pct:+.1f}%")
        with pnl_col2:
            st.metric("Si toca Stop Loss", f"-${loss_usd:,.2f}", f"{-loss_pct:.1f}%", delta_color="inverse")

        st.caption(f"Cantidad: {qty:.6f} {symbol.replace('USDT','')} · Ratio riesgo/beneficio: 1:{rr_ratio:.2f}")

        if result.get("low_quality_rr"):
            st.warning(
                f"⚠️ El ratio riesgo/beneficio de esta señal ({result['rr_ratio']}:1) está por debajo "
                f"de lo recomendado (mínimo {config.MIN_RR_RATIO}:1). Aunque el stop ya está limitado, "
                f"el take profit está relativamente cerca -- considera si vale la pena esta operación."
            )

        if implied_leverage > 1:
            st.warning(
                f"⚠️ Este monto implica un apalancamiento aproximado de **{implied_leverage:.1f}x** "
                f"sobre tu capital de ${capital:,.2f}. Verifica siempre el apalancamiento real que usa tu bróker."
            )

        if (
            result["status"] == "confirmada"
            and st.session_state.last_alert != alert_key
            and st.session_state.notifications_enabled
            and TOKEN and CHAT_ID
        ):
            ok, info = send_signal_alert(symbol, result)
            if ok:
                st.session_state.last_alert = alert_key
                st.toast(f"Alerta enviada a Telegram ({symbol})")
            else:
                st.warning(f"No se pudo enviar Telegram: {info}")
    else:
        st.info("Sin señal confirmada — mercado en zona de espera.")
        st.session_state.last_alert = alert_key

# --- Operaciones en seguimiento ---
open_ops = db.get_open_operations()
if open_ops:
    st.divider()
    st.subheader("📍 Operaciones en seguimiento")
    for op in open_ops:
        try:
            _, op_result = get_data_and_signal(op["symbol"])
            live = op_result["live_price"]
            if op["direction"] == "COMPRA":
                progress = (live - op["entry"]) / (op["tp"] - op["entry"]) if op["tp"] != op["entry"] else 0
            else:
                progress = (op["entry"] - live) / (op["entry"] - op["tp"]) if op["entry"] != op["tp"] else 0
            progress = max(0, min(1, progress))
            st.write(f"**{op['symbol']} {op['direction']}** · entrada ${format_price(op['entry'])} · precio actual ${format_price(live)}")
            st.progress(progress, text=f"{progress*100:.0f}% hacia el take profit")
        except Exception:
            st.write(f"{op['symbol']} {op['direction']} (no se pudo actualizar precio)")

history = db.get_operation_history(10)
if history:
    with st.expander(f"📜 Historial ({len(history)} operaciones cerradas recientes)"):
        wins = sum(1 for h in history if h["pnl_pct"] and h["pnl_pct"] > 0)
        st.caption(f"{wins}/{len(history)} operaciones ganadoras en este historial")
        for h in history:
            emoji = "🟢" if h["pnl_pct"] and h["pnl_pct"] > 0 else "🔴"
            st.write(f"{emoji} {h['symbol']} {h['direction']} · {h['outcome']} · {h['pnl_pct']:+.2f}%")

st.divider()
st.caption(
    "⚠️ Herramienta de apoyo técnico, no es asesoría financiera. "
    "Las señales combinan MACD, RSI, PVT, delta, ADX, patrón de velas y niveles de "
    "soporte/resistencia, calculadas solo sobre velas cerradas — no garantizan "
    "resultados. Define siempre tu propia gestión de riesgo."
)
