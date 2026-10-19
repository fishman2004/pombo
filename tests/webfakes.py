"""Peças falsas para testar as telas."""

from datetime import datetime

from pombo.engine import TimelineItem


class FakeEngine:
    def __init__(self, items_by_day=None):
        self.items_by_day = items_by_day or {}
        self.sent_now = []
        self.tested = []

    def timeline(self, day):
        return self.items_by_day.get(day, [])

    def send_now(self, dispatch_id, scheduled=None):
        self.sent_now.append((dispatch_id, scheduled))

    def send_test(self, dispatch_id):
        self.tested.append(dispatch_id)
        return [("email", "ok"), ("whatsapp", "WhatsApp desconectado")]


class FakeWhatsApp:
    def __init__(self, status="conectado", groups=None):
        self._status = status
        self.groups = groups or []
        self.restarts = 0

    def status(self):
        return self._status

    def qr_png(self):
        return b"\x89PNG-fake" if self._status == "aguardando_qr" else None

    def list_groups(self):
        return self.groups

    def restart(self):
        self.restarts += 1
        self._status = "conectando"


def item(h, m, state, detail="", sent=0, total=2, name="Vendas Diárias", dispatch_id="d1", day=None, manual=False):
    day = day or datetime(2026, 10, 19)
    return TimelineItem(day.replace(hour=h, minute=m), dispatch_id, name, state, detail, sent, total, manual)
