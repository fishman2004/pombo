"""Peças falsas para testar o motor sem relógio, rede ou WhatsApp de verdade."""

from datetime import datetime

from pombo.channels import ChannelUnavailable, SendError


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeChannel:
    def __init__(self, name: str, fail: bool = False, unavailable: bool = False, crash: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.unavailable = unavailable
        self.crash = crash
        self.calls: list[tuple] = []

    def send(self, target, subject, message, files, use_bcc=True):
        if self.unavailable:
            raise ChannelUnavailable(f"{self.name} desconectado")
        self.calls.append((target.label, subject, message, [f.name for f in files]))
        if self.crash:
            raise RuntimeError("erro inesperado")
        if self.fail:
            raise SendError("servidor recusou")


class FakeAlerts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> None:
        self.calls.append((title, body))
