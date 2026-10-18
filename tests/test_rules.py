from datetime import date, datetime, time, timedelta
from pathlib import Path

from pombo.models import Schedule
from pombo.rules import check_slots, greeting, is_fresh, is_missed, next_retry_at, render, runs_for_day


def test_runs_only_on_selected_weekdays():
    s = Schedule(weekdays={0, 1, 2, 3, 4}, times=[time(18, 0), time(14, 0)])
    assert runs_for_day(s, date(2026, 10, 19)) == [datetime(2026, 10, 19, 14), datetime(2026, 10, 19, 18)]  # segunda
    assert runs_for_day(s, date(2026, 10, 18)) == []  # domingo


def test_fresh_requires_today_and_after_last_success():
    now = datetime(2026, 10, 19, 18, 0)
    assert is_fresh(datetime(2026, 10, 19, 17, 50), now, None)
    assert not is_fresh(datetime(2026, 10, 18, 17, 50), now, None)  # ontem
    assert not is_fresh(datetime(2026, 10, 19, 13, 50), now, datetime(2026, 10, 19, 14, 0))  # já foi às 14h
    assert is_fresh(datetime(2026, 10, 19, 17, 50), now, datetime(2026, 10, 19, 14, 0))


def test_check_slots_every_15_min_for_1h():
    assert check_slots(datetime(2026, 10, 19, 18)) == [
        datetime(2026, 10, 19, 18, m) for m in (0, 15, 30, 45)
    ] + [datetime(2026, 10, 19, 19, 0)]


def test_missed_after_two_hours():
    sch = datetime(2026, 10, 19, 18)
    assert not is_missed(sch, datetime(2026, 10, 19, 19, 59))
    assert is_missed(sch, datetime(2026, 10, 19, 20, 1))


def test_retry_three_more_times_every_5_min():
    t = datetime(2026, 10, 19, 18)
    assert next_retry_at([]) == datetime.min  # sem falhas: já pode tentar
    assert next_retry_at([t]) == t + timedelta(minutes=5)
    four = [t + timedelta(minutes=5 * i) for i in range(4)]
    assert next_retry_at(four) is None


def test_render_fields_and_unknown_kept():
    now = datetime(2026, 10, 19, 18, 2)
    out = render("{saudacao}! {data} {hora} {arquivos} {xyz}", now, [Path("Vendas.xlsx"), Path("Plano.xlsx")])
    assert out == "Boa noite! 19/10/2026 18:02 Vendas.xlsx, Plano.xlsx {xyz}"


def test_render_tolerates_stray_braces():
    now = datetime(2026, 10, 19, 9, 0)
    assert render("Meta {100%} {saudacao", now, []) == "Meta {100%} {saudacao"


def test_greeting_boundaries():
    assert greeting(datetime(2026, 10, 19, 11, 59)) == "Bom dia"
    assert greeting(datetime(2026, 10, 19, 12, 0)) == "Boa tarde"
    assert greeting(datetime(2026, 10, 19, 18, 0)) == "Boa noite"
