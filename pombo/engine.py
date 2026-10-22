"""O motor: a cada tick decide o que enviar, para quem, e registra tudo no histórico.

Não guarda estado próprio que importe: o que já saiu vem do histórico.
Assim, reiniciar o PC no meio de uma rodada nunca causa reenvio.
"""

import logging
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable, Literal, Protocol

from . import rules
from .channels import Channel, ChannelUnavailable, Target
from .files import inspect
from .history import SUCCESS, History, Row, run_label
from .models import Dispatch, Registry
from .snapshot import Part, SnapshotRuns
from .store import Store

log = logging.getLogger(__name__)

State = Literal["agendado", "esperando", "enviado", "parcial", "falhou", "desistiu", "perdido"]
MANUAL_DEBOUNCE = timedelta(minutes=2)  # clique duplo em "Enviar agora" não manda duas vezes


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
                out.append(Target("email", lists[lid].name, addrs, f"list:{lid}"))
    for cid in dispatch.email_contact_ids:
        if cid in contacts and contacts[cid].email:
            out.append(Target("email", contacts[cid].name, (contacts[cid].email,), f"contact:{cid}"))
    for cid in dispatch.whatsapp_contact_ids:
        if cid in contacts and contacts[cid].whatsapp:
            out.append(Target("whatsapp", contacts[cid].name, (contacts[cid].whatsapp,), f"contact:{cid}"))
    for gid in dispatch.whatsapp_group_ids:
        if gid in groups:
            out.append(Target("whatsapp", groups[gid].name, (gid,), f"group:{gid}"))
    return out


def split_targets(targets: list[Target], parts: list[Part]) -> list[Target]:
    """Envio com print: cada destinatário recebe cada parte, e cada par tem a própria linha
    no histórico. Se a rede cair na terceira parte, só a terceira em diante sai de novo."""
    return [Target(t.channel, f"{t.label} · {p.label}" if p.label else t.label, t.addresses, f"{t.key}#{p.key}")
            for t in targets for p in parts]


def _matches(r: Row, t: Target) -> bool:
    if r.channel != t.channel:
        return False
    # linhas antigas não têm o identificador estável; aí vale o nome
    return r.target_key == t.key if r.target_key else r.target == t.label


def _done(rows: list[Row], t: Target) -> bool:
    return any(_matches(r, t) and r.status in SUCCESS for r in rows)


