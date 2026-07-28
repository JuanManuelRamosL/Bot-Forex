"""
mt5_client.py — Conexión con MetaTrader 5 vía la librería oficial de Python.

Copia exacta de BOT_FTMO/mt5_client.py. Duplicada acá a propósito para que esta
carpeta de experimento sea 100% independiente y no pueda afectar al bot que
corre en vivo en BOT_FTMO/.
"""

import math
import time
from datetime import datetime, timedelta
import MetaTrader5 as mt5


_TF_MAP = {
    "M1":  mt5.TIMEFRAME_M1,
    "M5":  mt5.TIMEFRAME_M5,
    "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30,
    "H1":  mt5.TIMEFRAME_H1,
    "H4":  mt5.TIMEFRAME_H4,
    "D":   mt5.TIMEFRAME_D1,
}


def _oanda_to_mt5(instrument: str) -> str:
    """EUR_USD  →  EURUSD"""
    return instrument.replace("_", "")


def _mt5_to_oanda(symbol: str) -> str:
    """EURUSD  →  EUR_USD"""
    if len(symbol) == 6:
        return symbol[:3] + "_" + symbol[3:]
    return symbol


def _filling_mode(info):
    """Elige un modo de relleno que el símbolo soporte (evita 'Unsupported filling')."""
    mode = info.filling_mode
    if mode & 1:   # SYMBOL_FILLING_FOK
        return mt5.ORDER_FILLING_FOK
    if mode & 2:   # SYMBOL_FILLING_IOC
        return mt5.ORDER_FILLING_IOC
    return mt5.ORDER_FILLING_RETURN


class MT5Client:
    def __init__(self, login: int = 0, password: str = "", server: str = ""):
        ok = mt5.initialize(timeout=15000)
        if not ok and login:
            ok = mt5.initialize(login=int(login), password=password,
                                server=server, timeout=15000)
        last = mt5.last_error()
        if not ok:
            raise RuntimeError(
                f"No se pudo conectar a MT5: {last}. "
                f"Verificá que el terminal esté abierto, logueado en {server or 'tu cuenta'} "
                f"y abierto SIN privilegios de administrador."
            )
        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"Sin info de cuenta: {mt5.last_error()}")
        if login and int(login) != info.login:
            mt5.initialize(login=int(login), password=password, server=server, timeout=15000)
            info = mt5.account_info()
            if info is None or int(login) != info.login:
                raise RuntimeError(
                    f"El MT5 está logueado en la cuenta {info.login if info else '?'} pero el "
                    f"config espera {login}. Hacé doble clic en la cuenta {login} en el "
                    f"Navigator del MT5 para activarla (o corregí MT5_LOGIN en config.py)."
                )

    def get_candles(self, instrument, granularity="H1", count=500):
        """Velas cerradas. Devuelve times (ISO), opens, highs, lows, closes."""
        sym = _oanda_to_mt5(instrument)
        tf  = _TF_MAP.get(granularity, mt5.TIMEFRAME_H1)
        mt5.symbol_select(sym, True)

        rates = mt5.copy_rates_from_pos(sym, tf, 0, count + 1)
        if rates is None or len(rates) == 0:
            raise RuntimeError(
                f"No se pudieron bajar velas de {sym} ({granularity}): {mt5.last_error()}"
            )
        rates = rates[:-1]  # descartar la vela actual (incompleta)

        times  = [datetime.utcfromtimestamp(r["time"]).strftime("%Y-%m-%dT%H:%M:%S")
                  for r in rates]
        opens  = [float(r["open"])  for r in rates]
        highs  = [float(r["high"])  for r in rates]
        lows   = [float(r["low"])   for r in rates]
        closes = [float(r["close"]) for r in rates]
        return times, opens, highs, lows, closes

    def __del__(self):
        mt5.shutdown()
