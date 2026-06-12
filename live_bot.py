"""
live_bot.py — Ejecuta la estrategia en VIVO sobre tu cuenta OANDA.

Con OANDA_ENV = "practice" opera en la cuenta DEMO (dinero virtual).
Revisá el mercado en cada vela cerrada y abre/cierra posiciones automáticamente.

Uso:
    python live_bot.py

Para frenarlo: Ctrl + C.

IMPORTANTE: probalo SIEMPRE primero en demo (practice). El stop-loss y take-profit
se mandan junto con la orden, así que aunque el bot se caiga, tus posiciones quedan protegidas.
"""

import time
from datetime import datetime
import config
from oanda_client import OandaClient
from strategy import MeanReversionStrategy

# Segundos entre cada chequeo. Para H1 con revisar cada 5 min sobra.
POLL_SECONDS = 300


def seconds_to_next_candle(granularity):
    """Espera aproximada. Simplificado: usa POLL_SECONDS fijo."""
    return POLL_SECONDS


def run_live():
    cfg = config
    client = OandaClient(cfg.OANDA_API_TOKEN, cfg.OANDA_ACCOUNT_ID, cfg.OANDA_ENV)
    strat = MeanReversionStrategy(cfg)

    acc = client.get_account_summary()
    print(f"Conectado a OANDA [{cfg.OANDA_ENV}]")
    print(f"Cuenta: {acc['id']}  |  Balance: {acc['balance']} {acc['currency']}")
    print(f"Operando {cfg.INSTRUMENT} en {cfg.GRANULARITY}")
    print(f"Riesgo por trade: {cfg.RISK_PER_TRADE * 100}%\n")

    pip = 0.01 if "JPY" in cfg.INSTRUMENT else 0.0001

    while True:
        try:
            stamp = datetime.now().strftime("%H:%M:%S")

            # 1. Bajar velas recientes
            need = max(cfg.BB_PERIOD, cfg.ATR_PERIOD, cfg.RSI_PERIOD) + 50
            times, opens, highs, lows, closes = client.get_candles(
                cfg.INSTRUMENT, cfg.GRANULARITY, need
            )
            ind = strat.compute_indicators(highs, lows, closes)
            i = len(closes) - 1
            price = closes[i]

            # 2. ¿Hay posición abierta en este instrumento?
            open_trades = [t for t in client.get_open_trades()
                           if t["instrument"] == cfg.INSTRUMENT]

            if open_trades:
                # El SL/TP ya están puestos en OANDA; revisamos salida por media móvil.
                trade = open_trades[0]
                is_long = float(trade["currentUnits"]) > 0
                mid_now = ind["mid"][i]
                exit_by_mean = (is_long and mid_now and price >= mid_now) or \
                               (not is_long and mid_now and price <= mid_now)
                if exit_by_mean:
                    client.close_trade(trade["id"])
                    print(f"[{stamp}] CERRADA posición (precio volvió a la media) @ {price:.5f}")
                else:
                    print(f"[{stamp}] Posición abierta, esperando salida. Precio {price:.5f}")
            else:
                # 3. Buscar señal de entrada
                sig = strat.signal_at(i, closes, ind)
                if sig:
                    acc = client.get_account_summary()
                    balance = float(acc["balance"])
                    sl_dist = abs(sig["entry"] - sig["sl"])
                    risk_amount = balance * cfg.RISK_PER_TRADE
                    units = int(risk_amount / sl_dist)
                    if sig["dir"] == "SHORT":
                        units = -units
                    if units != 0:
                        res = client.place_market_order(
                            cfg.INSTRUMENT, units,
                            stop_loss=sig["sl"], take_profit=sig["tp"],
                        )
                        print(f"[{stamp}] ABIERTA {sig['dir']} {abs(units)} units @ {sig['entry']:.5f} "
                              f"| SL {sig['sl']:.5f} | TP {sig['tp']:.5f}")
                    else:
                        print(f"[{stamp}] Señal {sig['dir']} pero units=0 (riesgo muy chico). Salteando.")
                else:
                    rsi_now = ind["rsi"][i]
                    print(f"[{stamp}] Sin señal. Precio {price:.5f}  RSI {rsi_now:.0f}")

        except KeyboardInterrupt:
            print("\nBot detenido por el usuario.")
            break
        except Exception as e:
            print(f"[error] {e}  -- reintentando en {POLL_SECONDS}s")

        time.sleep(seconds_to_next_candle(cfg.GRANULARITY))


if __name__ == "__main__":
    if config.OANDA_API_TOKEN.startswith("PEGA"):
        print("ERROR: Editá config.py con tu token y account ID de OANDA primero.")
    elif config.OANDA_ENV != "practice":
        confirm = input("⚠️  Estás en modo LIVE (dinero real). Escribí 'SI' para continuar: ")
        if confirm.strip().upper() == "SI":
            run_live()
        else:
            print("Cancelado. Cambiá OANDA_ENV a 'practice' para usar la demo.")
    else:
        run_live()
