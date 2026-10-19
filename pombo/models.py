"""O cadastro: contatos, listas, grupos, envios e configurações."""

from datetime import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class Contact(BaseModel):
    id: str
    name: str
    email: str | None = None
    whatsapp: str | None = None


class EmailList(BaseModel):
    id: str
    name: str
    contact_ids: list[str] = Field(default_factory=list)


class WhatsAppGroup(BaseModel):
    id: str  # identificador vindo do WhatsApp, nunca digitado à mão
    name: str


class Schedule(BaseModel):
    weekdays: set[int]  # 0 = segunda ... 6 = domingo
    times: list[time]


class Dispatch(BaseModel):
    id: str
    name: str
    files: list[Path]
    email_list_ids: list[str] = Field(default_factory=list)
    email_contact_ids: list[str] = Field(default_factory=list)
    whatsapp_contact_ids: list[str] = Field(default_factory=list)
    whatsapp_group_ids: list[str] = Field(default_factory=list)
    schedule: Schedule
    subject: str
    message: str
    use_bcc: bool = True
    check_freshness: bool = True
    active: bool = True


class Settings(BaseModel):
    analyst_name: str = ""
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_security: Literal["ssl", "starttls"] = "ssl"
    smtp_user: str = ""
    self_email: str = ""
    self_whatsapp: str = ""
    history_dir: Path | None = None
    max_email_mb: int = 20
    signature_path: Path | None = None  # imagem no fim dos e-mails (fica na pasta de dados do Pombo)
    demo_mode: bool = False
    start_with_windows: bool = True


class Registry(BaseModel):
    settings: Settings = Field(default_factory=Settings)
    contacts: list[Contact] = Field(default_factory=list)
    email_lists: list[EmailList] = Field(default_factory=list)
    whatsapp_groups: list[WhatsAppGroup] = Field(default_factory=list)
    dispatches: list[Dispatch] = Field(default_factory=list)
