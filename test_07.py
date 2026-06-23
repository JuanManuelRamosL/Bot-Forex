import sys, types, random
sys.stdout.reconfigure(encoding="utf-8")

import config_ftmo as cfg_base
from engine import simulate
from mt5_client import MT5Client

CAPITAL = 10000.0
FTMO_P  = 0.10
FTMO_DD = 0.05
FTMO_TOT = 0.10
MAX_W   = 1920 * 6
N       = 15
SEED    = 42

def make_cfg(risk):
    c = types.SimpleNamespace(**{k: v for k, v in vars(cfg_base).items() if not k.startswith("__")})
    c.RISK_PER_TRADE = risk
    return c

def check_viol(equity, times, start, cap):
    d_open = cap; cur_d = None
    for j, eq in enumerate(equity):
        tidx = start + j
        if tidx >= len(times): break
        d = times[tidx][:10]
        if d != cur_d: cur_d = d; d_open = eq
        if (d_open - eq) / cap > FTMO_DD:   return "dia"
        if (cap    - eq) / cap > FTMO_TOT:  return "total"
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

client = MT5Client(cfg_base.MT5_LOGIN, cfg_base.MT5_PASSWORD, cfg_base.MT5_SERVER)
times, _, highs, lows, closes = client.get_candles(cfg_base.INSTRUMENT, cfg_base.GRANULARITY, 99000)

random.seed(SEED)
step = (len(closes) - MAX_W) // N
starts = sorted([max(0, min(i * step + random.randint(-step // 5, step // 5), len(closes) - MAX_W - 1)) for i in range(N)])

for risk in [0.006, 0.007, 0.008]:
    cfg = make_cfg(risk)
    print(f"\n{'='*70}")
    print(f"  Riesgo {risk*100:.1f}%")
    print(f"{'='*70}")
    print(f"{'#':>3}  {'Inicio':>12}  {'Resultado':<36}  {'Dias':>6}  {'MaxDD':>7}  {'PeorDia':>9}")
    print("-" * 78)
    results = []
    for idx, si in enumerate(starts):
        ei = si + MAX_W
        wt = times[si:ei]; wh = highs[si:ei]; wl = lows[si:ei]; wc = closes[si:ei]
        sim = simulate(cfg, wt, wh, wl, wc, CAPITAL)
        eq = sim["equity"]; st = sim["start"]
        if not eq: continue
        date = wt[min(30, len(wt) - 1)][:10]
        viol = check_viol(eq, wt, st, CAPITAL)
        dias = None if viol else dias_obj(eq, wt, st, CAPITAL, FTMO_P)
        pico = (max(eq) - CAPITAL) / CAPITAL * 100
        maxdd = max(0.0, (CAPITAL - min(eq)) / CAPITAL * 100)
        wd = worst_day(eq, wt, st, CAPITAL)
        if viol:  estado = f"FAIL violacion {viol}";         ds = "---"
        elif dias: estado = f"PASS +10% en {dias} dias hab."; ds = str(dias)
        else:      estado = f"NO LLEGO (pico +{pico:.1f}%)"; ds = ">180d"
        print(f"{idx+1:>3}  {date:>12}  {estado:<36}  {ds:>6}  -{maxdd:>5.2f}%  -{wd:>7.2f}%")
        results.append({"viol": viol, "dias": dias, "maxdd": maxdd, "wd": wd})
    viols  = [r for r in results if r["viol"]]
    passed = [r for r in results if r["dias"] and not r["viol"]]
    dl     = [r["dias"] for r in passed]
    print(f"\n  Pasan: {len(passed)}/15  |  Violaciones: {len(viols)}/15  |  "
          f"Dias prom: {sum(dl)//len(dl) if dl else '---'}  |  "
          f"Min/Max: {min(dl) if dl else '---'}/{max(dl) if dl else '---'}  |  "
          f"Max DD: -{max(r['maxdd'] for r in results):.2f}%  |  "
          f"Peor dia: -{max(r['wd'] for r in results):.2f}%")
