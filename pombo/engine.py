"""O motor: a cada tick decide o que enviar, para quem, e registra tudo no histórico.

Não guarda estado próprio que importe: o que já saiu vem do histórico.
Assim, reiniciar o PC no meio de uma rodada nunca causa reenvio.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Literal, Protocol

from . import rules
from .channels import Channel, ChannelUnavailable, Target
from .files import inspect
from .history import SUCCESS, History, Row, run_label
from .models import Dispatch, Registry
from .store import Store

log = logging.getLogger(__name__)

State = Literal["agendado", "esperando", "enviado", "parcial", "falhou", "desistiu", "perdido"]


class Alerts(Protocol):
    def notify(self, title: str, body: str) -> None: ...


@dataclass(frozen=True)
class TimelineItem:
    scheduled: datetime
    dispatch_id: str
    dispatch_name: str
    state: State
    detail: str
    sent: int
    total: int
    manual: bool = False


def targets_for(dispatch: Dispatch, reg: Registry) -> list[Target]:
    contacts = {c.id: c for c in reg.contacts}
    lists = {lst.id: lst for lst in reg.email_lists}
    groups = {g.id: g for g in reg.whatsapp_groups}
    out: list[Target] = []
    for lid in dispatch.email_list_ids:
        if lid in lists:
            addrs = tuple(contacts[c].email for c in lists[lid].contact_ids if c in contacts and contacts[c].email)
            if addrs:
                out.append(Target("email", lists[lid].name, addrs))
    for cid in dispatch.email_contact_ids:
        if cid in contacts and contacts[cid].email:
            out.append(Target("email", contacts[cid].name, (contacts[cid].email,)))
    for cid in dispatch.whatsapp_contact_ids:
        if cid in contacts and contacts[cid].whatsapp:
            out.append(Target("whatsapp", contacts[cid].name, (contacts[cid].whatsapp,)))
    for gid in dispatch.whatsapp_group_ids:
        if gid in groups:
            out.append(Target("whatsapp", groups[gid].name, (gid,)))
    return out


def _done(rows: list[Row], t: Target) -> bool:
    return any(r.channel == t.channel and r.target == t.label and r.status in SUCCESS for r in rows)


def _failures(rows: list[Row], t: Target) -> list[datetime]:
    return [r.when for r in rows if r.channel == t.channel and r.target == t.label and r.status == "falhou"]


def _run_level(rows: list[Row], status: str) -> Row | None:
    return next((r for r in reversed(rows) if not r.channel and r.status == status), None)


class Engine:
    def __init__(
        self,
        store: Store,
        history: History,
        channels: dict[str, Channel],
        alerts: Alerts,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.store = store
        self.history = history
        self.channels = channels
        self.alerts = alerts
        self.clock = clock
        self._lock = threading.Lock()
        self._evaluated_slot: dict[tuple[str, str], datetime] = {}
        self._unavailable_at: dict[tuple[str, str, str], datetime] = {}
        self._alerted: set[tuple] = set()

    # ---------- ciclo automático ----------

    def tick(self) -> None:
        with self._lock:
            try:
                now = self.clock()
                reg = self.store.load()
                self.history.flush()
                for d in reg.dispatches:
                    if not d.active:
                        continue
                    for scheduled in rules.runs_for_day(d.schedule, now.date()):
                        if scheduled <= now:
                            self._safe_process(reg, d, scheduled, run_label(scheduled, False), now, force=False)
            except Exception:
                log.exception("erro inesperado no motor; seguindo no próximo ciclo")

    def _safe_process(self, reg, d, scheduled, run, now, force) -> None:
        try:
            self._process(reg, d, scheduled, run, now, force)
        except Exception:
            log.exception("erro ao processar %s %s", d.name, run)

    def _process(self, reg: Registry, d: Dispatch, scheduled: datetime, run: str, now: datetime, force: bool) -> None:
        rows = self.history.rows_for_run(d.id, run)
        targets = targets_for(d, reg)
        if not targets or all(_done(rows, t) for t in targets):
            return
        if not force:
            if _run_level(rows, "desistiu") or _run_level(rows, "perdido"):
                return
            if not rows and rules.is_missed(scheduled, now):
                self._record(reg, d, run, now, "", "", "perdido", "programa fechado no horário")
                return
            # passou na checagem antes se já existe alguma linha de destinatário nesta rodada
            already_checked = any(r.channel for r in rows)
            if d.check_freshness and not already_checked and not self._files_ready(reg, d, scheduled, run, now, rows):
                return
        for t in targets:
            if not _done(rows, t):
                self._send_one(reg, d, run, now, t, rows, force)

    def _files_ready(self, reg, d, scheduled, run, now, rows) -> bool:
        key = (d.id, run)
        slots = rules.check_slots(scheduled)
        current = max(s for s in slots if s <= now)
        if self._evaluated_slot.get(key) == current:
            return False
        self._evaluated_slot[key] = current

        last = self.history.last_success(d.id)
        problem = ""
        for f in d.files:
            st = inspect(f)
            if not st.ready:
                problem = f"{Path(f).name}: {st.reason}"
                break
            if not rules.is_fresh(st.mtime, now, last):
                problem = f"{Path(f).name}: não atualizado hoje"
                break
        if not problem:
            return True
        if current == slots[-1]:
            self._record(reg, d, run, now, "", "", "desistiu", problem)
            self._alert_once(("desistiu", d.id, run), f"Pombo: {d.name} não foi enviado",
                             f"{problem}. Abra o Pombo e use \"Enviar mesmo assim\" se quiser.")
        elif not _run_level(rows, "esperando"):
            self._record(reg, d, run, now, "", "", "esperando", f"{problem} (esperando até {slots[-1]:%H:%M})")
        return False

    def _send_one(self, reg, d, run, now, t: Target, rows, force) -> None:
        failures = _failures(rows, t)
        if not force:
            nxt = rules.next_retry_at(failures)
            if nxt is None or nxt > now:
                return
            last_down = self._unavailable_at.get((d.id, run, t.channel + t.label))
            if last_down and now - last_down < rules.RETRY_EVERY:
                return
        if reg.settings.demo_mode:
            self._record(reg, d, run, now, t.channel, t.label, "demonstracao", "modo demonstração: nada foi enviado")
            return
        channel = self.channels.get(t.channel)
        try:
            if channel is None:
                raise ChannelUnavailable(f"canal {t.channel} não configurado")
            channel.send(t, rules.render(d.subject, now, d.files), rules.render(d.message, now, d.files),
                         [Path(f) for f in d.files], use_bcc=d.use_bcc)
        except ChannelUnavailable as exc:
            key = (d.id, run, t.channel + t.label)
            if key not in self._unavailable_at:
                self._record(reg, d, run, now, t.channel, t.label, "esperando", str(exc))
            self._unavailable_at[key] = now
            self._alert_once(("indisponivel", t.channel, run), f"Pombo: {t.channel} indisponível",
                             f"{exc}. O envio de {d.name} sai assim que reconectar.")
            return
        except Exception as exc:
            self._record(reg, d, run, now, t.channel, t.label, "falhou", str(exc) or type(exc).__name__)
            if len(failures) + 1 >= rules.MAX_ATTEMPTS:
                self._alert_once(("falhou", d.id, run, t.label), f"Pombo: falha ao enviar {d.name}",
                                 f"Não consegui enviar para {t.label} depois de {rules.MAX_ATTEMPTS} tentativas: {exc}")
            return
        self._unavailable_at.pop((d.id, run, t.channel + t.label), None)
        self._record(reg, d, run, now, t.channel, t.label, "enviado", "")

    def _record(self, reg, d, run, now, channel, target, status, detail) -> None:
        files = "; ".join(Path(f).name for f in d.files)
        self.history.append(Row(now, reg.settings.analyst_name, d.name, run, channel, target, files, status, detail, d.id))

    def _alert_once(self, key: tuple, title: str, body: str) -> None:
        if key in self._alerted:
            return
        self._alerted.add(key)
        try:
            self.alerts.notify(title, body)
        except Exception:
            log.exception("falha ao avisar o usuário")

    # ---------- ações da tela ----------

    def send_now(self, dispatch_id: str, scheduled: datetime | None = None) -> None:
        """Envia já, ignorando a checagem de atualização. Nunca reenvia para quem já recebeu."""
        with self._lock:
            reg = self.store.load()
            d = next(x for x in reg.dispatches if x.id == dispatch_id)
            now = self.clock()
            run = run_label(scheduled, False) if scheduled else run_label(now, True)
            self._process(reg, d, scheduled or now, run, now, force=True)

    def send_test(self, dispatch_id: str) -> list[tuple[str, str]]:
        """Envia só para o próprio analista. Não grava histórico."""
        reg = self.store.load()
        d = next(x for x in reg.dispatches if x.id == dispatch_id)
        s = reg.settings
        now = self.clock()
        targets = []
        if s.self_email:
            targets.append(Target("email", "Eu (teste)", (s.self_email,)))
        if s.self_whatsapp:
            targets.append(Target("whatsapp", "Eu (teste)", (s.self_whatsapp,)))
        results = []
        for t in targets:
            try:
                self.channels[t.channel].send(t, "[TESTE] " + rules.render(d.subject, now, d.files),
                                              rules.render(d.message, now, d.files), [Path(f) for f in d.files])
                results.append((t.channel, "ok"))
            except Exception as exc:
                results.append((t.channel, str(exc) or type(exc).__name__))
        return results

    def timeline(self, day: date) -> list[TimelineItem]:
        reg = self.store.load()
        now = self.clock()
        items: list[TimelineItem] = []
        for d in reg.dispatches:
            if not d.active:
                continue
            for scheduled in rules.runs_for_day(d.schedule, day):
                items.append(self._item(reg, d, scheduled, run_label(scheduled, False), now, manual=False))
        manual_runs = {(r.dispatch_id, r.run) for r in self.history.rows_between(day, day) if r.run.startswith("manual ")}
        by_id = {d.id: d for d in reg.dispatches}
        for dispatch_id, run in manual_runs:
            if dispatch_id in by_id:
                when = datetime.strptime(run.removeprefix("manual "), "%Y-%m-%d %H:%M:%S")
                items.append(self._item(reg, by_id[dispatch_id], when, run, now, manual=True))
        return sorted(items, key=lambda i: (i.scheduled, i.dispatch_name))

    def _item(self, reg, d, scheduled, run, now, manual) -> TimelineItem:
        rows = self.history.rows_for_run(d.id, run)
        targets = targets_for(d, reg)
        sent_rows = [r for r in rows if r.status in SUCCESS and r.channel]
        sent = len({(r.channel, r.target) for r in sent_rows})
        total = len(targets)

        def item(state: State, detail: str = "") -> TimelineItem:
            return TimelineItem(scheduled, d.id, d.name, state, detail, sent, total, manual)

        if total and sent >= total:
            return item("enviado", max(r.when for r in sent_rows).strftime("%H:%M"))
        if r := _run_level(rows, "perdido"):
            return item("perdido", r.detail)
        if r := _run_level(rows, "desistiu"):
            return item("desistiu", r.detail)
        last_fail = next((r for r in reversed(rows) if r.status == "falhou"), None)
        if sent:
            return item("parcial", last_fail.detail if last_fail else "")
        if last_fail:
            return item("falhou", last_fail.detail)
        if r := next((r for r in reversed(rows) if r.status == "esperando"), None):
            return item("esperando", r.detail)
        if not rows and scheduled <= now and rules.is_missed(scheduled, now):
            return item("perdido", "programa fechado no horário")
        return item("agendado")
