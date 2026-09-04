"""
backtest_final_confirm.py — Comparacion exhaustiva: config VIEJA (trailing x2.0,
TP_RR 3.0, ADX_MAX 30 — lo que corrio en vivo la mayor parte del tiempo) vs
config NUEVA (sin trailing, TP_RR 4.5, ADX_MAX 25) sobre el motor realista
(SL/TP intravela + cooldown), en muchas ventanas distintas: historico completo,
por año calendario, en 4 y 8 tramos, y en varias ventanas recientes.

No toca config.py, engine.py, engine_realistic.py ni live_bot.py. Solo lectura.

Uso:
    python backtest_final_confirm.py
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


OLD = dict(USE_TRAILING_STOP=True, TRAIL_ATR_MULT=2.0, TP_RR=3.0, ADX_MAX=30)
NEW = dict(USE_TRAILING_STOP=False, TP_RR=4.5, ADX_MAX=25)

HEADER = f"{'Config':<10}{'Retorno':>10}{'PF':>7}{'WinRate':>9}{'MaxDD':>8}{'Trades':>8}"


def run(cfg_over, t, h, l, c, capital0=10000):
    cfg = clone_cfg(**cfg_over)
    return simulate_realistic(cfg, t, h, l, c, capital0=capital0)["metrics"]


def fmt(name, m):
    return f"{name:<10}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}{m['win_rate']:>8.1f}%{m['max_dd']:>7.2f}%{m['num_trades']:>8}"


def compare(label, t, h, l, c):
    mo = run(OLD, t, h, l, c)
    mn = run(NEW, t, h, l, c)
    winner = "NUEVA" if mn["total_ret"] > mo["total_ret"] else "VIEJA"
    print(f"\n--- {label} ({t[0][:10]} a {t[-1][:10]}) ---")
    print(HEADER)
    print(fmt("VIEJA", mo))
    print(fmt("NUEVA", mn))
    print(f"  -> gana: {winner}  (diferencia: {mn['total_ret']-mo['total_ret']:+.2f} pp)")
    return mn["total_ret"] > mo["total_ret"]


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    times, opens, highs, lows, closes = client.get_candles(config.INSTRUMENT, config.GRANULARITY, 90000)
    print(f"{len(closes)} velas ({times[0][:10]} -> {times[-1][:10]})")

    wins_new = 0
    total = 0

    print("\n" + "=" * 60)
    print("HISTORICO COMPLETO (3.6 anios)")
    print("=" * 60)
    if compare("Historico completo", times, highs, lows, closes):
        wins_new += 1
    total += 1

    print("\n" + "=" * 60)
    print("POR ANIO CALENDARIO")
    print("=" * 60)
    years = sorted(set(t[:4] for t in times))
    for y in years:
        idxs = [i for i, t in enumerate(times) if t[:4] == y]
        if len(idxs) < 500:
            continue
        a, b = idxs[0], idxs[-1] + 1
        if compare(f"Anio {y}", times[a:b], highs[a:b], lows[a:b], closes[a:b]):
            wins_new += 1
        total += 1

    print("\n" + "=" * 60)
    print("4 TRAMOS INDEPENDIENTES (~11 meses c/u)")
    print("=" * 60)
    n = len(closes)
    for i in range(4):
        a, b = i * (n // 4), (i + 1) * (n // 4) if i < 3 else n
        if compare(f"Tramo {i+1}/4", times[a:b], highs[a:b], lows[a:b], closes[a:b]):
            wins_new += 1
        total += 1

    print("\n" + "=" * 60)
    print("8 TRAMOS INDEPENDIENTES (~5.5 meses c/u)")
    print("=" * 60)
    for i in range(8):
        a, b = i * (n // 8), (i + 1) * (n // 8) if i < 7 else n
        if compare(f"Tramo {i+1}/8", times[a:b], highs[a:b], lows[a:b], closes[a:b]):
            wins_new += 1
        total += 1

    print("\n" + "=" * 60)
    print("VENTANAS RECIENTES")
    print("=" * 60)
    for dias, label in [(180, "Ultimos 180 dias"), (90, "Ultimos 90 dias"),
                        (45, "Ultimos 45 dias"), (20, "Ultimos 20 dias")]:
        nn = 96 * dias
        if compare(label, times[-nn:], highs[-nn:], lows[-nn:], closes[-nn:]):
            wins_new += 1
        total += 1

    print("\n" + "=" * 60)
    print(f"RESUMEN FINAL: la config NUEVA gano en {wins_new}/{total} ventanas probadas")
    print("=" * 60)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        main()
