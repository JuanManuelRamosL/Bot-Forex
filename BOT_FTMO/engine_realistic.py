"""
engine_realistic.py — Copia de engine.simulate() con dos correcciones para que
el backtest sea fiel a lo que REALMENTE hace live_bot.py:

1. Cooldown / una operacion por vela: engine.simulate() no lo modela (permite
   reentrar en la misma vela apenas cierra), pero live_bot.py SI lo aplica
   (ONE_TRADE_PER_CANDLE, REENTRY_COOLDOWN_SECONDS). Sin esto, el backtest
   sobre-opera respecto a lo real y las secuencias divergen desde el primer
   trade (ya lo confirmamos varias veces comparando ventanas reales).

2. SL/TP intravela: engine.simulate() solo mira closes[i] para decidir si se
   toco el stop o el take-profit. En la realidad el SL/TP es una orden puesta
   en el broker que se dispara apenas el precio la toca (con highs/lows, no
   solo al cierre de la vela). Esto puede hacer que el backtest se pierda
   cierres que si pasaron en la cuenta real.

No toca engine.py, live_bot.py ni mt5_client.py. Es de solo lectura.
"""

import math
from engine import make_strategy, compute_metrics


def pip_size(instrument):
    return 0.01 if "JPY" in instrument else 0.0001


def _spread_price(cfg):
    pips = cfg.SPREAD_PIPS.get(cfg.INSTRUMENT, cfg.DEFAULT_SPREAD_PIPS)
    return pips * pip_size(cfg.INSTRUMENT)


def quote_factor(instrument, price):
    if instrument.startswith("USD_") and price:
        return 1.0 / price
    return 1.0


def _unrealized(pos, price):
    if not pos:
        return 0.0
    if pos["dir"] == "LONG":
        return (price - pos["entry"]) * pos["units"] * pos["qf"]
    return (pos["entry"] - price) * abs(pos["units"]) * pos["qf"]


_BAR_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D": 86400}


