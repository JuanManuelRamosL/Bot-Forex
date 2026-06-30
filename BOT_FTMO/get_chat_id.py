"""
get_chat_id.py — Muestra tu chat_id de Telegram para pegarlo en config.py.

Pasos:
  1) Abrí Telegram y escribile cualquier cosa a tu bot (ej. "hola").
  2) Corré:  ..\\venv\\Scripts\\python.exe get_chat_id.py
  3) Copiá el chat_id que aparece a config.TELEGRAM_CHAT_ID.
"""
import sys
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import json
import urllib.request
import config

url = f"https://api.telegram.org/bot{config.TELEGRAM_TOKEN}/getUpdates"
try:
    with urllib.request.urlopen(url, timeout=10) as r:
        data = json.load(r)
except Exception as e:
    print(f"No se pudo consultar Telegram: {e}")
    sys.exit(1)

updates = data.get("result", [])
if not updates:
    print("No hay mensajes todavía. Escribile algo a tu bot en Telegram y volvé a correr esto.")
else:
    vistos = set()
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or {}
        chat = msg.get("chat", {})
        cid = chat.get("id")
        if cid and cid not in vistos:
            vistos.add(cid)
            nombre = (chat.get("first_name", "") + " " + chat.get("username", "")).strip()
            print(f"chat_id = {cid}   ({nombre})")
    print("\nPegá ese número en config.TELEGRAM_CHAT_ID (entre comillas).")
