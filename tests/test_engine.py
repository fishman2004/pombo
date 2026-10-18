import os
from datetime import date, datetime, time, timedelta

import pytest

from fakes import FakeAlerts, FakeChannel, FakeClock
from pombo.engine import Engine
from pombo.history import History, Row
from pombo.models import Contact, Dispatch, EmailList, Registry, Schedule, Settings, WhatsAppGroup
from pombo.store import Store

MON = date(2026, 10, 19)  # segunda-feira
RUN18 = "2026-10-19 18:00"


def at(h, m=0, day=MON) -> datetime:
    return datetime.combine(day, time(h, m))


class Env:
    def __init__(self, tmp_path, times=(time(18, 0),), n_files=1, check=True, demo=False, active=True):
        self.tmp = tmp_path
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.clock = FakeClock(at(17, 0))
        self.files = []
        for i in range(n_files):
            f = tmp_path / f"Arquivo{i}.xlsx"
            f.write_bytes(b"dados")
            self.files.append(f)
        self.store = Store(tmp_path / "cadastro.json")
        self.store.save(Registry(
            settings=Settings(analyst_name="Kayo", demo_mode=demo, self_email="eu@exemplo.com", self_whatsapp="83999990000"),
            contacts=[Contact(id="c1", name="Ana", email="ana@exemplo.com"), Contact(id="c2", name="Bia", email="bia@exemplo.com")],
            email_lists=[EmailList(id="l1", name="Gestão", contact_ids=["c1", "c2"])],
            whatsapp_groups=[WhatsAppGroup(id="123@g.us", name="Comercial")],
            dispatches=[Dispatch(
                id="d1", name="Vendas", files=self.files, email_list_ids=["l1"], whatsapp_group_ids=["123@g.us"],
                schedule=Schedule(weekdays={0, 1, 2, 3, 4}, times=list(times)),
                subject="Vendas {data}", message="{saudacao}!", check_freshness=check, active=active,
            )],
        ))
        self.history = History(tmp_path / "historico", "Kayo", tmp_path / "pendentes.csv")
        self.history.load(MON)
        self.email = FakeChannel("email")
        self.wa = FakeChannel("whatsapp")
        self.alerts = FakeAlerts()
        self.engine = self.new_engine()

    def new_engine(self) -> Engine:
        return Engine(self.store, self.history, {"email": self.email, "whatsapp": self.wa}, self.alerts, clock=self.clock)

    def touch(self, when: datetime, index: int | None = None) -> None:
        for i, f in enumerate(self.files):
            if index is None or i == index:
                os.utime(f, (when.timestamp(), when.timestamp()))

    def tick_at(self, when: datetime) -> None:
        self.clock.now = when
        self.engine.tick()

    def run_until(self, start: datetime, end: datetime) -> None:
        t = start
        while t <= end:
            self.tick_at(t)
            t += timedelta(minutes=1)

    def statuses(self, run: str = RUN18) -> list[str]:
        return [r.status for r in self.history.rows_for_run("d1", run)]

    def add_row(self, status, target="", channel="", run=RUN18, when=None, detail=""):
        self.history.append(Row(when or at(18, 0), "Kayo", "Vendas", run, channel, target, "", status, detail, "d1"))


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_sends_at_time_when_fresh(env):
    env.touch(at(17, 50))
    env.tick_at(at(17, 59))
    assert env.email.calls == [] and env.wa.calls == []
    env.tick_at(at(18, 0))
    assert len(env.email.calls) == 1 and len(env.wa.calls) == 1
    assert env.statuses() == ["enviado", "enviado"]
    label, subject, message, files = env.email.calls[0]
    assert (label, subject, message, files) == ("Gestão", "Vendas 19/10/2026", "Boa noite!", ["Arquivo0.xlsx"])
    env.tick_at(at(18, 1))
    assert len(env.email.calls) == 1 and len(env.wa.calls) == 1


def test_stale_waits_and_sends_on_next_slot(env):
    env.touch(at(17, 50, MON - timedelta(days=1)))
    env.tick_at(at(18, 0))
    assert env.email.calls == [] and env.statuses() == ["esperando"]
    env.touch(at(18, 10))
    env.tick_at(at(18, 10))
    assert env.email.calls == []
    env.tick_at(at(18, 15))
    assert len(env.email.calls) == 1 and len(env.wa.calls) == 1


def test_gives_up_after_one_hour_alerts_once(env):
    env.touch(at(17, 50, MON - timedelta(days=1)))
    env.run_until(at(18, 0), at(19, 10))
    assert env.email.calls == [] and env.wa.calls == []
    assert env.statuses().count("desistiu") == 1 and env.statuses().count("esperando") == 1
    assert len(env.alerts.calls) == 1


