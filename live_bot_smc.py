"""
live_bot_smc.py — Bot EN VIVO con estrategia SMC + gestión de riesgo FTMO.

Requiere MetaTrader 5 abierto y logueado.

Uso:
    python live_bot_smc.py     (frenar con Ctrl + C)
"""

import config_smc
from live_bot import run_live

if __name__ == "__main__":
    if config_smc.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run_live(config_smc)
