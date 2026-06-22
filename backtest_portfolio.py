"""
backtest_portfolio.py — Backtest del bot DIVERSIFICADO (los mismos 3 pares del bot en vivo).

Usa config_portfolio.py: los 3 pares (EUR/GBP/NZD) con sus parámetros, riesgo 0.35% del
total por trade. Muestra el resultado combinado + el desglose por par.

El PERÍODO se ajusta con BACKTEST_CANDLES en config_portfolio.py.
NO ejecuta órdenes: es 100% simulación.

Uso:
    python backtest_portfolio.py
"""

import config_portfolio as C
from mt5_client import MT5Client
from engine import simulate
from optimize import make_cfg
from portfolio_smc import combined_metrics


def run():
    client = MT5Client(C.MT5_LOGIN, C.MT5_PASSWORD, C.MT5_SERVER)
    n = len(C.PORTFOLIO)
    cap_total = getattr(C, "CAPITAL_INICIAL", 10000.0)
    sub_cap = cap_total / n
    risk_sub = C.RISK_PER_TRADE * n   # cada sub-cuenta arriesga esto de sí misma
    candles = getattr(C, "BACKTEST_CANDLES", 30000)

    print(f"Backtest PORTFOLIO: {', '.join(C.PORTFOLIO)}")
    print(f"Capital ${cap_total:,.0f} | riesgo {C.RISK_PER_TRADE*100:.2f}% del total/trade | {candles} velas M15\n")

    series = []
    n_tr = wins = 0
    gw = gl = 0.0
    rango = ""
    print(f"{'Par':<10}{'Retorno':<11}{'PF':<7}{'Max DD':<10}{'Trades'}")
    print("-" * 48)
    for par, params in C.PORTFOLIO.items():
        cfg = make_cfg(C, INSTRUMENT=par, BARS_PER_DAY=96, RISK_PER_TRADE=risk_sub, **params)
        times, o, h, l, cl = client.get_candles(par, C.GRANULARITY, candles)
        rango = f"{times[0][:10]} -> {times[-1][:10]}"
        res = simulate(cfg, times, h, l, cl, capital0=sub_cap)
        start = res["start"]
        tmap = {times[start + j]: res["equity"][j] for j in range(len(res["equity"]))}
        series.append(tmap)
        m = res["metrics"]
        print(f"{par:<10}{m['total_ret']:<+10.1f}%{m['profit_factor']:<7.2f}-{m['max_dd']:<8.1f}%{m['num_trades']}")
        for t in res["trades"]:
            n_tr += 1
            if t["pnl"] > 0:
                wins += 1; gw += t["pnl"]
            else:
                gl += abs(t["pnl"])

    all_times = sorted(set().union(*[set(s.keys()) for s in series]))
    last = [sub_cap] * n
    combined = []
    for t in all_times:
        for k, s in enumerate(series):
            if t in s:
                last[k] = s[t]
        combined.append(sum(last))

    m = combined_metrics(combined, cap_total, n_tr, wins, gw, gl)
    final = combined[-1] if combined else cap_total

    print("\n" + "=" * 52)
    print(f"PORTFOLIO COMBINADO ({rango})")
    print("=" * 52)
    print(f"Capital inicial:   ${cap_total:,.0f}")
    print(f"Capital final:     ${final:,.2f}")
    print(f"Ganancia:          ${final-cap_total:+,.2f}  ({m['ret']:+.2f}%)")
    print(f"Retorno mensual:   {m['monthly']:+.2f}%")
    print(f"Sharpe ratio:      {m['sharpe']:.2f}")
    print(f"Profit factor:     {m['pf']:.2f}")
    print(f"Win rate:          {m['wr']:.0f}%")
    print(f"Máximo drawdown:   -{m['max_dd']:.2f}%")
    print(f"Total operaciones: {m['trades']}")
    cumple = "SÍ cumple FTMO (DD < 10%)" if m['max_dd'] < 10 else "NO cumple FTMO (DD > 10%)"
    print(f"FTMO:              {cumple}")
    print("=" * 52)


if __name__ == "__main__":
    if C.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run()
