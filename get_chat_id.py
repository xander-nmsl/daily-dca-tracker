#!/usr/bin/env python3
"""Helper: discover Telegram chat_id by checking bot updates."""
import os
import requests

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
if not TOKEN:
    print("Set TELEGRAM_TOKEN env var first.")
    exit(1)

r = requests.get(f"https://api.telegram.org/bot{TOKEN}/getUpdates", timeout=15)
data = r.json()

if not data.get("result"):
    print("No messages yet! Send ANY message to your bot on Telegram first.")
    exit(1)

for u in data["result"]:
    chat = u.get("message", {}).get("chat", {})
    print(f"chat_id = {chat.get('id')}")
    print(f"name    = {chat.get('first_name', '')} {chat.get('last_name', '')}")
    print(f"username= {chat.get('username', '')}")
    print("---")

print("\nCopy the chat_id above and set it as TELEGRAM_CHAT_ID env var or GitHub Secret.")
