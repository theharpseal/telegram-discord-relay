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
import argostranslate.package
import argostranslate.translate
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

logger = logging.getLogger(__name__)
_ARGOS_READY = False

def _ensure_argos_models():
    """
    Install Ukrainian->English and Russian->English models if missing.
    Downloads from the official Argos package index.
    """
    global _ARGOS_READY
    if _ARGOS_READY:
        return

    # This pulls the latest list of downloadable models
    argostranslate.package.update_package_index()

    installed = argostranslate.package.get_installed_packages()
    installed_pairs = {(p.from_code, p.to_code) for p in installed}

    needed = {("uk", "en"), ("ru", "en")}
    missing = needed - installed_pairs
    if not missing:
        _ARGOS_READY = True
        logger.info("Argos models already installed: %s", installed_pairs)
        return

    available = argostranslate.package.get_available_packages()

    for (src, dst) in missing:
        pkg = next((p for p in available if p.from_code == src and p.to_code == dst), None)
        if not pkg:
            logger.warning("No Argos package found for %s->%s", src, dst)
            continue

        logger.info("Downloading Argos model %s->%s ...", src, dst)
        pkg_path = argostranslate.package.download_package(pkg)

        logger.info("Installing Argos model %s->%s ...", src, dst)
        argostranslate.package.install_from_path(pkg_path)

    _ARGOS_READY = True


def translate_text(text: str, target_lang: str = "en") -> str:
    text = (text or "").strip()
    if not text:
        return text

    # We only support translating to English in this setup
    if target_lang != "en":
        return text

    try:
        _ensure_argos_models()

        # Argos Translate auto-detect is not built-in like online APIs.
        # We’ll try ru->en first, then uk->en, and choose the one that changes the text more.
        ru = argostranslate.translate.translate(text, "ru", "en")
        uk = argostranslate.translate.translate(text, "uk", "en")

        # Pick whichever looks more "English" (very simple heuristic)
        # If both fail to change, return original.
        candidates = [ru, uk]
        best = max(candidates, key=lambda s: sum(ch.isascii() for ch in s))
        return best if best and best.strip() else text

    except Exception as e:
        logger.warning("Offline translation failed, sending original. Error: %s", e)
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