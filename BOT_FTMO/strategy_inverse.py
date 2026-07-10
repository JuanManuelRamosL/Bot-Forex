"""
strategy_inverse.py — Variante INVERTIDA de la mean reversion (para comparar
en backtest si conviene apostar a que el precio SIGUE en vez de revertir).

Mismas condiciones de entrada (banda de Bollinger + RSI + filtro ADX) que
MeanReversionStrategy, pero la dirección de la apuesta se invierte:
- Antes: precio en banda inferior + RSI bajo -> LONG (apuesta a que rebota)
  Ahora: precio en banda inferior + RSI bajo -> SHORT (apuesta a que sigue cayendo)
- Antes: precio en banda superior + RSI alto  -> SHORT (apuesta a que rebota)
  Ahora: precio en banda superior + RSI alto  -> LONG (apuesta a que sigue subiendo)

No es "trend following" real (no filtra por tendencia macro), solo la
contracara exacta de la mean reversion sobre la misma señal.
"""

from strategy import MeanReversionStrategy


class InverseMeanReversionStrategy(MeanReversionStrategy):

    def signal_at(self, i, closes, ind):
        price = closes[i]
        u, lo, m, a, r = ind["upper"][i], ind["lower"][i], ind["mid"][i], ind["atr"][i], ind["rsi"][i]
        if None in (u, lo, m, a, r):
            return None

        if not self.regime_ok(i, ind):
            return None

        use_trend = getattr(self.cfg, "USE_TREND_FILTER", False)
        e = ind["ema"][i] if use_trend else None
        if use_trend and e is None:
            return None

        sl_dist = self.cfg.ATR_SL_MULT * a

        if price <= lo and r < self.cfg.RSI_LONG_MAX:
            if not use_trend or price < e:
                tp = self._tp_for("SHORT", price, m, sl_dist)
                return {"dir": "SHORT", "entry": price, "sl": price + sl_dist, "tp": tp}

        if price >= u and r > self.cfg.RSI_SHORT_MIN:
            if not use_trend or price > e:
                tp = self._tp_for("LONG", price, m, sl_dist)
                return {"dir": "LONG", "entry": price, "sl": price - sl_dist, "tp": tp}

        return None
