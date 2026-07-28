"""
config_trend.py — Config del experimento de TENDENCIA (Donchian + ADX alto).

Lee credenciales MT5 y ajustes compartidos (instrumento, spread, riesgo, frenos
FTMO) DIRECTO de BOT_FTMO/config.py en tiempo de ejecución (no los copia acá),
así hay una sola fuente de verdad y ningún secreto queda duplicado en un
archivo nuevo. No importa ni modifica ningún módulo de BOT_FTMO más que config.

Carpeta 100% de backtest: mt5_client.py acá ni siquiera tiene métodos para
enviar órdenes.
"""

import os
import importlib.util

# Carga BOT_FTMO/config.py por RUTA DE ARCHIVO (no toca sys.path), para que
# esta carpeta siga usando su propio engine.py/mt5_client.py/strategy_trend.py
# y no los de BOT_FTMO.
_cfg_path = os.path.join(os.path.dirname(__file__), "..", "BOT_FTMO", "config.py")
_spec = importlib.util.spec_from_file_location("_bot_ftmo_config", _cfg_path)
_base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_base)

MT5_LOGIN = _base.MT5_LOGIN
MT5_PASSWORD = _base.MT5_PASSWORD
MT5_SERVER = _base.MT5_SERVER
INSTRUMENT = _base.INSTRUMENT
GRANULARITY = _base.GRANULARITY
BARS_PER_DAY = _base.BARS_PER_DAY
SPREAD_PIPS = _base.SPREAD_PIPS
DEFAULT_SPREAD_PIPS = _base.DEFAULT_SPREAD_PIPS
RISK_PER_TRADE = _base.RISK_PER_TRADE
USE_CIRCUIT_BREAKER = _base.USE_CIRCUIT_BREAKER
MAX_DAILY_LOSS = _base.MAX_DAILY_LOSS
ATR_PERIOD = _base.ATR_PERIOD
ADX_PERIOD = _base.ADX_PERIOD
BACKTEST_CANDLES = _base.BACKTEST_CANDLES
CAPITAL_INICIAL = _base.CAPITAL_INICIAL
USE_TRAILING_STOP = _base.USE_TRAILING_STOP
TRAIL_ATR_MULT = _base.TRAIL_ATR_MULT

# ─── Parámetros propios de la estrategia de tendencia ─────────────
DONCHIAN_PERIOD   = 20        # ruptura del máximo/mínimo de las últimas N velas
TREND_ADX_MIN     = 25        # solo operar si ADX >= esto (tendencia real, no ruido)
TREND_ATR_SL_MULT = 2.5       # stop-loss = entrada -/+ (ATR * esto)
TREND_TP_RR       = 3.0       # objetivo = N veces el riesgo (además del trailing)
