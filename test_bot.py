import os
import tempfile
import unittest
from datetime import datetime

import config
import scheduling
from handlers import BookingBot
from storage import Storage
from telegram_api import TelegramError

NOW = datetime(2026, 10, 8, 9, 0)  # четверг


class FakeAPI:
    def __init__(self):
        self.sent, self.edited, self.answered = [], [], []

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append((chat_id, text, reply_markup))

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.edited.append((chat_id, message_id, text, reply_markup))

    def answer_callback_query(self, callback_query_id, text=None):
        self.answered.append(callback_query_id)


def buttons_of(markup):
    return [b for row in markup["inline_keyboard"] for b in row]


class BotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.storage = Storage(os.path.join(self.tmp.name, "t.db"))
        self.api = FakeAPI()
        self.now = NOW
        self.bot = BookingBot(self.api, self.storage, admin_ids={999}, now=lambda: self.now)

    def tearDown(self):
        self.tmp.cleanup()

    def press(self, data, user_id=1, name="Аня"):
        self.bot.handle_update({"callback_query": {
            "id": "q", "data": data, "from": {"id": user_id, "first_name": name},
            "message": {"message_id": 10, "chat": {"id": user_id}}}})

    def say(self, text, user_id=1):
        self.bot.handle_update({"message": {
            "text": text, "chat": {"id": user_id}, "from": {"id": user_id, "first_name": "Аня"}}})

    def last_edit(self):
        return self.api.edited[-1]

    # ---------- расписание ----------
    def test_slots_cover_working_day(self):
        slots = scheduling.day_slots(NOW.date(), 10, 19, 60)
        self.assertEqual(slots[0], "10:00")
        self.assertEqual(slots[-1], "18:00")
        self.assertEqual(len(slots), 9)

    def test_past_slots_hidden_today(self):
        now = datetime(2026, 10, 8, 14, 10)
        free = scheduling.free_slots(now.date(), now, set(), 10, 19, 60, 30)
        self.assertEqual(free[0], "15:00")

    def test_days_off_excluded(self):
        days = scheduling.available_dates(NOW.date(), 7, {6})
        self.assertNotIn(11, [d.day for d in days])  # 11 октября, воскресенье

    # ---------- сценарии ----------
    def test_start_shows_menu(self):
        self.say("/start")
        chat_id, text, markup = self.api.sent[-1]
        self.assertIn("Здравствуйте", text)
        self.assertEqual({b["callback_data"] for b in buttons_of(markup)}, {"book", "my"})

    def test_unknown_text(self):
        self.say("привет")
        self.assertIn("/start", self.api.sent[-1][1])

    def test_full_booking_flow_and_admin_notification(self):
        self.press("book")
        self.assertIn("s:1", [b["callback_data"] for b in buttons_of(self.last_edit()[3])])
        self.press("s:1")
        self.assertIn("d:1:2026-10-09", [b["callback_data"] for b in buttons_of(self.last_edit()[3])])
        self.press("d:1:2026-10-09")
        self.assertIn("t:1:2026-10-09:14:00", [b["callback_data"] for b in buttons_of(self.last_edit()[3])])
        self.press("t:1:2026-10-09:14:00")
        self.assertIn("Вы записаны", self.last_edit()[2])
        self.assertEqual(self.storage.taken_slots("2026-10-09"), {"14:00"})
        admin_msgs = [m for m in self.api.sent if m[0] == 999]
        self.assertEqual(len(admin_msgs), 1)
        self.assertIn("Новая запись", admin_msgs[0][1])

    def test_double_booking_impossible(self):
        self.press("t:1:2026-10-09:14:00", user_id=1)
        self.press("t:1:2026-10-09:14:00", user_id=2, name="Борис")
        self.assertEqual(len(self.storage.bookings_for_date("2026-10-09")), 1)
        self.assertIn("недоступно", self.last_edit()[2])
        times = [b["callback_data"] for b in buttons_of(self.last_edit()[3])]
        self.assertNotIn("t:1:2026-10-09:14:00", times)

    def test_forged_callback_is_rejected(self):
        self.press("t:1:2026-10-11:12:00")   # воскресенье, выходной
        self.press("t:1:2026-10-09:03:00")   # время вне графика
        self.press("t:99:2026-10-09:12:00")  # несуществующая услуга
        self.press("t:1:мусор:12:00")
        self.press("s:abc")
        self.assertEqual(self.storage.bookings_for_date("2026-10-11"), [])
        self.assertEqual(self.storage.bookings_for_date("2026-10-09"), [])

    def test_limit_of_active_bookings(self):
        for hour in ("10:00", "11:00", "12:00"):
            self.press(f"t:1:2026-10-09:{hour}")
        self.press("t:1:2026-10-09:13:00")
        self.assertEqual(len(self.storage.user_bookings(1, "2026-10-08")), config.MAX_ACTIVE_BOOKINGS)
        self.assertIn("Отмените", self.last_edit()[2])

    def test_my_bookings_and_cancel(self):
        self.press("t:2:2026-10-09:15:00")
        self.press("my")
        self.assertIn("Стрижка + борода", self.last_edit()[2])
        booking = self.storage.user_bookings(1, "2026-10-08")[0]
        self.press(f"c:{booking['id']}")
        self.assertEqual(self.storage.user_bookings(1, "2026-10-08"), [])
        self.assertEqual(self.storage.taken_slots("2026-10-09"), set())  # время снова свободно
        self.assertTrue(any("отменена" in m[1] for m in self.api.sent if m[0] == 999))

    def test_cannot_cancel_foreign_booking(self):
        self.press("t:1:2026-10-09:10:00", user_id=1)
        booking = self.storage.user_bookings(1, "2026-10-08")[0]
        self.press(f"c:{booking['id']}", user_id=2, name="Чужой")
        self.assertEqual(len(self.storage.user_bookings(1, "2026-10-08")), 1)

    def test_admin_command(self):
        self.press("t:1:2026-10-09:10:00")
        self.say("/admin", user_id=1)
        self.assertIn("только администратору", self.api.sent[-1][1])
        self.say("/admin", user_id=999)
        self.assertIn("записей нет", self.api.sent[-1][1])  # на сегодня пусто

    def test_html_in_name_is_escaped(self):
        self.press("t:1:2026-10-09:10:00", name="<b>Хакер</b>")
        admin_text = [m for m in self.api.sent if m[0] == 999][0][1]
        self.assertNotIn("<b>Хакер</b>", admin_text)
        self.assertIn("&lt;b&gt;", admin_text)

    def test_edit_failure_falls_back_to_new_message(self):
        def broken(*a, **k):
            raise TelegramError("message to edit not found")
        self.api.edit_message_text = broken
        self.press("book")
        self.assertIn("Выберите услугу", self.api.sent[-1][1])


if __name__ == "__main__":
    unittest.main()
