from telethon.sync import TelegramClient

self.API_ID = int(_get_env("API_ID", required=True))
self.API_HASH = _get_env("API_HASH", required=True)

with TelegramClient('mtproto', API_ID, API_HASH) as client:
    print('Авторизация прошла успешно')
    print(f'API_ID: {API_ID}')
    print(f'API_HASH: {API_HASH}')
