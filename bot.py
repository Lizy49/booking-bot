"""Точка входа: запускает бота (long polling)."""
import logging
import sys
import time

import config
from handlers import BookingBot
from storage import Storage
from telegram_api import TelegramAPI, TelegramError


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config.load_env()
    token = config.get_token()
    if not token:
        print("Не найден BOT_TOKEN. Создайте файл .env по образцу .env.example "
              "и впишите токен от @BotFather.")
        sys.exit(1)

    api = TelegramAPI(token)
    bot = BookingBot(api, Storage(config.DB_PATH), config.get_admin_ids())
    logging.info("Бот запущен. Остановить: Ctrl+C")

    offset = None
    try:
        while True:
            try:
                updates = api.get_updates(offset)
            except TelegramError as err:
                logging.warning("Ошибка получения обновлений: %s", err)
                time.sleep(5)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    bot.handle_update(update)
                except Exception:  # одна ошибка не должна останавливать бота
                    logging.exception("Ошибка при обработке обновления")
    except KeyboardInterrupt:
        logging.info("Бот остановлен")


if __name__ == "__main__":
    main()
