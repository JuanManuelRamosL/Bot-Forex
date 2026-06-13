"""
Configuración del bot v2. Editá estos valores con tus datos de MetaTrader 5.

Cómo conseguir las credenciales:
1. Al registrarte en OANDA demo te mandan un email con Login, Password y Server.
2. Abrí MetaTrader 5 y logueate con esos datos.
3. Pegá los mismos datos acá abajo.

IMPORTANTE: MT5 debe estar abierto y logueado para que el bot funcione.
NUNCA subas este archivo a GitHub con tus claves reales.
"""

# ─── Credenciales MetaTrader 5 ────────────────────────────────────_yKuX6Gu
MT5_LOGIN    = 10011314164
MT5_PASSWORD = "0xI!AxBm"
MT5_SERVER   = "MetaQuotes-Demo"

# ─── Parámetros de la estrategia ──────────────────────────────────
INSTRUMENT      = "EUR_USD"   # par a operar (formato OANDA con guion bajo)
GRANULARITY     = "H1"        # H1 = velas de 1 hora. Otros: M15, M30, H4, D
BB_PERIOD       = 20          # períodos de la media de Bollinger
BB_STD          = 2.0         # desviaciones estándar de las bandas
ATR_PERIOD      = 14          # período del ATR (para el stop)
RSI_PERIOD      = 14          # período del RSI (filtro de confirmación)
RSI_LONG_MAX    = 30          # solo compra si RSI < este valor (optimizado)
RSI_SHORT_MIN   = 70          # solo vende en corto si RSI > este valor (optimizado)
ATR_SL_MULT     = 2.5         # stop-loss = entrada ± (ATR * este multiplicador) (optimizado)

# ─── MEJORA 1: Filtro de régimen (ADX) ────────────────────────────
# Mean reversion funciona en mercados LATERALES, no en tendencias.
# El ADX mide la fuerza de la tendencia: ADX bajo = lateral, ADX alto = tendencia.
# El bot solo opera cuando ADX < ADX_MAX (mercado lateral).
USE_REGIME_FILTER = True      # True para activar el filtro
ADX_PERIOD        = 14        # período del ADX
ADX_MAX           = 30        # solo operar si ADX < este valor (lateral) (optimizado)

# ─── MEJORA 2: Spread real ────────────────────────────────────────
# Spread típico en pips por par. Se descuenta en CADA operación del backtest
# para que los resultados sean honestos (no optimistas).
SPREAD_PIPS = {
    "EUR_USD": 1.2,
    "GBP_USD": 1.6,
    "USD_JPY": 1.3,
    "AUD_USD": 1.4,
}
DEFAULT_SPREAD_PIPS = 1.5     # si el par no está en la lista de arriba

# ─── MEJORA 3: Circuit breaker (freno de seguridad) ───────────────
# Si el bot pierde más de este % en un solo día, deja de abrir trades
# hasta el día siguiente. Protege contra rachas malas.
USE_CIRCUIT_BREAKER = True
MAX_DAILY_LOSS = 0.03         # 3% de pérdida diaria máxima (0.03 = 3%)

# ─── MEJORA 4: Filtro de tendencia macro (EMA) ────────────────────
# Solo compra caídas si la tendencia macro es alcista, y vende repuntes
# si es bajista. Evita pelear contra movimientos grandes (la causa #1 de
# pérdidas en mean reversion).
USE_TREND_FILTER  = False     # True para activar
TREND_EMA_PERIOD  = 200       # EMA larga que define la tendencia macro

# ─── MEJORA 5: Modo de take-profit ────────────────────────────────
# "mean" = salir al volver a la media (original, ganancias chicas y seguras)
# "rr"   = salir a un múltiplo fijo del riesgo (deja correr más las ganancias)
TP_MODE = "rr"                # optimizado: dejar correr ganadores
TP_RR   = 3.0                 # solo aplica si TP_MODE = "rr": objetivo = riesgo x esto (optimizado)

# ─── MEJORA 6: Trailing stop ──────────────────────────────────────
# Una vez en ganancia, mueve el stop a favor para proteger lo ganado
# y dejar correr las posiciones buenas.
USE_TRAILING_STOP = True      # optimizado: proteger ganancias y dejarlas correr
TRAIL_ATR_MULT    = 2.0       # distancia del trailing = ATR * esto

# ─── Gestión de riesgo ────────────────────────────────────────────
RISK_PER_TRADE  = 0.01        # arriesgar 1% del capital por operación (0.01 = 1%)
MAX_OPEN_TRADES = 1           # cuántas posiciones simultáneas permitir

# ─── Backtest ─────────────────────────────────────────────────────
BACKTEST_CANDLES = 15000      # cuántas velas históricas bajar para el backtest