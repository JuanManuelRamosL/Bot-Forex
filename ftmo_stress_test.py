"""
ftmo_stress_test.py — Prueba el bot en N ventanas de 2-3 meses aleatorias.

Descarga toda la historia disponible de MT5 y evalua si el bot hubiera pasado
la Prueba FTMO Fase 1 en multiples periodos historicos distintos.

Ventanas de 2 meses por defecto (usa --months 3 para 3 meses).
El bot normalmente necesita mas de 1 mes para alcanzar +10%, por eso se evalua
en ventanas de 2-3 meses que reflejan mejor su tiempo real de prueba.

Reglas FTMO Fase 1 evaluadas:
  Objetivo de ganancia : +10% del capital inicial
  Perdida diaria max   : -5%  del capital inicial (por dia de trading)
  Perdida total max    : -10% del capital inicial (en cualquier momento)
  Minimo dias activos  : 4 dias con al menos 1 operacion

Uso:
    python ftmo_stress_test.py
    python ftmo_stress_test.py --months 3
    python ftmo_stress_test.py --windows 15 --months 2 --capital 25000
"""

import sys
import random
import argparse

import config_ftmo as cfg
from engine import simulate
from mt5_client import MT5Client

# ── Parametros fijos ──────────────────────────────────────────────
TOTAL_BARS     = 99_000    # historia a descargar (~4 anos de M15, limite MT5 demo)
BARS_PER_MONTH = 1_920     # ~1 mes calendario en M15 (4 bars/h * 24h * ~20d activos)
DEFAULT_MONTHS = 2         # duracion de cada ventana por defecto
DEFAULT_N      = 12        # ventanas a evaluar
DEFAULT_CAP    = 10_000.0  # capital inicial simulado
SEED           = 42        # semilla reproducible

# Reglas FTMO Fase 1
FTMO_PROFIT    = 0.10      # objetivo +10%
FTMO_DAY_DD    = 0.05      # perdida diaria max: 5% del capital inicial
FTMO_TOTAL_DD  = 0.10      # perdida total max: 10% del capital inicial
MIN_TRADE_DAYS = 4         # minimo 4 dias con operaciones


# ── Calculo de peor dia ───────────────────────────────────────────

def worst_daily_loss_pct(equity, times, start_idx, capital0):
    """
    Peor caida dentro de un solo dia como % del capital0.
    Regla FTMO: (equity_apertura_dia - equity_minimo_ese_dia) / capital0.
    """
    worst = 0.0
    day_open_eq = capital0
    current_day = None
    for j, eq in enumerate(equity):
        idx = start_idx + j
        if idx >= len(times):
            break
        day = times[idx][:10]
        if day != current_day:
            current_day = day
            day_open_eq = eq
        dd = (day_open_eq - eq) / capital0 * 100.0
        if dd > worst:
            worst = dd
    return worst


# ── Evaluacion FTMO Fase 1 ────────────────────────────────────────

def evaluate_ftmo(sim_result, window_times, capital0):
    """
    Evalua si los resultados de simulate() pasan FTMO Fase 1.
    Devuelve dict con: pass, reason, profit, peak_profit,
                       max_dd_abs, worst_day, n_trades, trade_days.
    """
    equity  = sim_result["equity"]
    trades  = sim_result["trades"]
    start   = sim_result["start"]

    if not trades:
        return {
            "pass": False, "reason": "Sin operaciones en el periodo",
            "profit": 0.0, "peak_profit": 0.0,
            "max_dd_abs": 0.0, "worst_day": 0.0,
            "n_trades": 0, "trade_days": 0,
        }

    trade_days   = len(set(t["time"][:10] for t in trades))
    final_profit = (equity[-1]  - capital0) / capital0 * 100.0
    peak_profit  = (max(equity) - capital0) / capital0 * 100.0

    # Drawdown absoluto: FTMO mide caida desde capital INICIAL (no desde pico)
    max_dd_abs = max(0.0, (capital0 - min(equity)) / capital0 * 100.0)

    worst_day  = worst_daily_loss_pct(equity, window_times, start, capital0)

    passed = True
    reason = ""

    if max_dd_abs > FTMO_TOTAL_DD * 100.0:
        passed = False
        reason = f"FAIL — Drawdown total: -{max_dd_abs:.2f}%  (limite -10%)"
    elif worst_day > FTMO_DAY_DD * 100.0:
        passed = False
        reason = f"FAIL — Perdida diaria: -{worst_day:.2f}%  (limite -5%)"
    elif trade_days < MIN_TRADE_DAYS:
        passed = False
        reason = f"FAIL — Solo {trade_days} dia(s) activo(s)  (minimo {MIN_TRADE_DAYS})"
    elif peak_profit < FTMO_PROFIT * 100.0:
        passed = False
        reason = f"FAIL — Maximo alcanzado: +{peak_profit:.2f}%  (objetivo +10%)"
    else:
        reason = f"PASS — Objetivo alcanzado: pico +{peak_profit:.2f}%"

    return {
        "pass": passed, "reason": reason,
        "profit": final_profit, "peak_profit": peak_profit,
        "max_dd_abs": max_dd_abs, "worst_day": worst_day,
        "n_trades": len(trades), "trade_days": trade_days,
    }


