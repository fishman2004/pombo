"""As telas do Pombo: um site local, aberto só neste PC (127.0.0.1)."""

import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Callable

from urllib.parse import urlsplit

import keyring
from fastapi import FastAPI, Form, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..channels import Target
from ..channels.email import EmailChannel
from ..channels.whatsapp import normalize_phone
from ..files import inspect
from ..models import Contact, Dispatch, EmailList, Schedule, Settings
from ..store import Store, new_id
from ..winsys import set_start_with_windows

HERE = Path(__file__).parent
ALLOWED_HOSTS = ("127.0.0.1", "localhost")
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

    # outro site aberto no navegador não pode mandar formulários para o Pombo (CSRF),
    # nem ler as telas trocando o DNS (DNS rebinding)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(ALLOWED_HOSTS))

    @app.middleware("http")
    async def same_origin_only(request: Request, call_next):
        if request.method == "POST":
            source = request.headers.get("origin") or request.headers.get("referer")
            if source and urlsplit(source).hostname not in ALLOWED_HOSTS:
                return Response("Origem não permitida.", status_code=403)
        return await call_next(request)
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

    # ---------- Contatos, listas e grupos ----------

    def used_in(reg, kind: str, item_id: str) -> list[str]:
        fields = {
            "contact": ("email_contact_ids", "whatsapp_contact_ids"),
            "list": ("email_list_ids",),
            "group": ("whatsapp_group_ids",),
        }[kind]
        return [d.name for d in reg.dispatches if any(item_id in getattr(d, f) for f in fields)]

    def contatos_page(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
        return page(request, "contatos.html", status_code, active="contatos", reg=store.load(), **ctx)

    @app.get("/contatos", response_class=HTMLResponse)
    def contatos(request: Request):
        return contatos_page(request)

    @app.post("/contatos")
    def contato_salvar(request: Request, id: str = Form(""), name: str = Form(""), email: str = Form(""),
                       whatsapp: str = Form("")):
        name, email, whatsapp = name.strip(), email.strip(), whatsapp.strip()
        errors = []
        if not name:
            errors.append("Dê um nome ao contato.")
        if not email and not whatsapp:
            errors.append("Informe e-mail ou WhatsApp.")
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            errors.append(f"E-mail inválido: {email}")
        if errors:
            return contatos_page(request, 422, errors=errors)
        reg = store.load()
        c = Contact(id=id or new_id(), name=name, email=email or None,
                    whatsapp=normalize_phone(whatsapp) if whatsapp else None)
        reg.contacts = [x for x in reg.contacts if x.id != c.id] + [c]
        store.save(reg)
        return RedirectResponse("/contatos", status_code=303)

    @app.post("/contatos/{contact_id}/excluir")
    def contato_excluir(request: Request, contact_id: str):
        reg = store.load()
        if users := used_in(reg, "contact", contact_id):
            return contatos_page(request, 422, errors=[f"Usado em: {', '.join(users)}. Tire dos envios antes de excluir."])
        reg.contacts = [x for x in reg.contacts if x.id != contact_id]
        for lst in reg.email_lists:
            lst.contact_ids = [c for c in lst.contact_ids if c != contact_id]
        store.save(reg)
        return RedirectResponse("/contatos", status_code=303)

    @app.post("/listas")
    async def lista_salvar(request: Request):
        f = await request.form()
        name = f.get("name", "").strip()
        if not name:
            return contatos_page(request, 422, errors=["Dê um nome à lista."])
        reg = store.load()
        lst = EmailList(id=f.get("id") or new_id(), name=name, contact_ids=f.getlist("contact_ids"))
        reg.email_lists = [x for x in reg.email_lists if x.id != lst.id] + [lst]
        store.save(reg)
        return RedirectResponse("/contatos", status_code=303)

    @app.post("/listas/{list_id}/excluir")
    def lista_excluir(request: Request, list_id: str):
        reg = store.load()
        if users := used_in(reg, "list", list_id):
            return contatos_page(request, 422, errors=[f"Usado em: {', '.join(users)}. Tire dos envios antes de excluir."])
        reg.email_lists = [x for x in reg.email_lists if x.id != list_id]
        store.save(reg)
        return RedirectResponse("/contatos", status_code=303)

    @app.post("/grupos/atualizar")
    def grupos_atualizar(request: Request):
        try:
            fetched = whatsapp.list_groups()
        except Exception as exc:
            return contatos_page(request, 200, errors=[f"Não consegui buscar os grupos: {exc}"])
        reg = store.load()
        ids = {g.id for g in fetched}
        # grupo que sumiu mas está em uso fica, para não quebrar um envio em silêncio
        kept = [g for g in reg.whatsapp_groups if g.id not in ids and used_in(reg, "group", g.id)]
        reg.whatsapp_groups = sorted(fetched + kept, key=lambda g: g.name.lower())
        store.save(reg)
        return RedirectResponse("/contatos", status_code=303)

    @app.post("/grupos/{group_id}/excluir")
    def grupo_excluir(request: Request, group_id: str):
        reg = store.load()
        if users := used_in(reg, "group", group_id):
            return contatos_page(request, 422, errors=[f"Usado em: {', '.join(users)}. Tire dos envios antes de excluir."])
        reg.whatsapp_groups = [x for x in reg.whatsapp_groups if x.id != group_id]
        store.save(reg)
        return RedirectResponse("/contatos", status_code=303)

    # ---------- Histórico ----------

    @app.get("/historico", response_class=HTMLResponse)
    def historico(request: Request, de: str = "", ate: str = "", envio: str = "", canal: str = "", status: str = ""):
        end = date.fromisoformat(ate) if ate else today()
        start = date.fromisoformat(de) if de else end - timedelta(days=6)
        rows = history.rows_between(start, end) if history is not None else []
        rows = [r for r in rows if (not envio or r.dispatch_id == envio) and (not canal or r.channel == canal)
                and (not status or r.status == status)]
        rows.sort(key=lambda r: r.when, reverse=True)
        return page(request, "historico.html", active="historico", rows=rows, start=start, end=end,
                    f={"envio": envio, "canal": canal, "status": status}, reg=store.load())

    # ---------- Configurações ----------

    def config_page(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
        wa_status = whatsapp.status() if whatsapp is not None else "desconectado"
        return page(request, "configuracoes.html", status_code, active="configuracoes", wa_status=wa_status, **ctx)

    @app.get("/configuracoes", response_class=HTMLResponse)
    def configuracoes(request: Request):
        return config_page(request)

    @app.post("/configuracoes", response_class=HTMLResponse)
    async def configuracoes_salvar(request: Request):
        f = await request.form()
        errors = []
        history_dir = f.get("history_dir", "").strip().strip('"')
        if history_dir:
            p = Path(history_dir)
            if not p.is_dir():
                errors.append(f"Pasta do histórico não existe: {history_dir}")
            else:
                try:
                    probe = p / ".pombo-teste"
                    probe.write_text("ok")
                    probe.unlink()
                except OSError:
                    errors.append(f"Sem permissão para gravar na pasta do histórico: {history_dir}")
        try:
            port = int(f.get("smtp_port") or 465)
            max_mb = int(f.get("max_email_mb") or 20)
        except ValueError:
            errors.append("Porta e limite de anexos precisam ser números.")
            port, max_mb = 465, 20
        if errors:
            return config_page(request, 422, errors=errors)

        reg = store.load()
        old_history = reg.settings.history_dir
        reg.settings = Settings(
            analyst_name=f.get("analyst_name", "").strip(),
            smtp_host=f.get("smtp_host", "").strip(),
            smtp_port=port,
            smtp_security="starttls" if f.get("smtp_security") == "starttls" else "ssl",
            smtp_user=f.get("smtp_user", "").strip(),
            self_email=f.get("self_email", "").strip(),
            self_whatsapp=normalize_phone(f.get("self_whatsapp", "")) if f.get("self_whatsapp", "").strip() else "",
            history_dir=Path(history_dir) if history_dir else None,
            max_email_mb=max_mb,
            demo_mode="demo_mode" in f,
            start_with_windows="start_with_windows" in f,
        )
        store.save(reg)
        password = f.get("smtp_password", "")
        if password and reg.settings.smtp_user:
            keyring.set_password("pombo", reg.settings.smtp_user, password)
        if project_dir is not None:
            set_start_with_windows(reg.settings.start_with_windows, project_dir)
        notes = ["Configurações salvas."]
        if old_history != reg.settings.history_dir:
            notes.append("A nova pasta do histórico vale depois de fechar e abrir o Pombo.")
        return config_page(request, notes=notes)

    @app.post("/configuracoes/testar-email", response_class=HTMLResponse)
    def configuracoes_testar_email(request: Request):
        s = store.load().settings
        if not s.self_email:
            return config_page(request, errors=["Preencha \"Seu e-mail\" para receber o teste."])
        channel = EmailChannel(lambda: store.load().settings, lambda user: keyring.get_password("pombo", user))
        try:
            channel.send(Target("email", "Eu", (s.self_email,)), "Pombo: teste de e-mail",
                         "Se você recebeu isto, o Pombo consegue enviar e-mails.", [], use_bcc=False)
        except Exception as exc:
            return config_page(request, errors=[f"O teste falhou: {exc}"])
        return config_page(request, notes=[f"E-mail de teste enviado para {s.self_email}."])

    @app.get("/whatsapp/status")
    def whatsapp_status():
        status = whatsapp.status() if whatsapp is not None else "desconectado"
        return JSONResponse({"status": status}, headers={"Cache-Control": "no-store"})

    @app.get("/whatsapp/qr.png")
    def whatsapp_qr():
        png = whatsapp.qr_png() if whatsapp is not None else None
        if not png:
            return Response(status_code=404)
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})

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