def test_second_round_needs_new_update(tmp_path):
    env = Env(tmp_path, times=(time(14, 0), time(18, 0)))
    env.touch(at(13, 50))
    env.tick_at(at(14, 0))
    assert len(env.email.calls) == 1
    env.tick_at(at(18, 0))
    assert env.statuses() == ["esperando"] and len(env.email.calls) == 1


def test_all_files_must_be_fresh(tmp_path):
    env = Env(tmp_path, n_files=2)
    env.touch(at(17, 50), index=0)
    env.touch(at(17, 50, MON - timedelta(days=1)), index=1)
    env.tick_at(at(18, 0))
    assert env.email.calls == [] and env.statuses() == ["esperando"]


def test_never_resends_after_restart(env):
    env.touch(at(17, 50))
    env.add_row("enviado", target="Gestão", channel="email")
    env.engine = env.new_engine()
    env.tick_at(at(18, 1))
    assert env.email.calls == [] and len(env.wa.calls) == 1


def test_retries_three_times_every_5_min(env):
    env.email.fail = True
    env.touch(at(17, 50))
    env.run_until(at(18, 0), at(18, 30))
    assert len(env.email.calls) == 4 and len(env.wa.calls) == 1
    fails = [r.when for r in env.history.rows_for_run("d1", RUN18) if r.status == "falhou"]
    assert fails == [at(18, 0), at(18, 5), at(18, 10), at(18, 15)]
    assert len(env.alerts.calls) == 1


def test_missed_run_not_sent_after_two_hours(tmp_path):
    late = Env(tmp_path / "a")
    late.touch(at(17, 50))
    late.tick_at(at(20, 1))
    assert late.statuses() == ["perdido"] and late.email.calls == []

    in_time = Env(tmp_path / "b")
    in_time.touch(at(17, 50))
    in_time.tick_at(at(19, 59))
    assert len(in_time.email.calls) == 1


def test_demo_mode_records_without_sending(tmp_path):
    env = Env(tmp_path, demo=True)
    env.touch(at(17, 50))
    env.tick_at(at(18, 0))
    assert env.email.calls == [] and env.wa.calls == []
    assert env.statuses() == ["demonstracao", "demonstracao"]
    env.tick_at(at(18, 5))
    assert len(env.statuses()) == 2


def test_send_now_ignores_freshness_and_skips_sent(env):
    env.touch(at(17, 50, MON - timedelta(days=1)))
    env.add_row("desistiu", detail="não atualizado")
    env.add_row("enviado", target="Gestão", channel="email")
    env.clock.now = at(19, 20)
    env.engine.send_now("d1", at(18, 0))
    assert env.email.calls == [] and len(env.wa.calls) == 1

    env.engine.send_now("d1")  # rodada manual nova
    assert len(env.email.calls) == 1 and len(env.wa.calls) == 2
    assert env.statuses("manual 2026-10-19 19:20:00") == ["enviado", "enviado"]


def test_paused_dispatch_does_nothing(tmp_path):
    env = Env(tmp_path, active=False)
    env.touch(at(17, 50))
    env.tick_at(at(18, 0))
    assert env.statuses() == []


def test_whatsapp_unavailable_email_still_sent(env):
    # Review Focus 5
    env.wa.unavailable = True
    env.touch(at(17, 50))
    env.run_until(at(18, 0), at(18, 4))
    assert len(env.email.calls) == 1
    assert [r.status for r in env.history.rows_for_run("d1", RUN18) if r.channel == "whatsapp"] == ["esperando"]
    assert len(env.alerts.calls) == 1
    env.wa.unavailable = False
    env.tick_at(at(18, 5))
    wa_rows = [r.status for r in env.history.rows_for_run("d1", RUN18) if r.channel == "whatsapp"]
    assert wa_rows == ["esperando", "enviado"] and "falhou" not in wa_rows


def test_tick_survives_unexpected_exception(env):
    env.email.crash = True
    env.touch(at(17, 50))
    env.tick_at(at(18, 0))  # não pode lançar
    assert len(env.wa.calls) == 1
    assert "falhou" in [r.status for r in env.history.rows_for_run("d1", RUN18) if r.channel == "email"]


def test_send_test_goes_only_to_me_without_history(env):
    env.touch(at(17, 50, MON - timedelta(days=1)))
    env.clock.now = at(10, 0)
    result = env.engine.send_test("d1")
    assert result == [("email", "ok"), ("whatsapp", "ok")]
    assert env.email.calls[0][0] == "Eu (teste)" and env.email.calls[0][1].startswith("[TESTE] ")
    assert env.history.rows_between(MON, MON) == []


