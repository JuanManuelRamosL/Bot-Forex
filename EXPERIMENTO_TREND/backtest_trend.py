"""
backtest_trend.py — Backtest de la estrategia de TENDENCIA (Donchian + ADX alto).

100% aislado de BOT_FTMO: solo LEE credenciales de BOT_FTMO/config.py (vía
config_trend.py) para bajar velas históricas de MT5. No opera, no puede tocar
la cuenta real ni el bot en vivo.

Uso (con el venv activado):
    python backtest_trend.py
"""

import config_trend as config
from mt5_client import MT5Client
from engine import simulate


def print_results(res, closes, label=""):
    m = res["metrics"]
    capital0 = res["capital0"]
    final = res["final"]
    trades = res["trades"]

    print("=" * 60)
    print(f"RESULTADOS DEL BACKTEST — TREND {label}".strip())
    print("=" * 60)
    print(f"Capital inicial:      ${capital0:,.0f}")
    print(f"Capital final:        ${final:,.2f}")
    print(f"Retorno total:        {m['total_ret']:+.2f}%")
    print(f"Retorno mensual est.: {m['monthly_ret']:+.2f}%")
    print(f"Sharpe ratio:         {m['sharpe']:.2f}")
    print(f"Profit factor:        {m['profit_factor']:.2f}")
    print(f"Win rate:             {m['win_rate']:.0f}%  ({sum(1 for t in trades if t['pnl']>0)}/{len(trades)})")
    print(f"Ratio R:R:            {m['rr']:.2f}")
    print(f"Máximo drawdown:      -{m['max_dd']:.2f}%")
    print(f"Total operaciones:    {m['num_trades']}")
    print("=" * 60)


def run_backtest():
    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)
    print(f"Bajando {config.BACKTEST_CANDLES} velas de {config.INSTRUMENT} ({config.GRANULARITY})...")
    times, opens, highs, lows, closes = client.get_candles(
        config.INSTRUMENT, config.GRANULARITY, config.BACKTEST_CANDLES
    )
    print(f"Listo. {len(closes)} velas ({times[0][:10]} -> {times[-1][:10]}).")
    print(f"Donchian {config.DONCHIAN_PERIOD} | ADX >= {config.TREND_ADX_MIN} | "
          f"SL {config.TREND_ATR_SL_MULT}x ATR | TP R:R {config.TREND_TP_RR}\n")

    cap = getattr(config, "CAPITAL_INICIAL", 10000.0)
    res = simulate(config, times, highs, lows, closes, capital0=cap)
    print_results(res, closes)


if __name__ == "__main__":
    run_backtest()
