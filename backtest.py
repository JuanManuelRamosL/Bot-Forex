"""
backtest.py — Corre la estrategia sobre datos HISTÓRICOS REALES de MetaTrader 5.

Usa el motor compartido engine.simulate() — el mismo que usa el optimizador,
así que lo que ves acá es exactamente lo que se optimiza.

Uso:
    python backtest.py

NO ejecuta ninguna orden real. Es 100% simulación sobre el pasado.
"""

import config
from mt5_client import MT5Client
from engine import simulate


def run_backtest():
    cfg = config
    client = MT5Client(cfg.MT5_LOGIN, cfg.MT5_PASSWORD, cfg.MT5_SERVER)

    print(f"Bajando {cfg.BACKTEST_CANDLES} velas de {cfg.INSTRUMENT} ({cfg.GRANULARITY})...")
    times, opens, highs, lows, closes = client.get_candles(
        cfg.INSTRUMENT, cfg.GRANULARITY, cfg.BACKTEST_CANDLES
    )
    print(f"Listo. {len(closes)} velas completas ({times[0][:10]} → {times[-1][:10]}).")
    if cfg.USE_REGIME_FILTER:
        print(f"Filtro de régimen ACTIVO (solo opera con ADX < {cfg.ADX_MAX})")
    if getattr(cfg, "USE_TREND_FILTER", False):
        print(f"Filtro de tendencia ACTIVO (EMA {cfg.TREND_EMA_PERIOD})")
    if getattr(cfg, "USE_TRAILING_STOP", False):
        print(f"Trailing stop ACTIVO (ATR x {cfg.TRAIL_ATR_MULT})")
    print(f"Modo TP: {getattr(cfg, 'TP_MODE', 'mean')}"
          + (f" (R:R {cfg.TP_RR})" if getattr(cfg, 'TP_MODE', 'mean') == 'rr' else ""))
    print(f"Spread aplicado: {cfg.SPREAD_PIPS.get(cfg.INSTRUMENT, cfg.DEFAULT_SPREAD_PIPS)} pips por operación")
    if cfg.USE_CIRCUIT_BREAKER:
        print(f"Circuit breaker ACTIVO (freno al perder {cfg.MAX_DAILY_LOSS*100:.0f}% en un día)\n")
    else:
        print()

    res = simulate(cfg, times, highs, lows, closes)
    print_results(res, closes)


def print_results(res, closes):
    m = res["metrics"]
    capital0 = res["capital0"]
    final = res["final"]
    trades = res["trades"]
    start = res["start"]
    bh_ret = (closes[-1] - closes[start]) / closes[start] * 100

    print("=" * 52)
    print("RESULTADOS DEL BACKTEST (con spread real)")
    print("=" * 52)
    print(f"Capital inicial:      ${capital0:,.0f}")
    print(f"Capital final:        ${final:,.2f}")
    print(f"Retorno total:        {m['total_ret']:+.2f}%")
    print(f"Retorno mensual est.: {m['monthly_ret']:+.2f}%")
    print(f"Buy & Hold del par:   {bh_ret:+.2f}%")
    print(f"Sharpe ratio:         {m['sharpe']:.2f}")
    print(f"Profit factor:        {m['profit_factor']:.2f}")
    print(f"Win rate:             {m['win_rate']:.0f}%  ({sum(1 for t in trades if t['pnl']>0)}/{len(trades)})")
    print(f"Ratio R:R:            {m['rr']:.2f}")
    print(f"Máximo drawdown:      -{m['max_dd']:.2f}%")
    print(f"Total operaciones:    {m['num_trades']}")
    if m["blocked"]:
        print(f"Señales bloqueadas por circuit breaker: {m['blocked']}")
    print("=" * 52)

    if trades:
        print("\nÚltimas 10 operaciones:")
        print(f"{'Fecha':<22}{'Dir':<7}{'Entrada':<11}{'Salida':<11}{'P&L':<12}{'Pips':<8}{'Motivo'}")
        for t in trades[-10:]:
            print(f"{t['time'][:19]:<22}{t['dir']:<7}{t['entry']:<11.5f}"
                  f"{t['exit']:<11.5f}${t['pnl']:<11.2f}{t['pips']:<8.1f}{t['reason']}")


if __name__ == "__main__":
    if config.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tu MT5_LOGIN, MT5_PASSWORD y MT5_SERVER primero.")
    else:
        run_backtest()
