"""As telas do Pombo: um site local, aberto só neste PC (127.0.0.1)."""

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..store import Store

HERE = Path(__file__).parent
WEEKDAYS = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def state_label(i) -> str:
    return {
        "agendado": "○ agendado",
        "esperando": "⏳ esperando atualização",
        "enviado": f"✔ enviado {i.detail}",
        "parcial": f"◐ enviado {i.sent} de {i.total}",
        "falhou": "✖ falhou",
        "desistiu": "⏳ não atualizado",
        "perdido": "⚠ perdido",
    }[i.state]


def create_app(
    engine,
    store: Store,
    whatsapp,
    today: Callable[[], date] = date.today,
    history=None,
    project_dir: Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Pombo", docs_url=None, redoc_url=None)
    app.state.history_locked = False
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["state_label"] = state_label
    templates.env.globals["WEEKDAYS"] = WEEKDAYS

    def page(request: Request, name: str, status_code: int = 200, **ctx) -> HTMLResponse:
        reg = store.load()
        banners = []
        if reg.settings.demo_mode:
            banners.append(("info", "Modo demonstração: nada é enviado de verdade, só registrado no histórico.", None))
        if whatsapp is not None and whatsapp.status() != "conectado":
            banners.append(("alerta", "WhatsApp desconectado.", ("/configuracoes#whatsapp", "Reconectar")))
        if app.state.history_locked:
            banners.append(("alerta", "Histórico travado (aberto no Excel?). Os envios esperam até ele liberar.", None))
        return templates.TemplateResponse(
            request, name, {"banners": banners, "settings": reg.settings, **ctx}, status_code=status_code
        )

    @app.get("/", response_class=HTMLResponse)
    def hoje(request: Request):
        d = today()
        return page(
            request, "hoje.html", active="hoje", day=d,
            items=engine.timeline(d), tomorrow=engine.timeline(d + timedelta(days=1)),
        )

    @app.post("/envios/{dispatch_id}/enviar-agora")
    def enviar_agora(dispatch_id: str, scheduled: str = Form("")):
        engine.send_now(dispatch_id, datetime.fromisoformat(scheduled) if scheduled else None)
        return RedirectResponse("/", status_code=303)

    app.state.page = page
    app.state.templates = templates
    return app
