"""
montecarlo.py — Riesgo FTMO por Monte Carlo (bootstrap de operaciones).

Toma las operaciones reales del backtest y las rebaraja MILES de veces para
estimar, antes de pagar el challenge, las dos cosas que deciden FTMO:

  - PASAR:  llegar a +PROFIT_TARGET (+10%) ...
  - QUEMAR: ... antes de tocar el límite de pérdida total de FTMO (-10%).

Usa bootstrap POR BLOQUES (no baraja trade por trade) para no destruir las
RACHAS de pérdidas, que son lo que realmente revienta un challenge. También
reporta la peor pérdida diaria y la peor racha histórica vs los límites de FTMO.

Modelo: riesgo fijo-fraccional = RISK_PER_TRADE del equity en cada trade, igual
que el bot. Cada operación mueve el equity en (1 + RISK * R), donde R es el
resultado en múltiplos de riesgo (lo provee engine.simulate).

Requiere MT5 abierto. NO opera: es 100% simulación.

Uso:
    python montecarlo.py
"""

import sys
import random
import config
from mt5_client import MT5Client
from engine import simulate

try:
    sys.stdout.reconfigure(encoding="utf-8")  # consola Windows: permitir → y emojis
except Exception:
    pass

# ── Ajustes ───────────────────────────────────────────────────────
CANDLES = 40000          # velas a pedir (más velas = muestra de trades más robusta)
N_SIMS  = 20000          # cantidad de challenges simulados
BLOCK   = 5              # tamaño de bloque del bootstrap (preserva rachas); 1 = iid
MAX_TRADES = 3000        # tope de trades por intento (anti-bucle infinito)

# Límites REALES de FTMO (no los internos, más conservadores, del bot)
FTMO_TOTAL_LIMIT = 0.10  # pérdida total máxima: 10% del capital inicial
FTMO_DAILY_LIMIT = 0.05  # pérdida diaria máxima: 5%
PROFIT_TARGET    = 0.10  # objetivo fase 1: +10%

RISK = config.RISK_PER_TRADE


def attempt(Rs):
    """Simula un challenge: muestrea bloques de trades hasta PASAR, QUEMAR o agotar."""
    n = len(Rs)
    eq = 1.0
    count = 0
    min_eq = 1.0
    while count < MAX_TRADES:
        start = random.randrange(n)
        for k in range(BLOCK):
            r = Rs[(start + k) % n]
            eq *= (1 + RISK * r)
            count += 1
            min_eq = min(min_eq, eq)
            if eq <= 1 - FTMO_TOTAL_LIMIT:
                return "FAIL", count, min_eq
            if eq >= 1 + PROFIT_TARGET:
                return "PASS", count, min_eq
    return "UNRESOLVED", count, min_eq


def worst_daily_loss(equity, bar_times):
    """Peor caída intradía (desde el equity de apertura del día) en la curva real."""
    worst = 0.0
    cur_day = None
    day_start = None
    for e, t in zip(equity, bar_times):
        day = t[:10]
        if day != cur_day:
            cur_day = day
            day_start = e
        if day_start:
            worst = max(worst, (day_start - e) / day_start)
    return worst


def worst_losing_run(Rs):
    """Peor racha: máxima pérdida acumulada (en % de equity) trade a trade."""
    eq = 1.0
    peak = 1.0
    worst = 0.0
    longest = run = 0
    for r in Rs:
        eq *= (1 + RISK * r)
        peak = max(peak, eq)
        worst = max(worst, (peak - eq) / peak)
        run = run + 1 if r <= 0 else 0
        longest = max(longest, run)
    return worst, longest


