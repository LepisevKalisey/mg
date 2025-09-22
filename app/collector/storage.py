import json
import os
import time
import re
from typing import Any, Dict


def ensure_dirs(*paths: str) -> None:
    for p in paths:
        os.makedirs(p, exist_ok=True)


def _sanitize_filename(name: str) -> str:
    # Разрешаем Юникод, включая кириллицу; заменяем только недопустимые для файловых имён символы
    # Запрещенные символы Windows/Unix: \ / : * ? " < > |
    name = re.sub(r'[\\/:*?"<>|]+', '_', name)
    # Заменим последовательности пробелов и управляющих символов на один пробел
    name = re.sub(r'\s+', ' ', name)
    # Удалим не-печатаемые символы (категория C в Юникоде)
    name = ''.join(ch for ch in name if ch.isprintable())
    # Обрежем пробелы в конце/начале и приведём к разумной длине
    name = name.strip()
    if len(name) > 80:
        name = name[:80]
    return name or "unknown"


def save_pending_message(pending_dir: str, payload: Dict[str, Any]) -> str:
    # Файл как: {ts}_{channel_name}_{message_id}.json
    ts = int(time.time())
    channel_name = _sanitize_filename(str(payload.get("channel_name", "unknown")))
    message_id = str(payload.get("message_id", "unknown"))
    filename = f"{ts}_{channel_name}_{message_id}.json"
    path = os.path.join(pending_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    return path