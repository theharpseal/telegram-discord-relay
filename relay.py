# relay.py
import base64, os

if not os.path.exists("my_session.session"):
    encoded = os.environ.get("TELEGRAM_SESSION_B64")
    if encoded:
        with open("my_session.session", "wb") as f:
            f.write(base64.b64decode(encoded))
import os
import time
import logging
from datetime import datetime
import requests
from telethon import TelegramClient, events
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
DISCORD_WEBHOOK = os.environ["DISCORD_WEBHOOK"]
TELEGRAM_CHAT = os.environ["TELEGRAM_CHANNEL_ID"]
TARGET_LANG = os.environ.get("TARGET_LANG", "en")
LIBRE_URL = os.environ.get("LIBRE_URL", "https://libretranslate.com/translate")
SESSION_FILENAME = os.environ.get("SESSION_FILENAME", "my_session.session")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("relay")

client = TelegramClient(SESSION_FILENAME.replace(".session", ""), API_ID, API_HASH)

def translate_text(text, target="en"):
    try:
        payload = {"q": text, "source": "auto", "target": target, "format": "text"}
        resp = requests.post(LIBRE_URL, json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json().get("translatedText", text)
    except:
        return text

def post_to_discord(content, username="Telegram → Discord"):
    try:
        requests.post(DISCORD_WEBHOOK, json={"content": content, "username": username})
    except:
        pass

@client.on(events.NewMessage(chats=TELEGRAM_CHAT))
async def handler(event):
    sender = await event.get_sender()
    username = sender.username or sender.first_name or "Unknown"
    original = event.raw_text or ""
    if not original.strip():
        return

    translated = translate_text(original, TARGET_LANG)
    timestamp = datetime.utcfromtimestamp(event.date.timestamp()).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"**{username}** at {timestamp}:\n{translated}\n\n*(original: {original})*"
    post_to_discord(msg, username=f"TG: {username}")

def main():
    logger.info("Relay running...")
    client.start()
    client.run_until_disconnected()

if __name__ == "__main__":
    main()