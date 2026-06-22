"""
live_bot_portfolio.py — Bot SMC DIVERSIFICADO en vivo (3 pares a la vez).

Opera EUR/USD + GBP/USD + NZD/USD simultáneamente, cada uno con sus parámetros.
Riesgo 0.35% del equity total por operación. Frenos FTMO sobre el equity TOTAL:
- Para todo el bot si la pérdida total toca -8% (antes del -10% que elimina en FTMO).
- Bloquea nuevas entradas el día si la pérdida diaria toca -4%.
- Para al alcanzar +10% (objetivo de fase).

Requiere MetaTrader 5 abierto y logueado en la cuenta correcta.

Uso:
    python live_bot_portfolio.py     (frenar con Ctrl + C)
"""

import time
from datetime import datetime, timezone
import config_portfolio as C
from mt5_client import MT5Client
from engine import make_strategy
from optimize import make_cfg
import journal


def _dir_of(trade):
    return "LONG" if float(trade["currentUnits"]) > 0 else "SHORT"


def run():
    client = MT5Client(C.MT5_LOGIN, C.MT5_PASSWORD, C.MT5_SERVER)
    journal.configure(getattr(C, "LOG_FILE", None), getattr(C, "TRADES_FILE", None))
    poll = getattr(C, "POLL_SECONDS", 60)

    # Una config + estrategia por par (con sus parámetros propios)
    pares = {}
    for par, params in C.PORTFOLIO.items():
        cfg_par = make_cfg(C, INSTRUMENT=par, **params)
        pares[par] = {"cfg": cfg_par, "strat": make_strategy(cfg_par)}

    use_trail = getattr(C, "USE_TRAILING_STOP", False)
    trail_mult = getattr(C, "TRAIL_ATR_MULT", 2.0)
    htf_need = getattr(C, "HTF_EMA_PERIOD", 200) + 60 if getattr(C, "USE_HTF_BIAS", False) else 120

    ftmo_cap = getattr(C, "FTMO_INITIAL_CAPITAL", None)
    max_total = getattr(C, "MAX_TOTAL_LOSS", None)
    profit_target = getattr(C, "PROFIT_TARGET", None)

    acc = client.get_account_summary()
    journal.event("=" * 60)
    journal.event(f"Bot PORTFOLIO iniciado. Cuenta {acc['id']} | Balance {acc['balance']} {acc['currency']}")
    journal.event(f"Pares: {', '.join(C.PORTFOLIO)} | Riesgo {C.RISK_PER_TRADE*100:.2f}% del total por trade")
    if ftmo_cap:
        journal.event(f"MODO FTMO: capital ${ftmo_cap:,.0f} | freno total -{max_total*100:.0f}% "
                      f"| diario -{C.MAX_DAILY_LOSS*100:.0f}% | objetivo +{profit_target*100:.0f}%")

    known = {}   # ticket -> trade info (para registrar cierres)
    for t in client.get_open_trades():
        if t["instrument"] in C.PORTFOLIO:
            known[t["id"]] = t
            journal.event(f"Posición preexistente: {t['instrument']} ticket {t['id']} {_dir_of(t)}")

    current_day = None
    day_start_equity = float(acc.get("equity", acc["balance"]))
    day_blocked = False

    while True:
        try:
            stamp = datetime.now().strftime("%H:%M:%S")
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            acc = client.get_account_summary()
            equity = float(acc.get("equity", acc["balance"]))

            # ── Frenos FTMO sobre el equity TOTAL ──
            if ftmo_cap and max_total and equity <= ftmo_cap * (1 - max_total):
                journal.event(f"[{stamp}] 🛑 FRENO TOTAL FTMO: equity ${equity:,.2f}. DETENIENDO el bot.")
                break
            if ftmo_cap and profit_target and equity >= ftmo_cap * (1 + profit_target):
                journal.event(f"[{stamp}] 🎯 OBJETIVO FTMO ALCANZADO: equity ${equity:,.2f}. DETENIENDO.")
                break

            if today != current_day:
                current_day = today
                day_start_equity = equity
                day_blocked = False
            if not day_blocked and ftmo_cap and \
               (day_start_equity - equity) >= C.MAX_DAILY_LOSS * ftmo_cap:
                day_blocked = True
                journal.event(f"[{stamp}] CIRCUIT BREAKER diario: sin nuevas entradas hoy.")

            # ── Posiciones abiertas de nuestros pares ──
            open_by_par = {}
            open_ids = set()
            for t in client.get_open_trades():
                if t["instrument"] in C.PORTFOLIO:
                    open_by_par[t["instrument"]] = t
                    open_ids.add(t["id"])

            # ── Registrar cierres (SL/TP/trailing) ──
            for tid in list(known):
                if tid not in open_ids:
                    info = known.pop(tid)
                    res = client.get_deal_result(tid)
                    pnl = res["pnl"] if res else ""
                    journal.trade({
                        "accion": "CERRADA", "instrumento": info["instrument"],
                        "direccion": _dir_of(info), "lotes": info.get("volume", ""),
                        "precio": res["exit_price"] if res and res["exit_price"] else "",
                        "pnl": pnl, "balance": equity, "ticket": tid, "motivo": "SL/TP/trailing",
                    })
                    pnl_s = f"{pnl:+.2f}" if isinstance(pnl, (int, float)) else "?"
                    journal.event(f"[{stamp}] CERRADA {info['instrument']} {tid} | PnL {pnl_s}")

            # ── Procesar cada par ──
            for par, pdata in pares.items():
                strat = pdata["strat"]
                times, o, h, l, cl = client.get_candles(par, C.GRANULARITY, htf_need)
                ind = strat.compute_indicators(h, l, cl)
                i = len(cl) - 1
                price = cl[i]
                trade = open_by_par.get(par)

                if trade:
                    known[trade["id"]] = trade
                    if use_trail and ind["atr"][i] is not None:
                        is_long = float(trade["currentUnits"]) > 0
                        dist = trail_mult * ind["atr"][i]
                        cur_sl = trade["sl"]
                        new_sl = None
                        if is_long and price - dist > cur_sl:
                            new_sl = price - dist
                        elif not is_long and (cur_sl == 0 or price + dist < cur_sl):
                            new_sl = price + dist
                        if new_sl is not None:
                            client.modify_stop_loss(trade["id"], new_sl, trade["tp"])
                            journal.event(f"[{stamp}] {par} trailing: SL -> {new_sl:.5f}")
                elif not day_blocked:
                    sig = strat.signal_at(i, cl, ind)
                    if sig:
                        sl_dist = abs(sig["entry"] - sig["sl"])
                        risk_amount = equity * C.RISK_PER_TRADE
                        lots, real_risk = client.calc_lots(par, risk_amount, sl_dist)
                        if lots > 0:
                            r = client.place_market_order(par, sig["dir"], lots,
                                                          stop_loss=sig["sl"], take_profit=sig["tp"])
                            journal.trade({
                                "accion": "ABIERTA", "instrumento": par, "direccion": sig["dir"],
                                "lotes": lots, "precio": round(sig["entry"], 5),
                                "sl": round(sig["sl"], 5), "tp": round(sig["tp"], 5),
                                "riesgo_usd": round(real_risk, 2), "balance": equity,
                                "ticket": r.get("id", ""), "motivo": "señal SMC",
                            })
                            journal.event(f"[{stamp}] ABIERTA {par} {sig['dir']} {lots} lotes "
                                          f"@ {sig['entry']:.5f} | riesgo ${real_risk:.2f}")

            journal.event(f"[{stamp}] equity ${equity:,.2f} | posiciones abiertas: {len(open_by_par)}",
                          also_print=False)

        except KeyboardInterrupt:
            journal.event("Bot detenido por el usuario.")
            break
        except Exception as e:
            journal.event(f"[error] {e}  -- reintentando en {poll}s")

        time.sleep(poll)


if __name__ == "__main__":
    if C.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run()
