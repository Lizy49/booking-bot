"""Логика бота: команды и нажатия на кнопки. Не зависит от сети, поэтому тестируется без Telegram."""
import html
from datetime import date, datetime, timedelta

import config
import scheduling
from telegram_api import TelegramError

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def button(text, data):
    return {"text": text, "callback_data": data}


def keyboard(rows):
    return {"inline_keyboard": rows}


def chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def format_day(day):
    return f"{day.day:02d}.{day.month:02d} ({WEEKDAYS[day.weekday()]})"


def parse_day(text):
    try:
        return date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def user_title(user):
    name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")]))
    return name or user.get("username") or f"id{user.get('id')}"


class BookingBot:
    def __init__(self, api, storage, admin_ids=(), now=datetime.now):
        self.api = api
        self.storage = storage
        self.admin_ids = set(admin_ids)
        self.now = now

    # ================= вход =================
    def handle_update(self, update):
        if "message" in update:
            self._on_message(update["message"])
        elif "callback_query" in update:
            self._on_callback(update["callback_query"])

    def _on_message(self, message):
        text = (message.get("text") or "").strip()
        chat_id = message["chat"]["id"]
        user = message.get("from", {})
        command = text.split()[0].split("@")[0].lower() if text.startswith("/") else ""

        if command in ("/start", "/help"):
            self._home(chat_id, intro=True)
        elif command == "/book":
            self._services(chat_id)
        elif command == "/my":
            self._my_bookings(chat_id, user)
        elif command == "/admin":
            self._admin(chat_id, user)
        else:
            self.api.send_message(chat_id, "Не понял сообщение. Нажмите /start, чтобы открыть меню.")

    def _on_callback(self, query):
        self._safe(self.api.answer_callback_query, query["id"])  # убирает «часики» на кнопке
        message = query.get("message") or {}
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")
        user = query.get("from", {})
        if chat_id is None:
            return

        action, _, rest = (query.get("data") or "").partition(":")
        if action == "home":
            self._home(chat_id, message_id)
        elif action == "book":
            self._services(chat_id, message_id)
        elif action == "my":
            self._my_bookings(chat_id, user, message_id)
        elif action == "s" and rest.isdigit():
            self._dates(chat_id, message_id, int(rest))
        elif action == "d":
            sid, _, day = rest.partition(":")
            if sid.isdigit():
                self._times(chat_id, message_id, int(sid), day)
        elif action == "t":
            parts = rest.split(":", 2)
            if len(parts) == 3 and parts[0].isdigit():
                self._book(chat_id, message_id, user, int(parts[0]), parts[1], parts[2])
        elif action == "c" and rest.isdigit():
            self._cancel(chat_id, message_id, user, int(rest))
        else:
            self._home(chat_id, message_id)

    # ================= вспомогательное =================
    def _safe(self, func, *args):
        try:
            return func(*args)
        except TelegramError:
            return None

    def _show(self, chat_id, message_id, text, markup=None):
        """Редактирует сообщение с кнопками, а если его нет, отправляет новое."""
        if message_id is None:
            self.api.send_message(chat_id, text, markup)
            return
        try:
            self.api.edit_message_text(chat_id, message_id, text, markup)
        except TelegramError as err:
            if "not modified" not in str(err):
                self.api.send_message(chat_id, text, markup)

    def _free(self, day):
        return scheduling.free_slots(
            day, self.now(), self.storage.taken_slots(day.isoformat()),
            config.WORK_START, config.WORK_END, config.SLOT_MINUTES, config.MIN_NOTICE_MINUTES)

    def _working_days(self):
        return scheduling.available_dates(self.now().date(), config.DAYS_AHEAD, config.DAYS_OFF)

    def _notify_admins(self, text):
        for admin_id in self.admin_ids:
            self._safe(self.api.send_message, admin_id, text)

    # ================= экраны =================
    def _home(self, chat_id, message_id=None, intro=False):
        text = "Выберите действие:"
        if intro:
            text = "👋 Здравствуйте! Я помогу записаться на приём.\n\n" + text
        markup = keyboard([
            [button("📅 Записаться", "book")],
            [button("🗂 Мои записи", "my")],
        ])
        self._show(chat_id, message_id, text, markup)

    def _services(self, chat_id, message_id=None):
        rows = [[button(f"{s['name']} — {s['price']} ₽", f"s:{s['id']}")] for s in config.SERVICES]
        rows.append([button("⬅ Назад", "home")])
        self._show(chat_id, message_id, "Выберите услугу:", keyboard(rows))

    def _dates(self, chat_id, message_id, service_id):
        service = config.get_service(service_id)
        if not service:
            return self._home(chat_id, message_id)
        buttons = [button(format_day(day), f"d:{service_id}:{day.isoformat()}")
                   for day in self._working_days() if self._free(day)]
        rows = chunk(buttons, 3)
        rows.append([button("⬅ Назад", "book")])
        text = (f"<b>{html.escape(service['name'])}</b>\nВыберите дату:" if buttons
                else "К сожалению, свободных дат на ближайшую неделю нет.")
        self._show(chat_id, message_id, text, keyboard(rows))

    def _times(self, chat_id, message_id, service_id, day_text, notice=""):
        service = config.get_service(service_id)
        day = parse_day(day_text)
        if not service or day is None or day not in self._working_days():
            return self._dates(chat_id, message_id, service_id)
        slots = self._free(day)
        if not slots:
            return self._dates(chat_id, message_id, service_id)
        rows = chunk([button(s, f"t:{service_id}:{day.isoformat()}:{s}") for s in slots], 3)
        rows.append([button("⬅ Назад", f"s:{service_id}")])
        text = f"{notice}<b>{html.escape(service['name'])}</b>, {format_day(day)}\nВыберите время:"
        self._show(chat_id, message_id, text, keyboard(rows))

    def _book(self, chat_id, message_id, user, service_id, day_text, slot):
        service = config.get_service(service_id)
        day = parse_day(day_text)
        if not service or day is None:
            return self._home(chat_id, message_id)

        today = self.now().date().isoformat()
        if len(self.storage.user_bookings(user.get("id"), today)) >= config.MAX_ACTIVE_BOOKINGS:
            markup = keyboard([[button("🗂 Мои записи", "my")], [button("⬅ Меню", "home")]])
            self._show(chat_id, message_id,
                       f"У вас уже {config.MAX_ACTIVE_BOOKINGS} активные записи. "
                       "Отмените одну из них, чтобы записаться снова.", markup)
            return

        # время обязано быть в списке свободных: данные из кнопки не считаем доверенными
        if day not in self._working_days() or slot not in self._free(day):
            return self._times(chat_id, message_id, service_id, day_text,
                               notice="⚠ Это время уже недоступно.\n\n")

        name = user_title(user)
        booking_id = self.storage.add_booking(user.get("id"), name, service_id, day.isoformat(), slot)
        if booking_id is None:
            return self._times(chat_id, message_id, service_id, day_text,
                               notice="⚠ Это время только что заняли.\n\n")

        markup = keyboard([[button("🗂 Мои записи", "my")], [button("⬅ Меню", "home")]])
        self._show(chat_id, message_id,
                   f"✅ Вы записаны!\n\n<b>{html.escape(service['name'])}</b>\n"
                   f"📅 {format_day(day)} в {slot}\n💰 {service['price']} ₽", markup)
        self._notify_admins(
            f"🆕 Новая запись #{booking_id}\n{html.escape(name)}\n"
            f"{html.escape(service['name'])}, {format_day(day)} в {slot}")

    def _my_bookings(self, chat_id, user, message_id=None):
        today = self.now().date().isoformat()
        bookings = self.storage.user_bookings(user.get("id"), today)
        if not bookings:
            markup = keyboard([[button("📅 Записаться", "book")], [button("⬅ Меню", "home")]])
            return self._show(chat_id, message_id, "У вас пока нет активных записей.", markup)

        lines, rows = [], []
        for b in bookings:
            service = config.get_service(b["service_id"]) or {"name": "Услуга"}
            day = parse_day(b["date"])
            lines.append(f"• {html.escape(service['name'])} — {format_day(day)} в {b['time']}")
            rows.append([button(f"❌ Отменить {format_day(day)} {b['time']}", f"c:{b['id']}")])
        rows.append([button("⬅ Меню", "home")])
        self._show(chat_id, message_id, "<b>Ваши записи:</b>\n" + "\n".join(lines), keyboard(rows))

    def _cancel(self, chat_id, message_id, user, booking_id):
        booking = self.storage.cancel_booking(booking_id, user.get("id"))
        if booking:
            service = config.get_service(booking["service_id"]) or {"name": "Услуга"}
            self._notify_admins(
                f"🚫 Запись #{booking_id} отменена\n{html.escape(booking['user_name'])}\n"
                f"{html.escape(service['name'])}, {format_day(parse_day(booking['date']))} "
                f"в {booking['time']}")
        self._my_bookings(chat_id, user, message_id)

    def _admin(self, chat_id, user):
        if user.get("id") not in self.admin_ids:
            self.api.send_message(chat_id, "Эта команда доступна только администратору.")
            return
        today = self.now().date()
        parts = []
        for day in (today, today + timedelta(days=1)):
            items = self.storage.bookings_for_date(day.isoformat())
            lines = [
                f"{b['time']} — {html.escape(b['user_name'])} "
                f"({html.escape((config.get_service(b['service_id']) or {'name': '?'})['name'])})"
                for b in items] or ["записей нет"]
            parts.append(f"<b>{format_day(day)}</b>\n" + "\n".join(lines))
        self.api.send_message(chat_id, "\n\n".join(parts))
