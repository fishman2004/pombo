"""Regras puras do Pombo: sem arquivo, rede ou relógio de verdade, por isso fáceis de testar."""

import re
from datetime import date, datetime, timedelta
from pathlib import Path

from .models import Schedule

CHECK_EVERY = timedelta(minutes=15)
WAIT_LIMIT = timedelta(hours=1)
RETRY_EVERY = timedelta(minutes=5)
MAX_ATTEMPTS = 4  # 1 tentativa + 3 novas
MISSED_AFTER = timedelta(hours=2)


def runs_for_day(schedule: Schedule, day: date) -> list[datetime]:
    if day.weekday() not in schedule.weekdays:
        return []
    return sorted(datetime.combine(day, t) for t in schedule.times)


def is_fresh(mtime: datetime, now: datetime, last_success: datetime | None) -> bool:
    # "atualizado" = mexido hoje e depois do último envio que deu certo
    return mtime.date() == now.date() and (last_success is None or mtime > last_success)


def check_slots(scheduled: datetime) -> list[datetime]:
    steps = WAIT_LIMIT // CHECK_EVERY
    return [scheduled + CHECK_EVERY * i for i in range(steps + 1)]


def is_missed(scheduled: datetime, now: datetime) -> bool:
    return now - scheduled > MISSED_AFTER


def next_retry_at(failures: list[datetime]) -> datetime | None:
    if not failures:
        return datetime.min
    if len(failures) >= MAX_ATTEMPTS:
        return None
    return failures[-1] + RETRY_EVERY


def greeting(now: datetime) -> str:
    if now.hour < 12:
        return "Bom dia"
    if now.hour < 18:
        return "Boa tarde"
    return "Boa noite"


def render(template: str, now: datetime, files: list[Path]) -> str:
    values = {
        "saudacao": greeting(now),
        "data": now.strftime("%d/%m/%Y"),
        "hora": now.strftime("%H:%M"),
        "arquivos": ", ".join(Path(f).name for f in files),
    }
    # campo desconhecido ou chave solta fica como está, sem erro
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m[1], m[0]), template)