# ── Main ──────────────────────────────────────────────────────────

def main():
    # Forzar UTF-8 en la terminal de Windows para que los iconos se vean bien
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Stress test FTMO multi-periodo")
    parser.add_argument("--windows", type=int,   default=DEFAULT_N,
                        help="Numero de ventanas a probar (default: 12)")
    parser.add_argument("--months",  type=int,   default=DEFAULT_MONTHS,
                        choices=[1, 2, 3],
                        help="Duracion de cada ventana: 1, 2 o 3 meses (default: 2)")
    parser.add_argument("--capital", type=float, default=DEFAULT_CAP,
                        help="Capital inicial simulado en USD (default: 10000)")
    args = parser.parse_args()

    n_windows    = args.windows
    n_months     = args.months
    capital0     = args.capital
    window_size  = n_months * BARS_PER_MONTH

    print()
    print("=" * 68)
    print("  STRESS TEST FTMO — Bot Mean Reversion M15 EUR/USD")
    print("=" * 68)
    print(f"  Ventanas: {n_windows}   Capital: ${capital0:,.0f}   "
          f"Duracion: ~{n_months} mes(es) por ventana")
    print(f"  Riesgo/trade: {cfg.RISK_PER_TRADE*100:.1f}%   R:R objetivo: {cfg.TP_RR:.1f}   "
          f"Circuit breaker: -{cfg.MAX_DAILY_LOSS*100:.0f}% diario")
    print(f"  Filtro ADX: <{cfg.ADX_MAX}   Trailing stop: ON   "
          f"Spread: {cfg.SPREAD_PIPS.get(cfg.INSTRUMENT, cfg.DEFAULT_SPREAD_PIPS)} pips")
    print("=" * 68)

    # ── Descargar historia ─────────────────────────────────────────
    print(f"\n[1/2] Descargando hasta {TOTAL_BARS:,} velas M15 de MetaTrader 5...")
    try:
        client = MT5Client(cfg.MT5_LOGIN, cfg.MT5_PASSWORD, cfg.MT5_SERVER)
        times, _, highs, lows, closes = client.get_candles(
            cfg.INSTRUMENT, cfg.GRANULARITY, TOTAL_BARS
        )
    except Exception as exc:
        print(f"\nERROR al conectar con MT5: {exc}")
        print("Asegurate de que MetaTrader 5 este abierto y logueado.")
        sys.exit(1)

    total = len(closes)
    years = total / (480 * 52)
    print(f"    OK -- {total:,} velas ({times[0][:10]} a {times[-1][:10]}, ~{years:.1f} anos)")

    max_start = total - window_size
    if max_start < n_windows:
        print(f"\nERROR: Historia insuficiente para {n_windows} ventanas de "
              f"{n_months} mes(es). Reduce --windows o --months.")
        sys.exit(1)

    # ── Seleccionar ventanas uniformemente distribuidas ────────────
    random.seed(SEED)
    step = max_start // n_windows
    starts = []
    for i in range(n_windows):
        base   = i * step
        jitter = random.randint(-(step // 5), step // 5)
        si     = max(0, min(base + jitter, max_start - 1))
        starts.append(si)
    starts = sorted(starts)

    print(f"\n[2/2] Evaluando {len(starts)} ventanas de ~{n_months} mes(es)...\n")
    print(f"{'#':>3}  {'Periodo':<25}  {'Resultado'}")
    print("-" * 78)

    results = []
    n_pass  = 0

    for idx, si in enumerate(starts):
        ei = si + window_size
        wt = times[si:ei]
        wh = highs[si:ei]
        wl = lows[si:ei]
        wc = closes[si:ei]

        date_from = wt[30][:10] if len(wt) > 30 else wt[0][:10]
        date_to   = wt[-1][:10]

        sim  = simulate(cfg, wt, wh, wl, wc, capital0)
        ftmo = evaluate_ftmo(sim, wt, capital0)

        if ftmo["pass"]:
            n_pass += 1
            icon = "✓"
        else:
            icon = "✗"

        print(f"{idx+1:>3}  {date_from} → {date_to}   {icon} {ftmo['reason']}")
        print(f"     Profit final: {ftmo['profit']:+.2f}%  |  "
              f"Pico: +{ftmo['peak_profit']:.2f}%  |  "
              f"MaxDD: -{ftmo['max_dd_abs']:.2f}%  |  "
              f"PeorDia: -{ftmo['worst_day']:.2f}%  |  "
              f"{ftmo['n_trades']} trades / {ftmo['trade_days']} dias")
        print()

        results.append({"periodo": f"{date_from} → {date_to}", **ftmo})

    # ── Resumen final ──────────────────────────────────────────────
    print("=" * 68)
    tasa = n_pass / len(starts) * 100 if starts else 0
    print(f"  RESULTADO FINAL: {n_pass}/{len(starts)} ventanas PASARIAN FTMO Fase 1")
    print(f"  Tasa de aprobacion: {tasa:.0f}%  (en ventanas de ~{n_months} mes(es))")
    print("=" * 68)

    def avg(lst): return sum(lst) / len(lst) if lst else 0.0

    profits = [r["profit"]      for r in results]
    peaks   = [r["peak_profit"] for r in results]
    dds     = [r["max_dd_abs"]  for r in results]
    wdays   = [r["worst_day"]   for r in results]
    ntrades = [r["n_trades"]    for r in results]

    print(f"  Profit promedio:    {avg(profits):+.2f}%  "
          f"(pico prom: +{avg(peaks):.2f}%)")
    print(f"  Drawdown promedio: -{avg(dds):.2f}%  "
          f"(peor registro: -{max(dds):.2f}%)")
    print(f"  Peor dia prom:     -{avg(wdays):.2f}%  "
          f"(peor registro: -{max(wdays):.2f}%)")
    print(f"  Trades promedio:    {avg(ntrades):.0f} por ventana")
    print()

    # Diagnostico
    if n_pass == len(starts):
        print("  DIAGNOSTICO: Bot MUY CONSISTENTE.")
        print("  Paso FTMO en el 100% de los periodos probados.")
        print("  Muy buen candidato para la prueba real.")
    elif tasa >= 75:
        print("  DIAGNOSTICO: Bot BASTANTE CONSISTENTE.")
        print("  Pasa en la gran mayoria de periodos; los fallos suelen ser")
        print("  periodos de tendencia sostenida (ADX > 30) donde el mean")
        print("  reversion no opera y no llega al objetivo de ganancia.")
    elif tasa >= 50:
        print("  DIAGNOSTICO: Bot MODERADO — pasa en la mitad de periodos.")
        print("  Posibles causas:")
        print("  1. El +10% en 2 meses es dificil con solo 0.4% de riesgo.")
        print("  2. Periodos de tendencia fuerte reducen las oportunidades.")
        print("  Considera probar con cuenta de $25k o $50k (mismo % de ganancia,")
        print("  mas margenes de error) o ajustar RISK_PER_TRADE a 0.006-0.008.")
    else:
        print("  DIAGNOSTICO: Bot INCONSISTENTE para FTMO con estos parametros.")
        print("  El principal problema es no alcanzar +10% en el tiempo dado.")
        print("  Revisar: RISK_PER_TRADE, duracion de la ventana, TP_RR.")

    # Lista periodos fallidos
    failed = [r for r in results if not r["pass"]]
    if failed:
        fail_reasons = {}
        for r in failed:
            key = r["reason"].split("—")[1].strip().split(":")[0].strip() if "—" in r["reason"] else "Otro"
            fail_reasons[key] = fail_reasons.get(key, 0) + 1
        print()
        print(f"  Causas de fallo ({len(failed)} periodos):")
        for cause, count in sorted(fail_reasons.items(), key=lambda x: -x[1]):
            print(f"    • {cause}: {count} vez/veces")

    print()


if __name__ == "__main__":
    main()
