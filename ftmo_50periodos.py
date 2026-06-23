"""
ftmo_50periodos.py — Stress test masivo: 50 fechas de inicio x 4 niveles de riesgo.

Una fecha de inicio cada ~1 mes, cubriendo los 4 anos completos (2022-2026).
Evalua si el bot pasaria FTMO (sin limite de tiempo, max 6 meses de busqueda)
con riesgo 0.4%, 0.6%, 0.7% y 0.8%.
"""

import sys, types, random
sys.stdout.reconfigure(encoding="utf-8")

import config_ftmo as cfg_base
from engine import simulate
from mt5_client import MT5Client

CAPITAL  = 10_000.0
FTMO_P   = 0.10
FTMO_DD  = 0.05
FTMO_TOT = 0.10
MAX_W    = 1_920 * 6   # ventana maxima: 6 meses
N        = 50          # fechas de inicio
SEED     = 99

RISKS = [0.004, 0.006, 0.007, 0.008]

# ── helpers ───────────────────────────────────────────────────────

def make_cfg(risk):
    c = types.SimpleNamespace(**{k: v for k, v in vars(cfg_base).items()
                                  if not k.startswith("__")})
    c.RISK_PER_TRADE = risk
    return c

def check_viol(equity, times, start, cap):
    d_open = cap; cur_d = None
    for j, eq in enumerate(equity):
        tidx = start + j
        if tidx >= len(times): break
        d = times[tidx][:10]
        if d != cur_d: cur_d = d; d_open = eq
        if (d_open - eq) / cap > FTMO_DD:  return "dia"
        if (cap    - eq) / cap > FTMO_TOT: return "total"
    return None

def dias_obj(equity, times, start, cap, pct):
    tgt = cap * (1 + pct); seen = []; cur_d = None
    for j, eq in enumerate(equity):
        tidx = start + j
        if tidx >= len(times): break
        d = times[tidx][:10]
        if d != cur_d: cur_d = d; seen.append(d)
        if eq >= tgt: return len(seen)
    return None

def worst_day(equity, times, start, cap):
    w = 0.0; d_open = cap; cur_d = None
    for j, eq in enumerate(equity):
        tidx = start + j
        if tidx >= len(times): break
        d = times[tidx][:10]
        if d != cur_d: cur_d = d; d_open = eq
        dd = (d_open - eq) / cap * 100
        if dd > w: w = dd
    return w

def run_all(cfg, times, highs, lows, closes, starts):
    out = []
    for si in starts:
        ei = si + MAX_W
        sim = simulate(cfg, times[si:ei], highs[si:ei], lows[si:ei], closes[si:ei], CAPITAL)
        eq  = sim["equity"]; st = sim["start"]
        if not eq:
            out.append(None); continue
        viol  = check_viol(eq, times[si:ei], st, CAPITAL)
        dias  = None if viol else dias_obj(eq, times[si:ei], st, CAPITAL, FTMO_P)
        pico  = (max(eq) - CAPITAL) / CAPITAL * 100
        maxdd = max(0.0, (CAPITAL - min(eq)) / CAPITAL * 100)
        wd    = worst_day(eq, times[si:ei], st, CAPITAL)
        date  = times[si + min(30, len(times[si:ei]) - 1)][:10]
        out.append({"date": date, "viol": viol, "dias": dias,
                    "pico": pico, "maxdd": maxdd, "wd": wd})
    return out

# ── main ──────────────────────────────────────────────────────────

print()
print("=" * 72)
print("  STRESS TEST MASIVO — 50 periodos x 4 niveles de riesgo")
print("=" * 72)

print("Descargando datos...")
client = MT5Client(cfg_base.MT5_LOGIN, cfg_base.MT5_PASSWORD, cfg_base.MT5_SERVER)
times, _, highs, lows, closes = client.get_candles(cfg_base.INSTRUMENT, cfg_base.GRANULARITY, 99000)
total = len(closes)
print(f"  {total:,} velas: {times[0][:10]} a {times[-1][:10]}\n")

