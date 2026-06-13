"""
live_bot_scalp.py — Bot EN VIVO de menor temporalidad (M15), sobre tu cuenta demo.

Misma lógica que el bot H1 (trailing stop, TP por R:R, circuit breaker, registro
en bot.log y trades.json) pero operando velas de 15 minutos y revisando el mercado
cada minuto.

Requiere MetaTrader 5 abierto y logueado.

Uso:
    python live_bot_scalp.py     (frenar con Ctrl + C)
"""

import config_scalp
from live_bot import run_live

if __name__ == "__main__":
    if config_scalp.MT5_LOGIN == 0:
        print("ERROR: Editá config.py con tus credenciales de MT5 primero.")
    else:
        run_live(config_scalp)
