from pathlib import Path

import pytest

from pombo.channels import ChannelUnavailable, SendError, Target
from pombo.channels.whatsapp import WhatsAppChannel, normalize_phone


class FakeClient:
    def __init__(self, connected=True, fail=False):
        self.connected = connected
        self.fail = fail
        self.sent = []

    def start(self, on_qr, on_connected, on_disconnected):
        self.on_qr = on_qr
        if self.connected:
            on_connected()

    def is_connected(self):
        return self.connected

    def list_groups(self):
        return [("123@g.us", "Comercial")]

    def send_document(self, to, data, filename, caption, mimetype):
        if self.fail:
            raise RuntimeError("timeout")
        self.sent.append((to, filename, caption))


def make(tmp_path, client):
    sleeps = []
    ch = WhatsAppChannel(tmp_path / "sessao", client_factory=lambda path: client, sleep=sleeps.append)
    ch.start()
    return ch, sleeps


def docs(tmp_path, *names):
    out = []
    for n in names:
        p = tmp_path / n
        p.write_bytes(b"x")
        out.append(p)
    return out


@pytest.mark.parametrize(
    "raw, expected",
    [("(83) 99999-0000", "5583999990000"), ("5583999990000", "5583999990000"), ("+55 83 9 9999-0000", "5583999990000")],
)
def test_normalize_phone(raw, expected):
    assert normalize_phone(raw) == expected


def test_disconnected_raises_unavailable(tmp_path):
    ch, _ = make(tmp_path, FakeClient(connected=False))
    assert ch.status() == "desconectado"
    with pytest.raises(ChannelUnavailable):
        ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "oi", docs(tmp_path, "a.xlsx"))


def test_caption_only_on_first_and_pause_between(tmp_path):
    client = FakeClient()
    ch, sleeps = make(tmp_path, client)
    ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "Boa noite!", docs(tmp_path, "a.xlsx", "b.xlsx"))
    assert client.sent == [("123@g.us", "a.xlsx", "Boa noite!"), ("123@g.us", "b.xlsx", None)]
    assert sleeps == [3, 3]


def test_phone_target_becomes_user_jid(tmp_path):
    client = FakeClient()
    ch, _ = make(tmp_path, client)
    ch.send(Target("whatsapp", "Gestor", ("5583999990000",)), "", "oi", docs(tmp_path, "a.xlsx"))
    assert client.sent[0][0] == "5583999990000@s.whatsapp.net"


def test_library_error_becomes_send_error(tmp_path):
    ch, _ = make(tmp_path, FakeClient(fail=True))
    with pytest.raises(SendError):
        ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "oi", docs(tmp_path, "a.xlsx"))


def test_list_groups_and_qr(tmp_path):
    client = FakeClient(connected=False)
    ch, _ = make(tmp_path, client)
    assert ch.qr_png() is None
    client.on_qr(b"2@abc,def")
    assert ch.status() == "aguardando_qr"
    assert ch.qr_png().startswith(b"\x89PNG")
    with pytest.raises(ChannelUnavailable):
        ch.list_groups()
    client.connected = True
    assert ch.status() == "conectado" and ch.qr_png() is None
    [g] = ch.list_groups()
    assert (g.id, g.name) == ("123@g.us", "Comercial")
