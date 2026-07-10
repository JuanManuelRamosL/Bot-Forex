"""
backtest_inverse.py — Backtest de la variante INVERTIDA (ver strategy_inverse.py).

Reutiliza el mismo motor, datos y config que backtest.py (mismo capital, riesgo,
spread y período), solo cambia la dirección de las señales, para comparar
manzanas con manzanas contra la mean reversion original.

Uso (desde esta carpeta, con el venv activado):
    python backtest_inverse.py
"""

import config
from backtest import run_backtest

config.STRATEGY = "inverse"

if __name__ == "__main__":
    run_backtest()
