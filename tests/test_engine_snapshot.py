"""O motor com envios de print da planilha e envios só de texto."""

import os
from datetime import date, datetime, time

from fakes import FakeAlerts, FakeChannel, FakeClock
from pombo.channels import SendError
from pombo.engine import Engine
from pombo.history import History
from pombo.models import Contact, Dispatch, Registry, Schedule, Settings, Snapshot, WhatsAppGroup
from pombo.store import Store
from tools.make_phd import make_phd

THU = date(2026, 10, 22)
RUN = "2026-10-22 09:00"
SUPS = ["S-LT (MARINA COUTO)", "S-AG (RAFAEL DUARTE)", "S-ST (LUANA PRADO)"]


def at(h, m=0) -> datetime:
    return datetime.combine(THU, time(h, m))


class FlakyChannel(FakeChannel):
    """Falha só nas mensagens cuja legenda contém um texto."""

    def __init__(self, name, fail_on):
        super().__init__(name)
        self.fail_on = fail_on

    def send(self, target, subject, message, files, use_bcc=True):
        self.calls.append((target.label, subject, message, [f.name for f in files]))
        if self.fail_on and self.fail_on in message:
            raise SendError("rede caiu")


class Env:
    def __init__(self, tmp_path, snapshot=True, files=(), message="{valor}: {acima} de {linhas} na meta"):
        self.phd = make_phd(tmp_path / "PHD.xlsx")
        self.touch(at(8, 50))
        self.store = Store(tmp_path / "cadastro.json")
        sn = Snapshot(source=self.phd, header_row=15, columns=["D"], day_columns="F:AJ", day_row=14,
                      split_column="E", name_column="D") if snapshot else None
        self.store.save(Registry(
            settings=Settings(analyst_name="Kayo", self_whatsapp="83999990000"),
            contacts=[Contact(id="c1", name="Ana", whatsapp="5583999990000")],
            whatsapp_groups=[WhatsAppGroup(id="123@g.us", name="Gestão Comercial")],
            dispatches=[Dispatch(id="d1", name="PHD", files=list(files), whatsapp_group_ids=["123@g.us"],
                                 schedule=Schedule(weekdays={3}, times=[time(9, 0)]), subject="PHD {valor}",
                                 message=message, snapshot=sn)],
        ))
        self.history = History(tmp_path / "historico", "Kayo", tmp_path / "pendentes.csv")
        self.history.load(THU)
        self.wa = FakeChannel("whatsapp")
        self.alerts = FakeAlerts()
        self.clock = FakeClock(at(8, 0))
        self.engine = self.new_engine()

    def new_engine(self):
        return Engine(self.store, self.history, {"whatsapp": self.wa}, self.alerts, clock=self.clock)

    def touch(self, when):
        os.utime(self.phd, (when.timestamp(), when.timestamp()))

    def tick_at(self, when):
        self.clock.now = when
        self.engine.tick()

    def rows(self):
        return [r for r in self.history.rows_for_run("d1", RUN) if r.channel]


def test_one_photo_per_supervisor_with_its_caption(tmp_path):
    env = Env(tmp_path)
    env.tick_at(at(9, 0))
    assert [c[0] for c in env.wa.calls] == [f"Gestão Comercial · {s}" for s in SUPS]
    label, subject, message, files = env.wa.calls[2]
    assert subject == "PHD S-ST (LUANA PRADO)" and message.startswith("S-ST (LUANA PRADO): ")
    assert message.endswith(" de 12 na meta") and files == ["03-s-st-luana-prado.png"]
    assert [r.status for r in env.rows()] == ["enviado"] * 3
    assert {r.target_key for r in env.rows()} == {"group:123@g.us#s-lt-marina-couto", "group:123@g.us#s-ag-rafael-duarte",
                                                   "group:123@g.us#s-st-luana-prado"}
    assert env.rows()[0].files == "PHD.xlsx"
    [item] = env.engine.timeline(THU)
    assert (item.state, item.sent, item.total) == ("enviado", 3, 3)
    env.tick_at(at(9, 1))
    assert len(env.wa.calls) == 3


