"""
Configuración del bot. Editá estos valores con tus datos de OANDA.

Cómo conseguir las credenciales (gratis):
1. Crear cuenta demo en https://www.oanda.com/  (elegí "Practice / Demo")
2. Ir a "Manage API Access" -> generar un token
3. Copiar el Account ID (formato: 101-001-XXXXXXX-001) y el token acá abajo
"""

# ─── Credenciales OANDA ───────────────────────────────────────────
# NUNCA subas este archivo a GitHub con tus claves reales.
OANDA_API_TOKEN = "PEGA_TU_TOKEN_ACA"
OANDA_ACCOUNT_ID = "PEGA_TU_ACCOUNT_ID_ACA"

# "practice" = cuenta demo (dinero virtual) | "live" = dinero real
# Empezá SIEMPRE en "practice".
OANDA_ENV = "practice"

# ─── Parámetros de la estrategia ──────────────────────────────────
INSTRUMENT      = "EUR_USD"   # par a operar (formato OANDA con guion bajo)
GRANULARITY     = "H1"        # H1 = velas de 1 hora. Otros: M15, M30, H4, D
BB_PERIOD       = 20          # períodos de la media de Bollinger
BB_STD          = 2.0         # desviaciones estándar de las bandas
ATR_PERIOD      = 14          # período del ATR (para el stop)
RSI_PERIOD      = 14          # período del RSI (filtro de confirmación)
RSI_LONG_MAX    = 45          # solo compra si RSI < este valor
RSI_SHORT_MIN   = 55          # solo vende en corto si RSI > este valor
ATR_SL_MULT     = 1.5         # stop-loss = entrada ± (ATR * este multiplicador)

# ─── Gestión de riesgo ────────────────────────────────────────────
RISK_PER_TRADE  = 0.01        # arriesgar 1% del capital por operación (0.01 = 1%)
MAX_OPEN_TRADES = 1           # cuántas posiciones simultáneas permitir

# ─── Backtest ─────────────────────────────────────────────────────
BACKTEST_CANDLES = 2000       # cuántas velas históricas bajar para el backtest
