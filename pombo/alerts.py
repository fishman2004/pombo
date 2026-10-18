"""Avisos para o próprio analista: notificação do Windows + e-mail para si mesmo."""

import logging
from typing import Callable

from .channels import Target
from .models import Settings

log = logging.getLogger(__name__)


def windows_toast(title: str, body: str) -> None:
    from win11toast import notify

    notify(title, body, app_id="Pombo")


class UserAlerts:
    def __init__(self, settings_getter: Callable[[], Settings], email, toast: Callable[[str, str], None] = windows_toast):
        self._settings = settings_getter
        self._email = email
        self._toast = toast

    def notify(self, title: str, body: str) -> None:
        # cada meio de aviso falha sozinho: um não impede o outro
        try:
            self._toast(title, body)
        except Exception:
            log.exception("falha na notificação do Windows")
        me = self._settings().self_email
        if me and self._email is not None:
            try:
                self._email.send(Target("email", "Eu", (me,)), title, body, [], use_bcc=False)
            except Exception:
                log.exception("falha ao enviar aviso por e-mail")
