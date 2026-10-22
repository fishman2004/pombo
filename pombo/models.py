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


class Snapshot(BaseModel):
    """Print de um pedaço da planilha + texto calculado, um por valor da coluna de divisão.

    Colunas são letras do Excel ("B", "AJ") e linhas são números, como o analista vê na planilha.
    """

    source: Path
    sheet: str = ""  # vazio = primeira aba
    header_row: int  # linha com os nomes das colunas
    columns: list[str]  # colunas fixas, na ordem em que aparecem no print
    day_columns: str = ""  # intervalo das colunas de dia ("F:AJ"); vazio = sem colunas de dia
    day_row: int = 0  # linha com o dia do mês (1..31) ou a data de cada coluna de dia
    reference: Literal["hoje", "ontem"] = "ontem"  # "ontem" = último dia de venda (segunda olha o sábado)
    hide_sundays: bool = True
    extra_columns: list[str] = Field(default_factory=list)  # depois dos dias (ex.: média)
    split_column: str = ""  # um print por valor desta coluna (ex.: supervisor); vazio = um print só
    split_values: list[str] = Field(default_factory=list)  # vazio = todos os valores, na ordem da planilha
    name_column: str = ""  # nome que aparece em {piores} e {melhores}
    metric_column: str = ""  # vazio = média dos dias mostrados até a data de referência
    threshold: float = 5  # pinta os dias e conta {acima}/{abaixo}
    worst_count: int = 5
    title: str = ""  # faixa no topo da imagem; aceita os mesmos campos da mensagem


class Dispatch(BaseModel):
    id: str
    name: str
    files: list[Path] = Field(default_factory=list)  # vazio = só texto (ou só o print)
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
    snapshot: Snapshot | None = None

    @property
    def watched_files(self) -> list[Path]:
        """Arquivos que precisam estar prontos (e atualizados) antes de enviar."""
        return list(self.files) + ([self.snapshot.source] if self.snapshot else [])


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
