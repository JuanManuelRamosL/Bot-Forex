"""
engine.py — Motor de simulación reutilizable.

Una sola función `simulate()` corre la estrategia sobre datos históricos y
devuelve trades + curva de equity + métricas. La usan tanto backtest.py
(un solo run) como optimize.py (cientos de runs con distintos parámetros).

Así garantizamos que el backtest y la optimización miden EXACTAMENTE lo mismo.
NO ejecuta órdenes reales: es 100% simulación.
"""

import math
from strategy import MeanReversionStrategy


def pip_size(instrument):
    return 0.01 if "JPY" in instrument else 0.0001


def _spread_price(cfg):
    pips = cfg.SPREAD_PIPS.get(cfg.INSTRUMENT, cfg.DEFAULT_SPREAD_PIPS)
    return pips * pip_size(cfg.INSTRUMENT)


def _unrealized(pos, price):
    if not pos:
        return 0.0
    if pos["dir"] == "LONG":
        return (price - pos["entry"]) * pos["units"]
    return (pos["entry"] - price) * abs(pos["units"])


def simulate(cfg, times, highs, lows, closes, capital0=10000.0):
    """
    Corre la estrategia y devuelve un dict con: trades, equity, y métricas.
    `cfg` puede ser el módulo config o cualquier objeto con los mismos atributos.
    """
    strat = MeanReversionStrategy(cfg)
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

    start = max(cfg.BB_PERIOD, cfg.ATR_PERIOD, cfg.RSI_PERIOD,
                2 * cfg.ADX_PERIOD + 1)
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

        # ── Trailing stop: ajustar el SL a favor antes de evaluar la salida ──
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

        # ── Cerrar posición abierta (con spread en la salida) ──
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
                    gross = (exit_price - pos["entry"]) * pos["units"]
                else:
                    exit_price = raw_exit + half
                    gross = (pos["entry"] - exit_price) * abs(pos["units"])
                cash += gross
                pips = ((exit_price - pos["entry"]) if pos["dir"] == "LONG"
                        else (pos["entry"] - exit_price)) / pip
                trades.append({
                    "time": times[i], "dir": pos["dir"], "entry": pos["entry"],
                    "exit": exit_price, "pnl": gross, "pips": pips, "reason": reason,
                })
                pos = None

        # ── Circuit breaker ──
        if cfg.USE_CIRCUIT_BREAKER and not day_blocked:
            cur_eq = cash + _unrealized(pos, price)
            if cur_eq <= day_start_equity * (1 - cfg.MAX_DAILY_LOSS):
                day_blocked = True

        # ── Abrir nueva posición (con spread en la entrada) ──
        if not pos and not (cfg.USE_CIRCUIT_BREAKER and day_blocked):
            sig = strat.signal_at(i, closes, ind)
            if sig:
                sl_dist = abs(sig["entry"] - sig["sl"])
                if sl_dist > 0:
                    risk_amount = cash * cfg.RISK_PER_TRADE
                    units = risk_amount / sl_dist
                    if sig["dir"] == "LONG":
                        entry = sig["entry"] + half
                    else:
                        entry = sig["entry"] - half
                        units = -units
                    pos = {"dir": sig["dir"], "entry": entry,
                           "sl": sig["sl"], "tp": sig["tp"], "units": units}
        elif not pos and cfg.USE_CIRCUIT_BREAKER and day_blocked:
            if strat.signal_at(i, closes, ind):
                blocked += 1

        equity.append(cash + _unrealized(pos, price))

    # Cierre final
    if pos:
        price = closes[-1]
        if pos["dir"] == "LONG":
            exit_price = price - half
            gross = (exit_price - pos["entry"]) * pos["units"]
        else:
            exit_price = price + half
            gross = (pos["entry"] - exit_price) * abs(pos["units"])
        cash += gross
        pips = ((exit_price - pos["entry"]) if pos["dir"] == "LONG"
                else (pos["entry"] - exit_price)) / pip
        trades.append({
            "time": times[-1], "dir": pos["dir"], "entry": pos["entry"],
            "exit": exit_price, "pnl": gross, "pips": pips, "reason": "CIERRE_FINAL",
        })

    metrics = compute_metrics(capital0, cash, trades, equity, closes, start)
    metrics["blocked"] = blocked
    return {"trades": trades, "equity": equity, "final": cash, "metrics": metrics,
            "capital0": capital0, "start": start, "closes": closes}


def compute_metrics(capital0, final, trades, equity, closes, start):
    total_ret = (final - capital0) / capital0 * 100
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    profit_factor = gross_win / gross_loss if gross_loss else (gross_win or 0)
    avg_win = gross_win / len(wins) if wins else 0
    avg_loss = gross_loss / len(losses) if losses else 1
    rr = avg_win / avg_loss if avg_loss else 0

    peak, max_dd = capital0, 0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak * 100 if peak else 0)

    rets = [(equity[i] - equity[i - 1]) / equity[i - 1]
            for i in range(1, len(equity)) if equity[i - 1]]
    if rets:
        mean_r = sum(rets) / len(rets)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / len(rets))
        sharpe = (mean_r / std_r) * math.sqrt(24 * 365) if std_r else 0
    else:
        sharpe = 0

    months = len(equity) / (24 * 30) if equity else 0
    monthly = total_ret / months if months else 0

    return {
        "total_ret": total_ret, "monthly_ret": monthly, "sharpe": sharpe,
        "win_rate": win_rate, "profit_factor": profit_factor, "rr": rr,
        "max_dd": max_dd, "num_trades": len(trades),
    }
