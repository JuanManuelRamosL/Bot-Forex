"""
backtest_ftmo.py — Backtest del bot M15 con la gestión de riesgo de FTMO.

Uso:
    python backtest_ftmo.py
"""

import config_ftmo
from backtest import run_backtest

if __name__ == "__main__":
    if config_ftmo.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run_backtest(config_ftmo)
