"""
optimize_smc.py — Optimización HONESTA (out-of-sample) de la estrategia SMC.

Busca los parámetros SMC que mejor rinden en TRAIN y los valida en TEST (datos
no vistos). Incluye R:R altos (hasta 5:1) porque el objetivo es maximizar el ratio.
Compara el mejor resultado robusto contra el bot M15 mean-reversion (FTMO).

Uso:
    python optimize_smc.py
"""

import itertools
import config_smc
from mt5_client import MT5Client
from engine import simulate
from optimize import make_cfg, score, fmt

CANDLES    = 30000
TRAIN_FRAC = 0.70
BPD        = 96   # velas M15 por día (para anualizar métricas)

GRID = {
    "SWING_LOOKBACK":       [5, 8, 12],
    "SL_BUFFER_ATR":        [1.0, 2.0],
    "TP_RR":                [2.0, 3.0, 4.0, 5.0],
    "USE_HTF_BIAS":         [False, True],
    "FVG_MIN_ATR":          [0.0, 0.5, 1.0],
    "USE_PREMIUM_DISCOUNT": [False, True],
}


def combos():
    keys = list(GRID.keys())
    for vals in itertools.product(*(GRID[k] for k in keys)):
        yield dict(zip(keys, vals))


def describe(c):
    parts = [f"swing={c['SWING_LOOKBACK']}", f"slbuf={c['SL_BUFFER_ATR']}",
             f"rr={c['TP_RR']}", f"fvgmin={c['FVG_MIN_ATR']}"]
    if c["USE_HTF_BIAS"]:
        parts.append("htf")
    if c["USE_PREMIUM_DISCOUNT"]:
        parts.append("pd")
    return "  ".join(parts)


def run():
    base = config_smc
    client = MT5Client(base.MT5_LOGIN, base.MT5_PASSWORD, base.MT5_SERVER)
    times, o, h, l, cl = client.get_candles(base.INSTRUMENT, "M15", CANDLES)
    n = len(cl); split = int(n * TRAIN_FRAC)
    tr = (times[:split], h[:split], l[:split], cl[:split])
    te = (times[split:], h[split:], l[split:], cl[split:])
    print(f"SMC sobre {base.INSTRUMENT} M15")
    print(f"TRAIN {times[0][:10]}->{times[split-1][:10]} | TEST {times[split][:10]}->{times[-1][:10]}")
    todos = list(combos())
    print(f"Probando {len(todos)} combinaciones...\n")

    results = []
    for idx, combo in enumerate(todos, 1):
        cfg = make_cfg(base, BARS_PER_DAY=BPD, **combo)
        m = simulate(cfg, *tr)["metrics"]
        results.append((score(m), combo, m))
        if idx % 50 == 0:
            print(f"  ... {idx}/{len(todos)}")

    valid = [r for r in results if r[0] != float("-inf")]
    valid.sort(key=lambda x: x[0], reverse=True)
    print(f"\n{len(valid)}/{len(results)} pasaron restricciones (DD<35%, trades>20)\n")

    if not valid:
        print("NINGUNA combinación SMC pasó. La estrategia no tiene base acá.")
        return

    print("=" * 78)
    print("TOP 8 EN TRAIN  ->  validados en TEST (datos nunca vistos)")
    print("=" * 78)
    robust = []
    for s, combo, mtr in valid[:8]:
        cfg = make_cfg(base, BARS_PER_DAY=BPD, **combo)
        mte = simulate(cfg, *te)["metrics"]
        print(f"\n{describe(combo)}")
        print(f"   TRAIN: {fmt(mtr)}")
        print(f"   TEST : {fmt(mte)}")
        if mtr["total_ret"] > 0 and mte["total_ret"] > 0 and mte["num_trades"] >= 15:
            robust.append((combo, mtr, mte))

    print("\n" + "=" * 78)
    if robust:
        robust.sort(key=lambda x: x[2]["sharpe"], reverse=True)
        combo, mtr, mte = robust[0]
        print("MEJOR SMC ROBUSTO (gana en train Y en test)")
        print("=" * 78)
        print(f"\n{describe(combo)}")
        print(f"   TRAIN: {fmt(mtr)}")
        print(f"   TEST : {fmt(mte)}")
        print(f"\nComparación con el bot M15 mean-reversion (FTMO): PF 1.36, Sharpe test ~2-3")
        print(f"SMC mejor robusto: PF {mte['profit_factor']:.2f}, Sharpe test {mte['sharpe']:.2f}")
        if mte["profit_factor"] >= 1.36:
            print(">>> SMC SUPERA al mean reversion. Vale la pena.")
        else:
            print(">>> SMC sigue por debajo del mean reversion. No conviene cambiarse.")
        print("\nValores para config_smc.py:")
        for kk in ["SWING_LOOKBACK", "SL_BUFFER_ATR", "TP_RR", "USE_HTF_BIAS",
                   "FVG_MIN_ATR", "USE_PREMIUM_DISCOUNT"]:
            print(f"  {kk} = {combo[kk]}")
    else:
        print("NINGÚN SMC fue robusto (rentable en train Y test a la vez).")
        print("=" * 78)
        print("Veredicto honesto: SMC no tiene ventaja real en este par/temporalidad,")
        print("ni siquiera con los filtros de calidad. El bot M15 sigue siendo mejor.")


if __name__ == "__main__":
    if config_smc.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run()
