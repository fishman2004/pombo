from pathlib import Path

import pytest

from pombo.channels import ChannelUnavailable, SendError, Target
from pombo.channels.whatsapp import WhatsAppChannel, normalize_phone


class FakeClient:
    def __init__(self, connected=True, fail=False):
        self.connected = connected
        self.fail = fail
        self.sent = []
        self.stopped = False

    def stop(self):
        self.stopped = True

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

    def send_image(self, to, data, caption):
        if self.fail:
            raise RuntimeError("timeout")
        self.sent.append((to, "imagem", caption))

    def send_text(self, to, text):
        if self.fail:
            raise RuntimeError("timeout")
        self.sent.append((to, "texto", text))


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
    assert ch.status() == "conectando"  # acabou de abrir, esperando o QR
    with pytest.raises(ChannelUnavailable):
        ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "oi", docs(tmp_path, "a.xlsx"))


def test_caption_only_on_first_and_pause_between(tmp_path):
    client = FakeClient()
    ch, sleeps = make(tmp_path, client)
    ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "Boa noite!", docs(tmp_path, "a.xlsx", "b.xlsx"))
    assert client.sent == [("123@g.us", "a.xlsx", "Boa noite!"), ("123@g.us", "b.xlsx", None)]
    assert sleeps == [3, 3]


def test_png_goes_as_photo_with_caption(tmp_path):
    client = FakeClient()
    ch, sleeps = make(tmp_path, client)
    ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "Resultado do dia", docs(tmp_path, "print.png", "a.xlsx"))
    assert client.sent == [("123@g.us", "imagem", "Resultado do dia"), ("123@g.us", "a.xlsx", None)]
    assert sleeps == [3, 3]


def test_no_files_sends_text_message(tmp_path):
    client = FakeClient()
    ch, sleeps = make(tmp_path, client)
    ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "Lembrete: PHD até 9h", [])
    assert client.sent == [("123@g.us", "texto", "Lembrete: PHD até 9h")]
    assert sleeps == [3]


def test_text_error_becomes_send_error(tmp_path):
    ch, _ = make(tmp_path, FakeClient(fail=True))
    with pytest.raises(SendError):
        ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "oi", [])


def test_phone_target_becomes_user_jid(tmp_path):
    client = FakeClient()
    ch, _ = make(tmp_path, client)
    ch.send(Target("whatsapp", "Gestor", ("5583999990000",)), "", "oi", docs(tmp_path, "a.xlsx"))
    assert client.sent[0][0] == "5583999990000@s.whatsapp.net"


def test_library_error_becomes_send_error(tmp_path):
    ch, _ = make(tmp_path, FakeClient(fail=True))
    with pytest.raises(SendError):
        ch.send(Target("whatsapp", "Comercial", ("123@g.us",)), "", "oi", docs(tmp_path, "a.xlsx"))


def test_adapter_needs_login_not_just_socket():
    # a neonize conecta no servidor antes do QR ser lido; isso não é "conectado" para o Pombo
    from types import SimpleNamespace

    from pombo.channels.whatsapp import _NeonizeClient

    adapter = object.__new__(_NeonizeClient)
    adapter._client = SimpleNamespace(is_connected=True, is_logged_in=False)
    assert adapter.is_connected() is False
    adapter._client.is_logged_in = True
    assert adapter.is_connected() is True


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


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def test_qr_vence_e_vira_desconectado(tmp_path):
    clock = Clock()
    client = FakeClient(connected=False)
    ch = WhatsAppChannel(tmp_path / "sessao", client_factory=lambda path: client, sleep=lambda s: None, clock=clock)
    ch.start()
    assert ch.status() == "conectando"
    client.on_qr(b"2@abc,def")
    assert ch.status() == "aguardando_qr"
    clock.t += 61
    assert ch.status() == "desconectado"
    assert ch.qr_png() is None


def test_sem_qr_por_muito_tempo_vira_desconectado(tmp_path):
    clock = Clock()
    ch = WhatsAppChannel(tmp_path / "sessao", client_factory=lambda path: FakeClient(connected=False),
                         sleep=lambda s: None, clock=clock)
    ch.start()
    clock.t += 31
    assert ch.status() == "desconectado"


def test_reconectar_comeca_sessao_nova(tmp_path):
    clock = Clock()
    clients, paths = [], []

    def factory(path):
        paths.append(path)
        clients.append(FakeClient(connected=False))
        return clients[-1]

    ch = WhatsAppChannel(tmp_path / "sessao", client_factory=factory, sleep=lambda s: None, clock=clock)
    ch.start()
    assert paths[0].name == "sessao.db"
    clock.t += 31
    ch.restart()
    assert clients[0].stopped
    assert len(clients) == 2 and paths[1] != paths[0]
    assert ch.status() == "conectando"
    clients[0].on_qr(b"velho")  # evento atrasado do cliente antigo é ignorado
    assert ch.status() == "conectando"
    clients[1].on_qr(b"novo")
    assert ch.status() == "aguardando_qr"


def test_reconectar_nao_mexe_quando_conectado(tmp_path):
    clients = []

    def factory(path):
        clients.append(FakeClient(connected=True))
        return clients[-1]

    ch = WhatsAppChannel(tmp_path / "sessao", client_factory=factory, sleep=lambda s: None)
    ch.start()
    ch.restart()
    assert len(clients) == 1 and not clients[0].stopped


def test_abertura_apaga_sessoes_antigas(tmp_path):
    sessao = tmp_path / "sessao"
    sessao.mkdir()
    (sessao / "atual.txt").write_text("sessao-2.db", encoding="utf-8")
    (sessao / "sessao-2.db").write_bytes(b"x")
    (sessao / "sessao.db").write_bytes(b"x")
    (sessao / "sessao-1.db-wal").write_bytes(b"x")
    ch = WhatsAppChannel(sessao, client_factory=lambda path: FakeClient(), sleep=lambda s: None)
    ch.start()
    assert sorted(f.name for f in sessao.iterdir()) == ["atual.txt", "sessao-2.db"]
