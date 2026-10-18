import smtplib
from pathlib import Path

import pytest

from pombo.channels import SendError, Target
from pombo.channels.email import EmailChannel
from pombo.models import Settings


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail_with: Exception | None = None

    def __init__(self, host, port, **kwargs):
        self.host, self.port = host, port
        self.started_tls = False
        self.logged = None
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, **kwargs):
        self.started_tls = True

    def login(self, user, password):
        self.logged = (user, password)

    def send_message(self, msg, from_addr=None, to_addrs=None):
        if FakeSMTP.fail_with:
            raise FakeSMTP.fail_with
        self.sent.append((msg, to_addrs))


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail_with = None
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)


def settings(**kw) -> Settings:
    base = dict(smtp_host="mail.exemplo.com.br", smtp_port=465, smtp_user="kayo@exemplo.com.br")
    base.update(kw)
    return Settings(**base)


def channel(**kw) -> EmailChannel:
    s = settings(**kw)
    return EmailChannel(lambda: s, lambda user: "segredo")


def files(tmp_path, *names, size=10) -> list[Path]:
    out = []
    for n in names:
        p = tmp_path / n
        p.write_bytes(b"x" * size)
        out.append(p)
    return out


TARGET = Target(channel="email", label="Gestão", addresses=("a@exemplo.com.br", "b@exemplo.com.br"))


def test_sends_one_message_with_all_attachments_bcc(tmp_path):
    ch = channel()
    ch.send(TARGET, "Vendas 19/10", "Boa noite!", files(tmp_path, "Vendas.xlsx", "Plano.xlsx"), use_bcc=True)
    [smtp] = FakeSMTP.instances
    [(msg, to_addrs)] = smtp.sent
    assert msg["To"] == "kayo@exemplo.com.br"
    assert "a@exemplo.com.br" not in str(msg)  # ninguém vê a lista
    assert set(to_addrs) == {"a@exemplo.com.br", "b@exemplo.com.br"}
    assert len(list(msg.iter_attachments())) == 2
    assert smtp.logged == ("kayo@exemplo.com.br", "segredo")


def test_to_header_when_not_bcc(tmp_path):
    channel().send(TARGET, "s", "m", files(tmp_path, "Vendas.xlsx"), use_bcc=False)
    [(msg, _)] = FakeSMTP.instances[0].sent
    assert msg["To"] == "a@exemplo.com.br, b@exemplo.com.br"


def test_accented_attachment_filename(tmp_path):
    # Review Focus 4
    channel().send(TARGET, "s", "m", files(tmp_path, "(DADOS) - 8081 - Descrição.xlsx"))
    [(msg, _)] = FakeSMTP.instances[0].sent
    [part] = list(msg.iter_attachments())
    assert part.get_filename() == "(DADOS) - 8081 - Descrição.xlsx"
    assert part.get_content_type() == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_over_size_limit_raises_send_error(tmp_path):
    big = files(tmp_path, "a.xlsx", "b.xlsx", size=11 * 1024 * 1024)
    with pytest.raises(SendError, match="maior que 20 MB"):
        channel().send(TARGET, "s", "m", big)
    assert FakeSMTP.instances == []


def test_starttls_path(tmp_path):
    channel(smtp_security="starttls", smtp_port=587).send(TARGET, "s", "m", files(tmp_path, "a.xlsx"))
    assert FakeSMTP.instances[0].started_tls


@pytest.mark.parametrize("error", [OSError("rede"), smtplib.SMTPAuthenticationError(535, b"senha")])
def test_network_error_becomes_send_error(tmp_path, error):
    FakeSMTP.fail_with = error
    with pytest.raises(SendError):
        channel().send(TARGET, "s", "m", files(tmp_path, "a.xlsx"))


def test_missing_password_is_send_error(tmp_path):
    s = settings()
    ch = EmailChannel(lambda: s, lambda user: None)
    with pytest.raises(SendError, match="senha do e-mail não configurada"):
        ch.send(TARGET, "s", "m", files(tmp_path, "a.xlsx"))
