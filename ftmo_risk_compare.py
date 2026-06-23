"""
ftmo_risk_compare.py — Compara distintos niveles de riesgo por trade.

Prueba el mismo bot con riesgo 0.4% / 0.6% / 0.8% / 1.0% / 1.5%
sobre las mismas 15 fechas de inicio para ver como cambia:
  - Velocidad para llegar al +10%
  - Drawdown maximo
  - Peor dia
  - Tasa de violacion de reglas FTMO
"""

import sys
import types
import random

import config_ftmo as cfg_base
from engine import simulate
from mt5_client import MT5Client

CAPITAL        = 10_000.0
FTMO_PROFIT    = 0.10
FTMO_DAY_DD    = 0.05
FTMO_TOTAL_DD  = 0.10
BARS_PER_MONTH = 1_920
MAX_WINDOW     = BARS_PER_MONTH * 6
N_TESTS        = 15
SEED           = 42

RISK_LEVELS = [0.004, 0.006, 0.008, 0.010, 0.015]   # 0.4% → 1.5%


def make_cfg(risk):
    """Copia config_ftmo con un riesgo distinto."""
    c = types.SimpleNamespace(**{k: v for k, v in vars(cfg_base).items()
                                  if not k.startswith("__")})
    c.RISK_PER_TRADE = risk
    return c


def check_violations(equity, times, start_off, capital0):
    day_open = capital0
    current_day = None
    for j, eq in enumerate(equity):
        tidx = start_off + j
        if tidx >= len(times): break
        day = times[tidx][:10]
        if day != current_day:
            current_day = day
            day_open = eq
        if (day_open - eq) / capital0 > FTMO_DAY_DD:
            return "dia"
        if (capital0 - eq) / capital0 > FTMO_TOTAL_DD:
            return "total"
    return None


def dias_hasta_objetivo(equity, times, start_off, capital0, target_pct):
    target = capital0 * (1 + target_pct)
    seen_days = []
    current_day = None
    for j, eq in enumerate(equity):
        tidx = start_off + j
        if tidx >= len(times): break
        day = times[tidx][:10]
        if day != current_day:
            current_day = day
            seen_days.append(day)
        if eq >= target:
            return len(seen_days)
    return None


def worst_day_pct(equity, times, start_off, capital0):
    worst = 0.0
    d_open = capital0
    cur_d = None
    for j, eq in enumerate(equity):
        tidx = start_off + j
        if tidx >= len(times): break
        d = times[tidx][:10]
        if d != cur_d:
            cur_d = d
            d_open = eq
        dd = (d_open - eq) / capital0 * 100
        if dd > worst: worst = dd
    return worst


