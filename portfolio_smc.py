"""
portfolio_smc.py — Portfolio SMC diversificado (EUR/USD + GBP/USD + NZD/USD).

Cada par usa SUS PROPIOS parámetros (optimizados out-of-sample por optimize_smc_pairs.py).
AUD/USD queda afuera por no tener ventaja real. El capital se reparte en partes iguales
entre los pares; la equity total es la suma alineada por timestamp.

Barre el riesgo total por trade para mostrar la frontera y elegir el punto que
maximiza el retorno manteniendo el drawdown bajo el límite de FTMO.

Uso:
    python portfolio_smc.py
"""

import math
import config_smc
from mt5_client import MT5Client
from engine import simulate
from optimize import make_cfg

# Parámetros óptimos por par (de optimize_smc_pairs.py). HTF=True, PremiumDiscount=False.
# Mezcla de pares XXX_USD y USD_XXX = descorrelación real (lados opuestos del dólar).
PAIR_CONFIGS = {
    "EUR_USD": {"SWING_LOOKBACK": 5, "SL_BUFFER_ATR": 2.0, "TP_RR": 4.0, "FVG_MIN_ATR": 0.5},
    "GBP_USD": {"SWING_LOOKBACK": 8, "SL_BUFFER_ATR": 2.0, "TP_RR": 5.0, "FVG_MIN_ATR": 1.0},
    "NZD_USD": {"SWING_LOOKBACK": 8, "SL_BUFFER_ATR": 2.0, "TP_RR": 3.0, "FVG_MIN_ATR": 0.5},
    "USD_CHF": {"SWING_LOOKBACK": 8, "SL_BUFFER_ATR": 2.0, "TP_RR": 5.0, "FVG_MIN_ATR": 0.5},
    "USD_CAD": {"SWING_LOOKBACK": 8, "SL_BUFFER_ATR": 2.0, "TP_RR": 3.0, "FVG_MIN_ATR": 0.5},
}
CANDLES = 30000
CAP_TOTAL = 10000.0


def combined_metrics(equity, cap0, n_trades, wins, gw, gl, bpd=96):
    total_ret = (equity[-1] - cap0) / cap0 * 100
    peak, max_dd = cap0, 0.0
    for e in equity:
        peak = max(peak, e)
        max_dd = max(max_dd, (peak - e) / peak * 100 if peak else 0)
    rets = [(equity[i] - equity[i - 1]) / equity[i - 1]
            for i in range(1, len(equity)) if equity[i - 1]]
    if rets:
        mr = sum(rets) / len(rets)
        sd = math.sqrt(sum((r - mr) ** 2 for r in rets) / len(rets))
        sharpe = (mr / sd) * math.sqrt(bpd * 365) if sd else 0
    else:
        sharpe = 0
    months = len(equity) / (bpd * 30) if equity else 0
    return {
        "ret": total_ret, "monthly": total_ret / months if months else 0,
        "sharpe": sharpe, "max_dd": max_dd,
        "pf": gw / gl if gl else 0, "wr": wins / n_trades * 100 if n_trades else 0,
        "trades": n_trades,
    }


def run_portfolio(cache, risk_total):
    n = len(PAIR_CONFIGS)
    sub_cap = CAP_TOTAL / n
    risk_sub = risk_total * n   # cada sub-cuenta arriesga esto de sí misma

    series = []
    n_tr = wins = 0
    gw = gl = 0.0
    for par, params in PAIR_CONFIGS.items():
        cfg = make_cfg(config_smc, INSTRUMENT=par, BARS_PER_DAY=96,
                       RISK_PER_TRADE=risk_sub, USE_HTF_BIAS=True,
                       USE_PREMIUM_DISCOUNT=False, **params)
        times, h, l, cl = cache[par]
        res = simulate(cfg, times, h, l, cl, capital0=sub_cap)
        start = res["start"]
        tmap = {times[start + j]: res["equity"][j] for j in range(len(res["equity"]))}
        series.append(tmap)
        for t in res["trades"]:
            n_tr += 1
            if t["pnl"] > 0:
                wins += 1; gw += t["pnl"]
            else:
                gl += abs(t["pnl"])

    all_times = sorted(set().union(*[set(s.keys()) for s in series]))
    last = [sub_cap] * len(series)
    combined = []
    for t in all_times:
        for k, s in enumerate(series):
            if t in s:
                last[k] = s[t]
        combined.append(sum(last))
    return combined_metrics(combined, CAP_TOTAL, n_tr, wins, gw, gl)


def run():
    client = MT5Client(config_smc.MT5_LOGIN, config_smc.MT5_PASSWORD, config_smc.MT5_SERVER)
    print(f"Portfolio SMC: {', '.join(PAIR_CONFIGS)} (cada uno con sus parámetros)\n")
    cache = {}
    for par in PAIR_CONFIGS:
        times, o, h, l, cl = client.get_candles(par, "M15", CANDLES)
        cache[par] = (times, h, l, cl)

    print(f"{'Riesgo/trade':<14}{'Retorno':<11}{'Mensual':<11}{'Sharpe':<9}{'PF':<7}{'Max DD':<10}{'FTMO?'}")
    print("-" * 70)
    for risk in [0.002, 0.0025, 0.003, 0.0035, 0.004]:
        m = run_portfolio(cache, risk)
        ftmo = "SI" if m["max_dd"] < 10 else "NO"
        print(f"{risk*100:<13.1f}%{m['ret']:<+10.1f}%{m['monthly']:<+10.2f}%"
              f"{m['sharpe']:<9.2f}{m['pf']:<7.2f}-{m['max_dd']:<8.1f}%{ftmo}")

    print("\nReferencia — SMC un solo par (EUR/USD @ 0.6%): +48%, mensual +4.63%, DD -7.2%, PF 1.55")


if __name__ == "__main__":
    if config_smc.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run()
