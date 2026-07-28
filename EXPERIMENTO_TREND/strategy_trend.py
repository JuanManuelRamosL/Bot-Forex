"""
strategy_trend.py — Estrategia de TENDENCIA: ruptura de canal Donchian confirmada
por ADX alto. Pensada para operar en el régimen que la mean reversion del bot
real (BOT_FTMO/strategy.py) evita a propósito (ADX >= TREND_ADX_MIN, tendencia
fuerte), como posible pata complementaria del sistema.

- LONG  cuando el precio rompe el máximo de las últimas N velas Y hay tendencia (ADX alto).
- SHORT cuando el precio rompe el mínimo de las últimas N velas Y hay tendencia.
- Sale por stop-loss, take-profit (R:R fijo) o trailing stop (lo aplica engine.simulate).

Indicadores (atr/adx) duplicados a propósito de BOT_FTMO/strategy.py: son
funciones puras (sin estado), y así esta carpeta queda 100% independiente.
"""


def atr(highs, lows, closes, period=14):
    out = [None] * len(closes)
    trs = [None] * len(closes)
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs[i] = tr
    for i in range(period, len(closes)):
        window = [t for t in trs[i - period + 1:i + 1] if t is not None]
        if window:
            out[i] = sum(window) / len(window)
    return out


def adx(highs, lows, closes, period=14):
    n = len(closes)
    out = [None] * n
    if n < 2 * period + 1:
        return out

    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if (up_move > down_move and up_move > 0) else 0.0
        minus_dm[i] = down_move if (down_move > up_move and down_move > 0) else 0.0
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    atr_s = sum(tr[1:period + 1])
    plus_s = sum(plus_dm[1:period + 1])
    minus_s = sum(minus_dm[1:period + 1])

    dx_list = []
    for i in range(period + 1, n):
        atr_s = atr_s - (atr_s / period) + tr[i]
        plus_s = plus_s - (plus_s / period) + plus_dm[i]
        minus_s = minus_s - (minus_s / period) + minus_dm[i]
        if atr_s == 0:
            continue
        plus_di = 100 * plus_s / atr_s
        minus_di = 100 * minus_s / atr_s
        denom = plus_di + minus_di
        dx = 100 * abs(plus_di - minus_di) / denom if denom else 0
        dx_list.append((i, dx))

    if len(dx_list) >= period:
        first_adx = sum(d for _, d in dx_list[:period]) / period
        idx0 = dx_list[period - 1][0]
        out[idx0] = first_adx
        prev = first_adx
        for k in range(period, len(dx_list)):
            i, dx = dx_list[k]
            prev = (prev * (period - 1) + dx) / period
            out[i] = prev
    return out


class TrendStrategy:

    def __init__(self, cfg):
        self.cfg = cfg

    def compute_indicators(self, highs, lows, closes):
        n = len(closes)
        a = atr(highs, lows, closes, self.cfg.ATR_PERIOD)
        adx_vals = adx(highs, lows, closes, self.cfg.ADX_PERIOD)
        period = self.cfg.DONCHIAN_PERIOD
        dc_high = [None] * n
        dc_low = [None] * n
        for i in range(period, n):
            dc_high[i] = max(highs[i - period:i])  # canal de las N velas ANTERIORES
            dc_low[i] = min(lows[i - period:i])    # (no incluye la vela actual: sin lookahead)
        return {"atr": a, "adx": adx_vals, "dc_high": dc_high, "dc_low": dc_low,
                "mid": [None] * n}  # el motor accede a ind["mid"] genéricamente

    def signal_at(self, i, closes, ind):
        price = closes[i]
        dh, dl, a, adx_now = ind["dc_high"][i], ind["dc_low"][i], ind["atr"][i], ind["adx"][i]
        if None in (dh, dl, a, adx_now):
            return None
        if adx_now < self.cfg.TREND_ADX_MIN:
            return None

        sl_dist = self.cfg.TREND_ATR_SL_MULT * a
        rr = self.cfg.TREND_TP_RR

        if price > dh:
            return {"dir": "LONG", "entry": price, "sl": price - sl_dist, "tp": price + rr * sl_dist}
        if price < dl:
            return {"dir": "SHORT", "entry": price, "sl": price + sl_dist, "tp": price - rr * sl_dist}
        return None

    def should_exit(self, pos, price, mid_now=None):
        if pos["dir"] == "LONG":
            if price <= pos["sl"]:
                return "STOP_LOSS"
            if price >= pos["tp"]:
                return "TAKE_PROFIT"
        else:
            if price >= pos["sl"]:
                return "STOP_LOSS"
            if price <= pos["tp"]:
                return "TAKE_PROFIT"
        return None
