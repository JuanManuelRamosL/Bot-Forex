"""
backtest_smc.py — Backtest del bot SMC (Smart Money Concepts) con gestión FTMO.

Uso:
    python backtest_smc.py
"""

import config_smc
from backtest import run_backtest

if __name__ == "__main__":
    if config_smc.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run_backtest(config_smc)
