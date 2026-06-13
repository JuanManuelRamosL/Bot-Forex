"""
journal.py — Registro persistente de la actividad del bot.

Genera dos archivos en la carpeta del proyecto:
- bot.log     : todo lo que el bot ve y hace, línea por línea con timestamp UTC (texto).
- trades.json : lista de operaciones (apertura / cierre) con P&L real, en JSON.

Así queda registro exacto de qué hizo el bot, aunque cierres la terminal.
"""

import json
import os
from datetime import datetime, timezone

LOG_FILE    = "bot.log"
TRADES_JSON = "trades.json"


def configure(log_file=None, trades_file=None):
    """Permite que cada bot use sus propios archivos (ej. el bot M15 vs el H1)."""
    global LOG_FILE, TRADES_JSON
    if log_file:
        LOG_FILE = log_file
    if trades_file:
        TRADES_JSON = trades_file


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def event(msg, also_print=True):
    """Escribe una línea en bot.log (y la imprime en consola por defecto)."""
    if also_print:
        print(msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{_now()}] {msg}\n")
    except OSError:
        pass  # nunca dejamos que un fallo de logging tumbe el bot


def trade(row):
    """
    Agrega una operación a trades.json. El archivo es una lista de objetos;
    cada objeto trae fecha, acción (ABIERTA/CERRADA), dirección, lotes, precios,
    riesgo, P&L, balance, ticket y motivo. Legible a mano y fácil de procesar.
    """
    if "fecha_utc" not in row or not row["fecha_utc"]:
        row = {"fecha_utc": _now(), **row}
    try:
        data = []
        if os.path.exists(TRADES_JSON):
            with open(TRADES_JSON, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except json.JSONDecodeError:
                    data = []  # archivo vacío o corrupto: arrancamos limpio
        data.append(row)
        with open(TRADES_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        event(f"[journal] no se pudo escribir trades.json: {e}", also_print=False)
