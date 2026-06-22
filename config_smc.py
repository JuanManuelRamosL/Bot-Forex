"""
config_smc.py — Bot con estrategia Smart Money Concepts (SMC) + gestión de riesgo FTMO.

Hereda de config_ftmo.py toda la GESTIÓN DE RIESGO (riesgo 0.4%, frenos FTMO,
capital base, etc.) y cambia la ESTRATEGIA a SMC (estructura + FVG, trend-following).

La idea: misma protección que el bot FTMO, pero buscando un R:R más alto con SMC.
"""

from config_ftmo import *   # gestión de riesgo FTMO + credenciales + temporalidad M15

# ─── Estrategia ───────────────────────────────────────────────────
STRATEGY = "smc"              # usa strategy_smc.SMCStrategy

# ─── Riesgo ───────────────────────────────────────────────────────
# SMC tiene drawdown muy bajo, así que puede arriesgar más que el mean reversion
# (0.4%) y AÚN cumplir FTMO. A 0.6% supera al mean rev en ganancia (DD ~-7.2% < 10%).
RISK_PER_TRADE = 0.006

# ─── Parámetros SMC (base; optimize_smc.py busca los mejores) ─────
# Optimizado out-of-sample: TRAIN +17.6% / TEST +10.2% (PF 1.68, Sharpe 3.97, DD -4.4%)
SWING_LOOKBACK = 5            # velas a cada lado para confirmar un swing (estructura)
SL_BUFFER_ATR  = 2.0         # margen del stop por debajo/encima de la zona FVG (en ATR)
TP_RR          = 4.0         # objetivo = 4x el riesgo (ratio grande, sostenible)

# ─── Filtros de calidad (suben el ratio) ──────────────────────────
USE_HTF_BIAS        = True   # operar solo a favor de la tendencia mayor (EMA larga) ← CLAVE
HTF_EMA_PERIOD      = 200    # EMA que define la tendencia mayor
FVG_MIN_ATR         = 0.5    # ignorar FVGs más chicos que esto (en ATR) = filtrar ruido ← CLAVE
USE_PREMIUM_DISCOUNT = False # no aportó en la optimización
MAX_ENTRIES_PER_LEG = 2      # máximo de entradas por tramo de tendencia (anti-overtrading)

# El filtro ADX es de mean reversion; SMC es trend-following, así que lo apagamos
# (no afecta la lógica SMC, pero evita mensajes engañosos en el backtest).
USE_REGIME_FILTER = False

# ─── Archivos de registro propios ─────────────────────────────────
LOG_FILE    = "bot_smc.log"
TRADES_FILE = "trades_smc.json"
