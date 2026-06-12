"""
backtest.py — Corre la estrategia sobre datos HISTÓRICOS REALES de OANDA.

Uso:
    python backtest.py

Te muestra métricas: retorno total, retorno mensual, win rate, Sharpe ratio,
máximo drawdown, ratio riesgo/recompensa, y la lista de operaciones.

NO ejecuta ninguna orden real. Es 100% simulación sobre el pasado.
"""

import math
import config
from oanda_client import OandaClient
from strategy import MeanReversionStrategy


def run_backtest():
    cfg = config
    client = OandaClient(cfg.OANDA_API_TOKEN, cfg.OANDA_ACCOUNT_ID, cfg.OANDA_ENV)
    strat = MeanReversionStrategy(cfg)

    print(f"Bajando {cfg.BACKTEST_CANDLES} velas de {cfg.INSTRUMENT} ({cfg.GRANULARITY})...")
    times, opens, highs, lows, closes = client.get_candles(
        cfg.INSTRUMENT, cfg.GRANULARITY, cfg.BACKTEST_CANDLES
    )
    print(f"Listo. {len(closes)} velas completas.\n")

    ind = strat.compute_indicators(highs, lows, closes)

    # Simulación
    capital0 = 10000.0
    cash = capital0
    pos = None
    trades = []
    equity_curve = []
    pip = 0.01 if "JPY" in cfg.INSTRUMENT else 0.0001

    start = max(cfg.BB_PERIOD, cfg.ATR_PERIOD, cfg.RSI_PERIOD) + 1

    for i in range(start, len(closes)):
        price = closes[i]

        # ¿Cerrar posición abierta?
        if pos:
            reason = strat.should_exit(pos, price, ind["mid"][i])
            if reason:
                if reason == "STOP_LOSS":
                    exit_price = pos["sl"]
                elif price >= pos["tp"] if pos["dir"] == "LONG" else price <= pos["tp"]:
                    exit_price = pos["tp"]
                else:
                    exit_price = price
                gross = (exit_price - pos["entry"]) * pos["units"]
                if pos["dir"] == "SHORT":
                    gross = (pos["entry"] - exit_price) * abs(pos["units"])
                cash += gross
                pips = (exit_price - pos["entry"]) / pip
                if pos["dir"] == "SHORT":
                    pips = (pos["entry"] - exit_price) / pip
                trades.append({
                    "time": times[i], "dir": pos["dir"], "entry": pos["entry"],
                    "exit": exit_price, "pnl": gross, "pips": pips, "reason": reason,
                })
                pos = None

        # ¿Abrir nueva posición?
        if not pos:
            sig = strat.signal_at(i, closes, ind)
            if sig:
                sl_dist = abs(sig["entry"] - sig["sl"])
                if sl_dist > 0:
                    risk_amount = cash * cfg.RISK_PER_TRADE
                    units = risk_amount / sl_dist
                    if sig["dir"] == "SHORT":
                        units = -units
                    pos = {
                        "dir": sig["dir"], "entry": sig["entry"],
                        "sl": sig["sl"], "tp": sig["tp"], "units": units,
                    }

        # Equity marcado a mercado
        eq = cash
        if pos:
            mtm = (price - pos["entry"]) * pos["units"]
            if pos["dir"] == "SHORT":
                mtm = (pos["entry"] - price) * abs(pos["units"])
            eq += mtm
        equity_curve.append(eq)

    # Cerrar posición final si quedó abierta
    if pos:
        price = closes[-1]
        gross = (price - pos["entry"]) * pos["units"]
        if pos["dir"] == "SHORT":
            gross = (pos["entry"] - price) * abs(pos["units"])
        cash += gross
        trades.append({
            "time": times[-1], "dir": pos["dir"], "entry": pos["entry"],
            "exit": price, "pnl": gross, "pips": (price - pos["entry"]) / pip,
            "reason": "CIERRE_FINAL",
        })

    print_results(capital0, cash, trades, equity_curve, closes, start)


def print_results(capital0, final, trades, equity, closes, start):
    total_ret = (final - capital0) / capital0 * 100
    bh_ret = (closes[-1] - closes[start]) / closes[start] * 100
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
    avg_loss = abs(sum(t["pnl"] for t in losses) / len(losses)) if losses else 1
    rr = avg_win / avg_loss if avg_loss else 0

    peak, max_dd = capital0, 0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak * 100)

    rets = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity)) if equity[i - 1]]
    if rets:
        mean_r = sum(rets) / len(rets)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / len(rets))
        sharpe = (mean_r / std_r) * math.sqrt(24 * 365) if std_r else 0
    else:
        sharpe = 0

    candles_per_month = 24 * 30
    months = len(equity) / candles_per_month
    monthly = total_ret / months if months else 0

    print("=" * 50)
    print("RESULTADOS DEL BACKTEST")
    print("=" * 50)
    print(f"Capital inicial:      ${capital0:,.0f}")
    print(f"Capital final:        ${final:,.2f}")
    print(f"Retorno total:        {total_ret:+.2f}%")
    print(f"Retorno mensual est.: {monthly:+.2f}%")
    print(f"Buy & Hold del par:   {bh_ret:+.2f}%")
    print(f"Sharpe ratio:         {sharpe:.2f}")
    print(f"Win rate:             {win_rate:.0f}%  ({len(wins)}/{len(trades)})")
    print(f"Ratio R:R:            {rr:.2f}")
    print(f"Máximo drawdown:      -{max_dd:.2f}%")
    print(f"Total operaciones:    {len(trades)}")
    print("=" * 50)

    if trades:
        print("\nÚltimas 10 operaciones:")
        print(f"{'Fecha':<22}{'Dir':<7}{'Entrada':<11}{'Salida':<11}{'P&L':<12}{'Pips':<8}{'Motivo'}")
        for t in trades[-10:]:
            print(f"{t['time'][:19]:<22}{t['dir']:<7}{t['entry']:<11.5f}"
                  f"{t['exit']:<11.5f}${t['pnl']:<11.2f}{t['pips']:<8.1f}{t['reason']}")


if __name__ == "__main__":
    if config.OANDA_API_TOKEN.startswith("PEGA"):
        print("ERROR: Editá config.py con tu token y account ID de OANDA primero.")
    else:
        run_backtest()