def test_timeline_states(tmp_path):
    times = (time(8), time(12), time(14), time(18), time(20), time(22))
    env = Env(tmp_path, times=times)
    env.add_row("perdido", run="2026-10-19 08:00")
    env.add_row("enviado", "Gestão", "email", run="2026-10-19 12:00", when=at(12, 2))
    env.add_row("enviado", "Comercial", "whatsapp", run="2026-10-19 12:00", when=at(12, 2))
    env.add_row("enviado", "Gestão", "email", run="2026-10-19 14:00")
    for m in (0, 5, 10, 15):
        env.add_row("falhou", "Comercial", "whatsapp", run="2026-10-19 14:00", when=at(14, m), detail="timeout")
    env.add_row("esperando", run=RUN18)
    env.add_row("desistiu", run=RUN18, detail="Arquivo0.xlsx: não atualizado hoje")
    env.add_row("esperando", run="2026-10-19 20:00", detail="Arquivo0.xlsx: não atualizado hoje")
    env.clock.now = at(20, 30)
    items = env.engine.timeline(MON)
    assert [i.state for i in items] == ["perdido", "enviado", "parcial", "desistiu", "esperando", "agendado"]
    assert items[1].detail == "12:02" and (items[2].sent, items[2].total) == (1, 2)


# ---------- achados da revisão final ----------

def edit(env, fn):
    reg = env.store.load()
    fn(reg)
    env.store.save(reg)


def test_renamed_list_is_not_resent(env):
    env.touch(at(17, 50))
    env.tick_at(at(18, 0))
    edit(env, lambda reg: setattr(reg.email_lists[0], "name", "Diretoria"))
    env.tick_at(at(18, 30))
    assert len(env.email.calls) == 1


def test_same_name_contacts_have_separate_state(env):
    def two_anas(reg):
        reg.contacts.append(Contact(id="c9", name="Ana", email="outra.ana@exemplo.com"))
        reg.dispatches[0].email_list_ids = []
        reg.dispatches[0].email_contact_ids = ["c1", "c9"]
    edit(env, two_anas)
    env.touch(at(17, 50))
    env.tick_at(at(18, 0))
    assert len(env.email.calls) == 2


def test_late_added_recipient_not_sent_for_missed_run(env):
    env.touch(at(17, 50))
    env.tick_at(at(18, 0))
    edit(env, lambda reg: reg.dispatches[0].email_contact_ids.append("c2"))
    env.tick_at(at(20, 30))
    assert len(env.email.calls) == 1


def test_older_pending_run_does_not_duplicate_newer(tmp_path):
    env = Env(tmp_path, times=(time(14, 0), time(18, 0)))
    env.wa.unavailable = True
    env.touch(at(13, 50))
    env.tick_at(at(14, 0))
    env.touch(at(17, 50))
    env.tick_at(at(18, 0))
    assert len(env.email.calls) == 2
    env.wa.unavailable = False
    env.tick_at(at(18, 30))
    assert len(env.wa.calls) == 1


def test_forced_run_retries_failures(env):
    env.touch(at(17, 50, MON - timedelta(days=1)))
    env.run_until(at(18, 0), at(19, 0))  # desistiu
    env.wa.fail = True
    env.clock.now = at(19, 20)
    env.engine.send_now("d1", at(18, 0))
    assert env.engine.timeline(MON)[0].state == "parcial"
    env.wa.fail = False
    env.tick_at(at(19, 25))
    assert [r.status for r in env.history.rows_for_run("d1", RUN18) if r.channel == "whatsapp"] == ["falhou", "enviado"]


def test_manual_run_retries_when_whatsapp_comes_back(env):
    env.wa.unavailable = True
    env.clock.now = at(10, 0)
    env.engine.send_now("d1")
    env.wa.unavailable = False
    env.tick_at(at(10, 5))
    assert len(env.wa.calls) == 1


def test_manual_double_click_is_ignored(env):
    env.clock.now = at(10, 0)
    env.engine.send_now("d1")
    env.clock.now = at(10, 1)
    env.engine.send_now("d1")
    assert len(env.email.calls) == 1


def test_manual_send_covers_waiting_scheduled_run(env):
    env.touch(at(17, 50, MON - timedelta(days=1)))
    env.tick_at(at(18, 0))
    env.touch(at(18, 10))
    env.clock.now = at(18, 12)
    env.engine.send_now("d1")
    env.run_until(at(18, 13), at(19, 5))
    assert len(env.email.calls) == 1 and env.alerts.calls == []
    assert "desistiu" not in env.statuses()
    assert [i.state for i in env.engine.timeline(MON) if not i.manual] == ["enviado"]


def test_readiness_checked_even_without_freshness(tmp_path):
    env = Env(tmp_path, check=False)
    env.files[0].write_bytes(b"")
    env.tick_at(at(18, 0))
    assert env.email.calls == [] and env.statuses() == ["esperando"]


def test_send_now_waits_until_history_loaded(env):
    env.engine.ready = False
    env.clock.now = at(10, 0)
    env.engine.send_now("d1")
    assert env.email.calls == []
