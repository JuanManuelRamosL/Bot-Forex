"""
backtest_compare_tp.py — Compara la config ACTUAL (TP_MODE="rr" 3:1 + trailing
ATR x2.0) contra alternativas de salida (TP_MODE="mean", trailing más suelto)
sobre los MISMOS datos históricos.

Es de solo lectura: no modifica config.py ni ejecuta ninguna orden real. Solo
baja velas históricas y corre engine.simulate() con distintas copias del config
en memoria (igual que optimize.py, pero comparando variantes puntuales en vez
de barrer un grid completo).

Uso:
    python backtest_compare_tp.py
"""

import types
import config
from mt5_client import MT5Client
from engine import simulate


def clone_cfg(**overrides):
    """Copia los atributos de config.py a un objeto nuevo y le aplica overrides,
    sin tocar el módulo config real (así las variantes no se pisan entre sí)."""
    ns = types.SimpleNamespace(**{k: v for k, v in vars(config).items() if not k.startswith("_")})
    for k, v in overrides.items():
        setattr(ns, k, v)
    return ns


VARIANTS = [
    ("ACTUAL (rr 3:1 + trailing x2.0)",      clone_cfg()),
    ("MEAN (sale en la media, sin trailing)", clone_cfg(TP_MODE="mean", USE_TRAILING_STOP=False)),
    ("MEAN + trailing x2.0",                  clone_cfg(TP_MODE="mean", USE_TRAILING_STOP=True)),
    ("RR 3:1 + trailing mas suelto (x3.5)",   clone_cfg(TRAIL_ATR_MULT=3.5)),
]

HEADER = (f"{'Variante':<40}{'Retorno':>10}{'PF':>7}{'WinRate':>9}"
          f"{'R:R':>7}{'MaxDD':>8}{'Trades':>8}")


def fmt_row(name, res):
    m = res["metrics"]
    return (f"{name:<40}{m['total_ret']:>+9.2f}%{m['profit_factor']:>7.2f}"
            f"{m['win_rate']:>8.1f}%{m['rr']:>7.2f}{m['max_dd']:>7.2f}%{m['num_trades']:>8}")


def print_table(times, highs, lows, closes, capital0, variants=None):
    print(HEADER)
    print("-" * len(HEADER))
    for name, cfg in (variants if variants is not None else VARIANTS):
        res = simulate(cfg, times, highs, lows, closes, capital0=capital0)
        print(fmt_row(name, res))


def main():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    print(f"Bajando {config.BACKTEST_CANDLES} velas de {config.INSTRUMENT} ({config.GRANULARITY})...")
    times, opens, highs, lows, closes = client.get_candles(
        config.INSTRUMENT, config.GRANULARITY, config.BACKTEST_CANDLES
    )
    print(f"Listo. {len(closes)} velas completas ({times[0][:10]} -> {times[-1][:10]})\n")

    print("=== Historico completo ===")
    print_table(times, highs, lows, closes, config.CAPITAL_INICIAL)

    # Ventana reciente ~ equivalente a las 2.5 semanas que lleva operando el bot en
    # vivo (96 velas M15/dia x ~17.5 dias). Sirve para ver si el ranking cambia en
    # el regimen de mercado mas reciente, no solo en el promedio de 3.6 anios.
    n_recent = 96 * 18
    print(f"\n=== Solo las ultimas {n_recent} velas (~18 dias, el tramo mas reciente) ===")
    print_table(times[-n_recent:], highs[-n_recent:], lows[-n_recent:], closes[-n_recent:],
                config.CAPITAL_INICIAL)

    # Barrido de TRAIL_ATR_MULT sobre el historico completo: la comparacion de
    # arriba solo prueba 2.0 (actual) y 3.5 (una alternativa suelta). Esto barre
    # el rango completo para ver si 2.0 ya es un optimo o si hay algo mejor, en
    # vez de decidir con 2 puntos sueltos.
    print("\n=== Barrido de TRAIL_ATR_MULT (rr 3:1, historico completo) ===")
    sweep = [(f"trailing x{m}" if m else "sin trailing",
              clone_cfg(TRAIL_ATR_MULT=m, USE_TRAILING_STOP=bool(m)))
             for m in [None, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]]
    print_table(times, highs, lows, closes, config.CAPITAL_INICIAL, variants=sweep)

    print(f"\n=== Mismo barrido, solo ultimas {n_recent} velas (~18 dias) ===")
    print_table(times[-n_recent:], highs[-n_recent:], lows[-n_recent:], closes[-n_recent:],
                config.CAPITAL_INICIAL, variants=sweep)


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        main()