def run_risk(cfg, times, highs, lows, closes, starts):
    rows = []
    for si in starts:
        ei = si + MAX_WINDOW
        wt = times[si:ei]; wh = highs[si:ei]
        wl = lows[si:ei];  wc = closes[si:ei]

        sim    = simulate(cfg, wt, wh, wl, wc, CAPITAL)
        equity = sim["equity"]
        start  = sim["start"]
        if not equity:
            continue

        viol  = check_violations(equity, wt, start, CAPITAL)
        dias  = None if viol else dias_hasta_objetivo(equity, wt, start, CAPITAL, FTMO_PROFIT)
        pico  = (max(equity) - CAPITAL) / CAPITAL * 100
        maxdd = max(0.0, (CAPITAL - min(equity)) / CAPITAL * 100)
        wday  = worst_day_pct(equity, wt, start, CAPITAL)

        rows.append({"viol": viol, "dias": dias, "pico": pico,
                     "maxdd": maxdd, "wday": wday})
    return rows


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print()
    print("=" * 72)
    print("  COMPARACION DE RIESGO — FTMO sin limite de tiempo (6 meses max)")
    print("=" * 72)
    print(f"  {N_TESTS} fechas de inicio  |  Capital ${CAPITAL:,.0f}  |  R:R {cfg_base.TP_RR:.1f}")
    print("=" * 72)

    print(f"\nDescargando datos M15 EUR/USD...")
    client = MT5Client(cfg_base.MT5_LOGIN, cfg_base.MT5_PASSWORD, cfg_base.MT5_SERVER)
    times, _, highs, lows, closes = client.get_candles(
        cfg_base.INSTRUMENT, cfg_base.GRANULARITY, 99000)
    total = len(closes)
    print(f"  {total:,} velas: {times[0][:10]} a {times[-1][:10]}\n")

    random.seed(SEED)
    step = (total - MAX_WINDOW) // N_TESTS
    starts = []
    for i in range(N_TESTS):
        base = i * step
        jit  = random.randint(-(step // 5), step // 5)
        starts.append(max(0, min(base + jit, total - MAX_WINDOW - 1)))
    starts = sorted(starts)

    print(f"Corriendo {N_TESTS} tests para cada nivel de riesgo...\n")

    all_results = {}
    for risk in RISK_LEVELS:
        cfg = make_cfg(risk)
        rows = run_risk(cfg, times, highs, lows, closes, starts)
        all_results[risk] = rows
        print(f"  Riesgo {risk*100:.1f}% listo ({len(rows)} tests)")

    # ── Tabla resumen ──────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  TABLA COMPARATIVA")
    print("=" * 72)
    print(f"  {'Riesgo':>8}  {'Pasan':>7}  {'Violac':>7}  "
          f"{'DiasProm':>9}  {'DiasMin':>8}  {'DiasMax':>8}  "
          f"{'MaxDD':>7}  {'PeorDia':>9}")
    print("  " + "-" * 70)

    for risk in RISK_LEVELS:
        rows = all_results[risk]
        viols  = [r for r in rows if r["viol"]]
        passed = [r for r in rows if r["dias"] and not r["viol"]]
        dias_l = [r["dias"] for r in passed]
        maxdds = [r["maxdd"] for r in rows]
        wdays  = [r["wday"]  for r in rows]

        pasa_str = f"{len(passed)}/{len(rows)}"
        viol_str = str(len(viols))
        dias_p   = f"{sum(dias_l)//len(dias_l)}d" if dias_l else "---"
        dias_min = f"{min(dias_l)}d"  if dias_l else "---"
        dias_max = f"{max(dias_l)}d"  if dias_l else "---"
        maxdd_s  = f"-{max(maxdds):.2f}%"
        wday_s   = f"-{max(wdays):.2f}%"

        flag = ""
        if len(viols) == 0 and len(passed) >= len(rows) * 0.9:
            flag = " <-- optimo"
        elif len(viols) > 0:
            flag = " !! VIOLA FTMO"

        print(f"  {risk*100:>7.1f}%  {pasa_str:>7}  {viol_str:>7}  "
              f"{dias_p:>9}  {dias_min:>8}  {dias_max:>8}  "
              f"{maxdd_s:>7}  {wday_s:>9}{flag}")

    # ── Detalle por fecha para cada riesgo ────────────────────────
    print()
    print("=" * 72)
    print("  DETALLE POR FECHA DE INICIO")
    print("=" * 72)

    date_labels = []
    for si in starts:
        off = min(30, len(times) - 1)
        date_labels.append(times[si + off][:10])

    header = f"  {'Fecha':>12}"
    for risk in RISK_LEVELS:
        header += f"  {risk*100:.1f}%".rjust(10)
    print(header)
    print("  " + "-" * (12 + len(RISK_LEVELS) * 10 + 4))

    for i, date in enumerate(date_labels):
        row = f"  {date:>12}"
        for risk in RISK_LEVELS:
            r = all_results[risk][i] if i < len(all_results[risk]) else None
            if r is None:
                row += "       N/A"
            elif r["viol"]:
                row += "  VIOLA RK"
            elif r["dias"]:
                row += f"  {r['dias']:>4}d hab"
            else:
                row += f"  +{r['pico']:>4.1f}%(nm)"
        print(row)

    # ── Recomendacion ──────────────────────────────────────────────
    print()
    print("=" * 72)
    print("  RECOMENDACION")
    print("=" * 72)
    for risk in RISK_LEVELS:
        rows  = all_results[risk]
        viols = [r for r in rows if r["viol"]]
        passed = [r for r in rows if r["dias"] and not r["viol"]]
        dias_l = [r["dias"] for r in passed]
        maxdds = [r["maxdd"] for r in rows]
        dias_p = sum(dias_l) // len(dias_l) if dias_l else 999

        safe = max([r["maxdd"] for r in rows]) < 5.0 and max([r["wday"] for r in rows]) < 3.0

        print(f"  {risk*100:.1f}%:  "
              f"{len(passed)}/{len(rows)} pasan  |  "
              f"prom {dias_p}d hab  |  "
              f"max DD -{max(maxdds):.2f}%  |  "
              f"{'SIN violaciones' if not viols else str(len(viols))+' VIOLACIONES'}"
              f"{'  [SEGURO]' if safe and not viols else ''}")
    print()


if __name__ == "__main__":
    main()
