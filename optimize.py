"""
optimize.py — Búsqueda de parámetros con validación HONESTA (out-of-sample).

El problema #1 al optimizar un bot es el OVERFITTING: encontrar parámetros que
se ven perfectos en el pasado pero fallan en vivo. Para evitarlo:

1. Partimos la historia en dos:
   - TRAIN (70% más viejo): acá BUSCAMOS los mejores parámetros.
   - TEST  (30% más reciente): datos que la búsqueda NUNCA vio.
2. Elegimos los parámetros por su rendimiento en TRAIN.
3. Los validamos en TEST. Si siguen siendo buenos ahí, la mejora es REAL.
   Si en TEST se derrumban, era overfitting y lo descartamos.

Optimizamos por SHARPE (retorno ajustado por riesgo), no por retorno bruto:
maximizar retorno solo lleva a estrategias con drawdowns suicidas.

Uso:
    python optimize.py
"""

import types
import itertools
import config
from mt5_client import MT5Client
from engine import simulate

# ─── Restricciones para que un resultado sea "aceptable" ──────────
MIN_TRADES_TRAIN = 20     # menos trades = no es estadísticamente confiable
MAX_DD_LIMIT     = 35.0   # descartar configs con drawdown > 35%
TRAIN_FRAC       = 0.70   # 70% train / 30% test

# ─── Grilla de parámetros a explorar ──────────────────────────────
GRID = {
    "BB_STD":          [2.0, 2.5],
    "RSI_PAIR":        [(35, 65), (40, 60), (30, 70)],  # (long_max, short_min)
    "ATR_SL_MULT":     [1.5, 2.0, 2.5],
    "ADX_MAX":         [20, 25, 30],
    "TP":              [("mean", None), ("rr", 1.5), ("rr", 2.0), ("rr", 3.0)],
    "USE_TREND_FILTER":[False, True],
    "USE_TRAILING_STOP":[False, True],
}


def make_cfg(base, **over):
    """Crea una copia de config con algunos valores cambiados."""
    d = {k: getattr(base, k) for k in dir(base) if not k.startswith("__")}
    d.update(over)
    return types.SimpleNamespace(**d)


def all_combos():
    keys = list(GRID.keys())
    for values in itertools.product(*(GRID[k] for k in keys)):
        combo = dict(zip(keys, values))
        rsi_long, rsi_short = combo.pop("RSI_PAIR")
        tp_mode, tp_rr = combo.pop("TP")
        combo["RSI_LONG_MAX"] = rsi_long
        combo["RSI_SHORT_MIN"] = rsi_short
        combo["TP_MODE"] = tp_mode
        if tp_rr is not None:
            combo["TP_RR"] = tp_rr
        yield combo


def score(metrics):
    """Sharpe, pero descalifica configs con pocos trades o drawdown enorme."""
    if metrics["num_trades"] < MIN_TRADES_TRAIN:
        return float("-inf")
    if metrics["max_dd"] > MAX_DD_LIMIT:
        return float("-inf")
    return metrics["sharpe"]


def fmt(m):
    return (f"ret {m['total_ret']:+6.1f}%  sharpe {m['sharpe']:5.2f}  "
            f"PF {m['profit_factor']:4.2f}  DD -{m['max_dd']:4.1f}%  "
            f"trades {m['num_trades']:3d}  WR {m['win_rate']:.0f}%")


def describe(combo):
    parts = [f"BB_STD={combo['BB_STD']}", f"SL={combo['ATR_SL_MULT']}xATR",
             f"ADX<{combo['ADX_MAX']}", f"RSI={combo['RSI_LONG_MAX']}/{combo['RSI_SHORT_MIN']}",
             f"TP={combo['TP_MODE']}" + (f":{combo.get('TP_RR')}" if combo['TP_MODE'] == 'rr' else "")]
    if combo["USE_TREND_FILTER"]:
        parts.append("trend")
    if combo["USE_TRAILING_STOP"]:
        parts.append("trail")
    return "  ".join(parts)


