"""Canal de e-mail via SMTP (biblioteca padrão do Python)."""

import mimetypes
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from typing import Callable

from ..models import Settings
from . import SendError, Target

mimetypes.add_type("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".xlsx")


class EmailChannel:
    name = "email"

    def __init__(self, settings_getter: Callable[[], Settings], password_getter: Callable[[str], str | None]) -> None:
        # lê as configurações a cada envio: mudou na tela, vale na hora
        self._settings = settings_getter
        self._password = password_getter

    def send(self, target: Target, subject: str, message: str, files: list[Path], use_bcc: bool = True) -> None:
        s = self._settings()
        total = sum(Path(f).stat().st_size for f in files)
        if total > s.max_email_mb * 1024 * 1024:
            raise SendError(f"anexos somam {total / 1024 / 1024:.1f} MB, maior que {s.max_email_mb} MB")
        password = self._password(s.smtp_user)
        if not password:
            raise SendError("senha do e-mail não configurada")

        msg = EmailMessage()
        msg["From"] = s.smtp_user
        # em cópia oculta, o "Para" é o próprio remetente e ninguém vê a lista
        msg["To"] = s.smtp_user if use_bcc else ", ".join(target.addresses)
        msg["Subject"] = subject
        msg.set_content(message)
        for f in files:
            path = Path(f)
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            maintype, subtype = ctype.split("/", 1)
            msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)

        try:
            context = ssl.create_default_context()
            if s.smtp_security == "ssl":
                server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=context, timeout=60)
            else:
                server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=60)
                server.starttls(context=context)
            with server:
                server.login(s.smtp_user, password)
                server.send_message(msg, from_addr=s.smtp_user, to_addrs=list(target.addresses))
        except (OSError, smtplib.SMTPException) as exc:
            raise SendError(f"{type(exc).__name__}: {exc}") from exc
