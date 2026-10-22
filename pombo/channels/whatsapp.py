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
QR_VALID_SECONDS = 60  # o WhatsApp para de gerar códigos novos depois de ~2 min; um código parado vence
STARTING_SECONDS = 30  # tempo para o primeiro QR code aparecer depois de (re)conectar
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}  # vão como foto (aparecem na conversa), não como documento


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

    def stop(self) -> None:
        self._client.disconnect()

    def is_connected(self) -> bool:
        # conectar no servidor acontece antes do QR; só vale com a sessão logada
        return bool(self._client.is_connected and self._client.is_logged_in)

    def list_groups(self) -> list[tuple[str, str]]:
        from neonize.utils.jid import Jid2String

        return [(Jid2String(g.JID), g.GroupName.Name) for g in self._client.get_joined_groups()]

    def _jid(self, to: str):
        from neonize.utils.jid import build_jid

        user, server = to.split("@", 1)
        return self._resolve(user) if server == "s.whatsapp.net" else build_jid(user, server)

    def send_document(self, to: str, data: bytes, filename: str, caption: str | None, mimetype: str) -> None:
        self._client.send_document(self._jid(to), data, caption=caption, filename=filename, mimetype=mimetype)

    def send_image(self, to: str, data: bytes, caption: str | None) -> None:
        self._client.send_image(self._jid(to), data, caption=caption)

    def send_text(self, to: str, text: str) -> None:
        self._client.send_message(self._jid(to), text)

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
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.session_dir = Path(session_dir)
        self._factory = client_factory or _NeonizeClient
        self._sleep = sleep
        self._clock = clock
        self._client = None
        self._generation = 0  # ignora eventos atrasados de um cliente antigo
        self._qr: bytes | None = None
        self._qr_at = 0.0
        self._started_at = 0.0
        self._lock = threading.Lock()  # um envio de cada vez

    # --- sessão ---------------------------------------------------------

    def _pointer(self) -> Path:
        return self.session_dir / "atual.txt"

    def _db_path(self) -> Path:
        try:
            name = self._pointer().read_text(encoding="utf-8").strip()
        except OSError:
            name = ""
        return self.session_dir / (name or "sessao.db")

    def _new_db(self) -> None:
        """Aponta para um arquivo de sessão novo (o antigo pode estar preso pelo cliente anterior)."""
        name = f"sessao-{int(time.time())}.db"
        self._pointer().write_text(name, encoding="utf-8")

    def _cleanup_old_sessions(self) -> None:
        current = self._db_path().name
        for f in self.session_dir.glob("sessao*.db*"):
            if not f.name.startswith(current):
                try:
                    f.unlink()
                except OSError:
                    pass  # ainda em uso; sai na próxima abertura do Pombo

    def start(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_old_sessions()
        self._generation += 1
        gen = self._generation
        self._qr = None
        self._started_at = self._clock()
        self._client = self._factory(self._db_path())
        self._client.start(
            lambda data: self._on_qr(gen, data),
            lambda: self._on_connected(gen),
            lambda: self._on_disconnected(gen),
        )

    def restart(self) -> None:
        """Botão "Reconectar": derruba o cliente atual e começa de novo, com QR code novo."""
        if self.status() == "conectado":
            return
        old = self._client
        if old is not None:
            try:
                old.stop()
            except Exception:
                pass
        # sem login válido, a sessão antiga só atrapalha: começa com uma em branco
        self._new_db()
        self.start()

    def _on_qr(self, gen: int, data: bytes) -> None:
        if gen == self._generation:
            self._qr = data
            self._qr_at = self._clock()

    def _on_connected(self, gen: int) -> None:
        if gen == self._generation:
            self._qr = None

    def _on_disconnected(self, gen: int) -> None:
        if gen == self._generation:
            self._qr = None

    def status(self) -> Literal["conectado", "desconectado", "aguardando_qr", "conectando"]:
        if self._client is not None and self._client.is_connected():
            return "conectado"
        now = self._clock()
        if self._qr and now - self._qr_at < QR_VALID_SECONDS:
            return "aguardando_qr"
        if not self._qr and self._client is not None and now - self._started_at < STARTING_SECONDS:
            return "conectando"
        return "desconectado"

    def qr_png(self) -> bytes | None:
        if self.status() != "aguardando_qr":
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
            try:
                if not files:
                    # mensagem programada só com texto
                    if message.strip():
                        self._client.send_text(to, message)
                        self._sleep(PAUSE_SECONDS)
                    return
                for i, f in enumerate(files):
                    path = Path(f)
                    caption = message if i == 0 else None
                    if path.suffix.lower() in IMAGE_EXTS:
                        self._client.send_image(to, path.read_bytes(), caption)
                    else:
                        mimetype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                        self._client.send_document(to, path.read_bytes(), path.name, caption, mimetype)
                    self._sleep(PAUSE_SECONDS)
            except Exception as exc:  # a biblioteca lança tipos variados; todos viram falha de envio
                raise SendError(f"{type(exc).__name__}: {exc}") from exc