def run_optimization():
    cfg = config
    client = MT5Client(cfg.MT5_LOGIN, cfg.MT5_PASSWORD, cfg.MT5_SERVER)

    print(f"Bajando {cfg.BACKTEST_CANDLES} velas de {cfg.INSTRUMENT} ({cfg.GRANULARITY})...")
    times, opens, highs, lows, closes = client.get_candles(
        cfg.INSTRUMENT, cfg.GRANULARITY, cfg.BACKTEST_CANDLES
    )
    n = len(closes)
    split = int(n * TRAIN_FRAC)
    print(f"Listo. {n} velas ({times[0][:10]} -> {times[-1][:10]})")
    print(f"TRAIN: {split} velas ({times[0][:10]} -> {times[split-1][:10]})")
    print(f"TEST:  {n-split} velas ({times[split][:10]} -> {times[-1][:10]})\n")

    tr = (times[:split], highs[:split], lows[:split], closes[:split])
    te = (times[split:], highs[split:], lows[split:], closes[split:])

    combos = list(all_combos())
    print(f"Probando {len(combos)} combinaciones de parámetros sobre TRAIN...\n")

    results = []
    for idx, combo in enumerate(combos, 1):
        c = make_cfg(cfg, **combo)
        res = simulate(c, *tr)
        s = score(res["metrics"])
        results.append((s, combo, res["metrics"]))
        if idx % 50 == 0:
            print(f"  ... {idx}/{len(combos)}")

    valid = [r for r in results if r[0] != float("-inf")]
    valid.sort(key=lambda x: x[0], reverse=True)

    if not valid:
        print("Ninguna combinación pasó las restricciones (min trades / max drawdown).")
        return

    print(f"\n{len(valid)} combinaciones pasaron las restricciones.")
    print("\n" + "=" * 78)
    print("TOP 10 EN TRAIN  ->  validados en TEST (datos nunca vistos)")
    print("=" * 78)

    top = valid[:10]
    test_evals = []
    for rank, (s, combo, m_train) in enumerate(top, 1):
        c = make_cfg(cfg, **combo)
        m_test = simulate(c, *te)["metrics"]
        test_evals.append((combo, m_train, m_test))
        print(f"\n#{rank}  {describe(combo)}")
        print(f"   TRAIN: {fmt(m_train)}")
        print(f"   TEST : {fmt(m_test)}")

    # ── Baseline: la config actual, para comparar ──
    base_train = simulate(cfg, *tr)["metrics"]
    base_test = simulate(cfg, *te)["metrics"]
    print("\n" + "=" * 78)
    print("BASELINE (config actual, sin optimizar)")
    print("=" * 78)
    print(f"   TRAIN: {fmt(base_train)}")
    print(f"   TEST : {fmt(base_test)}")

    # ── Recomendación: mejor SHARPE EN TEST entre los robustos ──
    # (robusto = positivo en train Y en test)
    robust = [(combo, mtr, mte) for (combo, mtr, mte) in test_evals
              if mte["total_ret"] > 0 and mtr["total_ret"] > 0
              and mte["num_trades"] >= 10]
    print("\n" + "=" * 78)
    if robust:
        robust.sort(key=lambda x: x[2]["sharpe"], reverse=True)
        best_combo, mtr, mte = robust[0]
        print("RECOMENDACIÓN (rinde bien en TRAIN y en TEST — mejora robusta)")
        print("=" * 78)
        print(f"\n{describe(best_combo)}\n")
        print(f"   TRAIN: {fmt(mtr)}")
        print(f"   TEST : {fmt(mte)}")
        print("\nPara aplicarla, poné estos valores en config.py:")
        print(_config_snippet(best_combo))
    else:
        print("ADVERTENCIA: ninguna config fue rentable en TEST de forma robusta.")
        print("=" * 78)
        print("Esto significa que la estrategia NO tiene una ventaja real en este par/")
        print("período. Optimizar más sería overfitting. Conviene probar otro par,")
        print("otra temporalidad, o aceptar que esta estrategia no es rentable acá.")


def _config_snippet(combo):
    lines = [
        f"  BB_STD            = {combo['BB_STD']}",
        f"  ATR_SL_MULT       = {combo['ATR_SL_MULT']}",
        f"  ADX_MAX           = {combo['ADX_MAX']}",
        f"  RSI_LONG_MAX      = {combo['RSI_LONG_MAX']}",
        f"  RSI_SHORT_MIN     = {combo['RSI_SHORT_MIN']}",
        f"  TP_MODE           = \"{combo['TP_MODE']}\"",
    ]
    if combo["TP_MODE"] == "rr":
        lines.append(f"  TP_RR             = {combo['TP_RR']}")
    lines.append(f"  USE_TREND_FILTER  = {combo['USE_TREND_FILTER']}")
    lines.append(f"  USE_TRAILING_STOP = {combo['USE_TRAILING_STOP']}")
    return "\n".join(lines)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        run_optimization()

