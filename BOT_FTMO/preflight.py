"""
preflight.py — Chequeo de seguridad ANTES de arrancar el bot en la cuenta FTMO.

Verifica que todo esté listo para operar el challenge real:
  - MT5 conectado y a QUÉ cuenta (login, server, balance, moneda).
  - Que el balance coincida con FTMO_INITIAL_CAPITAL del config.
  - Que el AutoTrading (Algo Trading) esté ENCENDIDO.
  - Que el símbolo (EURUSD) exista, sea operable y su spread actual.
  - Que el sizing dé un lote válido (> mínimo) con el riesgo configurado.
  - Resume los frenos FTMO en dólares.

NO abre ninguna orden. Solo lee. Corré esto con el MT5 ya logueado en FTMO:
    ..\\venv\\Scripts\\python.exe preflight.py
"""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import MetaTrader5 as mt5
import config
from mt5_client import MT5Client, _oanda_to_mt5

OK, BAD, WARN = "✅", "❌", "⚠️ "
problemas = 0


def check(cond, ok_msg, bad_msg, fatal=True):
    global problemas
    if cond:
        print(f"  {OK} {ok_msg}")
    else:
        print(f"  {BAD if fatal else WARN}{bad_msg}")
        if fatal:
            problemas += 1


def main():
    global problemas
    print("=" * 64)
    print("PREFLIGHT — chequeo previo a operar el challenge FTMO")
    print("=" * 64)

    client = MT5Client(config.MT5_LOGIN, config.MT5_PASSWORD, config.MT5_SERVER)

    # ── Cuenta conectada ──
    info = mt5.account_info()
    term = mt5.terminal_info()
    print(f"\nCuenta conectada en el MT5 de escritorio:")
    print(f"  Login:   {info.login}")
    print(f"  Server:  {info.server}")
    print(f"  Balance: {info.balance:,.2f} {info.currency}")
    print(f"  Equity:  {info.equity:,.2f} {info.currency}")
    print(f"  Apalancamiento: 1:{info.leverage}")

    print("\nChequeos:")
    # 1) Balance vs capital configurado
    cap = config.FTMO_INITIAL_CAPITAL
    check(abs(info.balance - cap) < cap * 0.05,
          f"Balance ({info.balance:,.0f}) coincide con FTMO_INITIAL_CAPITAL ({cap:,.0f})",
          f"Balance ({info.balance:,.0f}) NO coincide con FTMO_INITIAL_CAPITAL ({cap:,.0f}). "
          f"Ajustá FTMO_INITIAL_CAPITAL o logueate en la cuenta correcta.")

    # 2) ¿Es la cuenta FTMO o todavía la demo MetaQuotes?
    es_demo_metaquotes = "metaquotes" in (info.server or "").lower()
    check(not es_demo_metaquotes,
          f"Server '{info.server}' parece ser tu cuenta del challenge",
          f"Server '{info.server}' es la demo MetaQuotes, NO tu cuenta FTMO. "
          f"Logueá el MT5 en la cuenta FTMO antes de operar.")

    # 3) AutoTrading / Algo Trading encendido
    algo_on = bool(getattr(term, "trade_allowed", False))
    check(algo_on,
          "AutoTrading (Algo Trading) ENCENDIDO en el terminal",
          "AutoTrading APAGADO. Activá el botón 'Algo Trading' en MT5 (si no, las órdenes fallan con retcode 10027).")
    acc_trade = bool(getattr(info, "trade_allowed", True))
    check(acc_trade,
          "La cuenta permite operar",
          "La cuenta NO permite operar (trade_allowed=False).", fatal=False)

    # 4) Símbolo operable
    sym = _oanda_to_mt5(config.INSTRUMENT)
    sel = mt5.symbol_select(sym, True)
    sinfo = mt5.symbol_info(sym)
    tick = mt5.symbol_info_tick(sym) if sinfo else None
    check(sel and sinfo is not None and tick is not None,
          f"Símbolo {sym} disponible y operable",
          f"Símbolo {sym} NO disponible. En FTMO puede llamarse distinto "
          f"(ej. con sufijo). Revisá el Market Watch y ajustá INSTRUMENT.")
    if sinfo and tick:
        pip = 0.01 if "JPY" in sym else 0.0001
        spread_pips = (tick.ask - tick.bid) / pip
        cfg_spread = config.SPREAD_PIPS.get(config.INSTRUMENT, config.DEFAULT_SPREAD_PIPS)
        print(f"      Spread actual: {spread_pips:.1f} pips "
              f"(backtest asumió {cfg_spread} pips)")
        if spread_pips > cfg_spread * 1.5:
            print(f"      {WARN}Spread bastante más alto que el del backtest ahora mismo "
                  f"(puede ser horario de baja liquidez).")

    # 5) Sizing: que dé un lote válido con un SL típico
    if sinfo and tick:
        atr_aprox = 0.0010  # ~10 pips de ATR en EURUSD M15 (aprox)
        sl_dist = config.ATR_SL_MULT * atr_aprox
        risk_amount = info.balance * config.RISK_PER_TRADE
        lots, real_risk = client.calc_lots(config.INSTRUMENT, risk_amount, sl_dist)
        check(lots >= sinfo.volume_min,
              f"Sizing OK: con SL ~{sl_dist/ (0.0001):.0f} pips → {lots} lotes "
              f"(riesgo ~${real_risk:.0f}, mínimo del símbolo {sinfo.volume_min})",
              f"Sizing da {lots} lotes, por debajo del mínimo {sinfo.volume_min}. "
              f"Con $ {info.balance:,.0f} y riesgo {config.RISK_PER_TRADE*100:.1f}% el lote sería muy chico.",
              fatal=False)

    # ── Resumen de frenos en dólares ──
    print("\nFrenos FTMO configurados (sobre capital base "
          f"${config.FTMO_INITIAL_CAPITAL:,.0f}):")
    print(f"  Riesgo por trade:   ${config.FTMO_INITIAL_CAPITAL*config.RISK_PER_TRADE:,.0f} "
          f"({config.RISK_PER_TRADE*100:.1f}%)")
    print(f"  Freno diario:      -${config.FTMO_INITIAL_CAPITAL*config.MAX_DAILY_LOSS:,.0f} "
          f"({config.MAX_DAILY_LOSS*100:.0f}%)   [FTMO elimina a -5%]")
    print(f"  Freno total:       -${config.FTMO_INITIAL_CAPITAL*config.MAX_TOTAL_LOSS:,.0f} "
          f"({config.MAX_TOTAL_LOSS*100:.0f}%)   [FTMO elimina a -10%]")
    print(f"  Objetivo (apaga):  +${config.FTMO_INITIAL_CAPITAL*config.PROFIT_TARGET:,.0f} "
          f"({config.PROFIT_TARGET*100:.0f}%)")
    print(f"  Se apaga al objetivo: {'SÍ' if getattr(config,'FTMO_AUTO_STOP',True) else 'NO'}  |  "
          f"Freno total activo: {'SÍ' if getattr(config,'FTMO_TOTAL_LOSS_STOP',True) else 'NO'}")

    print("\n" + "=" * 64)
    if problemas == 0:
        print(OK + r" TODO LISTO. Podés arrancar con:  ..\venv\Scripts\python.exe live_bot.py")
    else:
        print(f"{BAD} {problemas} problema(s) crítico(s). Resolvelos ANTES de arrancar el bot.")
    print("=" * 64)


if __name__ == "__main__":
    main()
