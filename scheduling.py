"""Расчёт дат и свободного времени. Чистые функции без базы данных и сети."""
from datetime import date, datetime, time, timedelta


def available_dates(today, days_ahead, days_off):
    """Список рабочих дат, начиная с сегодняшней."""
    days = [today + timedelta(days=i) for i in range(days_ahead)]
    return [d for d in days if d.weekday() not in days_off]


def day_slots(day, start_hour, end_hour, step_minutes):
    """Все слоты дня в виде строк 'ЧЧ:ММ'. Слот должен целиком поместиться в рабочий день."""
    step = timedelta(minutes=step_minutes)
    current = datetime.combine(day, time(start_hour))
    end = datetime.combine(day, time(end_hour))
    slots = []
    while current + step <= end:
        slots.append(current.strftime("%H:%M"))
        current += step
    return slots


def free_slots(day, now, taken, start_hour, end_hour, step_minutes, min_notice_minutes=0):
    """Свободные слоты: без занятых и (для сегодняшнего дня) без уже прошедших."""
    result = []
    deadline = now + timedelta(minutes=min_notice_minutes)
    for slot in day_slots(day, start_hour, end_hour, step_minutes):
        if slot in taken:
            continue
        slot_start = datetime.combine(day, datetime.strptime(slot, "%H:%M").time())
        if slot_start <= deadline:
            continue
        result.append(slot)
    return result
