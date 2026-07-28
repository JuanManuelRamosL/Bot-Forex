"""
check_robustez.py — Consistencia por tramos (como walk_forward.py de BOT_FTMO)
del mejor candidato encontrado por sweep_trend.py: Donchian=10, ADX>=20, SL=2.5, RR=4.0.
Si es consistente en los 5 tramos, la ventaja es más creible; si solo funciona en
uno o dos, es sobreajuste al período completo (mismo error que se cometio con SMC).
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
    return (f"ret {m['total_ret']:+7.1f}%  DD -{m['max_dd']:5.1f}%  "
            f"Sharpe {m['sharpe']:5.2f}  PF {m['profit_factor']:4.2f}  "
            f"WR {m['win_rate']:3.0f}%  trades {m['num_trades']:4d}")


def main():
    client = MT5Client(base_config.MT5_LOGIN, base_config.MT5_PASSWORD, base_config.MT5_SERVER)
    times, opens, highs, lows, closes = client.get_candles(
        base_config.INSTRUMENT, base_config.GRANULARITY, base_config.BACKTEST_CANDLES)
    n = len(closes)
    print(f"{n} velas ({times[0][:10]} -> {times[-1][:10]})\n")

    best = clone(base_config, DONCHIAN_PERIOD=10, TREND_ADX_MIN=20,
                TREND_ATR_SL_MULT=2.5, TREND_TP_RR=4.0)

    N_WINDOWS = 5
    w = n // N_WINDOWS
    print("Candidato: Donchian=10 ADX>=20 SL=2.5 RR=4.0 (el 'ganador' del sweep sobre TODO el período)\n")
    for k in range(N_WINDOWS):
        a = k * w
        b = (k + 1) * w if k < N_WINDOWS - 1 else n
        seg = (times[a:b], highs[a:b], lows[a:b], closes[a:b])
        res = simulate(best, *seg, capital0=10000)
        print(f"  Tramo {k+1} [{times[a][:10]}->{times[b-1][:10]}]: {fmt(res['metrics'])}")


if __name__ == "__main__":
    main()
