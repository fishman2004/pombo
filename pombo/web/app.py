"""As telas do Pombo: um site local, aberto só neste PC (127.0.0.1)."""

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..files import inspect
from ..models import Dispatch, Schedule
from ..store import Store, new_id

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

    # ---------- Envios ----------

    def dispatch_values(d: Dispatch | None) -> dict:
        if d is None:
            return {"id": "", "name": "", "files": "", "email_list_ids": [], "email_contact_ids": [],
                    "whatsapp_contact_ids": [], "whatsapp_group_ids": [], "weekdays": {0, 1, 2, 3, 4},
                    "times": "18:00", "subject": "{arquivos}: {data}",
                    "message": "{saudacao}! Segue o relatório atualizado em {data}.",
                    "use_bcc": True, "check_freshness": True, "active": True}
        return {**d.model_dump(), "files": "\n".join(str(f) for f in d.files),
                "times": ", ".join(t.strftime("%H:%M") for t in d.schedule.times), "weekdays": d.schedule.weekdays}

    def envio_form(request: Request, values: dict, status_code: int = 200, **ctx) -> HTMLResponse:
        reg = store.load()
        statuses = [inspect(Path(p)) for p in values["files"].splitlines() if p.strip()]
        return page(request, "envio_form.html", status_code, active="envios", v=values, reg=reg,
                    file_statuses=statuses, **ctx)

    @app.get("/envios", response_class=HTMLResponse)
    def envios(request: Request):
        reg = store.load()
        return page(request, "envios.html", active="envios", dispatches=reg.dispatches, reg=reg)

    @app.get("/envios/novo", response_class=HTMLResponse)
    def envio_novo(request: Request):
        return envio_form(request, dispatch_values(None))

    @app.get("/envios/{dispatch_id}", response_class=HTMLResponse)
    def envio_editar(request: Request, dispatch_id: str):
        d = next((x for x in store.load().dispatches if x.id == dispatch_id), None)
        if d is None:
            return RedirectResponse("/envios", status_code=303)
        return envio_form(request, dispatch_values(d))

    @app.post("/envios")
    async def envio_salvar(request: Request):
        f = await request.form()
        values = {
            "id": f.get("id", ""), "name": f.get("name", "").strip(), "files": f.get("files", ""),
            "email_list_ids": f.getlist("email_list_ids"), "email_contact_ids": f.getlist("email_contact_ids"),
            "whatsapp_contact_ids": f.getlist("whatsapp_contact_ids"),
            "whatsapp_group_ids": f.getlist("whatsapp_group_ids"),
            "weekdays": {int(x) for x in f.getlist("weekdays") if x.isdigit()},
            "times": f.get("times", ""), "subject": f.get("subject", ""), "message": f.get("message", ""),
            "use_bcc": "use_bcc" in f, "check_freshness": "check_freshness" in f, "active": "active" in f,
        }
        errors = []
        if not values["name"]:
            errors.append("Dê um nome ao envio.")
        # "Copiar como caminho" do Windows vem entre aspas
        files = [Path(p.strip().strip('"')) for p in values["files"].splitlines() if p.strip().strip('"')]
        if not files:
            errors.append("Informe pelo menos um arquivo.")
        if not any(values[k] for k in ("email_list_ids", "email_contact_ids", "whatsapp_contact_ids", "whatsapp_group_ids")):
            errors.append("Escolha pelo menos um destinatário.")
        if not values["weekdays"]:
            errors.append("Escolha pelo menos um dia.")
        times, bad = parse_times(values["times"])
        errors += [f"Horário inválido: {b}" for b in bad]
        if not times and not bad:
            errors.append("Informe pelo menos um horário.")
        if errors:
            return envio_form(request, values, 422, errors=errors)

        reg = store.load()
        d = Dispatch(
            id=values["id"] or new_id(), name=values["name"], files=files,
            email_list_ids=values["email_list_ids"], email_contact_ids=values["email_contact_ids"],
            whatsapp_contact_ids=values["whatsapp_contact_ids"], whatsapp_group_ids=values["whatsapp_group_ids"],
            schedule=Schedule(weekdays=values["weekdays"], times=times), subject=values["subject"],
            message=values["message"], use_bcc=values["use_bcc"], check_freshness=values["check_freshness"],
            active=values["active"],
        )
        reg.dispatches = [x for x in reg.dispatches if x.id != d.id] + [d]
        store.save(reg)
        warnings = [f"{s.path.name}: {s.reason}" for s in map(inspect, files) if not s.ready]
        if warnings:
            # caminho de rede fora do ar agora não impede salvar; só avisa
            return envio_form(request, dispatch_values(d), saved=True, warnings=warnings)
        return RedirectResponse("/envios", status_code=303)

    @app.post("/envios/{dispatch_id}/excluir")
    def envio_excluir(dispatch_id: str):
        reg = store.load()
        reg.dispatches = [x for x in reg.dispatches if x.id != dispatch_id]
        store.save(reg)
        return RedirectResponse("/envios", status_code=303)

    @app.post("/envios/{dispatch_id}/testar", response_class=HTMLResponse)
    def envio_testar(request: Request, dispatch_id: str):
        d = next(x for x in store.load().dispatches if x.id == dispatch_id)
        names = {"email": "e-mail", "whatsapp": "WhatsApp"}
        results = [f"{names.get(ch, ch)}: {res}" for ch, res in engine.send_test(dispatch_id)]
        return envio_form(request, dispatch_values(d), test_results=results or ["Configure seu e-mail ou WhatsApp em Configurações."])

    app.state.page = page
    app.state.templates = templates
    return app


def parse_times(text: str) -> tuple[list[time], list[str]]:
    good, bad = [], []
    for part in re.split(r"[,\s;]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d{1,2})[:h](\d{2})", part)
        if m and int(m[1]) < 24 and int(m[2]) < 60:
            good.append(time(int(m[1]), int(m[2])))
        else:
            bad.append(part)
    return sorted(set(good)), bad
