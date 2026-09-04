"""
backtest_partial_v2.py — Prueba cierre parcial (banco una parte al llegar a
75% del camino al TP, dejo el resto corriendo) sobre la base validada: SIN
trailing, con el motor REALISTA (SL/TP intravela + cooldown/una-vela).

No toca engine.py, engine_realistic.py, live_bot.py ni mt5_client.py.
Es de solo lectura.

Uso:
    python backtest_partial_v2.py
"""

import types
import config
from mt5_client import MT5Client
from engine import make_strategy, compute_metrics
from engine_realistic import pip_size, _spread_price, quote_factor, _unrealized, _BAR_SECONDS
import math


def clone_cfg(**overrides):
    ns = types.SimpleNamespace(**{k: v for k, v in vars(config).items() if not k.startswith("_")})
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def simulate_partial_realistic(cfg, times, highs, lows, closes, capital0=10000.0,
                                partial_pct=0.0, partial_r=0.75, breakeven_after_partial=True):
    """
    Motor realista (intravela + cooldown, sin trailing) + cierre parcial opcional.
    partial_r se expresa como FRACCION del camino a TP (0.75 = 75% del camino,
    o sea 0.75*TP_RR en R). partial_pct=0.0 -> sin parcial (control).
    """
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

        # ── Cierre parcial: chequeo intravela contra el precio-objetivo del
        #    parcial (75% del camino a TP), igual criterio que el SL/TP real ──
        if pos and partial_pct > 0 and not pos["partial_taken"]:
            trigger = (pos["entry"] + partial_r * pos["tp_dist"] if pos["dir"] == "LONG"
                       else pos["entry"] - partial_r * pos["tp_dist"])
            hit = (pos["dir"] == "LONG" and highs[i] >= trigger) or \
                  (pos["dir"] == "SHORT" and lows[i] <= trigger)
            if hit:
                part_units = pos["units"] * partial_pct
                if pos["dir"] == "LONG":
                    exit_price = trigger - half
                    part_gross = (exit_price - pos["entry"]) * part_units * pos["qf"]
                else:
                    exit_price = trigger + half
                    part_gross = (pos["entry"] - exit_price) * abs(part_units) * pos["qf"]
                cash += part_gross
                pos["realized"] += part_gross
                pos["units"] -= part_units
                pos["partial_taken"] = True
                if breakeven_after_partial:
                    if pos["dir"] == "LONG":
                        pos["sl"] = max(pos["sl"], pos["entry"])
                    else:
                        pos["sl"] = min(pos["sl"], pos["entry"])

        # ── Cierre total: SL/TP intravela (sin trailing, SL fijo salvo breakeven) ──
        if pos:
            reason, raw_exit = None, None
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
                total_pnl = pos["realized"] + gross
                trades.append({
                    "time": times[i], "dir": pos["dir"], "entry": pos["entry"],
                    "exit": exit_price, "pnl": total_pnl, "reason": reason,
                    "R": total_pnl / pos["risk"] if pos["risk"] else 0.0,
                })
                pos = None
                last_close_i = i

        if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
            cur_eq = cash + _unrealized(pos, price)
            if cur_eq <= day_start_equity * (1 - cfg.MAX_DAILY_LOSS):
                day_blocked = True

        if not pos and not (cfg.USE_CIRCUIT_BREAKER and day_blocked):
            blocked_same_bar = one_per_candle and (i == last_entry_i or i == last_close_i)
            in_cooldown = cooldown_bars and last_close_i is not None and (i - last_close_i) < cooldown_bars
            sig = strat.signal_at(i, closes, ind)
            if sig and (blocked_same_bar or in_cooldown):
                pass
            elif sig:
                sl_dist = abs(sig["entry"] - sig["sl"])
                tp_dist = abs(sig["tp"] - sig["entry"])
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
                           "risk": risk_amount, "tp_dist": tp_dist,
                           "partial_taken": False, "realized": 0.0}
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
        total_pnl = pos["realized"] + gross
        trades.append({"time": times[-1], "dir": pos["dir"], "entry": pos["entry"],
                        "exit": exit_price, "pnl": total_pnl, "reason": "CIERRE_FINAL",
                        "R": total_pnl / pos["risk"] if pos["risk"] else 0.0})

    bars_per_day = getattr(cfg, "BARS_PER_DAY", 24)
    metrics = compute_metrics(capital0, cash, trades, equity, closes, start, bars_per_day)
    metrics["blocked"] = blocked
    return {"trades": trades, "equity": equity, "final": cash, "metrics": metrics,
            "capital0": capital0, "start": start}


VARIANTS = [
    ("SIN parcial (control = config nueva)",        dict(partial_pct=0.0)),
    ("50% @ 75% del camino a TP + breakeven",        dict(partial_pct=0.5, partial_r=0.75, breakeven_after_partial=True)),
    ("50% @ 75% del camino, SIN breakeven",          dict(partial_pct=0.5, partial_r=0.75, breakeven_after_partial=False)),
    ("70% @ 75% del camino a TP + breakeven",        dict(partial_pct=0.7, partial_r=0.75, breakeven_after_partial=True)),
    ("50% @ 50% del camino a TP + breakeven",        dict(partial_pct=0.5, partial_r=0.50, breakeven_after_partial=True)),
]

HEADER = (f"{'Variante':<40}{'Retorno':>10}{'PF':>7}{'WinRate':>9}{'MaxDD':>8}{'Trades':>8}")


def fmt_row(name, res):
    m = res["metrics"]
    return (f"{name:<40}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}"
            f"{m['win_rate']:>8.1f}%{m['max_dd']:>7.2f}%{m['num_trades']:>8}")


def print_table(cfg, times, highs, lows, closes, capital0):
    print(HEADER)
    print("-" * len(HEADER))
    for name, kwargs in VARIANTS:
        res = simulate_partial_realistic(cfg, times, highs, lows, closes, capital0=capital0, **kwargs)
        print(fmt_row(name, res))


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    times, opens, highs, lows, closes = client.get_candles(config.INSTRUMENT, config.GRANULARITY, 90000)
    print(f"{len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})\n")

    cfg = clone_cfg(USE_TRAILING_STOP=False)  # la config nueva validada (sin trailing)

    print("=== Historico completo ===")
    print_table(cfg, times, highs, lows, closes, config.CAPITAL_INICIAL)

    n = len(closes)
    chunks = [(i * (n // 4), (i + 1) * (n // 4) if i < 3 else n) for i in range(4)]
    print("\n=== 4 tramos independientes (~11 meses c/u), solo control vs mejor candidato ===")
    for a, b in chunks:
        t, h, l, c = times[a:b], highs[a:b], lows[a:b], closes[a:b]
        print(f"\n--- {t[0][:10]} a {t[-1][:10]} ---")
        for name, kwargs in [VARIANTS[0], VARIANTS[1], VARIANTS[3]]:
            res = simulate_partial_realistic(cfg, t, h, l, c, capital0=10000, **kwargs)
            m = res["metrics"]
            print(f"  {name:<40} retorno={m['total_ret']:>+8.2f}%  PF={m['profit_factor']:.2f}  "
                  f"DD={m['max_dd']:.2f}%  trades={m['num_trades']}")

    n45 = 96 * 45
    print(f"\n=== Ultimos ~45 dias ===")
    print_table(cfg, times[-n45:], highs[-n45:], lows[-n45:], closes[-n45:], 10000)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        main()
