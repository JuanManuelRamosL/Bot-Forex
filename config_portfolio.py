"""
config_portfolio.py — Bot SMC DIVERSIFICADO en vivo (EUR/USD + GBP/USD + NZD/USD).

Hereda de config_smc (estrategia SMC + filtros + gestión FTMO) y define:
- Los 3 pares del portfolio, cada uno con SUS parámetros óptimos (de optimize_smc_pairs.py).
- Riesgo 0.35% del equity TOTAL por operación (validado: +61%, DD -8.6% en backtest).

Los frenos FTMO (total -8%, diario -4%, objetivo +10%) se miden sobre el EQUITY TOTAL
de la cuenta, no por par. Hasta 3 posiciones simultáneas (una por par).

IMPORTANTE: ajustá FTMO_INITIAL_CAPITAL (heredado) al tamaño real de tu cuenta.
"""

from config_smc import *   # estrategia SMC + filtros + gestión de riesgo FTMO

# Riesgo por operación, como % del equity TOTAL (no por par)
RISK_PER_TRADE = 0.0035

# Pares del portfolio con sus parámetros óptimos (validados out-of-sample)
# Re-optimizados sobre 3.6 años (train 2022-2025 / test 2025-2026), validados OOS.
PORTFOLIO = {
    "EUR_USD": {"SWING_LOOKBACK": 5, "SL_BUFFER_ATR": 2.0, "TP_RR": 4.0, "FVG_MIN_ATR": 0.5},
    "GBP_USD": {"SWING_LOOKBACK": 8, "SL_BUFFER_ATR": 1.0, "TP_RR": 5.0, "FVG_MIN_ATR": 1.0},
    "NZD_USD": {"SWING_LOOKBACK": 8, "SL_BUFFER_ATR": 2.0, "TP_RR": 5.0, "FVG_MIN_ATR": 0.5},
}

# ─── Período del backtest ─────────────────────────────────────────
# Cantidad de velas M15 a simular. Equivalencias aproximadas (96 velas = 1 día):
#   2000 ≈ 1 mes   |   6000 ≈ 3 meses   |   12000 ≈ 6 meses
#   24000 ≈ 1 año  |   30000 ≈ 15 meses (máximo histórico disponible)
BACKTEST_CANDLES = 90000
CAPITAL_INICIAL  = 10000      # capital inicial simulado (USD)

# Archivos de registro propios
LOG_FILE    = "bot_portfolio.log"
TRADES_FILE = "trades_portfolio.json"
