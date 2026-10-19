"""Canal de WhatsApp: automatiza um número conectado como "aparelho conectado".

Usa a biblioteca neonize (ver docs/decisoes.md). Ela fica atrás de um adaptador
pequeno (_NeonizeClient) para os testes usarem um cliente falso e para a
migração à API oficial da Meta trocar só este arquivo.
"""

import io
import mimetypes
import threading
import time
from pathlib import Path
from typing import Callable, Literal

from ..models import WhatsAppGroup
from . import ChannelUnavailable, SendError, Target

PAUSE_SECONDS = 3  # pausa entre mensagens, para não parecer disparo em massa


def normalize_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    return digits if digits.startswith("55") else "55" + digits


def _jid_text(address: str) -> str:
    # grupos já vêm como "123...@g.us"; contatos são só o número
    return address if "@" in address else f"{normalize_phone(address)}@s.whatsapp.net"


class _NeonizeClient:
    """Adaptador fino sobre a neonize. Só aqui o código conhece a biblioteca."""

    def __init__(self, db_path: Path) -> None:
        from neonize.client import NewClient

        self._client = NewClient(str(db_path))

    def start(self, on_qr, on_connected, on_disconnected) -> None:
        from neonize.events import ConnectedEv, DisconnectedEv, LoggedOutEv

        self._client.event.qr(lambda _c, data: on_qr(data))
        self._client.event(ConnectedEv)(lambda _c, _e: on_connected())
        self._client.event(DisconnectedEv)(lambda _c, _e: on_disconnected())
        self._client.event(LoggedOutEv)(lambda _c, _e: on_disconnected())
        threading.Thread(target=self._client.connect, daemon=True, name="whatsapp").start()

    def is_connected(self) -> bool:
        # conectar no servidor acontece antes do QR; só vale com a sessão logada
        return bool(self._client.is_connected and self._client.is_logged_in)

    def list_groups(self) -> list[tuple[str, str]]:
        from neonize.utils.jid import Jid2String

        return [(Jid2String(g.JID), g.GroupName.Name) for g in self._client.get_joined_groups()]

    def send_document(self, to: str, data: bytes, filename: str, caption: str | None, mimetype: str) -> None:
        from neonize.utils.jid import build_jid

        user, server = to.split("@", 1)
        jid = build_jid(user, server)
        if server == "s.whatsapp.net":
            jid = self._resolve(user)
        self._client.send_document(jid, data, caption=caption, filename=filename, mimetype=mimetype)

    def _resolve(self, number: str):
        """Pergunta ao WhatsApp o endereço real. Resolve o nono dígito sozinho."""
        candidates = [number]
        # celular brasileiro com 9: tenta também sem o 9 (contas antigas)
        if number.startswith("55") and len(number) == 13 and number[4] == "9":
            candidates.append(number[:4] + number[5:])
        for candidate in candidates:
            for r in self._client.is_on_whatsapp("+" + candidate):
                if r.IsIn:
                    return r.JID
        raise RuntimeError(f"o número {number} não está no WhatsApp")


class WhatsAppChannel:
    name = "whatsapp"

    def __init__(
        self,
        session_dir: Path,
        client_factory: Callable[[Path], object] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session_dir = Path(session_dir)
        self._factory = client_factory or _NeonizeClient
        self._sleep = sleep
        self._client = None
        self._qr: bytes | None = None
        self._lock = threading.Lock()  # um envio de cada vez

    def start(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._client = self._factory(self.session_dir / "sessao.db")
        self._client.start(self._on_qr, self._on_connected, lambda: None)

    def _on_qr(self, data: bytes) -> None:
        self._qr = data

    def _on_connected(self) -> None:
        self._qr = None

    def status(self) -> Literal["conectado", "desconectado", "aguardando_qr"]:
        if self._client is not None and self._client.is_connected():
            return "conectado"
        return "aguardando_qr" if self._qr else "desconectado"

    def qr_png(self) -> bytes | None:
        if not self._qr or self.status() == "conectado":
            return None
        import segno

        buf = io.BytesIO()
        segno.make_qr(self._qr).save(buf, kind="png", scale=6, border=2)
        return buf.getvalue()

    def list_groups(self) -> list[WhatsAppGroup]:
        if self.status() != "conectado":
            raise ChannelUnavailable("WhatsApp desconectado")
        return [WhatsAppGroup(id=gid, name=name) for gid, name in self._client.list_groups()]

    def send(self, target: Target, subject: str, message: str, files: list[Path], use_bcc: bool = True) -> None:
        if self.status() != "conectado":
            raise ChannelUnavailable("WhatsApp desconectado")
        to = _jid_text(target.addresses[0])
        with self._lock:
            for i, f in enumerate(files):
                path = Path(f)
                mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                try:
                    self._client.send_document(to, path.read_bytes(), path.name, message if i == 0 else None, mimetype)
                except Exception as exc:  # a biblioteca lança tipos variados; todos viram falha de envio
                    raise SendError(f"{type(exc).__name__}: {exc}") from exc
                self._sleep(PAUSE_SECONDS)
