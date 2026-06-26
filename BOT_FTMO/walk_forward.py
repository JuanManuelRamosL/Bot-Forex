"""
walk_forward.py — Validación OUT-OF-SAMPLE (prueba anti-sobreoptimización).

La idea: dividir el histórico real en ventanas consecutivas. En cada paso se
OPTIMIZAN los parámetros sobre un tramo (in-sample, IS) y se PRUEBAN tal cual en
el tramo siguiente que el optimizador NUNCA vio (out-of-sample, OOS).

    [ IS ventana 1 ] -> mejores params -> se prueban en [ OOS ventana 2 ]
                        [ IS ventana 2 ] -> mejores params -> [ OOS ventana 3 ]
                                            ...

- Si el rendimiento OOS se parece al IS  -> la ventaja es REAL.
- Si el OOS se derrumba frente al IS      -> estaba CURVO-AJUSTADO (overfit).

Además muestra cómo rinde tu config ACTUAL (la que vas a operar) en cada tramo,
para ver si es consistente o solo anduvo en un período puntual.

Requiere MT5 abierto y logueado. NO opera: es 100% simulación.

Uso:
    python walk_forward.py
"""

import sys
import types
import config
from mt5_client import MT5Client
from engine import simulate

try:
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows: permitir → y emojis
except Exception:
    pass

# ── Ajustes de la validación ──────────────────────────────────────
CANDLES   = 40000   # velas a pedir (M15: 40000 ≈ 1.6 años; pedí lo que haya)
N_WINDOWS = 5       # en cuántos tramos consecutivos partir el histórico
CAPITAL0  = 10000

# Grilla de parámetros a optimizar en cada tramo IS (la que se "curvo-ajusta").
GRID_RSI = [(30, 70), (35, 65), (40, 60)]   # (RSI_LONG_MAX, RSI_SHORT_MIN)
GRID_ATR = [2.0, 2.5, 3.0]                  # ATR_SL_MULT
GRID_ADX = [25, 30]                         # ADX_MAX
GRID_RR  = [2.5, 3.0, 3.5]                  # TP_RR


def clone(base, **overrides):
    """Copia el config como objeto editable y aplica overrides."""
    c = types.SimpleNamespace()
    for k in dir(base):
        if not k.startswith("__"):
            setattr(c, k, getattr(base, k))
    for k, v in overrides.items():
        setattr(c, k, v)
    return c


def score(m):
    """Objetivo robusto: retorno penalizado por drawdown (estilo Calmar).
    Descarta combinaciones con muy pocas operaciones (no son confiables)."""
    if m["num_trades"] < 5:
        return -1e9
    return m["total_ret"] / (m["max_dd"] + 1e-6)


def optimize(seg):
    """Prueba toda la grilla sobre un tramo y devuelve los mejores params."""
    times, highs, lows, closes = seg
    best = None
    for rl, rs in GRID_RSI:
        for atr in GRID_ATR:
            for adx in GRID_ADX:
                for rr in GRID_RR:
                    cfg = clone(config, RSI_LONG_MAX=rl, RSI_SHORT_MIN=rs,
                                ATR_SL_MULT=atr, ADX_MAX=adx, TP_RR=rr)
                    res = simulate(cfg, times, highs, lows, closes, capital0=CAPITAL0)
                    s = score(res["metrics"])
                    if best is None or s > best["score"]:
                        best = {"score": s,
                                "params": dict(RSI_LONG_MAX=rl, RSI_SHORT_MIN=rs,
                                               ATR_SL_MULT=atr, ADX_MAX=adx, TP_RR=rr),
                                "metrics": res["metrics"]}
    return best


def run_on(seg, **params):
    times, highs, lows, closes = seg
    cfg = clone(config, **params) if params else config
    return simulate(cfg, times, highs, lows, closes, capital0=CAPITAL0)["metrics"]


