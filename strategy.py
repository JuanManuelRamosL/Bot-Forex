"""
strategy.py — Indicadores técnicos y lógica de señales.

Estrategia: Mean Reversion con Bandas de Bollinger.
- COMPRA (LONG)  cuando el precio toca la banda inferior y el RSI confirma sobreventa.
- VENDE (SHORT)  cuando el precio toca la banda superior y el RSI confirma sobrecompra.
- SALE en la media móvil (objetivo), en el stop-loss, o si toca el take-profit.

Nada acá depende de internet: son cálculos puros sobre listas de precios.
"""

import math


def sma(values, period):
    """Media móvil simple. Devuelve lista del mismo largo (None al inicio)."""
    out = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1:i + 1]
        out[i] = sum(window) / period
    return out


def bollinger_bands(closes, period=20, mult=2.0):
    """Devuelve (media, banda_superior, banda_inferior)."""
    mid = sma(closes, period)
    upper = [None] * len(closes)
    lower = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = closes[i - period + 1:i + 1]
        m = mid[i]
        std = math.sqrt(sum((x - m) ** 2 for x in window) / period)
        upper[i] = m + mult * std
        lower[i] = m - mult * std
    return mid, upper, lower


def atr(highs, lows, closes, period=14):
    """Average True Range — mide volatilidad. Se usa para dimensionar el stop."""
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


def rsi(closes, period=14):
    """Relative Strength Index — filtro de momentum (0 a 100)."""
    out = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains, losses = 0.0, 0.0
    for i in range(1, period + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            gains += d
        else:
            losses -= d
    gains /= period
    losses /= period
    out[period] = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    for i in range(period + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = d if d > 0 else 0
        l = -d if d < 0 else 0
        gains = (gains * (period - 1) + g) / period
        losses = (losses * (period - 1) + l) / period
        out[i] = 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)
    return out


class MeanReversionStrategy:
    """Encapsula la lógica de señales. La usan tanto el backtest como el bot en vivo."""

    def __init__(self, cfg):
        self.cfg = cfg

    def compute_indicators(self, highs, lows, closes):
        mid, upper, lower = bollinger_bands(closes, self.cfg.BB_PERIOD, self.cfg.BB_STD)
        a = atr(highs, lows, closes, self.cfg.ATR_PERIOD)
        r = rsi(closes, self.cfg.RSI_PERIOD)
        return {"mid": mid, "upper": upper, "lower": lower, "atr": a, "rsi": r}

    def signal_at(self, i, closes, ind):
        """
        Devuelve un dict de señal de ENTRADA en la vela i, o None si no hay señal.
        {'dir': 'LONG'/'SHORT', 'entry': precio, 'sl': stop, 'tp': objetivo}
        """
        price = closes[i]
        u, lo, m, a, r = ind["upper"][i], ind["lower"][i], ind["mid"][i], ind["atr"][i], ind["rsi"][i]
        if None in (u, lo, m, a, r):
            return None

        sl_dist = self.cfg.ATR_SL_MULT * a

        # Señal de compra: precio en/bajo banda inferior + RSI en sobreventa
        if price <= lo and r < self.cfg.RSI_LONG_MAX:
            return {"dir": "LONG", "entry": price, "sl": price - sl_dist, "tp": m}

        # Señal de venta en corto: precio en/sobre banda superior + RSI en sobrecompra
        if price >= u and r > self.cfg.RSI_SHORT_MIN:
            return {"dir": "SHORT", "entry": price, "sl": price + sl_dist, "tp": m}

        return None

    def should_exit(self, pos, price, mid_now):
        """Decide si cerrar una posición abierta en esta vela."""
        if pos["dir"] == "LONG":
            if price <= pos["sl"]:
                return "STOP_LOSS"
            if price >= pos["tp"] or (mid_now and price >= mid_now):
                return "TAKE_PROFIT"
        else:  # SHORT
            if price >= pos["sl"]:
                return "STOP_LOSS"
            if price <= pos["tp"] or (mid_now and price <= mid_now):
                return "TAKE_PROFIT"
        return None
