"""
live_bot.py — Ejecuta la estrategia en VIVO sobre tu cuenta MetaTrader 5 (demo).

- Usa el filtro de régimen (ADX), el modo de TP (mean/rr) y el trailing stop
  exactamente como los configuraste en config.py (los mismos que el backtest).
- Circuit breaker: si perdés más del % diario, deja de abrir trades hasta el
  día siguiente (las posiciones abiertas siguen protegidas por su SL/TP).
- Registro persistente en bot.log y trades.json (ver journal.py).

Requiere MetaTrader 5 abierto y logueado.

Uso:
    python live_bot.py     (frenar con Ctrl + C)
"""

import os
import time
import msvcrt
from datetime import datetime, timezone
import config
from mt5_client import MT5Client
from engine import make_strategy
import journal
from telegram_notifier import (
    TelegramNotifier, msg_inicio, msg_trade_abierto, msg_trade_cerrado,
    msg_circuit_breaker, msg_objetivo_alcanzado, msg_freno_total, msg_error,
)

POLL_SECONDS = 300  # revisar el mercado cada 5 minutos
_LOCK_HANDLE = None


def _dir_of(trade):
    return "LONG" if float(trade["currentUnits"]) > 0 else "SHORT"


def _handle_telegram_commands(tg, offset, client, cfg, state):
    """
    Lee mensajes nuevos escritos al bot y ejecuta comandos. Solo responde a
    mensajes que vengan del chat configurado (TELEGRAM_CHAT_ID), ignora el resto.
    Actualiza 'state' (dict: paused/stop) y devuelve el nuevo offset.
    """
    for upd in tg.get_updates(offset):
        offset = upd["update_id"] + 1
        msg = upd.get("message") or {}
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != tg.chat_id:
            continue
        text = (msg.get("text") or "").strip().lower().split("@")[0]

        if text in ("/status", "/balance", "/estado"):
            acc = client.get_account_summary()
            trades = [t for t in client.get_open_trades() if t["instrument"] == cfg.INSTRUMENT]
            if trades:
                t = trades[0]
                dir_ = "LONG" if float(t["currentUnits"]) > 0 else "SHORT"
                pos_str = f"{dir_} @ {t['entry']:.5f}  (SL {t['sl']:.5f} / TP {t['tp']:.5f})"
            else:
                pos_str = "sin posición abierta"
            estado_bot = "⏸ PAUSADO (sin abrir trades nuevos)" if state["paused"] else "▶️ operando normal"
            tg.send(
                f"📊 <b>Estado del bot</b>\n"
                f"Balance: <b>${float(acc['balance']):,.2f}</b>\n"
                f"Equity: <b>${float(acc['equity']):,.2f}</b>\n"
                f"Posición: {pos_str}\n"
                f"{estado_bot}"
            )
        elif text in ("/stop", "/parar", "/detener"):
            state["stop"] = True
            tg.send("⏹ Deteniendo el bot. Las posiciones abiertas NO se cierran, "
                     "siguen protegidas por su SL/TP en el servidor de MT5.")
        elif text in ("/pausar", "/pause"):
            state["paused"] = True
            tg.send("⏸ Pausado: no abro trades nuevos. Las posiciones abiertas siguen "
                     "con su SL/TP/trailing normal. Mandá /reanudar para seguir operando.")
        elif text in ("/reanudar", "/resume", "/continuar"):
            state["paused"] = False
            tg.send("▶️ Reanudado: vuelvo a operar señales nuevas.")
        elif text in ("/cerrar", "/cerrar_todo", "/close", "/cerrar_operaciones"):
            trades = [t for t in client.get_open_trades() if t["instrument"] == cfg.INSTRUMENT]
            if not trades:
                tg.send("No hay ninguna posición abierta para cerrar.")
            else:
                cerrados = []
                for t in trades:
                    if client.close_trade_ok(t["id"]):
                        state["manual_close_ids"].add(t["id"])
                        cerrados.append(t["id"])
                if cerrados:
                    tg.send(f"✋ Cerrando {len(cerrados)} posición(es) manualmente: "
                            f"{', '.join(str(c) for c in cerrados)}. Te aviso cuando se confirme.")
                else:
                    tg.send("⚠️ No se pudo cerrar la posición. Revisá MT5.")
        elif text in ("/ayuda", "/help", "/start"):
            tg.send(
                "<b>Comandos disponibles</b>\n"
                "/status — balance, equity y posición abierta\n"
                "/pausar — dejar de abrir trades nuevos (el bot sigue corriendo)\n"
                "/reanudar — volver a operar tras un /pausar\n"
                "/cerrar — cerrar la(s) posición(es) abierta(s) ahora mismo\n"
                "/stop — detener el bot por completo\n"
                "/ayuda — este mensaje"
            )
        else:
            tg.send("No reconozco ese comando. Mandá /ayuda para ver la lista.")
    return offset


