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

def translate_text(text: str, target_lang: str = "en") -> str:
    text = text.strip()
    if not text:
        return text

    try:
        resp = requests.post(
            TRANSLATE_URL,
            json={
                "q": text,
                "source": "auto",      # auto-detect source language
                "target": target_lang,
                "format": "text",
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        translated = data.get("translatedText")

        if not translated:
            logger.warning("Translation API returned no translatedText: %s", data)
            return text

        return translated
    except Exception as e:
        logger.warning("Translation failed, returning original. Error: %s", e)
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
    media_paths = []
    try:
        sender = await event.get_sender()
        username = sender.username or sender.first_name or "Unknown"

        # 1) Download *all* media if present
        if event.message.media:
            result = await event.message.download_media()
            # download_media may return a single path or a list
            if isinstance(result, list):
                media_paths = [p for p in result if isinstance(p, str)]
            elif isinstance(result, str):
                media_paths = [result]
            logger.info("Downloaded media files: %s", media_paths)

        # 2) Get text / caption (prefer caption over raw_text)
        original_text = event.message.message or event.raw_text or ""
        original_text = original_text.strip()

        # Ignore completely empty posts with no media
        if not original_text and not media_paths:
            return

        # 3) Translate caption if present
        translated_text = ""
        if original_text:
            translated_text = translate_text(original_text, TARGET_LANG)

        # 4) Build Discord message text
        from datetime import datetime
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        if translated_text:
            content = f"**{username}** at {timestamp}:\n{translated_text}\n\n*(original: {original_text})*"
        else:
            # No caption, but we have images
            content = f"**{username}** at {timestamp} sent image(s)."

        logger.info("Relaying message from %s (media_count=%d)", username, len(media_paths))

        # 5) Send to Discord
        if media_paths:
            # If multiple images, send each with the same caption
            for path in media_paths:
                post_to_discord(content, username=f"TG: {username}", file_path=path)
        else:
            # Text-only message
            post_to_discord(content, username=f"TG: {username}")

    except Exception as e:
        logger.exception("Error handling message: %s", e)
    finally:
        # 6) Cleanup downloaded files
        for path in media_paths:
            try:
                os.remove(path)
                logger.info("Deleted temp media file %s", path)
            except Exception as cleanup_err:
                logger.warning("Failed to delete temp media file %s: %s", path, cleanup_err)

def main():
    logger.info("Relay running...")
    client.start()
    client.run_until_disconnected()

if __name__ == "__main__":
    main()