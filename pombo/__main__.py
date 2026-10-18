"""Ponto de entrada: `python -m pombo` (é o que o iniciar.bat chama)."""

import logging
import socket
import sys
import threading
import time
import webbrowser
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .engine import Engine
from .paths import data_dir

PORT = 8765
TICK_SECONDS = 30
PROJECT_DIR = Path(__file__).resolve().parent.parent
log = logging.getLogger("pombo")


def acquire_single_instance(port: int = PORT) -> socket.socket | None:
    """Reserva a porta do Pombo. Se já estiver em uso, outra cópia está aberta."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32":
        # no Windows, sem isto, dois programas conseguem ocupar a mesma porta
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        sock.bind(("127.0.0.1", port))
    except OSError:
        sock.close()
        return None
    return sock


def _setup_logging() -> None:
    handler = RotatingFileHandler(data_dir() / "pombo.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler])


def _engine_loop(engine: Engine, history, app) -> None:
    from .history import HistoryLocked

    # o motor só começa depois de ler o histórico; sem ele, poderia reenviar o que já saiu
    while True:
        try:
            history.load(date.today())
            app.state.history_locked = False
            break
        except HistoryLocked:
            app.state.history_locked = True
            log.warning("histórico travado; tentando de novo em %ss", TICK_SECONDS)
            time.sleep(TICK_SECONDS)
    while True:
        engine.tick()
        time.sleep(TICK_SECONDS)


def main() -> None:
    url = f"http://127.0.0.1:{PORT}/"
    sock = acquire_single_instance(PORT)
    if sock is None:
        webbrowser.open(url)  # já está rodando: só mostra a tela
        return

    import keyring
    import uvicorn

    from .alerts import UserAlerts
    from .channels.email import EmailChannel
    from .channels.whatsapp import WhatsAppChannel
    from .history import History
    from .store import Store
    from .web.app import create_app
    from .winsys import keep_awake

    _setup_logging()
    keep_awake()
    store = Store(data_dir() / "cadastro.json")
    settings = store.load().settings
    history = History(store.history_dir(), settings.analyst_name or "analista", data_dir() / "historico-pendente.csv")

    whatsapp = WhatsAppChannel(data_dir() / "whatsapp-sessao")
    try:
        whatsapp.start()
    except Exception:
        log.exception("não foi possível iniciar o WhatsApp")
    email = EmailChannel(lambda: store.load().settings, lambda user: keyring.get_password("pombo", user))
    alerts = UserAlerts(lambda: store.load().settings, email)
    engine = Engine(store, history, {"email": email, "whatsapp": whatsapp}, alerts)
    app = create_app(engine, store, whatsapp, history=history, project_dir=PROJECT_DIR)

    threading.Thread(target=_engine_loop, args=(engine, history, app), daemon=True, name="motor").start()
    threading.Timer(1.5, webbrowser.open, args=(url,)).start()
    log.info("Pombo iniciado em %s", url)
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


if __name__ == "__main__":
    main()