def _acquire_instance_lock(cfg):
    """Evita dos instancias del mismo bot operando la misma cuenta."""
    global _LOCK_HANDLE
    lock_path = os.path.abspath(getattr(cfg, "LOCK_FILE", "live_bot.lock"))
    handle = open(lock_path, "a+", encoding="utf-8")
    try:
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()} started={datetime.now(timezone.utc).isoformat()}\n")
    handle.flush()
    _LOCK_HANDLE = handle
    return lock_path


def run_live(cfg=config):
    poll = getattr(cfg, "POLL_SECONDS", POLL_SECONDS)
    journal.configure(getattr(cfg, "LOG_FILE", None), getattr(cfg, "TRADES_FILE", None))
    lock_path = _acquire_instance_lock(cfg)
    if not lock_path:
        journal.event("OTRA INSTANCIA DEL BOT YA ESTA CORRIENDO. Abortando para evitar ordenes duplicadas.")
        return
    client = MT5Client(cfg.MT5_LOGIN, cfg.MT5_PASSWORD, cfg.MT5_SERVER)
    strat = make_strategy(cfg)

    # ── Telegram (opcional: solo si hay token y chat_id configurados) ──
    tg_token = getattr(cfg, "TELEGRAM_TOKEN", "")
    tg_chat_id = getattr(cfg, "TELEGRAM_CHAT_ID", "")
    tg = TelegramNotifier(tg_token, tg_chat_id) if (tg_token and tg_chat_id) else None
    tg_state = {"paused": False, "stop": False, "manual_close_ids": set()}
    tg_offset = None
    if tg:
        # Descarta mensajes viejos (evita ejecutar un /stop atrasado de antes de arrancar)
        old_updates = tg.get_updates()
        if old_updates:
            tg_offset = old_updates[-1]["update_id"] + 1

    acc = client.get_account_summary()
    tp_mode = getattr(cfg, "TP_MODE", "mean")
    journal.event("=" * 60)
    journal.event(f"Bot iniciado. Conectado a MT5. Cuenta {acc['id']} | "
                  f"Balance {acc['balance']} {acc['currency']}")
    journal.event(f"Operando {cfg.INSTRUMENT} en {cfg.GRANULARITY} | "
                  f"Riesgo {cfg.RISK_PER_TRADE*100:.2f}% | TP={tp_mode}"
                  + (f" (R:R {cfg.TP_RR})" if tp_mode == "rr" else ""))
    if getattr(cfg, "USE_TRAILING_STOP", False):
        journal.event(f"Trailing stop ACTIVO (ATR x {cfg.TRAIL_ATR_MULT})")
    if cfg.USE_REGIME_FILTER:
        journal.event(f"Filtro de régimen ACTIVO (ADX < {cfg.ADX_MAX})")
    if cfg.USE_CIRCUIT_BREAKER:
        journal.event(f"Circuit breaker ACTIVO (freno al perder {cfg.MAX_DAILY_LOSS*100:.0f}% diario)")

    if tg:
        tg.send(msg_inicio(acc["id"], float(acc["balance"]),
                           cfg.RISK_PER_TRADE * 100, getattr(cfg, "TP_RR", 1.5)))

    # Posiciones ya abiertas al arrancar (para seguir su cierre y registrarlo)
    known = {}
    for t in client.get_open_trades():
        if t["instrument"] == cfg.INSTRUMENT:
            known[t["id"]] = t
            journal.event(f"Posición preexistente detectada: ticket {t['id']} {_dir_of(t)}")

    # ── Modo FTMO (opcional): frenos de pérdida total y objetivo de ganancia ──
    # Se activa si config define FTMO_INITIAL_CAPITAL. Mide EQUITY (igual que FTMO).
    ftmo_cap = getattr(cfg, "FTMO_INITIAL_CAPITAL", None)
    max_total = getattr(cfg, "MAX_TOTAL_LOSS", None)
    profit_target = getattr(cfg, "PROFIT_TARGET", None)
    # Si FTMO_AUTO_STOP = False, el bot NO se apaga solo al tocar el objetivo
    # (+10%) ni el freno total (-8%): queda corriendo hasta que vos lo frenes.
    ftmo_auto_stop = getattr(cfg, "FTMO_AUTO_STOP", True)
    # Red de seguridad independiente del objetivo. Por defecto sigue a auto_stop
    # (retrocompatible), pero se puede dejar el freno total ON con el objetivo OFF.
    ftmo_total_stop = getattr(cfg, "FTMO_TOTAL_LOSS_STOP", ftmo_auto_stop)
    if ftmo_cap:
        obj = "SE APAGA" if ftmo_auto_stop else "NO se apaga (sigue operando)"
        prot = "PROTEGIDO" if ftmo_total_stop else "OFF"
        journal.event(f"MODO FTMO: capital base ${ftmo_cap:,.0f} | "
                      f"objetivo +{profit_target*100:.0f}% → {obj} | "
                      f"freno total -{max_total*100:.0f}% → {prot}")

    current_day = None
    day_start_equity = float(acc.get("equity", acc["balance"]))
    day_blocked = False
    last_entry_bar = None
    last_close_bar = None
    last_close_ts = 0.0
    dd_alert_pct = getattr(cfg, "DRAWDOWN_ALERT_PCT", None)  # punto de reevaluación
    dd_alerted = False

    while True:
        try:
            stamp = datetime.now().strftime("%H:%M:%S")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            acc = client.get_account_summary()
            balance = float(acc["balance"])
            equity = float(acc.get("equity", acc["balance"]))

            # ── Comandos de Telegram (/status, /pausar, /reanudar, /stop) ──
            if tg:
                tg_offset = _handle_telegram_commands(tg, tg_offset, client, cfg, tg_state)
                if tg_state["stop"]:
                    journal.event(f"[{stamp}] Bot detenido remotamente vía Telegram (/stop).")
                    break

            # ── Frenos FTMO: detienen el bot por completo (no solo el día) ──
            # Freno total = red de seguridad (FTMO_TOTAL_LOSS_STOP), independiente
            # del freno por objetivo (FTMO_AUTO_STOP).
            if ftmo_total_stop and ftmo_cap and max_total and equity <= ftmo_cap * (1 - max_total):
                journal.event(f"[{stamp}] 🛑 FRENO TOTAL FTMO: equity ${equity:,.2f} "
                              f"tocó el límite (-{max_total*100:.0f}%). DETENIENDO el bot.")
                if tg:
                    tg.send(msg_freno_total(equity, ftmo_cap))
                break
            if ftmo_auto_stop and ftmo_cap and profit_target and equity >= ftmo_cap * (1 + profit_target):
                journal.event(f"[{stamp}] 🎯 OBJETIVO FTMO ALCANZADO: equity ${equity:,.2f} "
                              f"(+{profit_target*100:.0f}%). DETENIENDO el bot (fase superada).")
                if tg:
                    tg.send(msg_objetivo_alcanzado(equity, ftmo_cap))
                break

            # ── Alerta de reevaluación (una sola vez, no frena el bot) ──
            if (tg and dd_alert_pct and ftmo_cap and not dd_alerted
                    and equity <= ftmo_cap * (1 - dd_alert_pct)):
                dd_alerted = True
                dd_now = (ftmo_cap - equity) / ftmo_cap * 100
                journal.event(f"[{stamp}] ALERTA drawdown -{dd_now:.1f}% (punto de reevaluación).")
                tg.send(f"⚠️ <b>Alerta: drawdown -{dd_now:.1f}%</b>\n"
                        f"Equity <b>${equity:,.2f}</b> (base ${ftmo_cap:,.0f}).\n"
                        f"Llegaste al punto de reevaluación que fijamos. "
                        f"Decidí si seguir o pausar el bot.")

            if today != current_day:
                current_day = today
                day_start_equity = equity
                day_blocked = False

            # Freno diario: mide caída de equity desde el inicio del día.
            # En modo FTMO el límite es % del capital base; si no, % del equity del día.
            if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
                ref = ftmo_cap if ftmo_cap else day_start_equity
                if (day_start_equity - equity) >= cfg.MAX_DAILY_LOSS * ref:
                    day_blocked = True
                    perdida_dia = (day_start_equity - equity) / ref * 100 if ref else 0
                    journal.event(f"[{stamp}] CIRCUIT BREAKER activado: pérdida diaria > "
                                  f"{cfg.MAX_DAILY_LOSS*100:.0f}%. No se abren más trades hoy.")
                    if tg:
                        tg.send(msg_circuit_breaker(perdida_dia, balance))

            need = max(cfg.BB_PERIOD, cfg.ATR_PERIOD, cfg.RSI_PERIOD,
                       2 * cfg.ADX_PERIOD + 1) + 50
            if getattr(cfg, "USE_TREND_FILTER", False):
                need = max(need, getattr(cfg, "TREND_EMA_PERIOD", 200) + 50)
            times, opens, highs, lows, closes = client.get_candles(
                cfg.INSTRUMENT, cfg.GRANULARITY, need
            )
            ind = strat.compute_indicators(highs, lows, closes)
            i = len(closes) - 1
            price = closes[i]

            open_trades = [t for t in client.get_open_trades()
                           if t["instrument"] == cfg.INSTRUMENT]
            open_ids = {t["id"] for t in open_trades}

            # ── Detectar y registrar cierres (SL/TP/trailing/manual) ──
            for tid in list(known):
                if tid not in open_ids:
                    info = known.pop(tid)
                    res = client.get_deal_result(tid)
                    pnl = res["pnl"] if res else ""
                    exit_price = res["exit_price"] if res and res["exit_price"] else ""
                    manual = tid in tg_state["manual_close_ids"]
                    tg_state["manual_close_ids"].discard(tid)
                    motivo = "CIERRE_MANUAL" if manual else "SL/TP/trailing"
                    journal.trade({
                        "accion": "CERRADA", "instrumento": cfg.INSTRUMENT,
                        "direccion": _dir_of(info), "lotes": info.get("volume", ""),
                        "precio": exit_price, "sl": "", "tp": "",
                        "riesgo_usd": "", "pnl": pnl, "balance": balance,
                        "ticket": tid, "motivo": motivo,
                    })
                    pnl_str = f"{pnl:+.2f}" if isinstance(pnl, (int, float)) else "?"
                    journal.event(f"[{stamp}] CERRADA posición {tid} ({_dir_of(info)}) | PnL {pnl_str}"
                                  + (" | manual vía Telegram" if manual else ""))
                    # Marca el cierre para el cooldown y el bloqueo por vela (evita
                    # reentrar a los minutos en la misma vela, como pasó el día 1).
                    last_close_ts = time.time()
                    last_close_bar = times[i]
                    if tg:
                        tg.send(msg_trade_cerrado(
                            direccion=_dir_of(info),
                            lotes=info.get("volume", "?"),
                            entrada=info.get("entry", 0),
                            salida=res["exit_price"] if res and res.get("exit_price") else "?",
                            pnl=pnl if isinstance(pnl, (int, float)) else 0,
                            balance=balance,
                            motivo=motivo,
                        ))

            if open_trades:
                trade = open_trades[0]
                known[trade["id"]] = trade  # refrescar (incluye SL ya movido)
                is_long = float(trade["currentUnits"]) > 0

                # ── Trailing stop (igual que el backtest) ──
                if getattr(cfg, "USE_TRAILING_STOP", False) and ind["atr"][i] is not None:
                    dist = cfg.TRAIL_ATR_MULT * ind["atr"][i]
                    cur_sl = trade["sl"]
                    new_sl = None
                    if is_long and price - dist > cur_sl:
                        new_sl = price - dist
                    elif not is_long and (cur_sl == 0 or price + dist < cur_sl):
                        new_sl = price + dist
                    if new_sl is not None:
                        client.modify_stop_loss(trade["id"], new_sl, trade["tp"])
                        journal.event(f"[{stamp}] Trailing: SL de {trade['id']} movido a {new_sl:.5f}")

                if tp_mode == "mean":
                    mid_now = ind["mid"][i]
                    exit_by_mean = (is_long and mid_now and price >= mid_now) or \
                                   (not is_long and mid_now and price <= mid_now)
                    if exit_by_mean:
                        client.close_trade(trade["id"])
                        journal.event(f"[{stamp}] Cerrando {trade['id']} (volvió a la media) @ {price:.5f}")
                    else:
                        journal.event(f"[{stamp}] Posición abierta, esperando salida. Precio {price:.5f}")
                else:
                    journal.event(f"[{stamp}] Posición abierta (SL/TP en servidor). Precio {price:.5f}")

            elif cfg.USE_CIRCUIT_BREAKER and day_blocked:
                journal.event(f"[{stamp}] Freno diario activo, sin abrir trades. Precio {price:.5f}")
            elif tg_state["paused"]:
                journal.event(f"[{stamp}] Pausado por Telegram, sin abrir trades. Precio {price:.5f}")
            else:
                sig = strat.signal_at(i, closes, ind)
                # ── Anti-sobreoperación (alinea el live con el backtest) ──
                # No reentrar varias veces en la MISMA vela ni justo después de un
                # cierre. El backtest toma 1 trade por vela; el live, sin esto,
                # reentraba cada 60s mientras la señal seguía activa.
                bar_id = times[i]
                one_per_candle = getattr(cfg, "ONE_TRADE_PER_CANDLE", True)
                cooldown = getattr(cfg, "REENTRY_COOLDOWN_SECONDS", 0)
                blocked_same_bar = one_per_candle and bar_id in (last_entry_bar, last_close_bar)
                in_cooldown = cooldown and (time.time() - last_close_ts) < cooldown
                if sig and (blocked_same_bar or in_cooldown):
                    motivo = "misma vela ya operada" if blocked_same_bar else "cooldown tras cierre"
                    journal.event(f"[{stamp}] Señal {sig['dir']} pero NO se reentra ({motivo}). "
                                  f"Precio {price:.5f}")
                elif sig:
                    sl_dist = abs(sig["entry"] - sig["sl"])
                    risk_amount = balance * cfg.RISK_PER_TRADE
                    lots, real_risk = client.calc_lots(cfg.INSTRUMENT, risk_amount, sl_dist)
                    if lots > 0:
                        r = client.place_market_order(
                            cfg.INSTRUMENT, sig["dir"], lots,
                            stop_loss=sig["sl"], take_profit=sig["tp"],
                        )
                        last_entry_bar = bar_id   # esta vela ya operó
                        risk_pct = real_risk / balance * 100 if balance else 0
                        journal.trade({
                            "accion": "ABIERTA", "instrumento": cfg.INSTRUMENT,
                            "direccion": sig["dir"], "lotes": lots,
                            "precio": round(sig["entry"], 5), "sl": round(sig["sl"], 5),
                            "tp": round(sig["tp"], 5), "riesgo_usd": round(real_risk, 2),
                            "pnl": "", "balance": balance, "ticket": r.get("id", ""),
                            "motivo": "señal de entrada",
                        })
                        journal.event(f"[{stamp}] ABIERTA {sig['dir']} {lots} lotes @ {sig['entry']:.5f} "
                                      f"| SL {sig['sl']:.5f} | TP {sig['tp']:.5f} "
                                      f"| riesgo ${real_risk:.2f} ({risk_pct:.1f}%)")
                        if tg:
                            tg.send(msg_trade_abierto(
                                direccion=sig["dir"], lotes=lots,
                                entrada=sig["entry"], sl=sig["sl"], tp=sig["tp"],
                                riesgo_usd=real_risk, balance=balance,
                            ))
                    else:
                        journal.event(f"[{stamp}] Señal {sig['dir']} pero lotes=0. Salteando.")
                else:
                    adx_now = ind["adx"][i]
                    rsi_now = ind["rsi"][i]
                    adx_str = f"{adx_now:.0f}" if adx_now is not None else "--"
                    journal.event(f"[{stamp}] Sin señal. Precio {price:.5f}  RSI {rsi_now:.0f}  ADX {adx_str}")

        except KeyboardInterrupt:
            journal.event("Bot detenido por el usuario.")
            if tg:
                tg.send("⏹ <b>Bot detenido manualmente</b>\nHasta la próxima.")
            break
        except Exception as e:
            journal.event(f"[error] {e}  -- reintentando en {poll}s")
            if tg:
                tg.send(msg_error(str(e)))

        time.sleep(poll)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        run_live()
