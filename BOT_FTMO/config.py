"""
config.py — Bot GANADOR para FTMO (mean reversion M15).

Esta es la estrategia que ganó tras probar todo (mean reversion vs SMC, single vs
multi-par) sobre 3.6 años de historia:
    +283% | Sharpe 3.89 | Profit Factor 1.43 | Drawdown -6.31% | CUMPLE FTMO

Estrategia: mean reversion con Bandas de Bollinger + RSI + filtro ADX, salida por
ratio 3:1 con trailing stop. Riesgo 0.4% por trade + frenos FTMO.

Todo está en este archivo (sin depender de otros configs). Editá lo que necesites.
"""

# ─── Credenciales MetaTrader 5 ────────────────────────────────────
# MT5 debe estar abierto y logueado en esta cuenta. NUNCA subas esto a GitHub.
MT5_LOGIN    = 5052108194
MT5_PASSWORD = "Wh_d4kZe"
MT5_SERVER   = "MetaQuotes-Demo"

# ─── Mercado y temporalidad ───────────────────────────────────────
INSTRUMENT   = "EUR_USD"
GRANULARITY  = "M15"          # velas de 15 minutos
BARS_PER_DAY = 96             # para anualizar métricas
POLL_SECONDS = 60             # en vivo, revisar el mercado cada 1 minuto

# ─── Parámetros de la estrategia ──────────────────────────────────
BB_PERIOD     = 20
BB_STD        = 2.0
ATR_PERIOD    = 14
RSI_PERIOD    = 14
RSI_LONG_MAX  = 35            # compra si RSI < 35
RSI_SHORT_MIN = 65            # vende en corto si RSI > 65
ATR_SL_MULT   = 2.5           # stop-loss = entrada ± (ATR * 2.5)

# ─── Filtro de régimen (ADX): solo opera en mercado lateral ───────
USE_REGIME_FILTER = True
ADX_PERIOD        = 14
ADX_MAX           = 30

# ─── Take-profit y trailing (lo que hace efectiva la estrategia) ──
TP_MODE = "rr"                # salir a un múltiplo del riesgo (dejar correr ganadores)
TP_RR   = 3.0                 # objetivo = 3 veces el riesgo
USE_TRAILING_STOP = True      # mover el stop a favor para proteger ganancias
TRAIL_ATR_MULT    = 2.0

# Filtro de tendencia macro: apagado (no mejoró en la optimización)
USE_TREND_FILTER = False
TREND_EMA_PERIOD = 200

# ─── Spreads (descontados en el backtest para resultados honestos) ─
SPREAD_PIPS = {
    "EUR_USD": 1.2,
    "GBP_USD": 1.6,
    "USD_JPY": 1.3,
    "AUD_USD": 1.4,
}
DEFAULT_SPREAD_PIPS = 1.5

# ─── Gestión de riesgo + reglas FTMO ──────────────────────────────
RISK_PER_TRADE  = 0.005       # 0.5% del capital por operación (ajustado para FTMO)
MAX_OPEN_TRADES = 1

USE_CIRCUIT_BREAKER  = True
FTMO_INITIAL_CAPITAL = 10000  # ← CAMBIÁ esto al tamaño REAL de tu cuenta FTMO
MAX_DAILY_LOSS = 0.04         # freno propio a 4% diario  (FTMO elimina a 5%)
MAX_TOTAL_LOSS = 0.08         # freno propio a 8% total   (FTMO elimina a 10%)
PROFIT_TARGET  = 0.10         # parar al llegar a +10% (objetivo de la fase 1)

# Si está en False, el bot NO se apaga solo al tocar el objetivo (+10%) ni el
# freno total (-8%): se enciende y queda corriendo hasta que lo frenes con Ctrl+C.
# (El circuit breaker diario y los SL/TP de cada trade siguen funcionando igual.)
FTMO_AUTO_STOP = True   # detiene el bot al llegar al +10% (necesario para FTMO)

# ─── Backtest ─────────────────────────────────────────────────────
# 96 velas = 1 día. 24000 ≈ 1 año, 90000 ≈ 3.6 años (máximo disponible).
BACKTEST_CANDLES = 300
CAPITAL_INICIAL  = 10000

# ─── Notificaciones Telegram ──────────────────────────────────────
# Token del bot @Juanforexbot. Para obtener tu CHAT_ID: python get_chat_id.py
TELEGRAM_TOKEN   = "8287464229:AAH3whKvLBfg6NmddFTuGFZ4Q4r46w1pESE"
TELEGRAM_CHAT_ID = "2045946385"   # ← completar con tu chat_id (correr get_chat_id.py)

# ─── Archivos de registro ─────────────────────────────────────────
LOG_FILE    = "bot.log"
TRADES_FILE = "trades.json"