def test_waits_for_the_sheet_to_be_updated(tmp_path):
    env = Env(tmp_path)
    env.touch(datetime(2026, 10, 21, 18, 0))
    env.tick_at(at(9, 0))
    assert env.wa.calls == []
    [item] = env.engine.timeline(THU)
    assert item.state == "esperando" and "PHD.xlsx" in item.detail


def test_failed_part_is_the_only_one_retried(tmp_path):
    env = Env(tmp_path)
    env.wa = FlakyChannel("whatsapp", fail_on="S-AG")
    env.engine = env.new_engine()
    env.tick_at(at(9, 0))
    assert len(env.wa.calls) == 3
    [item] = env.engine.timeline(THU)
    assert (item.state, item.sent, item.total) == ("parcial", 2, 3)
    env.wa.fail_on = ""
    env.tick_at(at(9, 5))
    assert [c[0] for c in env.wa.calls[3:]] == ["Gestão Comercial · S-AG (RAFAEL DUARTE)"]
    assert env.engine.timeline(THU)[0].state == "enviado"


def test_restart_reuses_the_same_print(tmp_path):
    env = Env(tmp_path)
    env.wa = FlakyChannel("whatsapp", fail_on="S-ST")
    env.engine = env.new_engine()
    env.tick_at(at(9, 0))
    first_caption = env.wa.calls[2][2]
    # a planilha muda e o PC reinicia: quem falta recebe o mesmo print da rodada, não um novo
    make_phd(env.phd, seed=99)
    env.touch(at(9, 3))
    env.wa.fail_on = ""
    env.engine = env.new_engine()
    env.tick_at(at(9, 5))
    assert env.wa.calls[-1][2] == first_caption


def test_broken_sheet_gives_up_and_alerts(tmp_path):
    env = Env(tmp_path)
    reg = env.store.load()
    reg.dispatches[0].snapshot.sheet = "Não existe"
    env.store.save(reg)
    env.tick_at(at(9, 0))
    env.tick_at(at(9, 1))
    assert env.wa.calls == []
    [item] = env.engine.timeline(THU)
    assert item.state == "desistiu" and "print da planilha" in item.detail
    assert len(env.alerts.calls) == 1 and "não foi enviado" in env.alerts.calls[0][0]


def test_send_now_rebuilds_after_fixing_the_sheet(tmp_path):
    env = Env(tmp_path)
    reg = env.store.load()
    reg.dispatches[0].snapshot.sheet = "Não existe"
    env.store.save(reg)
    env.tick_at(at(9, 0))
    reg.dispatches[0].snapshot.sheet = "PHD"
    env.store.save(reg)
    env.clock.now = at(9, 10)
    env.engine.send_now("d1", at(9, 0))
    assert len(env.wa.calls) == 3


def test_text_only_message(tmp_path):
    env = Env(tmp_path, snapshot=False, message="{saudacao}! Lembrete: PHD até {hora}.")
    env.tick_at(at(9, 0))
    assert env.wa.calls == [("Gestão Comercial", "PHD {valor}", "Bom dia! Lembrete: PHD até 09:00.", [])]
    assert [r.status for r in env.rows()] == ["enviado"]


def test_preview_and_test_send_only_to_me(tmp_path):
    env = Env(tmp_path)
    env.clock.now = at(8, 30)
    parts = env.engine.preview("d1")
    assert [p.label for p in parts] == SUPS and all(p.image.is_file() for p in parts)
    assert env.engine.send_test("d1") == [("whatsapp", "ok")]
    assert [c[0] for c in env.wa.calls] == ["Eu (teste)"] * 3
    assert env.history.rows_for_run("d1", RUN) == []
