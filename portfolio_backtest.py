"""
portfolio_backtest.py — Backtest de SMC DIVERSIFICADO en varios pares a la vez.

Idea: repartir el capital entre N pares (sub-cuentas iguales). Cada par opera su
parte con la estrategia SMC. La curva de equity total es la suma de las sub-cuentas,
alineadas por timestamp. Como los pares no pierden todos a la vez (descorrelación),
el drawdown combinado suele ser MENOR que el de un solo par — lo que permite más
ganancia con el mismo riesgo, o el mismo riesgo con menos drawdown.

Solo pares quote-USD (EUR/USD, GBP/USD, AUD/USD, NZD/USD): ahí el motor calcula el
P&L correctamente (1 unidad de movimiento = 1 USD).

Uso:
    python portfolio_backtest.py
"""

import math
import config_smc
from mt5_client import MT5Client
from engine import simulate
from optimize import make_cfg

PARES   = ["EUR_USD", "GBP_USD", "AUD_USD", "NZD_USD"]
CANDLES = 30000
CAP_TOTAL = 10000.0
# Riesgo POR TRADE como % del capital TOTAL (se reparte: cada sub-cuenta arriesga
# este valor escalado a su tamaño, de modo que un trade = RISK_TOTAL del total).
RISK_TOTAL = 0.006


def metrics_from_equity(equity, cap0, n_trades, wins, gross_win, gross_loss, bars_per_day=96):
    total_ret = (equity[-1] - cap0) / cap0 * 100
    peak, max_dd = cap0, 0.0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak * 100 if peak else 0)
    rets = [(equity[i] - equity[i - 1]) / equity[i - 1]
            for i in range(1, len(equity)) if equity[i - 1]]
    if rets:
        mean_r = sum(rets) / len(rets)
        std_r = math.sqrt(sum((r - mean_r) ** 2 for r in rets) / len(rets))
        sharpe = (mean_r / std_r) * math.sqrt(bars_per_day * 365) if std_r else 0
    else:
        sharpe = 0
    months = len(equity) / (bars_per_day * 30) if equity else 0
    monthly = total_ret / months if months else 0
    pf = gross_win / gross_loss if gross_loss else 0
    wr = wins / n_trades * 100 if n_trades else 0
    return {"total_ret": total_ret, "monthly_ret": monthly, "sharpe": sharpe,
            "max_dd": max_dd, "pf": pf, "wr": wr, "num_trades": n_trades}


def run():
    client = MT5Client(config_smc.MT5_LOGIN, config_smc.MT5_PASSWORD, config_smc.MT5_SERVER)
    n = len(PARES)
    sub_cap = CAP_TOTAL / n
    risk_sub = RISK_TOTAL * n   # cada sub-cuenta arriesga esto de SÍ MISMA

    print(f"Diversificando SMC en {n} pares: {', '.join(PARES)}")
    print(f"Capital total ${CAP_TOTAL:,.0f} (${sub_cap:,.0f} por par) | riesgo {RISK_TOTAL*100:.1f}% del total por trade\n")

    series = []      # (par, metrics_individual, {time: equity})
    agg_trades = wins = 0
    gw = gl = 0.0
    print(f"{'Par':<10}{'Retorno':<11}{'PF':<7}{'Max DD':<10}{'Trades'}")
    print("-" * 48)
    for par in PARES:
        cfg = make_cfg(config_smc, INSTRUMENT=par, BARS_PER_DAY=96, RISK_PER_TRADE=risk_sub)
        times, o, h, l, cl = client.get_candles(par, "M15", CANDLES)
        res = simulate(cfg, times, h, l, cl, capital0=sub_cap)
        start = res["start"]
        eq = res["equity"]
        tmap = {times[start + j]: eq[j] for j in range(len(eq))}
        series.append((par, res["metrics"], tmap))
        m = res["metrics"]
        print(f"{par:<10}{m['total_ret']:<+10.1f}%{m['profit_factor']:<7.2f}-{m['max_dd']:<8.1f}%{m['num_trades']}")
        for t in res["trades"]:
            agg_trades += 1
            if t["pnl"] > 0:
                wins += 1
                gw += t["pnl"]
            else:
                gl += abs(t["pnl"])

    # Equity combinada alineada por timestamp (forward fill por par)
    all_times = sorted(set().union(*[set(s[2].keys()) for s in series]))
    last = [sub_cap] * n
    combined = []
    for t in all_times:
        for k, (par, m, tmap) in enumerate(series):
            if t in tmap:
                last[k] = tmap[t]
        combined.append(sum(last))

    pm = metrics_from_equity(combined, CAP_TOTAL, agg_trades, wins, gw, gl)

    print("\n" + "=" * 56)
    print(f"PORTFOLIO COMBINADO ({n} pares, riesgo {RISK_TOTAL*100:.1f}%/trade)")
    print("=" * 56)
    print(f"Retorno total:    {pm['total_ret']:+.1f}%")
    print(f"Retorno mensual:  {pm['monthly_ret']:+.2f}%")
    print(f"Sharpe:           {pm['sharpe']:.2f}")
    print(f"Profit factor:    {pm['pf']:.2f}")
    print(f"Win rate:         {pm['wr']:.0f}%")
    print(f"Máximo drawdown:  -{pm['max_dd']:.2f}%")
    print(f"Total operaciones:{pm['num_trades']}")
    print("=" * 56)
    print("\nComparación con SMC un solo par (EUR/USD @ 0.6%): +48%, DD -7.2%, PF 1.55")
    if pm["max_dd"] < 7.2:
        print(f">>> El portfolio BAJA el drawdown ({pm['max_dd']:.1f}% vs 7.2%) = la diversificación funciona.")
    if pm["total_ret"] > 48:
        print(f">>> Y ADEMÁS rinde más (+{pm['total_ret']:.0f}% vs +48%).")


if __name__ == "__main__":
    if config_smc.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run()
