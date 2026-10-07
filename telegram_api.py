"""Тонкая обёртка над Telegram Bot API (только стандартная библиотека)."""
import json
import urllib.error
import urllib.request


class TelegramError(Exception):
    """Ошибка при обращении к Telegram. В тексте нет токена."""


class TelegramAPI:
    def __init__(self, token, base_url="https://api.telegram.org"):
        self._url = f"{base_url}/bot{token}/"

    def call(self, method, params=None, timeout=15):
        data = json.dumps(params or {}).encode("utf-8")
        request = urllib.request.Request(
            self._url + method, data=data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as err:
            try:
                description = json.load(err).get("description", f"HTTP {err.code}")
            except ValueError:
                description = f"HTTP {err.code}"
            raise TelegramError(description) from None
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            raise TelegramError(f"Сетевая ошибка: {type(err).__name__}") from None
        if not payload.get("ok"):
            raise TelegramError(payload.get("description", "Неизвестная ошибка"))
        return payload["result"]

    def get_updates(self, offset=None, timeout=30):
        params = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            params["offset"] = offset
        return self.call("getUpdates", params, timeout=timeout + 10)

    def send_message(self, chat_id, text, reply_markup=None):
        params = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self.call("sendMessage", params)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        params = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
        if reply_markup:
            params["reply_markup"] = reply_markup
        return self.call("editMessageText", params)

    def answer_callback_query(self, callback_query_id, text=None):
        params = {"callback_query_id": callback_query_id}
        if text:
            params["text"] = text
        return self.call("answerCallbackQuery", params)
