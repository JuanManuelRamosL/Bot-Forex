"""
strategy_smc.py — Estrategia Smart Money Concepts (versión rule-based OBJETIVA).

Implementa SOLO las partes de SMC que se pueden programar sin subjetividad:
- Estructura de mercado: swing highs/lows -> BOS (Break of Structure) define la tendencia.
- FVG (Fair Value Gap): imbalance de 3 velas (matemático, sin interpretación).
- Entrada: A FAVOR de la tendencia, cuando el precio retrocede a un FVG del impulso.

Filtros de CALIDAD (configurables, para subir el ratio sin overfitting):
- USE_HTF_BIAS:        solo operar a favor de una EMA larga (tendencia mayor).
- FVG_MIN_ATR:         ignorar FVGs chicos (ruido); exigir un tamaño mínimo en ATR.
- USE_PREMIUM_DISCOUNT: comprar solo en "descuento" (mitad baja del rango) y vender
                        solo en "premium" (mitad alta). Mejora el precio de entrada.
- MAX_ENTRIES_PER_LEG: cuántas entradas permitir por cada tramo de tendencia (anti-overtrading).

NO incluye "liquidity grabs" ni zonas discrecionales (subjetivas / humo).

Interfaz idéntica a MeanReversionStrategy: compute_indicators / signal_at / should_exit.
"""

from strategy import atr, ema


class SMCStrategy:
    def __init__(self, cfg):
        self.cfg = cfg

    def compute_indicators(self, highs, lows, closes):
        cfg = self.cfg
        n = len(closes)
        a = atr(highs, lows, closes, cfg.ATR_PERIOD)
        k = getattr(cfg, "SWING_LOOKBACK", 5)
        sl_buf = getattr(cfg, "SL_BUFFER_ATR", 1.0)
        use_htf = getattr(cfg, "USE_HTF_BIAS", False)
        htf_p = getattr(cfg, "HTF_EMA_PERIOD", 200)
        fvg_min = getattr(cfg, "FVG_MIN_ATR", 0.0)
        use_pd = getattr(cfg, "USE_PREMIUM_DISCOUNT", False)
        max_entries = getattr(cfg, "MAX_ENTRIES_PER_LEG", 99)

        htf = ema(closes, htf_p) if use_htf else [None] * n

        # Swing highs/lows confirmados (pivote con k velas a cada lado)
        swing_high = [None] * n
        swing_low = [None] * n
        for j in range(k, n - k):
            if highs[j] == max(highs[j - k:j + k + 1]):
                swing_high[j] = highs[j]
            if lows[j] == min(lows[j - k:j + k + 1]):
                swing_low[j] = lows[j]

        signals = [None] * n
        trend = 0
        last_sh = last_sl = None      # consumibles, para detectar BOS
        recent_sh = recent_sl = None  # últimos swings, para el rango premium/descuento
        active_fvg = None
        entries_this_leg = 0

        for i in range(2, n):
            j = i - k
            if j >= 0:
                if swing_high[j] is not None:
                    last_sh = recent_sh = swing_high[j]
                if swing_low[j] is not None:
                    last_sl = recent_sl = swing_low[j]

            # BOS: el cierre rompe el último swing -> define/renueva la tendencia
            if last_sh is not None and closes[i] > last_sh:
                if trend != 1:
                    trend = 1
                    active_fvg = None
                    entries_this_leg = 0
                last_sh = None
            elif last_sl is not None and closes[i] < last_sl:
                if trend != -1:
                    trend = -1
                    active_fvg = None
                    entries_this_leg = 0
                last_sl = None

            # Equilibrio del rango (para premium/descuento)
            eq = None
            if recent_sh is not None and recent_sl is not None and recent_sh > recent_sl:
                eq = (recent_sh + recent_sl) / 2.0

            atr_i = a[i] or 0

            # ¿El precio retrocedió a un FVG activo? -> evaluar entrada con filtros
            if active_fvg is not None and entries_this_leg < max_entries:
                if active_fvg["dir"] == 1 and trend == 1 and lows[i] <= active_fvg["hi"]:
                    entry = closes[i]
                    ok = True
                    if use_htf and htf[i] is not None and entry <= htf[i]:
                        ok = False                      # contra la tendencia mayor
                    if use_pd and eq is not None and entry >= eq:
                        ok = False                      # caro (premium), no comprar
                    sl = active_fvg["lo"] - sl_buf * atr_i
                    if ok and entry > sl:
                        signals[i] = {"dir": "LONG", "entry": entry, "sl": sl}
                        entries_this_leg += 1
                    active_fvg = None
                elif active_fvg["dir"] == -1 and trend == -1 and highs[i] >= active_fvg["lo"]:
                    entry = closes[i]
                    ok = True
                    if use_htf and htf[i] is not None and entry >= htf[i]:
                        ok = False
                    if use_pd and eq is not None and entry <= eq:
                        ok = False                      # barato (discount), no vender
                    sl = active_fvg["hi"] + sl_buf * atr_i
                    if ok and entry < sl:
                        signals[i] = {"dir": "SHORT", "entry": entry, "sl": sl}
                        entries_this_leg += 1
                    active_fvg = None

            # Detectar FVG nuevo (3 velas) con tamaño mínimo
            if trend == 1 and lows[i] > highs[i - 2]:
                if (lows[i] - highs[i - 2]) >= fvg_min * atr_i:
                    active_fvg = {"dir": 1, "lo": highs[i - 2], "hi": lows[i]}
            elif trend == -1 and highs[i] < lows[i - 2]:
                if (lows[i - 2] - highs[i]) >= fvg_min * atr_i:
                    active_fvg = {"dir": -1, "lo": highs[i], "hi": lows[i - 2]}

        return {"atr": a, "mid": [None] * n, "signals": signals}

    def signal_at(self, i, closes, ind):
        sig = ind["signals"][i]
        if sig is None:
            return None
        rr = getattr(self.cfg, "TP_RR", 2.0)
        entry, sl = sig["entry"], sig["sl"]
        dist = abs(entry - sl)
        if dist <= 0:
            return None
        tp = entry + rr * dist if sig["dir"] == "LONG" else entry - rr * dist
        return {"dir": sig["dir"], "entry": entry, "sl": sl, "tp": tp}

    def should_exit(self, pos, price, mid_now):
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
