"""Хранение записей в SQLite."""
import sqlite3
from contextlib import closing
from datetime import datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    user_name  TEXT NOT NULL,
    service_id INTEGER NOT NULL,
    date       TEXT NOT NULL,
    time       TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL
);
-- Одно и то же время не может быть занято двумя активными записями.
-- Эту защиту обеспечивает сама база, поэтому двойная запись невозможна даже при гонке запросов.
CREATE UNIQUE INDEX IF NOT EXISTS uniq_active_slot
    ON bookings(date, time) WHERE status = 'active';
"""


class Storage:
    def __init__(self, path):
        self.path = path
        with closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            conn.commit()

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

    def add_booking(self, user_id, user_name, service_id, day, slot):
        """Создаёт запись. Возвращает её id или None, если время уже занято."""
        try:
            with closing(self._connect()) as conn:
                cur = conn.execute(
                    "INSERT INTO bookings (user_id, user_name, service_id, date, time, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (user_id, user_name, service_id, day, slot,
                     datetime.now().isoformat(timespec="seconds")))
                conn.commit()
                return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def taken_slots(self, day):
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT time FROM bookings WHERE date = ? AND status = 'active'", (day,))
            return {r["time"] for r in rows}

    def user_bookings(self, user_id, from_day):
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' AND date >= ?"
                " ORDER BY date, time", (user_id, from_day))
            return [dict(r) for r in rows]

    def bookings_for_date(self, day):
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT * FROM bookings WHERE date = ? AND status = 'active' ORDER BY time", (day,))
            return [dict(r) for r in rows]

    def cancel_booking(self, booking_id, user_id):
        """Отменяет запись, только если она принадлежит этому пользователю.
        Возвращает данные записи или None."""
        with closing(self._connect()) as conn:
            row = conn.execute(
                "SELECT * FROM bookings WHERE id = ? AND user_id = ? AND status = 'active'",
                (booking_id, user_id)).fetchone()
            if row is None:
                return None
            conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
            conn.commit()
            return dict(row)
