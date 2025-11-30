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

def post_to_discord(content: str, username: str = "Telegram ↠ Discord", file_path: str | None = None):
    try:
        if file_path:
            # Send message + file (image) in one webhook call
            with open(file_path, "rb") as f:
                files = {"file": (os.path.basename(file_path), f)}
                data = {"content": content, "username": username}
                r = requests.post(DISCORD_WEBHOOK, data=data, files=files, timeout=20)
        else:
            # Normal text-only message
            payload = {"content": content, "username": username}
            r = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)

        r.raise_for_status()
    except Exception as e:
        logger.error("Failed to post to Discord: %s", e)

@client.on(events.NewMessage(chats=TELEGRAM_CHAT))
async def handler(event):
    try:
        sender = await event.get_sender()
        username = sender.username or sender.first_name or "Unknown"

        media_path = None
        original_text = ""

        # 1) Check if there is media (photo, document, etc.)
        if event.message.media:
            # Download to a temporary file inside the container
            media_path = await event.message.download_media()
            logger.info("Downloaded media to %s", media_path)

        # 2) Get text (normal message or caption)
        original_text = event.raw_text or (event.message.message or "")

        # If literally no text and no media, ignore (e.g. pure sticker, etc.)
        if not original_text.strip() and not media_path:
            return

        # 3) Translate if there's text
        translated_text = ""
        if original_text.strip():
            translated_text = translate_text(original_text, TARGET_LANG)

        # 4) Build Discord message
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        if translated_text:
            content = f"**{username}** at {timestamp}:\n{translated_text}\n\n*(original: {original_text})*"
        else:
            # Image only, no text
            content = f"**{username}** at {timestamp} sent an image."

        logger.info("Relaying message from %s (media=%s)", username, bool(media_path))

        # 5) Send to Discord (with or without file)
        post_to_discord(content, username=f"TG: {username}", file_path=media_path)

    except Exception as e:
        logger.exception("Error handling message: %s", e)
    finally:
        # 6) Cleanup temp file if we downloaded one
        if media_path:
            try:
                os.remove(media_path)
                logger.info("Deleted temp media file %s", media_path)
            except Exception as cleanup_err:
                logger.warning("Failed to delete temp media file %s: %s", media_path, cleanup_err)

def main():
    logger.info("Relay running...")
    client.start()
    client.run_until_disconnected()

if __name__ == "__main__":
    main()