def simulate_realistic(cfg, times, highs, lows, closes, capital0=10000.0):
    strat = make_strategy(cfg)
    ind = strat.compute_indicators(highs, lows, closes)
    pip = pip_size(cfg.INSTRUMENT)
    spread = _spread_price(cfg)
    half = spread / 2.0

    bar_seconds = _BAR_SECONDS.get(cfg.GRANULARITY, 900)
    one_per_candle = getattr(cfg, "ONE_TRADE_PER_CANDLE", True)
    cooldown_s = getattr(cfg, "REENTRY_COOLDOWN_SECONDS", 0)
    cooldown_bars = math.ceil(cooldown_s / bar_seconds) if cooldown_s else 0

    cash = capital0
    pos = None
    trades = []
    equity = []
    blocked = 0

    current_day = None
    day_start_equity = capital0
    day_blocked = False

    use_trail = getattr(cfg, "USE_TRAILING_STOP", False)
    trail_mult = getattr(cfg, "TRAIL_ATR_MULT", 2.0)

    start = max(cfg.BB_PERIOD, cfg.ATR_PERIOD, cfg.RSI_PERIOD, 2 * cfg.ADX_PERIOD + 1)
    if getattr(cfg, "USE_TREND_FILTER", False):
        start = max(start, getattr(cfg, "TREND_EMA_PERIOD", 200))
    start += 1

    last_entry_i = None
    last_close_i = None

    for i in range(start, len(closes)):
        price = closes[i]
        today = times[i][:10]
        if today != current_day:
            current_day = today
            day_start_equity = cash
            day_blocked = False

        # ── Trailing stop (igual que engine.simulate) ──
        if pos and use_trail and ind["atr"][i] is not None:
            dist = trail_mult * ind["atr"][i]
            if pos["dir"] == "LONG":
                new_sl = price - dist
                if new_sl > pos["sl"]:
                    pos["sl"] = new_sl
            else:
                new_sl = price + dist
                if new_sl < pos["sl"]:
                    pos["sl"] = new_sl

        # ── Cierre: SL/TP chequeados con el rango intravela (high/low), no
        #    solo el close. Empate SL+TP en la misma vela -> asumimos SL
        #    primero (regla conservadora estandar de backtesting). El exit
        #    por "vuelta a la media" (modo mean) sigue siendo por close,
        #    porque conceptualmente es una condicion de cierre, no una orden
        #    puesta en el broker.
        if pos:
            reason = None
            raw_exit = None
            if pos["dir"] == "LONG":
                if lows[i] <= pos["sl"]:
                    reason, raw_exit = "STOP_LOSS", pos["sl"]
                elif highs[i] >= pos["tp"]:
                    reason, raw_exit = "TAKE_PROFIT", pos["tp"]
            else:
                if highs[i] >= pos["sl"]:
                    reason, raw_exit = "STOP_LOSS", pos["sl"]
                elif lows[i] <= pos["tp"]:
                    reason, raw_exit = "TAKE_PROFIT", pos["tp"]
            if reason is None:
                mean_exit = getattr(cfg, "TP_MODE", "mean") == "mean"
                mid_now = ind["mid"][i]
                if mean_exit and mid_now:
                    if (pos["dir"] == "LONG" and price >= mid_now) or \
                       (pos["dir"] == "SHORT" and price <= mid_now):
                        reason, raw_exit = "TAKE_PROFIT", price

            if reason:
                if pos["dir"] == "LONG":
                    exit_price = raw_exit - half
                    gross = (exit_price - pos["entry"]) * pos["units"] * pos["qf"]
                else:
                    exit_price = raw_exit + half
                    gross = (pos["entry"] - exit_price) * abs(pos["units"]) * pos["qf"]
                cash += gross
                pips = ((exit_price - pos["entry"]) if pos["dir"] == "LONG"
                        else (pos["entry"] - exit_price)) / pip
                trades.append({
                    "time": times[i], "dir": pos["dir"], "entry": pos["entry"],
                    "exit": exit_price, "pnl": gross, "pips": pips, "reason": reason,
                    "bars": i - pos["entry_i"],
                    "R": gross / pos["risk"] if pos["risk"] else 0.0,
                })
                pos = None
                last_close_i = i

        if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
            cur_eq = cash + _unrealized(pos, price)
            if cur_eq <= day_start_equity * (1 - cfg.MAX_DAILY_LOSS):
                day_blocked = True

        # ── Abrir: ahora respeta "una operacion por vela" + cooldown, igual
        #    que live_bot.py (bloqueado_misma_vela / en_cooldown) ──
        if not pos and not (cfg.USE_CIRCUIT_BREAKER and day_blocked):
            blocked_same_bar = one_per_candle and (i == last_entry_i or i == last_close_i)
            in_cooldown = cooldown_bars and last_close_i is not None and (i - last_close_i) < cooldown_bars
            sig = strat.signal_at(i, closes, ind)
            if sig and (blocked_same_bar or in_cooldown):
                pass  # señal descartada por anti-sobreoperacion, igual que en vivo
            elif sig:
                sl_dist = abs(sig["entry"] - sig["sl"])
                if sl_dist > 0:
                    risk_amount = cash * cfg.RISK_PER_TRADE
                    qf = quote_factor(cfg.INSTRUMENT, sig["entry"])
                    units = risk_amount / (sl_dist * qf)
                    if sig["dir"] == "LONG":
                        entry = sig["entry"] + half
                    else:
                        entry = sig["entry"] - half
                        units = -units
                    pos = {"dir": sig["dir"], "entry": entry, "entry_i": i,
                           "sl": sig["sl"], "tp": sig["tp"], "units": units, "qf": qf,
                           "risk": risk_amount}
                    last_entry_i = i
        elif not pos and cfg.USE_CIRCUIT_BREAKER and day_blocked:
            if strat.signal_at(i, closes, ind):
                blocked += 1

        equity.append(cash + _unrealized(pos, price))

    if pos:
        price = closes[-1]
        if pos["dir"] == "LONG":
            exit_price = price - half
            gross = (exit_price - pos["entry"]) * pos["units"] * pos["qf"]
        else:
            exit_price = price + half
            gross = (pos["entry"] - exit_price) * abs(pos["units"]) * pos["qf"]
        cash += gross
        pips = ((exit_price - pos["entry"]) if pos["dir"] == "LONG"
                else (pos["entry"] - exit_price)) / pip
        trades.append({
            "time": times[-1], "dir": pos["dir"], "entry": pos["entry"],
            "exit": exit_price, "pnl": gross, "pips": pips, "reason": "CIERRE_FINAL",
            "bars": (len(closes) - 1) - pos["entry_i"],
            "R": gross / pos["risk"] if pos["risk"] else 0.0,
        })

    bars_per_day = getattr(cfg, "BARS_PER_DAY", 24)
    metrics = compute_metrics(capital0, cash, trades, equity, closes, start, bars_per_day)
    metrics["blocked"] = blocked
    return {"trades": trades, "equity": equity, "final": cash, "metrics": metrics,
            "capital0": capital0, "start": start}
