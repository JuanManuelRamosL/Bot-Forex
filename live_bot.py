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

import time
from datetime import datetime, timezone
import config
from mt5_client import MT5Client
from strategy import MeanReversionStrategy
import journal

POLL_SECONDS = 300  # revisar el mercado cada 5 minutos


def _dir_of(trade):
    return "LONG" if float(trade["currentUnits"]) > 0 else "SHORT"


def run_live(cfg=config):
    poll = getattr(cfg, "POLL_SECONDS", POLL_SECONDS)
    journal.configure(getattr(cfg, "LOG_FILE", None), getattr(cfg, "TRADES_FILE", None))
    client = MT5Client(cfg.MT5_LOGIN, cfg.MT5_PASSWORD, cfg.MT5_SERVER)
    strat = MeanReversionStrategy(cfg)

    acc = client.get_account_summary()
    tp_mode = getattr(cfg, "TP_MODE", "mean")
    journal.event("=" * 60)
    journal.event(f"Bot iniciado. Conectado a MT5. Cuenta {acc['id']} | "
                  f"Balance {acc['balance']} {acc['currency']}")
    journal.event(f"Operando {cfg.INSTRUMENT} en {cfg.GRANULARITY} | "
                  f"Riesgo {cfg.RISK_PER_TRADE*100:.0f}% | TP={tp_mode}"
                  + (f" (R:R {cfg.TP_RR})" if tp_mode == "rr" else ""))
    if getattr(cfg, "USE_TRAILING_STOP", False):
        journal.event(f"Trailing stop ACTIVO (ATR x {cfg.TRAIL_ATR_MULT})")
    if cfg.USE_REGIME_FILTER:
        journal.event(f"Filtro de régimen ACTIVO (ADX < {cfg.ADX_MAX})")
    if cfg.USE_CIRCUIT_BREAKER:
        journal.event(f"Circuit breaker ACTIVO (freno al perder {cfg.MAX_DAILY_LOSS*100:.0f}% diario)")

    # Posiciones ya abiertas al arrancar (para seguir su cierre y registrarlo)
    known = {}
    for t in client.get_open_trades():
        if t["instrument"] == cfg.INSTRUMENT:
            known[t["id"]] = t
            journal.event(f"Posición preexistente detectada: ticket {t['id']} {_dir_of(t)}")

    current_day = None
    day_start_balance = float(acc["balance"])
    day_blocked = False

    while True:
        try:
            stamp = datetime.now().strftime("%H:%M:%S")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

            acc = client.get_account_summary()
            balance = float(acc["balance"])

            if today != current_day:
                current_day = today
                day_start_balance = balance
                day_blocked = False

            if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
                if balance <= day_start_balance * (1 - cfg.MAX_DAILY_LOSS):
                    day_blocked = True
                    journal.event(f"[{stamp}] CIRCUIT BREAKER activado: pérdida diaria > "
                                  f"{cfg.MAX_DAILY_LOSS*100:.0f}%. No se abren más trades hoy.")

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
                    journal.trade({
                        "accion": "CERRADA", "instrumento": cfg.INSTRUMENT,
                        "direccion": _dir_of(info), "lotes": info.get("volume", ""),
                        "precio": exit_price, "sl": "", "tp": "",
                        "riesgo_usd": "", "pnl": pnl, "balance": balance,
                        "ticket": tid, "motivo": "SL/TP/trailing",
                    })
                    pnl_str = f"{pnl:+.2f}" if isinstance(pnl, (int, float)) else "?"
                    journal.event(f"[{stamp}] CERRADA posición {tid} ({_dir_of(info)}) | PnL {pnl_str}")

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
            else:
                sig = strat.signal_at(i, closes, ind)
                if sig:
                    sl_dist = abs(sig["entry"] - sig["sl"])
                    risk_amount = balance * cfg.RISK_PER_TRADE
                    lots, real_risk = client.calc_lots(cfg.INSTRUMENT, risk_amount, sl_dist)
                    if lots > 0:
                        r = client.place_market_order(
                            cfg.INSTRUMENT, sig["dir"], lots,
                            stop_loss=sig["sl"], take_profit=sig["tp"],
                        )
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
                    else:
                        journal.event(f"[{stamp}] Señal {sig['dir']} pero lotes=0. Salteando.")
                else:
                    adx_now = ind["adx"][i]
                    rsi_now = ind["rsi"][i]
                    adx_str = f"{adx_now:.0f}" if adx_now is not None else "--"
                    journal.event(f"[{stamp}] Sin señal. Precio {price:.5f}  RSI {rsi_now:.0f}  ADX {adx_str}")

        except KeyboardInterrupt:
            journal.event("Bot detenido por el usuario.")
            break
        except Exception as e:
            journal.event(f"[error] {e}  -- reintentando en {poll}s")

        time.sleep(poll)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        run_live()
