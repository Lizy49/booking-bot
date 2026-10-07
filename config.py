"""Настройки бота. Здесь меняются услуги, часы работы и прочие параметры."""
import os
from pathlib import Path

# ---------- Услуги ----------
SERVICES = [
    {"id": 1, "name": "Стрижка", "price": 1500},
    {"id": 2, "name": "Стрижка + борода", "price": 2200},
    {"id": 3, "name": "Моделирование бороды", "price": 900},
]

# ---------- Расписание ----------
WORK_START = 10          # начало работы, час
WORK_END = 19            # конец работы, час
SLOT_MINUTES = 60        # длина одной записи в минутах
DAYS_AHEAD = 7           # на сколько дней вперёд можно записаться
DAYS_OFF = {6}           # выходные: 0 = понедельник ... 6 = воскресенье
MIN_NOTICE_MINUTES = 30  # за сколько минут до начала запись ещё возможна
MAX_ACTIVE_BOOKINGS = 3  # сколько активных записей может иметь один человек

DB_PATH = "bookings.db"


def get_service(service_id):
    for service in SERVICES:
        if service["id"] == service_id:
            return service
    return None


def load_env(path=".env"):
    """Читает файл .env (строки вида КЛЮЧ=значение) и кладёт значения в окружение."""
    file = Path(path)
    if not file.exists():
        return
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_token():
    return os.environ.get("BOT_TOKEN", "").strip()


def get_admin_ids():
    """ADMIN_IDS=123456,789012 -> {123456, 789012}"""
    result = set()
    for part in os.environ.get("ADMIN_IDS", "").split(","):
        part = part.strip()
        if part.isdigit():
            result.add(int(part))
    return result
