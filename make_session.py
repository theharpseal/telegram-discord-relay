from telethon.sync import TelegramClient
import os

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

client = TelegramClient("my_session", API_ID, API_HASH)
client.start()
print("Created session file")
client.disconnect()