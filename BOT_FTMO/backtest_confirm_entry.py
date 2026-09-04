"""
backtest_confirm_entry.py (v2) — Prueba cerrar la posicion abierta cuando
aparece la señal OPUESTA (ej. estando LONG, si el precio toca la banda
superior con RSI sobrecomprado — las condiciones de entrada en SHORT — cerrar
el LONG ahi en vez de esperar al TP fijo de 4.5R).

Idea del usuario: si el bot "sabe" entrar en la direccion contraria, esa misma
evaluacion sirve como aviso de que la operacion actual se puede estar
revirtiendo, en vez de dejarla correr hasta el TP fijo.

Sobre la base validada: sin trailing, TP_RR=4.5, ADX_MAX=25, motor realista
(SL/TP intravela + cooldown). No toca engine.py, engine_realistic.py,
strategy.py ni live_bot.py. Solo lectura.

Uso:
    python backtest_confirm_entry.py
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


def opposite_signal_fired(cfg, ind, i, closes, current_dir):
    """True si en la vela i se dan las condiciones de entrada de la direccion
    CONTRARIA a la posicion abierta (misma logica que strategy.signal_at)."""
    price = closes[i]
    u, lo, r = ind["upper"][i], ind["lower"][i], ind["rsi"][i]
    adx_now = ind["adx"][i]
    if None in (u, lo, r):
        return False
    if cfg.USE_REGIME_FILTER and (adx_now is None or adx_now >= cfg.ADX_MAX):
        return False
    if current_dir == "LONG":
        return price >= u and r > cfg.RSI_SHORT_MIN
    else:
        return price <= lo and r < cfg.RSI_LONG_MAX


def simulate_opposite_exit(cfg, times, highs, lows, closes, capital0=10000.0,
                            use_opposite_exit=False, only_if_profit=False, flip=False):
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

    def close_pos(i, exit_price, reason):
        nonlocal cash, pos, last_close_i
        if pos["dir"] == "LONG":
            gross = (exit_price - pos["entry"]) * pos["units"] * pos["qf"]
        else:
            gross = (pos["entry"] - exit_price) * abs(pos["units"]) * pos["qf"]
        cash += gross
        trades.append({"time": times[i], "dir": pos["dir"], "pnl": gross,
                        "reason": reason, "R": gross / pos["risk"] if pos["risk"] else 0.0})
        pos = None
        last_close_i = i

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
                exit_price = raw_exit - half if pos["dir"] == "LONG" else raw_exit + half
                close_pos(i, exit_price, reason)
            elif use_opposite_exit and opposite_signal_fired(cfg, ind, i, closes, pos["dir"]):
                unrl = _unrealized(pos, price)
                if not only_if_profit or unrl > 0:
                    exit_price = price - half if pos["dir"] == "LONG" else price + half
                    close_pos(i, exit_price, "SENAL_OPUESTA")

        if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
            cur_eq = cash + _unrealized(pos, price)
            if cur_eq <= day_start_equity * (1 - cfg.MAX_DAILY_LOSS):
                day_blocked = True

        if not pos and not (cfg.USE_CIRCUIT_BREAKER and day_blocked):
            blocked_same_bar = one_per_candle and (i == last_entry_i or i == last_close_i)
            in_cooldown = cooldown_bars and last_close_i is not None and (i - last_close_i) < cooldown_bars
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
                    pos = {"dir": sig["dir"], "entry": entry, "sl": sig["sl"], "tp": sig["tp"],
                           "units": units, "qf": qf, "risk": risk_amount}
                    last_entry_i = i
        elif not pos and cfg.USE_CIRCUIT_BREAKER and day_blocked:
            if strat.signal_at(i, closes, ind):
                blocked += 1

        equity.append(cash + _unrealized(pos, price))

    if pos:
        price = closes[-1]
        exit_price = price - half if pos["dir"] == "LONG" else price + half
        close_pos(len(closes) - 1, exit_price, "CIERRE_FINAL")

    bars_per_day = getattr(cfg, "BARS_PER_DAY", 24)
    metrics = compute_metrics(capital0, cash, trades, equity, closes, start, bars_per_day)
    metrics["blocked"] = blocked
    return {"trades": trades, "equity": equity, "final": cash, "metrics": metrics, "start": start}


VARIANTS = [
    ("Control (solo SL/TP fijo, sin señal opuesta)", dict(use_opposite_exit=False)),
    ("Cierra con señal opuesta (siempre)",            dict(use_opposite_exit=True, only_if_profit=False)),
    ("Cierra con señal opuesta (solo si en ganancia)", dict(use_opposite_exit=True, only_if_profit=True)),
]

HEADER = f"{'Variante':<46}{'Retorno':>10}{'PF':>7}{'WinRate':>9}{'MaxDD':>8}{'Trades':>8}"


def fmt(name, res):
    m = res["metrics"]
    wr = sum(1 for t in res["trades"] if t["pnl"] > 0) / len(res["trades"]) * 100 if res["trades"] else 0
    n_opp = sum(1 for t in res["trades"] if t["reason"] == "SENAL_OPUESTA")
    return (f"{name:<46}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}{wr:>8.1f}%"
            f"{m['max_dd']:>7.2f}%{m['num_trades']:>8}   (cierres por señal opuesta: {n_opp})")


def print_table(cfg, times, highs, lows, closes, capital0):
    print(HEADER)
    print("-" * len(HEADER))
    for name, kwargs in VARIANTS:
        res = simulate_opposite_exit(cfg, times, highs, lows, closes, capital0=capital0, **kwargs)
        print(fmt(name, res))


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    times, opens, highs, lows, closes = client.get_candles(config.INSTRUMENT, config.GRANULARITY, 90000)
    print(f"{len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})\n")

    cfg = clone_cfg(USE_TRAILING_STOP=False, TP_RR=4.5, ADX_MAX=25)

    print("=== Historico completo ===")
    print_table(cfg, times, highs, lows, closes, 10000)

    n = len(closes)
    chunks = [(i * (n // 8), (i + 1) * (n // 8) if i < 7 else n) for i in range(8)]
    print("\n=== 8 tramos independientes ===")
    for a, b in chunks:
        t, h, l, c = times[a:b], highs[a:b], lows[a:b], closes[a:b]
        print(f"\n--- {t[0][:10]} a {t[-1][:10]} ---")
        for name, kwargs in VARIANTS:
            res = simulate_opposite_exit(cfg, t, h, l, c, capital0=10000, **kwargs)
            m = res["metrics"]
            print(f"  {name:<46} retorno={m['total_ret']:>+8.2f}%  PF={m['profit_factor']:.2f}  "
                  f"DD={m['max_dd']:.2f}%  trades={m['num_trades']}")

    n45 = 96 * 45
    print(f"\n=== Ultimos 45 dias ===")
    print_table(cfg, times[-n45:], highs[-n45:], lows[-n45:], closes[-n45:], 10000)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        main()
