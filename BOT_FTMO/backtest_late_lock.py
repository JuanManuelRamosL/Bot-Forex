"""
backtest_late_lock.py — Prueba mover el SL UNA SOLA VEZ (no trailing continuo)
cuando el precio recorre el 75% del camino al TP, a un nivel que asegura una
ganancia minima (ej. +4% del riesgo original), sobre la base validada: SIN
trailing ATR, motor realista (SL/TP intravela + cooldown).

No toca engine.py, engine_realistic.py, live_bot.py. Solo lectura.
"""
import types
import math
import config
from mt5_client import MT5Client
from engine import make_strategy, compute_metrics
from engine_realistic import pip_size, _spread_price, quote_factor, _unrealized, _BAR_SECONDS


def clone_cfg(**overrides):
    ns = types.SimpleNamespace(**{k: v for k, v in vars(config).items() if not k.startswith("_")})
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


def simulate_late_lock(cfg, times, highs, lows, closes, capital0=10000.0,
                        lock_trigger_r=0.0, lock_level_r=0.0):
    """lock_trigger_r y lock_level_r en fraccion de R (1R = distancia al SL original).
    lock_trigger_r=0 -> sin lock (control)."""
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
    start = max(cfg.BB_PERIOD, cfg.ATR_PERIOD, cfg.RSI_PERIOD, 2 * cfg.ADX_PERIOD + 1) + 1
    last_entry_i = None
    last_close_i = None

    for i in range(start, len(closes)):
        price = closes[i]
        today = times[i][:10]
        if today != current_day:
            current_day = today
            day_start_equity = cash
            day_blocked = False

        if pos and lock_trigger_r > 0 and not pos["locked"]:
            trigger = (pos["entry"] + lock_trigger_r * pos["sl_dist"] if pos["dir"] == "LONG"
                       else pos["entry"] - lock_trigger_r * pos["sl_dist"])
            hit = (pos["dir"] == "LONG" and highs[i] >= trigger) or \
                  (pos["dir"] == "SHORT" and lows[i] <= trigger)
            if hit:
                new_sl = (pos["entry"] + lock_level_r * pos["sl_dist"] if pos["dir"] == "LONG"
                          else pos["entry"] - lock_level_r * pos["sl_dist"])
                pos["sl"] = new_sl
                pos["locked"] = True

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
            if reason:
                if pos["dir"] == "LONG":
                    exit_price = raw_exit - half
                    gross = (exit_price - pos["entry"]) * pos["units"] * pos["qf"]
                else:
                    exit_price = raw_exit + half
                    gross = (pos["entry"] - exit_price) * abs(pos["units"]) * pos["qf"]
                cash += gross
                trades.append({"time": times[i], "dir": pos["dir"], "pnl": gross,
                                "reason": reason, "R": gross / pos["risk"] if pos["risk"] else 0.0})
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
                if sl_dist > 0:
                    risk_amount = cash * cfg.RISK_PER_TRADE
                    qf = quote_factor(cfg.INSTRUMENT, sig["entry"])
                    units = risk_amount / (sl_dist * qf)
                    entry = sig["entry"] + half if sig["dir"] == "LONG" else sig["entry"] - half
                    if sig["dir"] == "SHORT":
                        units = -units
                    pos = {"dir": sig["dir"], "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                           "units": units, "qf": qf, "risk": risk_amount, "sl_dist": sl_dist,
                           "locked": False}
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
        trades.append({"time": times[-1], "dir": pos["dir"], "pnl": gross, "reason": "CIERRE_FINAL",
                        "R": gross / pos["risk"] if pos["risk"] else 0.0})

    bars_per_day = getattr(cfg, "BARS_PER_DAY", 24)
    metrics = compute_metrics(capital0, cash, trades, equity, closes, start, bars_per_day)
    metrics["blocked"] = blocked
    return {"trades": trades, "equity": equity, "final": cash, "metrics": metrics, "start": start}


VARIANTS = [
    ("Control (sin lock)",                      dict(lock_trigger_r=0.0, lock_level_r=0.0)),
    ("Lock a breakeven (0%) @ 75% del camino",  dict(lock_trigger_r=2.25, lock_level_r=0.0)),
    ("Lock a +4% del riesgo @ 75% del camino",  dict(lock_trigger_r=2.25, lock_level_r=0.04)),
    ("Lock a +10% del riesgo @ 75% del camino", dict(lock_trigger_r=2.25, lock_level_r=0.10)),
    ("Lock a +4% del riesgo @ 50% del camino",  dict(lock_trigger_r=1.50, lock_level_r=0.04)),
    ("Lock a +4% del riesgo @ 90% del camino",  dict(lock_trigger_r=2.70, lock_level_r=0.04)),
]

HEADER = f"{'Variante':<40}{'Retorno':>10}{'PF':>7}{'WinRate':>9}{'MaxDD':>8}{'Trades':>8}"


def fmt(name, res):
    m = res["metrics"]
    wr = sum(1 for t in res["trades"] if t["pnl"] > 0) / len(res["trades"]) * 100 if res["trades"] else 0
    return f"{name:<40}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}{wr:>8.1f}%{m['max_dd']:>7.2f}%{m['num_trades']:>8}"


def print_table(cfg, times, highs, lows, closes, capital0):
    print(HEADER)
    print("-" * len(HEADER))
    for name, kwargs in VARIANTS:
        res = simulate_late_lock(cfg, times, highs, lows, closes, capital0=capital0, **kwargs)
        print(fmt(name, res))


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    times, opens, highs, lows, closes = client.get_candles(config.INSTRUMENT, config.GRANULARITY, 90000)
    print(f"{len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})\n")
    cfg = clone_cfg(USE_TRAILING_STOP=False)

    print("=== Historico completo ===")
    print_table(cfg, times, highs, lows, closes, 10000)

    n = len(closes)
    chunks = [(i * (n // 4), (i + 1) * (n // 4) if i < 3 else n) for i in range(4)]
    print("\n=== 4 tramos independientes ===")
    for a, b in chunks:
        t, h, l, c = times[a:b], highs[a:b], lows[a:b], closes[a:b]
        print(f"\n--- {t[0][:10]} a {t[-1][:10]} ---")
        for name, kwargs in [VARIANTS[0], VARIANTS[2]]:
            res = simulate_late_lock(cfg, t, h, l, c, capital0=10000, **kwargs)
            m = res["metrics"]
            print(f"  {name:<40} retorno={m['total_ret']:>+8.2f}%  PF={m['profit_factor']:.2f}  "
                  f"DD={m['max_dd']:.2f}%  trades={m['num_trades']}")

    n45 = 96 * 45
    print(f"\n=== Ultimos 45 dias ===")
    print_table(cfg, times[-n45:], highs[-n45:], lows[-n45:], closes[-n45:], 10000)


if __name__ == "__main__":
    main()
