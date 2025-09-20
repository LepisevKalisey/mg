import asyncio
import os
from telethon import TelegramClient
from dotenv import load_dotenv

# Подхватим .env из корня проекта
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(BASE_DIR, ".env")
if os.path.exists(ENV_PATH):
    load_dotenv(ENV_PATH)

API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH")
# Поддерживаем обе переменные: PHONE_NUMBER (предпочтительно) и PHONE (обратная совместимость)
PHONE_NUMBER = os.getenv("PHONE_NUMBER") or os.getenv("PHONE")

DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
os.makedirs(SESSIONS_DIR, exist_ok=True)

SESSION_PATH = os.path.join(SESSIONS_DIR, "mtproto")  # Telethon добавит .session


async def main():
    if not API_ID or not API_HASH or not PHONE_NUMBER:
        print("Fill API_ID, API_HASH, and PHONE or PHONE_NUMBER in .env first")
        return

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.connect()

    if not await client.is_user_authorized():
        print("Not authorized yet. Sending code...")
        await client.send_code_request(PHONE_NUMBER)
        code = input("Enter the code you received: ").strip()
        try:
            await client.sign_in(PHONE_NUMBER, code)
        except Exception as e:
            print(f"Sign in failed: {e}")
            return

    me = await client.get_me()
    print(f"Authorized as: {me.username or me.first_name}")
    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())