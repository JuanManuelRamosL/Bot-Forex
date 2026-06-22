"""
live_bot_ftmo.py — Bot M15 EN VIVO adaptado a las reglas de FTMO.

Misma estrategia M15, pero con riesgo 0.4% y frenos FTMO:
  - Para el bot si la pérdida total toca -8% (antes del -10% que elimina en FTMO).
  - Bloquea el día si la pérdida diaria toca -4% (antes del -5% de FTMO).
  - Para el bot al alcanzar +10% (objetivo de la fase, para no arriesgar de más).

IMPORTANTE: ajustá FTMO_INITIAL_CAPITAL en config_ftmo.py al tamaño real de tu cuenta.
Requiere MetaTrader 5 abierto y logueado en la cuenta de FTMO.

Uso:
    python live_bot_ftmo.py     (frenar con Ctrl + C)
"""

import config_ftmo
from live_bot import run_live

if __name__ == "__main__":
    if config_ftmo.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run_live(config_ftmo)
