"""
ftmo_time_test.py — Cuanto tiempo le toma al bot alcanzar el +10% de FTMO.

Desde distintas fechas de inicio, simula el bot hasta que:
  a) Alcanza +10% de ganancia (PASS), o
  b) Viola alguna regla FTMO (perdida diaria >5% o total >10%), o
  c) Pasan 6 meses sin llegar al objetivo.

Esto simula exactamente como funciona FTMO ahora: sin limite de tiempo,
el bot opera hasta que cumple el objetivo o viola las reglas.
"""

import sys
import random

import config_ftmo as cfg
from engine import simulate
from mt5_client import MT5Client

CAPITAL        = 10_000.0
FTMO_PROFIT    = 0.10
FTMO_DAY_DD    = 0.05
FTMO_TOTAL_DD  = 0.10
BARS_PER_MONTH = 1_920
MAX_WINDOW     = BARS_PER_MONTH * 6   # buscar hasta 6 meses
N_TESTS        = 15
SEED           = 42


def dias_habiles_hasta(equity, times, start_off, capital0, target_pct):
    """Devuelve el nro de dias habiles hasta que equity supere capital0*(1+target_pct), o None."""
    target = capital0 * (1 + target_pct)
    seen_days = []
    current_day = None
    for j, eq in enumerate(equity):
        tidx = start_off + j
        if tidx >= len(times):
            break
        day = times[tidx][:10]
        if day != current_day:
            current_day = day
            seen_days.append(day)
        if eq >= target:
            return len(seen_days)
    return None


def check_violations(equity, times, start_off, capital0):
    """Retorna (violacion_tipo, fecha) o (None, None)."""
    day_open = capital0
    current_day = None
    for j, eq in enumerate(equity):
        tidx = start_off + j
        if tidx >= len(times):
            break
        day = times[tidx][:10]
        if day != current_day:
            current_day = day
            day_open = eq
        if (day_open - eq) / capital0 > FTMO_DAY_DD:
            return "perdida diaria >5%", day
        if (capital0 - eq) / capital0 > FTMO_TOTAL_DD:
            return "perdida total >10%", day
    return None, None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print()
    print("=" * 72)
    print("  FTMO SIN LIMITE DE TIEMPO — Cuanto tarda el bot en llegar al +10%")
    print("=" * 72)
    print(f"  Capital: ${CAPITAL:,.0f}  |  Riesgo: {cfg.RISK_PER_TRADE*100:.1f}%/trade  |  R:R {cfg.TP_RR:.1f}")
    print(f"  Ventana maxima: 6 meses  |  15 fechas de inicio distintas")
    print("=" * 72)

    print(f"\nDescargando datos M15 EUR/USD...")
    client = MT5Client(cfg.MT5_LOGIN, cfg.MT5_PASSWORD, cfg.MT5_SERVER)
    times, _, highs, lows, closes = client.get_candles(cfg.INSTRUMENT, cfg.GRANULARITY, 99000)
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

    print(f"{'#':>3}  {'Inicio':>12}  {'Resultado':<38}  {'Dias':>6}  {'MaxDD':>7}  {'PeorDia':>9}")
    print("-" * 83)

    results = []
    for idx, si in enumerate(starts):
        ei = si + MAX_WINDOW
        wt = times[si:ei]
        wh = highs[si:ei]
        wl = lows[si:ei]
        wc = closes[si:ei]

        sim    = simulate(cfg, wt, wh, wl, wc, CAPITAL)
        equity = sim["equity"]
        start  = sim["start"]

        if not equity:
            continue

        date_from = wt[start][:10] if start < len(wt) else wt[0][:10]

        viol_tipo, viol_fecha = check_violations(equity, wt, start, CAPITAL)
        dias = dias_habiles_hasta(equity, wt, start, CAPITAL, FTMO_PROFIT)
        pico = (max(equity) - CAPITAL) / CAPITAL * 100
        max_dd = max(0.0, (CAPITAL - min(equity)) / CAPITAL * 100)

        # Peor dia
        worst_day = 0.0
        d_open = CAPITAL
        cur_d  = None
        for j, eq in enumerate(equity):
            tidx = start + j
            if tidx >= len(wt): break
            d = wt[tidx][:10]
            if d != cur_d:
                cur_d = d
                d_open = eq
            dd = (d_open - eq) / CAPITAL * 100
            if dd > worst_day:
                worst_day = dd

        if viol_tipo:
            estado  = f"FAIL ({viol_tipo} el {viol_fecha})"
            dias_str = "---"
        elif dias:
            estado  = f"PASS +10% alcanzado en {dias} dias hab."
            dias_str = str(dias)
        else:
            estado  = f"NO LLEGO en 6 meses (pico: +{pico:.1f}%)"
            dias_str = ">180d"

        print(f"{idx+1:>3}  {date_from:>12}  {estado:<38}  {dias_str:>6}  -{max_dd:>5.2f}%  -{worst_day:>7.2f}%")
        results.append({
            "date": date_from, "dias": dias, "pico": pico,
            "max_dd": max_dd, "worst_day": worst_day,
            "violacion": viol_tipo is not None,
        })

    print()
    print("=" * 72)

    violations  = [r for r in results if r["violacion"]]
    passed      = [r for r in results if r["dias"] and not r["violacion"]]
    not_reached = [r for r in results if not r["dias"] and not r["violacion"]]

    print(f"  Violaciones de riesgo FTMO (perdio la prueba):  {len(violations)}/{N_TESTS}")
    print(f"  Llegaron al +10% dentro de 6 meses:            {len(passed)}/{N_TESTS}")
    print(f"  No llegaron al +10% en 6 meses:                {len(not_reached)}/{N_TESTS}")

    if passed:
        dias_list = [r["dias"] for r in passed]
        print(f"  Tiempo promedio para alcanzar +10%:          {sum(dias_list)//len(dias_list)} dias habiles")
        print(f"  Tiempo minimo / maximo:                      {min(dias_list)} / {max(dias_list)} dias habiles")

    print()
    all_dd  = [r["max_dd"]    for r in results]
    all_wd  = [r["worst_day"] for r in results]
    print(f"  Drawdown total max visto:  -{max(all_dd):.2f}%  (limite FTMO: -10%)")
    print(f"  Peor dia visto:            -{max(all_wd):.2f}%  (limite FTMO:  -5%)")
    print()

    if not violations:
        print("  CONCLUSION: El bot NUNCA viola las reglas de riesgo de FTMO.")
        if not_reached:
            print(f"  En {len(not_reached)} periodo(s) no llego al +10% en 6 meses.")
            print("  Con el plan sin limite de tiempo de FTMO, solo hay que esperar mas.")
        if passed:
            dias_list = [r["dias"] for r in passed]
            print(f"  En el {len(passed)*100//N_TESTS}% de los casos llega en menos de 6 meses.")
    else:
        print(f"  ATENCION: Hubo {len(violations)} violacion(es) de reglas.")

    print()


if __name__ == "__main__":
    main()
