"""
telegram_notifier.py — Notificaciones al Telegram del bot FTMO.

Si no hay conexion en el momento del envio, el mensaje se guarda en una
cola en disco (pending_telegram.json) y se reintenta automaticamente en
el proximo ciclo del bot (cada 60 segundos).

Configuracion en config.py:
    TELEGRAM_TOKEN   = "tu_token"
    TELEGRAM_CHAT_ID = "tu_chat_id"   (obtenelo con get_chat_id.py)
"""

import json
import os
import urllib.request
import urllib.parse
from datetime import datetime

_PENDING_FILE = os.path.join(os.path.dirname(__file__), "pending_telegram.json")
_API = "https://api.telegram.org/bot{}/sendMessage"


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.token   = token
        self.chat_id = str(chat_id)
        self._pending = self._load_pending()

    # ── API interna ───────────────────────────────────────────────

    def _send_raw(self, text: str) -> bool:
        """Intenta enviar un mensaje. True = exito, False = sin conexion."""
        try:
            url  = _API.format(self.token)
            data = urllib.parse.urlencode({
                "chat_id":    self.chat_id,
                "text":       text,
                "parse_mode": "HTML",
            }).encode()
            req = urllib.request.Request(url, data=data)
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=6) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _load_pending(self) -> list:
        try:
            with open(_PENDING_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_pending(self):
        try:
            with open(_PENDING_FILE, "w") as f:
                json.dump(self._pending, f)
        except Exception:
            pass

    def _flush_pending(self):
        """Intenta enviar mensajes acumulados. Elimina los que llegan OK."""
        if not self._pending:
            return
        still = []
        for msg in self._pending:
            if not self._send_raw(msg):
                still.append(msg)
        self._pending = still
        self._save_pending()

    # ── API publica ───────────────────────────────────────────────

    def send(self, text: str):
        """
        Envia un mensaje a Telegram.
        Si hay mensajes pendientes de antes, los intenta primero.
        Si el envio actual falla, lo guarda en cola para el proximo ciclo.
        """
        self._flush_pending()
        if not self._send_raw(text):
            self._pending.append(text)
            self._save_pending()

    def pending_count(self) -> int:
        return len(self._pending)


# ── Mensajes predefinidos ─────────────────────────────────────────

def msg_inicio(account_id, balance, risk_pct, rr):
    return (
        f"<b>🤖 Bot FTMO iniciado</b>\n"
        f"Cuenta: <code>{account_id}</code>\n"
        f"Balance: <b>${balance:,.2f}</b>\n"
        f"Riesgo/trade: {risk_pct:.1f}%  |  R:R {rr:.1f}\n"
        f"Par: EUR/USD M15  |  Estrategia: Mean Reversion"
    )


def msg_trade_abierto(direccion, lotes, entrada, sl, tp, riesgo_usd, balance):
    icono = "🟢" if direccion == "LONG" else "🔴"
    return (
        f"{icono} <b>{direccion} abierta — EUR/USD</b>\n"
        f"Lotes: {lotes}  |  Entrada: <code>{entrada:.5f}</code>\n"
        f"SL: <code>{sl:.5f}</code>  |  TP: <code>{tp:.5f}</code>\n"
        f"Riesgo: <b>${riesgo_usd:.2f}</b>  |  Balance: ${balance:,.2f}"
    )


def msg_trade_cerrado(direccion, lotes, entrada, salida, pnl, balance, motivo):
    if isinstance(pnl, (int, float)):
        if pnl >= 0:
            icono  = "✅"
            estado = "GANANCIA"
            pnl_pct = pnl / (balance - pnl) * 100 if (balance - pnl) else 0
            pnl_str = f"+${pnl:.2f} (+{pnl_pct:.2f}%)"
        else:
            icono  = "🔴"
            estado = "PERDIDA"
            pnl_pct = abs(pnl) / (balance - pnl) * 100 if (balance - pnl) else 0
            pnl_str = f"-${abs(pnl):.2f} (-{pnl_pct:.2f}%)"
    else:
        icono  = "⬜"
        estado = "CERRADA"
        pnl_str = str(pnl)

    motivo_map = {
        "STOP_LOSS":    "🛑 Stop Loss",
        "TAKE_PROFIT":  "🎯 Take Profit",
        "SL/TP/trailing": "🎯 SL/TP/Trailing",
        "CIERRE_FINAL": "⏹ Cierre final",
    }
    motivo_label = motivo_map.get(motivo, motivo)

    sal_str = f"{salida:.5f}" if isinstance(salida, float) else str(salida)
    return (
        f"{icono} <b>{direccion} cerrada — {estado}</b>\n"
        f"EUR/USD  |  {lotes} lotes\n"
        f"Entrada <code>{entrada:.5f}</code> → Salida <code>{sal_str}</code>\n"
        f"P&L: <b>{pnl_str}</b>\n"
        f"Balance: <b>${balance:,.2f}</b>\n"
        f"Motivo: {motivo_label}"
    )


def msg_circuit_breaker(perdida_pct, balance):
    return (
        f"⚠️ <b>CIRCUIT BREAKER activado</b>\n"
        f"Perdida del dia: -{perdida_pct:.2f}%\n"
        f"Balance: ${balance:,.2f}\n"
        f"Sin nuevos trades hasta manana."
    )


def msg_objetivo_alcanzado(equity, capital_base):
    ganancia_pct = (equity - capital_base) / capital_base * 100
    return (
        f"🎯 <b>OBJETIVO FTMO ALCANZADO</b>\n"
        f"Equity: <b>${equity:,.2f}</b>  (+{ganancia_pct:.2f}%)\n"
        f"Bot detenido automaticamente.\n"
        f"<b>Fase 1 completada. Podes solicitar la Fase 2.</b>"
    )


def msg_freno_total(equity, capital_base):
    perdida_pct = (capital_base - equity) / capital_base * 100
    return (
        f"🛑 <b>FRENO TOTAL ACTIVADO</b>\n"
        f"Equity: ${equity:,.2f}  (-{perdida_pct:.2f}%)\n"
        f"Bot detenido por seguridad.\n"
        f"Revisa la cuenta en MT5."
    )


def msg_error(detalle: str):
    return (
        f"⚠️ <b>Error en el bot</b>\n"
        f"<code>{detalle[:200]}</code>\n"
        f"Reintentando en el proximo ciclo."
    )


def msg_sin_senal(precio, rsi, adx):
    # Solo para debug, generalmente no se manda
    return (
        f"📊 Sin señal  |  Precio {precio:.5f}  "
        f"RSI {rsi:.0f}  ADX {adx:.0f}"
    )
