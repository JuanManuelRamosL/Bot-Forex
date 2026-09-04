"""
backtest_risk_report.py — Reporte de riesgo exhaustivo de la config ACTUAL
(sin trailing, TP_RR=4.5, ADX_MAX=25) sobre el motor realista: retorno, peor
drawdown, peor perdida diaria y peor racha perdedora, en MUCHOS segmentos de
tiempo distintos (por trimestre, por año, en 12 tramos, y varias ventanas
recientes), para tener una foto completa del riesgo real, no solo el retorno.

No toca config.py, engine.py ni engine_realistic.py. Solo lectura.

Uso:
    python backtest_risk_report.py
"""

import types
import config
from mt5_client import MT5Client
from engine_realistic import simulate_realistic


def clone_cfg(**overrides):
    ns = types.SimpleNamespace(**{k: v for k, v in vars(config).items() if not k.startswith("_")})
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


NEW = dict(USE_TRAILING_STOP=False, TP_RR=4.5, ADX_MAX=25)


def worst_daily_loss(equity, bar_times):
    worst, cur_day, day_start = 0.0, None, None
    for e, t in zip(equity, bar_times):
        day = t[:10]
        if day != cur_day:
            cur_day = day
            day_start = e
        if day_start:
            worst = max(worst, (day_start - e) / day_start)
    return worst


def worst_losing_streak(trades):
    run = longest = 0
    for t in trades:
        run = run + 1 if t["pnl"] <= 0 else 0
        longest = max(longest, run)
    return longest


def analyze(label, times, highs, lows, closes, capital0=10000):
    cfg = clone_cfg(**NEW)
    res = simulate_realistic(cfg, times, highs, lows, closes, capital0=capital0)
    m = res["metrics"]
    start = res["start"]
    bar_times = times[start:start + len(res["equity"])]
    wd = worst_daily_loss(res["equity"], bar_times)
    wl = worst_losing_streak(res["trades"])
    print(f"{label:<26}{t0(times):>12}{t1(times):>12}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}"
          f"{m['max_dd']:>8.2f}%{wd*100:>8.2f}%{wl:>6}{m['num_trades']:>8}")
    return m, wd, wl


def t0(times):
    return times[0][:10]


def t1(times):
    return times[-1][:10]


HEADER = (f"{'Segmento':<26}{'Desde':>12}{'Hasta':>12}{'Retorno':>10}{'PF':>7}"
          f"{'MaxDD':>9}{'PeorDia':>9}{'RachaP':>7}{'Trades':>8}")


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    times, opens, highs, lows, closes = client.get_candles(config.INSTRUMENT, config.GRANULARITY, 90000)
    print(f"{len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})")
    print("Config: sin trailing, TP_RR=4.5, ADX_MAX=25, SL=2.5, riesgo 0.4%/trade\n")

    print(HEADER)
    print("-" * len(HEADER))

    print("\n[ HISTORICO COMPLETO ]")
    analyze("Historico completo", times, highs, lows, closes)

    print("\n[ POR TRIMESTRE CALENDARIO ]")
    quarters = {}
    for i, t in enumerate(times):
        y, mo = int(t[:4]), int(t[5:7])
        q = f"{y}-Q{(mo-1)//3+1}"
        quarters.setdefault(q, []).append(i)
    for q, idxs in quarters.items():
        if len(idxs) < 300:
            continue
        a, b = idxs[0], idxs[-1] + 1
        analyze(q, times[a:b], highs[a:b], lows[a:b], closes[a:b])

    print("\n[ POR ANIO CALENDARIO ]")
    years = sorted(set(t[:4] for t in times))
    for y in years:
        idxs = [i for i, t in enumerate(times) if t[:4] == y]
        if len(idxs) < 500:
            continue
        a, b = idxs[0], idxs[-1] + 1
        analyze(f"Anio {y}", times[a:b], highs[a:b], lows[a:b], closes[a:b])

    print("\n[ 12 TRAMOS INDEPENDIENTES (~3.6 meses c/u) ]")
    n = len(closes)
    for i in range(12):
        a, b = i * (n // 12), (i + 1) * (n // 12) if i < 11 else n
        analyze(f"Tramo {i+1}/12", times[a:b], highs[a:b], lows[a:b], closes[a:b])

    print("\n[ VENTANAS RECIENTES (terminan hoy) ]")
    for dias in [365, 270, 180, 120, 90, 60, 45, 30, 20, 10]:
        nn = 96 * dias
        analyze(f"Ultimos {dias} dias", times[-nn:], highs[-nn:], lows[-nn:], closes[-nn:])

    print("\nLimites de referencia: freno propio del bot -8% total | limite real FTMO -5% diario / -10% total")


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        main()