def fmt(m):
    return (f"ret {m['total_ret']:+7.1f}%  DD -{m['max_dd']:4.1f}%  "
            f"PF {m['profit_factor']:4.2f}  WR {m['win_rate']:3.0f}%  "
            f"trades {m['num_trades']:3d}")


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    print(f"Bajando hasta {CANDLES} velas de {config.INSTRUMENT} ({config.GRANULARITY})...")
    times, opens, highs, lows, closes = client.get_candles(
        config.INSTRUMENT, config.GRANULARITY, CANDLES)
    n = len(closes)
    print(f"Listo. {n} velas ({times[0][:10]} → {times[-1][:10]}). "
          f"Tramos: {N_WINDOWS}\n")

    w = n // N_WINDOWS
    windows = []
    for k in range(N_WINDOWS):
        a = k * w
        b = (k + 1) * w if k < N_WINDOWS - 1 else n
        windows.append((times[a:b], highs[a:b], lows[a:b], closes[a:b],
                        times[a][:10], times[b - 1][:10]))

    # ── 1) Consistencia de tu config ACTUAL en cada tramo ──
    print("=" * 78)
    print("1) TU CONFIG ACTUAL en cada tramo (¿es consistente o anduvo en uno solo?)")
    print("=" * 78)
    for k, win in enumerate(windows):
        seg = win[:4]
        m = run_on(seg)
        print(f"  Tramo {k+1} [{win[4]}→{win[5]}]: {fmt(m)}")

    # ── 2) Walk-forward: optimizar en IS, probar en OOS ──
    print("\n" + "=" * 78)
    print("2) WALK-FORWARD: optimizo en un tramo (IS) y pruebo en el SIGUIENTE (OOS)")
    print("   La caída IS→OOS es la medida de sobreoptimización.")
    print("=" * 78)
    is_rets, oos_rets = [], []
    for k in range(N_WINDOWS - 1):
        is_seg = windows[k][:4]
        oos_seg = windows[k + 1][:4]
        best = optimize(is_seg)
        oos_m = run_on(oos_seg, **best["params"])
        is_m = best["metrics"]
        is_rets.append(is_m["total_ret"])
        oos_rets.append(oos_m["total_ret"])
        p = best["params"]
        print(f"\n  IS  tramo {k+1} [{windows[k][4]}→{windows[k][5]}] "
              f"params óptimos: RSI {p['RSI_LONG_MAX']}/{p['RSI_SHORT_MIN']} "
              f"ATR {p['ATR_SL_MULT']} ADX<{p['ADX_MAX']} RR {p['TP_RR']}")
        print(f"      IS  (optimizado, lo lindo):  {fmt(is_m)}")
        print(f"      OOS (datos nuevos, la verdad): {fmt(oos_m)}")

    # ── Veredicto ──
    avg_is = sum(is_rets) / len(is_rets) if is_rets else 0
    avg_oos = sum(oos_rets) / len(oos_rets) if oos_rets else 0
    print("\n" + "=" * 78)
    print("VEREDICTO")
    print("=" * 78)
    print(f"  Retorno medio IS  (optimizado): {avg_is:+.1f}%")
    print(f"  Retorno medio OOS (datos nuevos): {avg_oos:+.1f}%")
    keep = (avg_oos / avg_is * 100) if avg_is > 0 else 0
    print(f"  Retención fuera de muestra: {keep:.0f}%  (cuánto del rendimiento sobrevive)")
    if avg_oos <= 0:
        print("  ⚠️  El OOS no es rentable: fuerte señal de SOBREOPTIMIZACIÓN.")
    elif keep < 40:
        print("  ⚠️  El OOS retiene <40% del IS: la estrategia depende mucho del ajuste.")
    else:
        print("  ✅  El OOS mantiene buena parte del rendimiento: ventaja más creíble.")
    print("  (Recordá: nada garantiza el futuro; esto solo descarta el autoengaño.)")


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales MT5 primero.")
    else:
        main()
