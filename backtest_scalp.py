"""
backtest_scalp.py — Backtest del bot de menor temporalidad (M15).

Usa el mismo motor que el bot H1, pero con config_scalp.py.
NO ejecuta órdenes reales: es 100% simulación.

Uso:
    python backtest_scalp.py
"""

import config_scalp
from backtest import run_backtest

if __name__ == "__main__":
    if config_scalp.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run_backtest(config_scalp)