random.seed(SEED)
step    = (total - MAX_W) // N
starts  = []
for i in range(N):
    base = i * step
    jit  = random.randint(-(step // 4), step // 4)
    starts.append(max(0, min(base + jit, total - MAX_W - 1)))
starts = sorted(starts)
print(f"  {len(starts)} fechas de inicio: {times[starts[0]][:10]} a {times[starts[-1]][:10]}")
print(f"  Separacion promedio entre fechas: ~{step // 480 * 7:.0f} dias calendario\n")

# Correr todos los tests
all_res = {}
for risk in RISKS:
    print(f"  Calculando riesgo {risk*100:.1f}%...", end=" ", flush=True)
    all_res[risk] = run_all(make_cfg(risk), times, highs, lows, closes, starts)
    print("listo")

# ── Tabla resumen ──────────────────────────────────────────────────
print()
print("=" * 72)
print("  TABLA RESUMEN (50 periodos cada uno)")
print("=" * 72)
print(f"  {'Riesgo':>8}  {'Pasan':>8}  {'%Apro':>6}  {'Violac':>7}  "
      f"{'DiasProm':>9}  {'DiasMin':>8}  {'DiasMax':>8}  {'MaxDD':>7}  {'PeorDia':>9}")
print("  " + "-" * 72)

for risk in RISKS:
    rows   = [r for r in all_res[risk] if r]
    viols  = [r for r in rows if r["viol"]]
    passed = [r for r in rows if r["dias"] and not r["viol"]]
    nomade = [r for r in rows if not r["dias"] and not r["viol"]]
    dl     = [r["dias"] for r in passed]
    maxdds = [r["maxdd"] for r in rows]
    wdays  = [r["wd"]    for r in rows]
    apro   = len(passed) / len(rows) * 100 if rows else 0

    print(f"  {risk*100:>7.1f}%  {len(passed):>3}/{len(rows):<4}  {apro:>5.0f}%  "
          f"{len(viols):>7}  "
          f"{(sum(dl)//len(dl) if dl else 0):>8}d  "
          f"{(min(dl) if dl else 0):>7}d  "
          f"{(max(dl) if dl else 0):>7}d  "
          f"{max(maxdds):>6.2f}%  "
          f"{max(wdays):>8.2f}%"
          + ("  [sin violaciones]" if not viols else f"  [{len(viols)} VIOLACIONES]"))

# ── Detalle completo caso a caso ──────────────────────────────────
print()
print("=" * 72)
print("  DETALLE POR PERIODO  (dias habiles para llegar a +10%,")
print("  'VIOL' = viola regla FTMO, 'nm' = no llego en 6 meses)")
print("=" * 72)

header = f"  {'#':>3}  {'Inicio':>12}"
for risk in RISKS:
    header += f"  {risk*100:.1f}%".rjust(9)
print(header)
print("  " + "-" * (19 + len(RISKS) * 9 + 2))

for i, si in enumerate(starts):
    date = times[si + min(30, len(times) - si - 1)][:10]
    row  = f"  {i+1:>3}  {date:>12}"
    for risk in RISKS:
        r = all_res[risk][i] if i < len(all_res[risk]) else None
        if r is None:
            row += "        N/A"
        elif r["viol"]:
            row += "       VIOL"
        elif r["dias"]:
            row += f"    {r['dias']:>4}d hab"
        else:
            row += f"  +{r['pico']:>4.1f}%(nm)"
    print(row)

# ── Periodos problematicos ────────────────────────────────────────
print()
print("=" * 72)
print("  PERIODOS PROBLEMATICOS (alguna violacion o no llego en 6m)")
print("=" * 72)
any_problem = False
for i, si in enumerate(starts):
    date = times[si + min(30, len(times) - si - 1)][:10]
    problems = []
    for risk in RISKS:
        r = all_res[risk][i] if i < len(all_res[risk]) else None
        if r and r["viol"]:
            problems.append(f"{risk*100:.1f}%:VIOLA({r['viol']})")
        elif r and not r["dias"]:
            problems.append(f"{risk*100:.1f}%:no_llego(+{r['pico']:.1f}%)")
    if problems:
        any_problem = True
        print(f"  [{i+1:>2}] {date}  ->  {', '.join(problems)}")
if not any_problem:
    print("  Ninguno -- todos los periodos pasan con todos los niveles probados.")

print()
