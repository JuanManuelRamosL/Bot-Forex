"""
oanda_client.py — Conexión con la API REST v20 de OANDA.

Usa solo la librería 'requests'. No necesitás librerías raras.
Documentación oficial: https://developer.oanda.com/rest-live-v20/introduction/
"""

import requests


class OandaClient:
    def __init__(self, token, account_id, env="practice"):
        self.token = token
        self.account_id = account_id
        if env == "practice":
            self.base = "https://api-fxpractice.oanda.com"
        else:
            self.base = "https://api-fxtrade.oanda.com"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_candles(self, instrument, granularity="H1", count=500):
        """
        Baja velas históricas. Devuelve listas paralelas: times, opens, highs, lows, closes.
        Solo usa velas completas (complete=True).
        """
        url = f"{self.base}/v3/instruments/{instrument}/candles"
        params = {"granularity": granularity, "count": count, "price": "M"}
        resp = requests.get(url, headers=self.headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        times, opens, highs, lows, closes = [], [], [], [], []
        for c in data["candles"]:
            if not c["complete"]:
                continue
            times.append(c["time"])
            opens.append(float(c["mid"]["o"]))
            highs.append(float(c["mid"]["h"]))
            lows.append(float(c["mid"]["l"]))
            closes.append(float(c["mid"]["c"]))
        return times, opens, highs, lows, closes

    def get_account_summary(self):
        url = f"{self.base}/v3/accounts/{self.account_id}/summary"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()["account"]

    def get_open_trades(self):
        url = f"{self.base}/v3/accounts/{self.account_id}/openTrades"
        resp = requests.get(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()["trades"]

    def place_market_order(self, instrument, units, stop_loss=None, take_profit=None):
        """
        Abre una orden de mercado.
        units > 0  -> compra (LONG)
        units < 0  -> venta en corto (SHORT)
        stop_loss / take_profit son PRECIOS absolutos.
        """
        order = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": str(int(units)),
                "timeInForce": "FOK",
                "positionFill": "DEFAULT",
            }
        }
        if stop_loss is not None:
            order["order"]["stopLossOnFill"] = {"price": f"{stop_loss:.5f}"}
        if take_profit is not None:
            order["order"]["takeProfitOnFill"] = {"price": f"{take_profit:.5f}"}

        url = f"{self.base}/v3/accounts/{self.account_id}/orders"
        resp = requests.post(url, headers=self.headers, json=order, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def close_trade(self, trade_id):
        url = f"{self.base}/v3/accounts/{self.account_id}/trades/{trade_id}/close"
        resp = requests.put(url, headers=self.headers, timeout=30)
        resp.raise_for_status()
        return resp.json()
