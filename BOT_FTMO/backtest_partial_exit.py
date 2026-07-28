"""
backtest_partial_exit.py — Prueba la idea de CIERRE PARCIAL: banco una parte de
la posicion al llegar a cierto R (ej. 50% al llegar a +1R) y muevo el stop del
resto a breakeven, dejando que el resto siga al TP/trailing normal.

Es un cambio mas grande que ajustar un multiplicador, asi que en vez de tocar
engine.py directamente, esta es una COPIA del motor (simulate_partial) con la
logica de parcial agregada. No toca engine.py, live_bot.py ni mt5_client.py.
Es de solo lectura: no ejecuta ninguna orden real.

Uso:
    python backtest_partial_exit.py
"""

import types
import config
from mt5_client import MT5Client
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


def clone_cfg(**overrides):
    ns = types.SimpleNamespace(**{k: v for k, v in vars(config).items() if not k.startswith("_")})
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def simulate_partial(cfg, times, highs, lows, closes, capital0=10000.0,
                      partial_pct=0.0, partial_r=1.0, breakeven_after_partial=True):
    """
    Igual logica que engine.simulate(), con un cierre parcial agregado:
    - partial_pct=0.0 -> se comporta EXACTO igual que engine.simulate() (control).
    - partial_pct>0.0 -> al llegar a +partial_r*R a favor, cierra partial_pct de
      las unidades y (si breakeven_after_partial) mueve el SL del resto a la
      entrada. El resto sigue al TP/trailing normal.
    """
    strat = make_strategy(cfg)
    ind = strat.compute_indicators(highs, lows, closes)
    pip = pip_size(cfg.INSTRUMENT)
    spread = _spread_price(cfg)
    half = spread / 2.0

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

    for i in range(start, len(closes)):
        price = closes[i]
        today = times[i][:10]
        if today != current_day:
            current_day = today
            day_start_equity = cash
            day_blocked = False

        # ── Cierre parcial (antes del trailing, para fijar breakeven primero) ──
        if pos and partial_pct > 0 and not pos["partial_taken"]:
            trigger = (pos["entry"] + partial_r * pos["sl_dist"] if pos["dir"] == "LONG"
                       else pos["entry"] - partial_r * pos["sl_dist"])
            hit = (pos["dir"] == "LONG" and price >= trigger) or \
                  (pos["dir"] == "SHORT" and price <= trigger)
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

        # ── Cierre total del resto de la posicion ──
        if pos:
            reason = strat.should_exit(pos, price, ind["mid"][i])
            if reason:
                if reason == "STOP_LOSS":
                    raw_exit = pos["sl"]
                elif (pos["dir"] == "LONG" and price >= pos["tp"]) or \
                     (pos["dir"] == "SHORT" and price <= pos["tp"]):
                    raw_exit = pos["tp"]
                else:
                    raw_exit = price
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
                    "partial_taken": pos["partial_taken"],
                })
                pos = None

        if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
            cur_eq = cash + _unrealized(pos, price)
            if cur_eq <= day_start_equity * (1 - cfg.MAX_DAILY_LOSS):
                day_blocked = True

        if not pos and not (cfg.USE_CIRCUIT_BREAKER and day_blocked):
            sig = strat.signal_at(i, closes, ind)
            if sig:
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
                           "risk": risk_amount, "sl_dist": sl_dist,
                           "partial_taken": False, "realized": 0.0}
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
                        "R": total_pnl / pos["risk"] if pos["risk"] else 0.0,
                        "partial_taken": pos["partial_taken"]})

    bars_per_day = getattr(cfg, "BARS_PER_DAY", 24)
    metrics = compute_metrics(capital0, cash, trades, equity, closes, start, bars_per_day)
    metrics["blocked"] = blocked
    return {"trades": trades, "equity": equity, "final": cash, "metrics": metrics,
            "capital0": capital0, "start": start}


VARIANTS = [
    ("SIN parcial (control, = config actual)", dict(partial_pct=0.0)),
    ("50% @ +1.0R + breakeven",                dict(partial_pct=0.5, partial_r=1.0, breakeven_after_partial=True)),
    ("50% @ +1.5R + breakeven",                dict(partial_pct=0.5, partial_r=1.5, breakeven_after_partial=True)),
    ("33% @ +1.0R + breakeven",                dict(partial_pct=0.33, partial_r=1.0, breakeven_after_partial=True)),
    ("50% @ +1.0R, SIN breakeven",             dict(partial_pct=0.5, partial_r=1.0, breakeven_after_partial=False)),
    ("70% @ +1.0R + breakeven",                dict(partial_pct=0.7, partial_r=1.0, breakeven_after_partial=True)),
]

HEADER = (f"{'Variante':<34}{'Retorno':>10}{'PF':>7}{'WinRate':>9}"
          f"{'R:R':>7}{'MaxDD':>8}{'Trades':>8}")


def fmt_row(name, res):
    m = res["metrics"]
    return (f"{name:<34}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}"
            f"{m['win_rate']:>8.1f}%{m['rr']:>7.2f}{m['max_dd']:>7.2f}%{m['num_trades']:>8}")


def print_table(cfg_base, times, highs, lows, closes, capital0):
    print(HEADER)
    print("-" * len(HEADER))
    for name, kwargs in VARIANTS:
        res = simulate_partial(cfg_base, times, highs, lows, closes, capital0=capital0, **kwargs)
        print(fmt_row(name, res))


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    print(f"Bajando {config.BACKTEST_CANDLES} velas de {config.INSTRUMENT} ({config.GRANULARITY})...")
    # Usamos un pedido grande fijo (90000) para el historico completo, sin depender
    # de lo que haya quedado seteado en config.BACKTEST_CANDLES para otras pruebas.
    times, opens, highs, lows, closes = client.get_candles(config.INSTRUMENT, config.GRANULARITY, 90000)
    print(f"Listo. {len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})\n")

    cfg = clone_cfg()  # config actual (trailing 1.5, rr 3:1)

    print("=== Historico completo ===")
    print_table(cfg, times, highs, lows, closes, config.CAPITAL_INICIAL)

    n_recent = 96 * 30
    print(f"\n=== Solo las ultimas {n_recent} velas (~30 dias) ===")
    print_table(cfg, times[-n_recent:], highs[-n_recent:], lows[-n_recent:], closes[-n_recent:],
                config.CAPITAL_INICIAL)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        main()
