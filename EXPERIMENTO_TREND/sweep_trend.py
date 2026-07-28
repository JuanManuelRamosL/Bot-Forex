"""
sweep_trend.py — Grilla simple sobre DONCHIAN_PERIOD / TREND_ADX_MIN / SL / RR
para ver si alguna combinación razonable mejora al baseline de backtest_trend.py.
Todo en la misma carpeta aislada, no toca BOT_FTMO.
"""
import types

import config_trend as base_config
from mt5_client import MT5Client
from engine import simulate


def clone(base, **overrides):
    c = types.SimpleNamespace()
    for k in dir(base):
        if not k.startswith("__"):
            setattr(c, k, getattr(base, k))
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


def fmt(m):
    return (f"ret {m['total_ret']:+7.1f}%  mensual {m['monthly_ret']:+5.2f}%  "
            f"DD -{m['max_dd']:5.1f}%  Sharpe {m['sharpe']:5.2f}  PF {m['profit_factor']:4.2f}  "
            f"WR {m['win_rate']:3.0f}%  trades {m['num_trades']:4d}")


def main():
    client = MT5Client(base_config.MT5_LOGIN, base_config.MT5_PASSWORD, base_config.MT5_SERVER)
    print(f"Bajando {base_config.BACKTEST_CANDLES} velas...")
    times, opens, highs, lows, closes = client.get_candles(
        base_config.INSTRUMENT, base_config.GRANULARITY, base_config.BACKTEST_CANDLES)
    print(f"Listo. {len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})\n")

    grid = []
    for donch in (10, 20, 40, 55):
        for adx_min in (20, 25, 30, 35):
            for sl_mult in (2.0, 2.5, 3.0):
                for rr in (2.0, 3.0, 4.0):
                    grid.append((donch, adx_min, sl_mult, rr))

    print(f"Probando {len(grid)} combinaciones sobre 3.6 años...\n")
    results = []
    for donch, adx_min, sl_mult, rr in grid:
        cfg = clone(base_config, DONCHIAN_PERIOD=donch, TREND_ADX_MIN=adx_min,
                    TREND_ATR_SL_MULT=sl_mult, TREND_TP_RR=rr)
        res = simulate(cfg, times, highs, lows, closes, capital0=10000)
        m = res["metrics"]
        if m["num_trades"] < 30:
            continue
        score = m["total_ret"] / (m["max_dd"] + 1e-6)
        results.append((score, donch, adx_min, sl_mult, rr, m))

    results.sort(key=lambda r: -r[0])
    print("=" * 100)
    print("TOP 10 por retorno/DD (Calmar-like)")
    print("=" * 100)
    for score, donch, adx_min, sl_mult, rr, m in results[:10]:
        print(f"  Donchian={donch:3d} ADX>={adx_min:2d} SL={sl_mult} RR={rr}  ->  {fmt(m)}")

    print("\n" + "=" * 100)
    print("PEORES 3 (referencia)")
    print("=" * 100)
    for score, donch, adx_min, sl_mult, rr, m in results[-3:]:
        print(f"  Donchian={donch:3d} ADX>={adx_min:2d} SL={sl_mult} RR={rr}  ->  {fmt(m)}")


if __name__ == "__main__":
    main()
