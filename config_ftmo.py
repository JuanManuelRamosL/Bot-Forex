"""
config_ftmo.py — Versión del bot M15 ADAPTADA a las reglas de FTMO.

Hereda TODO de config_scalp.py (misma estrategia M15 validada) y solo cambia la
GESTIÓN DE RIESGO para sobrevivir a una prueba de FTMO. No es sobreoptimización:
no se toca la estrategia, solo el tamaño de las apuestas y los frenos.

Reglas FTMO Challenge 2 pasos (2026):
  - Pérdida diaria máxima:  5% del capital inicial
  - Pérdida total máxima:  10% del capital inicial
  - Objetivo:             +10% (fase 1), +5% (fase 2)
Acá usamos márgenes MÁS conservadores que esos límites, para no rozarlos.

Backtest del bot M15 con riesgo 0.4% (14 meses): +44%, drawdown -6.3%, peor día -1.5%.
"""

from config_scalp import *   # misma estrategia M15 (BB, RSI, ADX, TP 3:1, trailing)

# ─── Riesgo reducido para FTMO ────────────────────────────────────
RISK_PER_TRADE = 0.004        # 0.4% por operación (vs 1% del bot normal)

# ─── Tamaño de la cuenta FTMO ─────────────────────────────────────
# ¡IMPORTANTE! Cambiá esto al tamaño REAL de tu cuenta FTMO (10000, 25000, 100000...)
FTMO_INITIAL_CAPITAL = 10000

# ─── Frenos alineados con FTMO (con margen de seguridad) ──────────
MAX_DAILY_LOSS = 0.04         # freno propio a 4% diario (FTMO elimina a 5%)
MAX_TOTAL_LOSS = 0.08         # freno propio a 8% total  (FTMO elimina a 10%)
PROFIT_TARGET  = 0.10         # parar al llegar a +10% (objetivo de la fase 1)

# ─── Backtest ─────────────────────────────────────────────────────
BACKTEST_CANDLES = 9000      # ~14 meses de velas M15
CAPITAL_INICIAL  = 10000      # capital simulado en el backtest

# ─── Archivos de registro propios (no mezclar con los otros bots) ──
LOG_FILE    = "bot_ftmo.log"
TRADES_FILE = "trades_ftmo.json"
