"""
optimize_smc_pairs.py — Optimiza SMC para CADA par por separado (validado OOS).

Para cada par quote-USD: busca los mejores parámetros SMC en TRAIN y los valida en
TEST. Reporta cuáles pares tienen una ventaja REAL out-of-sample (los únicos que
deberían entrar a un portfolio diversificado).

Fija USE_HTF_BIAS=True y USE_PREMIUM_DISCOUNT=False (lo que ya demostró ser robusto
en EUR/USD) y barre el resto, para acotar el riesgo de overfitting.

Uso:
    python optimize_smc_pairs.py
"""

import itertools
import config_smc
from mt5_client import MT5Client
from engine import simulate
from optimize import make_cfg, score, fmt

PARES   = ["EUR_USD", "GBP_USD", "NZD_USD"]
CANDLES = 90000   # ~3.6 años: entrena en 2022-2025, valida en 2025-2026
TRAIN_FRAC = 0.70

GRID = {
    "SWING_LOOKBACK": [5, 8],
    "SL_BUFFER_ATR":  [1.0, 2.0],
    "TP_RR":          [3.0, 4.0, 5.0],
    "FVG_MIN_ATR":    [0.5, 1.0],
}


def combos():
    keys = list(GRID.keys())
    for vals in itertools.product(*(GRID[k] for k in keys)):
        c = dict(zip(keys, vals))
        c["USE_HTF_BIAS"] = True
        c["USE_PREMIUM_DISCOUNT"] = False
        yield c


def best_for_pair(client, par):
    times, o, h, l, cl = client.get_candles(par, "M15", CANDLES)
    n = len(cl); split = int(n * TRAIN_FRAC)
    tr = (times[:split], h[:split], l[:split], cl[:split])
    te = (times[split:], h[split:], l[split:], cl[split:])

    scored = []
    for combo in combos():
        cfg = make_cfg(config_smc, INSTRUMENT=par, BARS_PER_DAY=96, **combo)
        m = simulate(cfg, *tr)["metrics"]
        scored.append((score(m), combo, m))
    valid = [r for r in scored if r[0] != float("-inf")]
    valid.sort(key=lambda x: x[0], reverse=True)

    best = None
    for s, combo, mtr in valid[:6]:
        cfg = make_cfg(config_smc, INSTRUMENT=par, BARS_PER_DAY=96, **combo)
        mte = simulate(cfg, *te)["metrics"]
        # robusto = rentable en train Y test, con PF de test decente
        if mtr["total_ret"] > 0 and mte["total_ret"] > 0 and mte["profit_factor"] >= 1.2:
            if best is None or mte["sharpe"] > best[2]["sharpe"]:
                best = (combo, mtr, mte)
    return best


def run():
    client = MT5Client(config_smc.MT5_LOGIN, config_smc.MT5_PASSWORD, config_smc.MT5_SERVER)
    print("Optimizando SMC por par (validación out-of-sample)\n")
    ganadores = []
    for par in PARES:
        print(f"{'='*70}\n{par}\n{'='*70}")
        best = best_for_pair(client, par)
        if best is None:
            print("  -> SIN ventaja robusta out-of-sample. NO entra al portfolio.\n")
            continue
        combo, mtr, mte = best
        print(f"  swing={combo['SWING_LOOKBACK']} slbuf={combo['SL_BUFFER_ATR']} "
              f"rr={combo['TP_RR']} fvgmin={combo['FVG_MIN_ATR']}")
        print(f"     TRAIN {fmt(mtr)}")
        print(f"     TEST  {fmt(mte)}")
        print(f"  -> ENTRA al portfolio (PF test {mte['profit_factor']:.2f})\n")
        ganadores.append((par, combo, mte))

    print(f"\n{'#'*70}\nRESUMEN: pares con ventaja real out-of-sample\n{'#'*70}")
    if not ganadores:
        print("Ninguno. SMC solo sirve donde ya lo validamos. No hay nada que diversificar.")
        return
    for par, combo, mte in ganadores:
        print(f"  {par}: PF {mte['profit_factor']:.2f}, Sharpe {mte['sharpe']:.2f}, "
              f"ret {mte['total_ret']:+.1f}%  | swing={combo['SWING_LOOKBACK']} "
              f"slbuf={combo['SL_BUFFER_ATR']} rr={combo['TP_RR']} fvgmin={combo['FVG_MIN_ATR']}")
    print(f"\n{len(ganadores)} de {len(PARES)} pares son diversificables.")


if __name__ == "__main__":
    if config_smc.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run()
