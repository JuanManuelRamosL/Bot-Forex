"""
config_scalp.py — Configuración del bot de MENOR TEMPORALIDAD (M15, intradía).

Misma estrategia que el bot H1 (mean reversion con Bollinger + RSI + ADX + trailing),
pero sobre velas de 15 minutos. Los parámetros salieron de optimize_scalp.py con
validación out-of-sample (TRAIN 2025-03→2026-02 / TEST 2026-02→2026-06):
    TRAIN: +100.5%  Sharpe 3.67   |   TEST: +26.3%  Sharpe 2.99  (datos no vistos)

Las credenciales y los spreads se reutilizan de config.py (un solo lugar para editarlos).

NO toca el bot H1: este es un bot independiente con sus propios archivos.
"""

# Credenciales y spreads: reutilizados del bot principal
from config import (
    MT5_LOGIN, MT5_PASSWORD, MT5_SERVER,
    SPREAD_PIPS, DEFAULT_SPREAD_PIPS,
)

# ─── Mercado y temporalidad ───────────────────────────────────────
INSTRUMENT   = "EUR_USD"
GRANULARITY  = "M15"          # velas de 15 minutos (intradía)
BARS_PER_DAY = 96             # 96 velas de 15 min por día (para anualizar métricas)
POLL_SECONDS = 60             # en vivo, revisar el mercado cada 1 minuto

# ─── Parámetros de la estrategia (optimizados para M15) ───────────
BB_PERIOD     = 20
BB_STD        = 2.0
ATR_PERIOD    = 14
RSI_PERIOD    = 14
RSI_LONG_MAX  = 35            # compra si RSI < 35
RSI_SHORT_MIN = 65            # vende en corto si RSI > 65
ATR_SL_MULT   = 2.5           # stop-loss = entrada ± (ATR * 2.5)

# ─── Filtro de régimen (ADX) ──────────────────────────────────────
USE_REGIME_FILTER = True
ADX_PERIOD        = 14
ADX_MAX           = 30        # solo opera con ADX < 30 (mercado lateral)

# ─── Circuit breaker ──────────────────────────────────────────────
USE_CIRCUIT_BREAKER = True
MAX_DAILY_LOSS = 0.03         # freno al perder 3% en un día

# ─── Filtro de tendencia macro (apagado: no mejoró en la optimización) ──
USE_TREND_FILTER = False
TREND_EMA_PERIOD = 200

# ─── Take-profit y trailing (lo que hizo efectiva la estrategia) ──
TP_MODE = "rr"                # dejar correr ganadores
TP_RR   = 3.0                 # objetivo = 3 veces el riesgo
USE_TRAILING_STOP = True      # proteger ganancias y dejarlas correr
TRAIL_ATR_MULT    = 2.0

# ─── Gestión de riesgo ────────────────────────────────────────────
RISK_PER_TRADE  = 0.01        # 1% del capital por operación
MAX_OPEN_TRADES = 1

# ─── Backtest ─────────────────────────────────────────────────────
BACKTEST_CANDLES = 30000      # ~14 meses de velas M15

# ─── Archivos de registro (separados del bot H1 para no mezclarlos) ──
LOG_FILE    = "bot_scalp.log"
TRADES_FILE = "trades_scalp.json"
