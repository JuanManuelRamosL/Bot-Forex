"""
strategy.py — Indicadores técnicos y lógica de señales. Versión 2.

Estrategia: Mean Reversion con Bandas de Bollinger + FILTRO DE RÉGIMEN (ADX).
- COMPRA (LONG)  cuando el precio toca la banda inferior, el RSI confirma sobreventa
                 Y el mercado está lateral (ADX bajo).
- VENDE (SHORT)  cuando el precio toca la banda superior, el RSI confirma sobrecompra
                 Y el mercado está lateral.
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


def ema(values, period):
    """Media móvil exponencial. Devuelve lista del mismo largo (None al inicio)."""
    out = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    # arranca con SMA de los primeros 'period' valores
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
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


def adx(highs, lows, closes, period=14):
    """
    Average Directional Index — mide la FUERZA de la tendencia (0 a 100).
    - ADX < 25  -> mercado lateral (bueno para mean reversion)
    - ADX > 25  -> tendencia fuerte (peligroso para mean reversion)
    Devuelve una lista del mismo largo (None hasta que hay suficientes datos).
    """
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

    # Suavizado de Wilder
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

    # ADX = media móvil suavizada del DX
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


class MeanReversionStrategy:
    """Encapsula la lógica de señales. La usan tanto el backtest como el bot en vivo."""

    def __init__(self, cfg):
        self.cfg = cfg

    def compute_indicators(self, highs, lows, closes):
        mid, upper, lower = bollinger_bands(closes, self.cfg.BB_PERIOD, self.cfg.BB_STD)
        a = atr(highs, lows, closes, self.cfg.ATR_PERIOD)
        r = rsi(closes, self.cfg.RSI_PERIOD)
        adx_vals = adx(highs, lows, closes, self.cfg.ADX_PERIOD)
        # MEJORA 4: EMA macro para filtro de tendencia (solo si está activado)
        trend = ema(closes, getattr(self.cfg, "TREND_EMA_PERIOD", 200)) \
            if getattr(self.cfg, "USE_TREND_FILTER", False) else [None] * len(closes)
        return {"mid": mid, "upper": upper, "lower": lower,
                "atr": a, "rsi": r, "adx": adx_vals, "ema": trend}

    def regime_ok(self, i, ind):
        """True si el mercado está lateral (apto para mean reversion)."""
        if not self.cfg.USE_REGIME_FILTER:
            return True
        adx_now = ind["adx"][i]
        if adx_now is None:
            return False  # sin dato de ADX, mejor no operar
        return adx_now < self.cfg.ADX_MAX

    def _tp_for(self, direction, entry, mid, sl_dist):
        """Calcula el take-profit según el modo configurado."""
        mode = getattr(self.cfg, "TP_MODE", "mean")
        if mode == "rr":
            rr = getattr(self.cfg, "TP_RR", 1.5)
            return entry + rr * sl_dist if direction == "LONG" else entry - rr * sl_dist
        return mid  # modo "mean": objetivo = media móvil

    def signal_at(self, i, closes, ind):
        """
        Devuelve un dict de señal de ENTRADA en la vela i, o None si no hay señal.
        {'dir': 'LONG'/'SHORT', 'entry': precio, 'sl': stop, 'tp': objetivo}
        """
        price = closes[i]
        u, lo, m, a, r = ind["upper"][i], ind["lower"][i], ind["mid"][i], ind["atr"][i], ind["rsi"][i]
        if None in (u, lo, m, a, r):
            return None

        # MEJORA 1: no operar si el mercado está en tendencia
        if not self.regime_ok(i, ind):
            return None

        # MEJORA 4: filtro de tendencia macro — comprar caídas solo en tendencia
        # alcista, vender repuntes solo en tendencia bajista. Evita pelear el macro.
        use_trend = getattr(self.cfg, "USE_TREND_FILTER", False)
        e = ind["ema"][i] if use_trend else None
        if use_trend and e is None:
            return None

        sl_dist = self.cfg.ATR_SL_MULT * a

        if price <= lo and r < self.cfg.RSI_LONG_MAX:
            if not use_trend or price > e:
                tp = self._tp_for("LONG", price, m, sl_dist)
                return {"dir": "LONG", "entry": price, "sl": price - sl_dist, "tp": tp}

        if price >= u and r > self.cfg.RSI_SHORT_MIN:
            if not use_trend or price < e:
                tp = self._tp_for("SHORT", price, m, sl_dist)
                return {"dir": "SHORT", "entry": price, "sl": price + sl_dist, "tp": tp}

        return None

    def should_exit(self, pos, price, mid_now):
        """Decide si cerrar una posición abierta en esta vela."""
        # En modo "rr" la salida es por TP/SL fijos; en modo "mean" también
        # cuenta el regreso a la media móvil como toma de ganancia.
        mean_exit = getattr(self.cfg, "TP_MODE", "mean") == "mean"
        if pos["dir"] == "LONG":
            if price <= pos["sl"]:
                return "STOP_LOSS"
            if price >= pos["tp"] or (mean_exit and mid_now and price >= mid_now):
                return "TAKE_PROFIT"
        else:  # SHORT
            if price >= pos["sl"]:
                return "STOP_LOSS"
            if price <= pos["tp"] or (mean_exit and mid_now and price <= mid_now):
                return "TAKE_PROFIT"
        return None