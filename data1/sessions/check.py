import os
from telethon.sync import TelegramClient

# Read API credentials from environment
API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH")

if not API_ID or not API_HASH:
    raise ValueError("API_ID and API_HASH must be set in environment variables")

# Use the same session location as the collector: mtproto.session in this folder
SESSION_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_PATH = os.path.join(SESSION_DIR, "mtproto")

print(f"Using session: {SESSION_PATH}.session, exists={os.path.exists(SESSION_PATH + '.session')}")

with TelegramClient(SESSION_PATH, API_ID, API_HASH) as client:
    print("Connected:", client.is_connected())
    print("Authorized:", client.is_user_authorized())
    print(f"API_ID: {API_ID}")
    print(f"API_HASH: {API_HASH}")
