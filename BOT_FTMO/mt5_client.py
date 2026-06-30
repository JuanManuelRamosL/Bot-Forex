"""
mt5_client.py — Conexión con MetaTrader 5 vía la librería oficial de Python.

Reemplaza a oanda_client.py. Requiere:
- MetaTrader 5 instalado, abierto y logueado en la PC.
- pip install MetaTrader5
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
        # Se conecta al terminal MT5 ya abierto. Primero intenta adjuntarse a la
        # sesión activa; si falla (típico IPC timeout), reintenta forzando el login
        # con las credenciales del config. Hasta 3 intentos.
        # 1) Adjuntarse a la sesión ACTIVA del terminal (funciona aun en fin de
        #    semana si la cuenta correcta ya está abierta en el MT5).
        ok = mt5.initialize(timeout=15000)
        # 2) Si la activa no conecta y hay credenciales, intentar forzar el login
        #    (esto requiere que el servidor esté online: no funciona en fin de semana).
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
        # 3) Garantía de cuenta correcta: si el config pide una cuenta puntual y la
        #    activa NO es esa, intentar cambiarla; si no se puede, ABORTAR (nunca
        #    operar en la cuenta equivocada).
        if login and int(login) != info.login:
            mt5.initialize(login=int(login), password=password, server=server, timeout=15000)
            info = mt5.account_info()
            if info is None or int(login) != info.login:
                raise RuntimeError(
                    f"El MT5 está logueado en la cuenta {info.login if info else '?'} pero el "
                    f"config espera {login}. Hacé doble clic en la cuenta {login} en el "
                    f"Navigator del MT5 para activarla (o corregí MT5_LOGIN en config.py)."
                )

    # ── Datos históricos ──────────────────────────────────────────────

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

    # ── Cuenta ───────────────────────────────────────────────────────

    def get_account_summary(self):
        info = mt5.account_info()
        if info is None:
            raise RuntimeError(f"Sin info de cuenta: {mt5.last_error()}")
        return {
            "id":       str(info.login),
            "balance":  str(info.balance),
            "equity":   str(info.equity),
            "currency": info.currency,
        }

    # ── Posiciones abiertas ───────────────────────────────────────────

    def get_open_trades(self):
        """
        Lista de posiciones con: id (ticket), instrument, currentUnits
        (>0 LONG, <0 SHORT), entry (precio de apertura), sl, tp.
        """
        positions = mt5.positions_get()
        if positions is None:
            return []
        result = []
        for p in positions:
            units = p.volume * 100_000
            if p.type != mt5.POSITION_TYPE_BUY:
                units = -units
            result.append({
                "id":           p.ticket,
                "instrument":   _mt5_to_oanda(p.symbol),
                "currentUnits": units,
                "entry":        p.price_open,
                "sl":           p.sl,
                "tp":           p.tp,
                "volume":       p.volume,
            })
        return result

    # ── Cálculo de tamaño (sizing) ────────────────────────────────────

    def calc_lots(self, instrument, risk_amount, sl_dist):
        """
        Convierte 'cuánto dinero arriesgar' + 'distancia al stop (en precio)'
        en un volumen de lotes VÁLIDO para el símbolo (respeta min/max/step).

        Usa el valor real del tick del símbolo, así funciona para cualquier par
        (no asume que la moneda de cotización sea USD).
        Devuelve (lots, riesgo_real_estimado).
        """
        sym = _oanda_to_mt5(instrument)
        if not mt5.symbol_select(sym, True):
            raise RuntimeError(f"No se pudo activar el símbolo {sym}")
        info = mt5.symbol_info(sym)
        if info is None:
            raise RuntimeError(f"Sin info del símbolo {sym}: {mt5.last_error()}")

        tick_size  = info.trade_tick_size or 0.0
        tick_value = info.trade_tick_value or 0.0
        if tick_size > 0 and tick_value > 0:
            loss_per_lot = (sl_dist / tick_size) * tick_value
        else:  # fallback genérico (contrato estándar de 100k)
            loss_per_lot = sl_dist * 100_000
        if loss_per_lot <= 0:
            return 0.0, 0.0

        raw = risk_amount / loss_per_lot

        step = info.volume_step or 0.01
        lots = math.floor(raw / step) * step
        lots = max(info.volume_min, min(lots, info.volume_max))
        lots = round(lots, 2)

        real_risk = lots * loss_per_lot
        return lots, real_risk

    # ── Órdenes ──────────────────────────────────────────────────────

    def place_market_order(self, instrument, direction, lots, stop_loss=None, take_profit=None):
        """
        Abre una orden de mercado.
        direction: "LONG" o "SHORT".  lots: volumen ya validado.
        stop_loss / take_profit: precios absolutos.
        """
        sym = _oanda_to_mt5(instrument)
        if not mt5.symbol_select(sym, True):
            raise RuntimeError(f"No se pudo activar el símbolo {sym}")
        info = mt5.symbol_info(sym)
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            raise RuntimeError(f"No se pudo obtener precio de {sym}: {mt5.last_error()}")

        if direction == "LONG":
            order_type, price = mt5.ORDER_TYPE_BUY, tick.ask
        else:
            order_type, price = mt5.ORDER_TYPE_SELL, tick.bid

        digits = info.digits
        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       sym,
            "volume":       float(lots),
            "type":         order_type,
            "price":        price,
            "deviation":    20,
            "magic":        234000,
            "comment":      "forex-bot",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": _filling_mode(info),
        }
        if stop_loss is not None:
            request["sl"] = round(stop_loss, digits)
        if take_profit is not None:
            request["tp"] = round(take_profit, digits)

        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            err = result.comment if result else str(mt5.last_error())
            code = getattr(result, "retcode", "?")
            raise RuntimeError(f"Orden fallida (retcode={code}): {err}")
        return {"id": result.order}

    def modify_stop_loss(self, ticket, new_sl, take_profit=None):
        """Mueve el stop-loss de una posición abierta (para el trailing stop)."""
        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            return None
        pos    = positions[0]
        info   = mt5.symbol_info(pos.symbol)
        digits = info.digits if info else 5
        request = {
            "action":   mt5.TRADE_ACTION_SLTP,
            "symbol":   pos.symbol,
            "position": int(ticket),
            "sl":       round(new_sl, digits),
            "tp":       round(take_profit, digits) if take_profit is not None else pos.tp,
        }
        return mt5.order_send(request)

    def get_deal_result(self, position_id, days_back=90):
        """
        Resultado real de una posición CERRADA (por SL/TP/trailing/manual).
        Devuelve {pnl, exit_price} o None si no encuentra el historial.
        """
        deals = mt5.history_deals_get(position=int(position_id))
        if not deals:
            now = datetime.now()
            mt5.history_select(now - timedelta(days=days_back), now + timedelta(days=1))
            deals = mt5.history_deals_get(position=int(position_id))
        if not deals:
            return None
        pnl = sum(d.profit + d.swap + d.commission for d in deals)
        exit_price = next((d.price for d in deals
                           if d.entry == mt5.DEAL_ENTRY_OUT), None)
        return {"pnl": pnl, "exit_price": exit_price}

    def close_trade(self, ticket):
        """Cierra una posición abierta por su ticket."""
        positions = mt5.positions_get(ticket=int(ticket))
        if not positions:
            return None
        pos  = positions[0]
        info = mt5.symbol_info(pos.symbol)
        tick = mt5.symbol_info_tick(pos.symbol)

        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type, price = mt5.ORDER_TYPE_SELL, tick.bid
        else:
            order_type, price = mt5.ORDER_TYPE_BUY, tick.ask

        request = {
            "action":       mt5.TRADE_ACTION_DEAL,
            "symbol":       pos.symbol,
            "volume":       pos.volume,
            "type":         order_type,
            "position":     int(ticket),
            "price":        price,
            "deviation":    20,
            "magic":        234000,
            "comment":      "close",
            "type_time":    mt5.ORDER_TIME_GTC,
            "type_filling": _filling_mode(info),
        }
        return mt5.order_send(request)

    def __del__(self):
        mt5.shutdown()
