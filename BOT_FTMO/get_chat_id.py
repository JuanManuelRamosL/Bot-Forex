"""
get_chat_id.py — Obtiene tu chat_id de Telegram para configurar el bot.

ANTES DE CORRER ESTO:
  1. Abri Telegram y busca @Juanforexbot
  2. Apreta START o manda cualquier mensaje al bot
  3. Recien ahi corri este script:  python get_chat_id.py
"""

import urllib.request
import json
import config

TOKEN = getattr(config, "TELEGRAM_TOKEN", "")

if not TOKEN:
    print("ERROR: Pone TELEGRAM_TOKEN en config.py primero.")
else:
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())

        if data.get("ok") and data["result"]:
            ultimo = data["result"][-1]
            chat   = ultimo["message"]["chat"]
            print(f"\nTu chat_id es: {chat['id']}")
            print(f"Nombre:        {chat.get('first_name', '')} {chat.get('last_name', '')}")
            print(f"\nAgrega esta linea a config.py:")
            print(f'TELEGRAM_CHAT_ID = "{chat["id"]}"')
        elif data.get("ok") and not data["result"]:
            print("\nNo hay mensajes aun.")
            print("Abri Telegram, buscá @Juanforexbot y apreta START.")
            print("Despues volvé a correr este script.")
        else:
            print(f"Error de Telegram: {data}")
    except Exception as e:
        print(f"Error de conexion: {e}")
