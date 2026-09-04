"""
backtest_hybrid_regime.py — Prueba un enfoque HIBRIDO por regimen: mean
reversion cuando ADX < ADX_MAX (rango, como ahora), y una señal de
TREND-FOLLOWING real (pullback a la media dentro de una tendencia confirmada
por EMA) cuando ADX >= ADX_MAX — en vez de quedarse afuera del mercado esos
períodos, como hace la config actual.

Basado en literatura de regime-switching en FX (mean reversion en rango,
trend-following en tendencia). Se compara contra la mejor config validada
hasta ahora: mean reversion sola, sin trailing, TP_RR=4.5, SL=2.5.

No toca engine.py, engine_realistic.py, strategy.py ni live_bot.py. Solo lectura.

Uso:
    python backtest_hybrid_regime.py
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


def hybrid_signal(cfg, ind, i, closes, trend_ema_period_tag="ema"):
    price = closes[i]
    prev_price = closes[i - 1]
    u, lo, m, a, r = ind["upper"][i], ind["lower"][i], ind["mid"][i], ind["atr"][i], ind["rsi"][i]
    adx_now = ind["adx"][i]
    ema_now = ind[trend_ema_period_tag][i]
    prev_m = ind["mid"][i - 1]
    if None in (u, lo, m, a, r, adx_now, ema_now, prev_m):
        return None

    sl_dist = cfg.ATR_SL_MULT * a
    rr = getattr(cfg, "TP_RR", 1.5)

    if adx_now < cfg.ADX_MAX:
        # Regimen de rango: mean reversion normal (igual que la estrategia actual)
        if price <= lo and r < cfg.RSI_LONG_MAX:
            tp = price + rr * sl_dist
            return {"dir": "LONG", "entry": price, "sl": price - sl_dist, "tp": tp}
        if price >= u and r > cfg.RSI_SHORT_MIN:
            tp = price - rr * sl_dist
            return {"dir": "SHORT", "entry": price, "sl": price + sl_dist, "tp": tp}
        return None
    else:
        # Regimen de tendencia fuerte: antes el bot no operaba nada aca.
        # Trend-following: pullback a la media (BB mid) dentro de una
        # tendencia confirmada por la EMA larga.
        if price > ema_now and prev_price > prev_m and price <= m:
            tp = price + rr * sl_dist
            return {"dir": "LONG", "entry": price, "sl": price - sl_dist, "tp": tp}
        if price < ema_now and prev_price < prev_m and price >= m:
            tp = price - rr * sl_dist
            return {"dir": "SHORT", "entry": price, "sl": price + sl_dist, "tp": tp}
        return None


def simulate_hybrid(cfg, times, highs, lows, closes, capital0=10000.0, use_hybrid=True, trend_ema="ema"):
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
    start = max(cfg.BB_PERIOD, cfg.ATR_PERIOD, cfg.RSI_PERIOD, 2 * cfg.ADX_PERIOD + 1,
                getattr(cfg, "TREND_EMA_PERIOD", 200)) + 1
    last_entry_i = None
    last_close_i = None

    for i in range(start, len(closes)):
        price = closes[i]
        today = times[i][:10]
        if today != current_day:
            current_day = today
            day_start_equity = cash
            day_blocked = False

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
                trades.append({"time": times[i], "dir": pos["dir"], "pnl": gross, "reason": reason,
                                "regime": pos["regime"], "R": gross / pos["risk"] if pos["risk"] else 0.0})
                pos = None
                last_close_i = i

        if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
            cur_eq = cash + _unrealized(pos, price)
            if cur_eq <= day_start_equity * (1 - cfg.MAX_DAILY_LOSS):
                day_blocked = True

        if not pos and not (cfg.USE_CIRCUIT_BREAKER and day_blocked):
            blocked_same_bar = one_per_candle and (i == last_entry_i or i == last_close_i)
            in_cooldown = cooldown_bars and last_close_i is not None and (i - last_close_i) < cooldown_bars
            if use_hybrid:
                sig = hybrid_signal(cfg, ind, i, closes, trend_ema)
            else:
                sig = strat.signal_at(i, closes, ind)
            if sig and not (blocked_same_bar or in_cooldown):
                sl_dist = abs(sig["entry"] - sig["sl"])
                if sl_dist > 0:
                    risk_amount = cash * cfg.RISK_PER_TRADE
                    qf = quote_factor(cfg.INSTRUMENT, sig["entry"])
                    units = risk_amount / (sl_dist * qf)
                    entry = sig["entry"] + half if sig["dir"] == "LONG" else sig["entry"] - half
                    if sig["dir"] == "SHORT":
                        units = -units
                    regime = "rango" if (ind["adx"][i] is not None and ind["adx"][i] < cfg.ADX_MAX) else "tendencia"
                    pos = {"dir": sig["dir"], "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                           "units": units, "qf": qf, "risk": risk_amount, "regime": regime}
                    last_entry_i = i
        elif not pos and cfg.USE_CIRCUIT_BREAKER and day_blocked:
            sig = hybrid_signal(cfg, ind, i, closes, trend_ema) if use_hybrid else strat.signal_at(i, closes, ind)
            if sig:
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
                        "regime": pos["regime"], "R": gross / pos["risk"] if pos["risk"] else 0.0})

    bars_per_day = getattr(cfg, "BARS_PER_DAY", 24)
    metrics = compute_metrics(capital0, cash, trades, equity, closes, start, bars_per_day)
    metrics["blocked"] = blocked
    return {"trades": trades, "equity": equity, "final": cash, "metrics": metrics, "start": start}


def fmt(name, res):
    m = res["metrics"]
    trend_trades = [t for t in res["trades"] if t.get("regime") == "tendencia"]
    tw = sum(1 for t in trend_trades if t["pnl"] > 0)
    return (f"{name:<38}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}{m['win_rate']:>8.1f}%"
            f"{m['max_dd']:>7.2f}%{m['num_trades']:>8}   (trades de tendencia: {len(trend_trades)}, "
            f"ganados: {tw})")


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    times, opens, highs, lows, closes = client.get_candles(config.INSTRUMENT, config.GRANULARITY, 90000)
    print(f"{len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})\n")

    base = clone_cfg(USE_TRAILING_STOP=False, TP_RR=4.5, USE_TREND_FILTER=True, TREND_EMA_PERIOD=100)
    base50 = clone_cfg(USE_TRAILING_STOP=False, TP_RR=4.5, USE_TREND_FILTER=True, TREND_EMA_PERIOD=50)
    base_control = clone_cfg(USE_TRAILING_STOP=False, TP_RR=4.5)

    print("=== Historico completo ===")
    print(fmt("Solo mean reversion (actual, TP 4.5)", simulate_hybrid(base_control, times, highs, lows, closes, use_hybrid=False)))
    print(fmt("Hibrido: MR + trend-follow (EMA100)", simulate_hybrid(base, times, highs, lows, closes, use_hybrid=True, trend_ema="ema")))
    print(fmt("Hibrido: MR + trend-follow (EMA50)", simulate_hybrid(base50, times, highs, lows, closes, use_hybrid=True, trend_ema="ema")))

    n = len(closes)
    chunks = [(i * (n // 4), (i + 1) * (n // 4) if i < 3 else n) for i in range(4)]
    print("\n=== 4 tramos independientes ===")
    for a, b in chunks:
        t, h, l, c = times[a:b], highs[a:b], lows[a:b], closes[a:b]
        print(f"\n--- {t[0][:10]} a {t[-1][:10]} ---")
        r1 = simulate_hybrid(base_control, t, h, l, c, use_hybrid=False)
        r2 = simulate_hybrid(base, t, h, l, c, use_hybrid=True, trend_ema="ema")
        print("  " + fmt("Solo mean reversion", r1))
        print("  " + fmt("Hibrido (EMA100)", r2))

    n45 = 96 * 45
    print(f"\n=== Ultimos 45 dias ===")
    r1 = simulate_hybrid(base_control, times[-n45:], highs[-n45:], lows[-n45:], closes[-n45:], use_hybrid=False)
    r2 = simulate_hybrid(base, times[-n45:], highs[-n45:], lows[-n45:], closes[-n45:], use_hybrid=True, trend_ema="ema")
    print(fmt("Solo mean reversion", r1))
    print(fmt("Hibrido (EMA100)", r2))


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        main()