def _failures(rows: list[Row], t: Target) -> list[datetime]:
    return [r.when for r in rows if _matches(r, t) and r.status == "falhou"]


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
        snapshots: SnapshotRuns | None = None,
    ) -> None:
        self.store = store
        self.snapshots = snapshots or SnapshotRuns(store.path.parent / "recortes")
        self.history = history
        self.channels = channels
        self.alerts = alerts
        self.clock = clock
        self.ready = True  # o __main__ deixa False até o histórico ser lido
        self._lock = threading.Lock()
        self._evaluated_slot: dict[tuple[str, str], datetime] = {}
        self._unavailable_at: dict[tuple[str, str, str], datetime] = {}
        self._alerted: set[tuple] = set()

    # ---------- ciclo automático ----------

    def tick(self) -> None:
        with self._lock:
            if not self.ready:
                return
            try:
                now = self.clock()
                reg = self.store.load()
                self.history.flush()
                for d in reg.dispatches:
                    if d.active:
                        self._tick_dispatch(reg, d, now)
            except Exception:
                log.exception("erro inesperado no motor; seguindo no próximo ciclo")

    def _tick_dispatch(self, reg: Registry, d: Dispatch, now: datetime) -> None:
        due = [s for s in rules.runs_for_day(d.schedule, now.date()) if s <= now]
        # da rodada mais nova para a mais velha: quem já entrou numa rodada nova
        # não recebe de novo por uma rodada velha que ficou pendente
        newer: list[Row] = []
        for scheduled in reversed(due):
            run = run_label(scheduled, False)
            self._safe(reg, d, scheduled, run, now, force=False, newer=newer)
            newer = newer + [r for r in self.history.rows_for_run(d.id, run) if r.channel]
        for run, when in self._manual_runs(d.id, now.date()):
            self._safe(reg, d, when, run, now, force=False, retry_only=True)

    def _manual_runs(self, dispatch_id: str, day: date) -> list[tuple[str, datetime]]:
        runs = {r.run for r in self.history.rows_between(day, day) if r.dispatch_id == dispatch_id and r.run.startswith("manual ")}
        return sorted((run, datetime.strptime(run.removeprefix("manual "), "%Y-%m-%d %H:%M:%S")) for run in runs)

    def _covered_by_manual(self, dispatch_id: str, scheduled: datetime) -> datetime | None:
        """Um "Enviar agora" depois do horário já cumpriu a rodada agendada."""
        times = [r.when for r in self.history.rows_between(scheduled.date(), scheduled.date())
                 if r.dispatch_id == dispatch_id and r.run.startswith("manual ") and r.channel and r.when >= scheduled]
        return min(times, default=None)

    def _safe(self, reg, d, scheduled, run, now, **kw) -> None:
        try:
            self._process(reg, d, scheduled, run, now, **kw)
        except Exception:
            log.exception("erro ao processar %s %s", d.name, run)

    def _process(self, reg: Registry, d: Dispatch, scheduled: datetime, run: str, now: datetime,
                 force: bool, newer: list[Row] = (), retry_only: bool = False) -> None:
        rows = self.history.rows_for_run(d.id, run)
        targets, parts = self._targets(reg, d, run)
        if not targets or all(_done(rows, t) for t in targets):
            return
        started = any(r.channel for r in rows)
        if not force and not retry_only and not started:
            if _run_level(rows, "desistiu") or _run_level(rows, "perdido"):
                return
            if self._covered_by_manual(d.id, scheduled):
                return
            if not rows and rules.is_missed(scheduled, now):
                self._record(reg, d, run, now, None, "perdido", "programa fechado no horário")
                return
            if not self._files_ready(reg, d, scheduled, run, now, rows):
                return
        if d.snapshot is not None and parts is None:
            built = self._build(reg, d, run, now)
            if built is None:
                return
            targets, parts = built
        for t in targets:
            if _done(rows, t) or any(_matches(r, t) for r in newer):
                continue
            touched = any(_matches(r, t) for r in rows)
            # rodada manual só repete o que falhou; rodada antiga não ganha destinatário novo
            if not force and not touched and (retry_only or rules.is_missed(scheduled, now)):
                continue
            self._send_one(reg, d, run, now, t, rows, force, parts)

    def _targets(self, reg: Registry, d: Dispatch, run: str) -> tuple[list[Target], dict[str, Part] | None]:
        """Os destinatários da rodada. Com print, só depois de gerado é que se sabe quantas partes há."""
        base = targets_for(d, reg)
        parts = self.snapshots.load(d.id, run) if d.snapshot is not None else None
        if parts is None:
            return base, None
        return split_targets(base, parts), {p.key: p for p in parts}

    def _build(self, reg, d, run, now) -> tuple[list[Target], dict[str, Part]] | None:
        try:
            parts = self.snapshots.build(d, run, now)
        except Exception as exc:
            log.exception("erro ao montar o print de %s", d.name)
            self._record(reg, d, run, now, None, "desistiu", f"print da planilha: {exc}")
            self._alert_once(("print", d.id, run), f"Pombo: {d.name} não foi enviado",
                             f"Não consegui montar o print da planilha: {exc}")
            return None
        return split_targets(targets_for(d, reg), parts), {p.key: p for p in parts}

    def _files_ready(self, reg, d, scheduled, run, now, rows) -> bool:
        key = (d.id, run)
        slots = rules.check_slots(scheduled)
        current = max(s for s in slots if s <= now)
        if self._evaluated_slot.get(key) == current:
            return False
        self._evaluated_slot[key] = current

        last = self.history.last_success(d.id)
        problem = ""
        for f in d.watched_files:
            st = inspect(f)
            if not st.ready:
                problem = f"{Path(f).name}: {st.reason}"
                break
            if d.check_freshness and not rules.is_fresh(st.mtime, now, last):
                problem = f"{Path(f).name}: não atualizado hoje"
                break
        if not problem:
            return True
        if current == slots[-1]:
            self._record(reg, d, run, now, None, "desistiu", problem)
            self._alert_once(("desistiu", d.id, run), f"Pombo: {d.name} não foi enviado",
                             f"{problem}. Abra o Pombo e use \"Enviar mesmo assim\" se quiser.")
        elif not _run_level(rows, "esperando"):
            self._record(reg, d, run, now, None, "esperando", f"{problem} (esperando até {slots[-1]:%H:%M})")
        return False

    def _send_one(self, reg, d, run, now, t: Target, rows, force, parts: dict[str, Part] | None = None) -> None:
        failures = _failures(rows, t)
        down_key = (d.id, run, f"{t.channel}:{t.key or t.label}")
        if not force:
            nxt = rules.next_retry_at(failures)
            if nxt is None or nxt > now:
                return
            last_down = self._unavailable_at.get(down_key)
            if last_down and now - last_down < rules.RETRY_EVERY:
                return
        if reg.settings.demo_mode:
            self._record(reg, d, run, now, t, "demonstracao", "modo demonstração: nada foi enviado")
            return
        channel = self.channels.get(t.channel)
        try:
            if channel is None:
                raise ChannelUnavailable(f"canal {t.channel} não configurado")
            channel.send(t, *_content(d, now, parts.get(t.key.rpartition("#")[2]) if parts else None),
                         use_bcc=d.use_bcc)
        except ChannelUnavailable as exc:
            if down_key not in self._unavailable_at:
                self._record(reg, d, run, now, t, "esperando", str(exc))
            self._unavailable_at[down_key] = now
            self._alert_once(("indisponivel", t.channel, run), f"Pombo: {t.channel} indisponível",
                             f"{exc}. O envio de {d.name} sai assim que reconectar.")
            return
        except Exception as exc:
            self._record(reg, d, run, now, t, "falhou", str(exc) or type(exc).__name__)
            if len(failures) + 1 >= rules.MAX_ATTEMPTS:
                self._alert_once(("falhou", d.id, run, t.key or t.label), f"Pombo: falha ao enviar {d.name}",
                                 f"Não consegui enviar para {t.label} depois de {rules.MAX_ATTEMPTS} tentativas: {exc}")
            return
        self._unavailable_at.pop(down_key, None)
        self._record(reg, d, run, now, t, "enviado", "")

    def _record(self, reg, d, run, now, target: Target | None, status, detail) -> None:
        files = "; ".join(Path(f).name for f in d.watched_files)
        channel, label, key = (target.channel, target.label, target.key) if target else ("", "", "")
        self.history.append(Row(now, reg.settings.analyst_name, d.name, run, channel, label, files, status, detail, d.id, key))

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
            if not self.ready:
                return  # sem o histórico carregado, não dá para saber quem já recebeu
            reg = self.store.load()
            d = next(x for x in reg.dispatches if x.id == dispatch_id)
            now = self.clock()
            if scheduled is None:
                recent = [w for _, w in self._manual_runs(d.id, now.date()) if now - w < MANUAL_DEBOUNCE]
                if recent:
                    return
                run = run_label(now, True)
            else:
                run = run_label(scheduled, False)
            self._safe(reg, d, scheduled or now, run, now, force=True)

    def send_test(self, dispatch_id: str) -> list[tuple[str, str]]:
        """Envia só para o próprio analista. Não grava histórico."""
        reg = self.store.load()
        d = next(x for x in reg.dispatches if x.id == dispatch_id)
        s = reg.settings
        now = self.clock()
        try:
            parts = self.snapshots.preview(d, now) if d.snapshot is not None else [None]
        except Exception as exc:
            return [("print", str(exc) or type(exc).__name__)]
        targets = []
        if s.self_email:
            targets.append(Target("email", "Eu (teste)", (s.self_email,)))
        if s.self_whatsapp:
            targets.append(Target("whatsapp", "Eu (teste)", (s.self_whatsapp,)))
        results = []
        for t in targets:
            try:
                for part in parts:
                    subject, message, files = _content(d, now, part)
                    self.channels[t.channel].send(t, "[TESTE] " + subject, message, files)
                results.append((t.channel, "ok"))
            except Exception as exc:
                results.append((t.channel, str(exc) or type(exc).__name__))
        return results

    def preview(self, dispatch_id: str) -> list[Part]:
        """Gera as imagens e textos do print sem enviar nada (botão "Pré-visualizar")."""
        d = next(x for x in self.store.load().dispatches if x.id == dispatch_id)
        if d.snapshot is None:
            return []
        return self.snapshots.preview(d, self.clock())

    def timeline(self, day: date) -> list[TimelineItem]:
        reg = self.store.load()
        now = self.clock()
        items: list[TimelineItem] = []
        for d in reg.dispatches:
            if not d.active:
                continue
            for scheduled in rules.runs_for_day(d.schedule, day):
                items.append(self._item(reg, d, scheduled, run_label(scheduled, False), now, manual=False))
            for run, when in self._manual_runs(d.id, day):
                items.append(self._item(reg, d, when, run, now, manual=True))
        return sorted(items, key=lambda i: (i.scheduled, i.dispatch_name))

    def _item(self, reg, d, scheduled, run, now, manual) -> TimelineItem:
        rows = self.history.rows_for_run(d.id, run)
        targets, _ = self._targets(reg, d, run)
        sent = sum(1 for t in targets if _done(rows, t))
        total = len(targets)

        def item(state: State, detail: str = "") -> TimelineItem:
            return TimelineItem(scheduled, d.id, d.name, state, detail, sent, total, manual)

        channel_rows = [r for r in rows if r.channel]
        if total and sent >= total:
            return item("enviado", max(r.when for r in channel_rows if r.status in SUCCESS).strftime("%H:%M"))
        if channel_rows:
            # algo já foi enviado ou tentado: isso importa mais que "não atualizado"
            last = channel_rows[-1]
            if sent:
                return item("parcial", last.detail)
            if any(r.status == "falhou" for r in channel_rows):
                return item("falhou", next(r for r in reversed(channel_rows) if r.status == "falhou").detail)
            return item("esperando", last.detail)
        if not manual and (when := self._covered_by_manual(d.id, scheduled)):
            return item("enviado", f"pelo envio manual das {when:%H:%M}")
        if r := _run_level(rows, "perdido"):
            return item("perdido", r.detail)
        if r := _run_level(rows, "desistiu"):
            return item("desistiu", r.detail)
        if r := _run_level(rows, "esperando"):
            return item("esperando", r.detail)
        if not rows and scheduled <= now and rules.is_missed(scheduled, now):
            return item("perdido", "programa fechado no horário")
        return item("agendado")


def _content(d: Dispatch, now: datetime, part: Part | None) -> tuple[str, str, list[Path]]:
    """Assunto, texto e anexos de um envio. Com print, cada parte leva a sua imagem e a sua legenda."""
    if part is not None:
        return part.subject, part.text, [part.image]
    return rules.render(d.subject, now, d.files), rules.render(d.message, now, d.files), [Path(f) for f in d.files]