def pct(x):
    return f"{x*100:.2f}%"


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    print(f"Bajando hasta {CANDLES} velas de {config.INSTRUMENT} ({config.GRANULARITY})...")
    times, opens, highs, lows, closes = client.get_candles(
        config.INSTRUMENT, config.GRANULARITY, CANDLES)
    res = simulate(config, times, highs, lows, closes, capital0=10000)
    trades = res["trades"]
    Rs = [t["R"] for t in trades]
    if len(Rs) < 20:
        print(f"Solo {len(Rs)} operaciones: muestra demasiado chica para Monte Carlo "
              f"confiable. Subí CANDLES o ampliá el período.")
        return

    print(f"Listo. {len(Rs)} operaciones reales del backtest "
          f"({times[0][:10]} → {times[-1][:10]}).")
    print(f"Riesgo por trade: {RISK*100:.2f}%  |  Simulaciones: {N_SIMS}  |  "
          f"bloque bootstrap: {BLOCK}\n")

    # ── Diagnóstico de la curva real (límites diario y rachas) ──
    start = res["start"]
    bar_times = times[start:start + len(res["equity"])]
    wd = worst_daily_loss(res["equity"], bar_times)
    wr, longest = worst_losing_run(Rs)
    print("=" * 70)
    print("DIAGNÓSTICO DE LA CURVA REAL (backtest)")
    print("=" * 70)
    print(f"  Peor pérdida diaria:        -{pct(wd)}   (límite FTMO -{pct(FTMO_DAILY_LIMIT)})"
          + ("   ✅" if wd < FTMO_DAILY_LIMIT else "   ⚠️ ROZA/SUPERA"))
    print(f"  Peor drawdown (rachas):     -{pct(wr)}   (límite FTMO -{pct(FTMO_TOTAL_LIMIT)})"
          + ("   ✅" if wr < FTMO_TOTAL_LIMIT else "   ⚠️ ROZA/SUPERA"))
    print(f"  Racha de pérdidas más larga: {longest} operaciones seguidas")

    # ── Monte Carlo ──
    outcomes = {"PASS": 0, "FAIL": 0, "UNRESOLVED": 0}
    trades_to_pass = []
    worst_eqs = []
    for _ in range(N_SIMS):
        out, count, min_eq = attempt(Rs)
        outcomes[out] += 1
        worst_eqs.append(min_eq)
        if out == "PASS":
            trades_to_pass.append(count)

    p_pass = outcomes["PASS"] / N_SIMS
    p_fail = outcomes["FAIL"] / N_SIMS
    p_unres = outcomes["UNRESOLVED"] / N_SIMS
    worst_eqs.sort()
    p5_dd = 1 - worst_eqs[int(0.05 * N_SIMS)]   # drawdown del peor 5% de los casos

    print("\n" + "=" * 70)
    print(f"MONTE CARLO — {N_SIMS} challenges simulados (límites REALES de FTMO)")
    print("=" * 70)
    print(f"  Probabilidad de PASAR (+{pct(PROFIT_TARGET)} antes de -{pct(FTMO_TOTAL_LIMIT)}): "
          f"{pct(p_pass)}")
    print(f"  Probabilidad de QUEMAR la cuenta (-{pct(FTMO_TOTAL_LIMIT)} total):        "
          f"{pct(p_fail)}")
    if p_unres > 0.01:
        print(f"  Sin resolver dentro de {MAX_TRADES} trades:                    {pct(p_unres)}")
    if trades_to_pass:
        trades_to_pass.sort()
        med = trades_to_pass[len(trades_to_pass) // 2]
        print(f"  Operaciones típicas para llegar al objetivo (mediana): {med}")
    print(f"  Drawdown del peor 5% de los escenarios: -{pct(p5_dd)}")

    print("\n" + "=" * 70)
    print("CÓMO LEERLO")
    print("=" * 70)
    if p_fail > 0.30:
        print("  ⚠️  Más de 1 de cada 3 intentos quema la cuenta: riesgo ALTO para FTMO.")
    elif p_pass > 2 * p_fail:
        print("  ✅  Pasás bastante más seguido de lo que quemás. Perfil razonable,")
        print("      pero recordá que el Monte Carlo asume que el futuro se parece al")
        print("      backtest (mismo problema de sobreoptimización: ver walk_forward.py).")
    else:
        print("  ⚖️  Pasar y quemar están parejos: el resultado depende mucho de la suerte")
        print("      de la racha. Considerá bajar el riesgo por trade para inclinar la balanza.")


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales MT5 primero.")
    else:
        main()
