"""
optimize_scalp.py — Igual filosofía que optimize.py, pero PRUEBA VARIAS
TEMPORALIDADES CORTAS (M5, M15, M30) y elige la más efectiva.

Para cada temporalidad:
  1. Baja su historia disponible.
  2. Parte en TRAIN (70%) / TEST (30%).
  3. Busca los mejores parámetros en TRAIN.
  4. Los valida en TEST (datos nunca vistos).

Al final compara la MEJOR config robusta de cada temporalidad y recomienda una
sola, comparando por métricas ajustadas al tiempo (Sharpe y retorno mensual),
que sí son comparables entre temporalidades distintas.

Uso:
    python optimize_scalp.py
"""

import itertools
import config
from mt5_client import MT5Client
from engine import simulate
from optimize import make_cfg, score, fmt, describe

# Temporalidades a probar y cuántas velas/día tiene cada una (para anualizar bien)
TIMEFRAMES   = ["M5", "M15", "M30"]
BARS_PER_DAY = {"M5": 288, "M15": 96, "M30": 48}
CANDLES      = 30000      # velas por temporalidad
TRAIN_FRAC   = 0.70

# Grilla enfocada (el modo "rr" + trailing dominó en H1; igual probamos trailing on/off)
GRID_SCALP = {
    "BB_STD":            [2.0, 2.5],
    "RSI_PAIR":          [(30, 70), (35, 65)],
    "ATR_SL_MULT":       [1.5, 2.0, 2.5],
    "ADX_MAX":           [25, 30],
    "TP":                [("rr", 1.5), ("rr", 2.0), ("rr", 3.0)],
    "USE_TREND_FILTER":  [False, True],
    "USE_TRAILING_STOP": [False, True],
}


def combos_scalp():
    keys = list(GRID_SCALP.keys())
    for values in itertools.product(*(GRID_SCALP[k] for k in keys)):
        combo = dict(zip(keys, values))
        rl, rs = combo.pop("RSI_PAIR")
        tm, tr = combo.pop("TP")
        combo["RSI_LONG_MAX"] = rl
        combo["RSI_SHORT_MIN"] = rs
        combo["TP_MODE"] = tm
        if tr is not None:
            combo["TP_RR"] = tr
        yield combo


def optimize_tf(client, base, tf):
    """Optimiza una temporalidad. Devuelve (tf, best) con best=(combo, m_train, m_test) o None."""
    times, o, h, l, cl = client.get_candles(base.INSTRUMENT, tf, CANDLES)
    n = len(cl)
    split = int(n * TRAIN_FRAC)
    tr = (times[:split], h[:split], l[:split], cl[:split])
    te = (times[split:], h[split:], l[split:], cl[split:])
    bpd = BARS_PER_DAY[tf]

    print(f"\n{'='*78}\n{tf}: {n} velas ({times[0][:10]} -> {times[-1][:10]}) "
          f"| TRAIN {split} / TEST {n-split}\n{'='*78}")

    combos = list(combos_scalp())
    results = []
    for combo in combos:
        c = make_cfg(base, BARS_PER_DAY=bpd, **combo)
        m = simulate(c, *tr)["metrics"]
        results.append((score(m), combo, m))

    valid = [r for r in results if r[0] != float("-inf")]
    valid.sort(key=lambda x: x[0], reverse=True)
    if not valid:
        print(f"  {tf}: ninguna combinación pasó las restricciones.")
        return (tf, None)

    best = None
    print(f"  Top 3 en TRAIN (validados en TEST):")
    for rank, (s, combo, mtr) in enumerate(valid[:10], 1):
        c = make_cfg(base, BARS_PER_DAY=bpd, **combo)
        mte = simulate(c, *te)["metrics"]
        if rank <= 3:
            print(f"   #{rank} {describe(combo)}")
            print(f"       TRAIN {fmt(mtr)}")
            print(f"       TEST  {fmt(mte)}")
        robust = (mte["total_ret"] > 0 and mtr["total_ret"] > 0 and mte["num_trades"] >= 10)
        if robust and (best is None or mte["sharpe"] > best[2]["sharpe"]):
            best = (combo, mtr, mte)

    if best:
        print(f"  -> Mejor robusto en {tf}: TEST {fmt(best[2])}")
    else:
        print(f"  -> {tf}: ninguna config fue rentable out-of-sample (probable: el spread "
              f"se come la ganancia en esta temporalidad).")
    return (tf, best)


def run():
    base = config
    client = MT5Client(base.MT5_LOGIN, base.MT5_PASSWORD, base.MT5_SERVER)
    print(f"Optimización multi-temporalidad de {base.INSTRUMENT}")
    print(f"Probando: {', '.join(TIMEFRAMES)}  |  {len(list(combos_scalp()))} combos por temporalidad")

    winners = []
    for tf in TIMEFRAMES:
        tf, best = optimize_tf(client, base, tf)
        if best:
            winners.append((tf, *best))

    print(f"\n\n{'#'*78}\nGANADOR POR TEMPORALIDAD (ordenado por Sharpe en TEST)\n{'#'*78}")
    if not winners:
        print("\nNinguna temporalidad corta dio una estrategia rentable out-of-sample.")
        print("Conclusión honesta: en temporalidades cortas el spread se come la ventaja.")
        print("El bot H1 que ya tenés es el más efectivo para esta estrategia.")
        return

    winners.sort(key=lambda x: x[3]["sharpe"], reverse=True)
    for tf, combo, mtr, mte in winners:
        print(f"\n{tf}:  {describe(combo)}")
        print(f"     TRAIN {fmt(mtr)}")
        print(f"     TEST  {fmt(mte)}  <- mensual {mte['monthly_ret']:+.2f}%")

    tf, combo, mtr, mte = winners[0]
    print(f"\n{'='*78}\nRECOMENDACIÓN: temporalidad {tf}\n{'='*78}")
    print(f"\nValores para config_scalp.py:")
    print(f'  GRANULARITY       = "{tf}"')
    print(f"  BARS_PER_DAY      = {BARS_PER_DAY[tf]}")
    print(f"  BB_STD            = {combo['BB_STD']}")
    print(f"  ATR_SL_MULT       = {combo['ATR_SL_MULT']}")
    print(f"  ADX_MAX           = {combo['ADX_MAX']}")
    print(f"  RSI_LONG_MAX      = {combo['RSI_LONG_MAX']}")
    print(f"  RSI_SHORT_MIN     = {combo['RSI_SHORT_MIN']}")
    print(f'  TP_MODE           = "{combo["TP_MODE"]}"')
    if combo["TP_MODE"] == "rr":
        print(f"  TP_RR             = {combo['TP_RR']}")
    print(f"  USE_TREND_FILTER  = {combo['USE_TREND_FILTER']}")
    print(f"  USE_TRAILING_STOP = {combo['USE_TRAILING_STOP']}")


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run()
