"""Canais de envio. Todo canal tem a mesma forma, então trocar um (por exemplo,
WhatsApp Web -> API oficial da Meta) é escrever outra classe com este formato.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class Target:
    channel: str  # "email" | "whatsapp"
    label: str  # nome que aparece no histórico ("Gestão", "Grupo Comercial")
    addresses: tuple[str, ...]  # e-mails, ou um único id de WhatsApp
    key: str = ""  # identificador estável ("list:l1", "contact:c1", "group:...") que sobrevive a renomear


class SendError(Exception):
    """O envio falhou. Conta como tentativa."""


class ChannelUnavailable(SendError):
    """O canal está fora do ar (ex.: WhatsApp desconectado). Não conta como tentativa."""


class Channel(Protocol):
    name: str

    def send(self, target: Target, subject: str, message: str, files: list[Path], use_bcc: bool = True) -> None: ...
