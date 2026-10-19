from datetime import date, datetime, time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pombo.web.app as web
from pombo.history import History, Row
from pombo.models import Contact, Dispatch, EmailList, Registry, Schedule, Settings, WhatsAppGroup
from pombo.store import Store
from webfakes import FakeEngine, FakeWhatsApp

TODAY = date(2026, 10, 19)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    store = Store(tmp_path / "cadastro.json")
    store.save(Registry(
        contacts=[Contact(id="c1", name="Ana", email="ana@exemplo.com"), Contact(id="c2", name="Bia", whatsapp="5583988887777")],
        email_lists=[EmailList(id="l1", name="Gestão", contact_ids=["c1"])],
        whatsapp_groups=[WhatsAppGroup(id="123@g.us", name="Comercial")],
        dispatches=[Dispatch(id="d1", name="Vendas Diárias", files=[Path("V.xlsx")], email_contact_ids=["c1"],
                             whatsapp_group_ids=["123@g.us"], schedule=Schedule(weekdays={0}, times=[time(18)]),
                             subject="s", message="m")],
    ))
    history = History(tmp_path / "hist", "Kayo", tmp_path / "pend.csv")
    history.load(TODAY)
    wa = FakeWhatsApp(groups=[WhatsAppGroup(id="999@g.us", name="Diretoria")])
    app = web.create_app(FakeEngine(), store, wa, today=lambda: TODAY, history=history, project_dir=Path(r"C:\Pombo"))
    return TestClient(app, base_url="http://127.0.0.1:8765"), store, history, wa, tmp_path


def test_contact_phone_normalized(env):
    c, store, *_ = env
    c.post("/contatos", data={"id": "", "name": "Gestor", "email": "", "whatsapp": "(83) 99999-0000"})
    gestor = next(x for x in store.load().contacts if x.name == "Gestor")
    assert gestor.whatsapp == "5583999990000"


def test_contact_needs_email_or_whatsapp(env):
    c, *_ = env
    r = c.post("/contatos", data={"id": "", "name": "Sem nada", "email": "", "whatsapp": ""})
    assert r.status_code == 422 and "Informe e-mail ou WhatsApp" in r.text


def test_delete_contact_in_use_is_blocked(env):
    c, store, *_ = env
    r = c.post("/contatos/c1/excluir")
    assert r.status_code == 422 and "Usado em: Vendas Diárias" in r.text
    assert any(x.id == "c1" for x in store.load().contacts)


def test_delete_unused_contact(env):
    c, store, *_ = env
    c.post("/contatos/c2/excluir")
    assert all(x.id != "c2" for x in store.load().contacts)


def test_email_list_create(env):
    c, store, *_ = env
    c.post("/listas", data={"id": "", "name": "Supervisores", "contact_ids": ["c1"]})
    assert any(lst.name == "Supervisores" and lst.contact_ids == ["c1"] for lst in store.load().email_lists)


def test_refresh_groups_keeps_ones_in_use(env):
    c, store, *_ = env
    c.post("/grupos/atualizar")
    names = {g.name for g in store.load().whatsapp_groups}
    assert names == {"Diretoria", "Comercial"}  # "Comercial" some do WhatsApp, mas é usado em um envio


def test_refresh_groups_when_disconnected(env):
    c, _, _, wa, _ = env
    wa._status = "desconectado"
    from pombo.channels import ChannelUnavailable

    def down():
        raise ChannelUnavailable("WhatsApp desconectado")

    wa.list_groups = down
    r = c.post("/grupos/atualizar")
    assert "WhatsApp desconectado" in r.text


def test_history_filters(env):
    c, _, history, *_ = env
    history.append(Row(datetime(2026, 10, 19, 18, 2), "Kayo", "Vendas Diárias", "2026-10-19 18:00", "email", "Gestão", "V.xlsx", "enviado", "", "d1"))
    history.append(Row(datetime(2026, 10, 19, 18, 3), "Kayo", "Vendas Diárias", "2026-10-19 18:00", "whatsapp", "Comercial", "V.xlsx", "falhou", "timeout", "d1"))
    html = c.get("/historico").text
    assert "Gestão" in html and "Comercial" in html
    html = c.get("/historico?status=falhou").text
    assert "Comercial" in html and "Gestão" not in html


def test_save_settings_uses_keyring_not_file(env, monkeypatch):
    c, store, _, _, tmp_path = env
    saved = {}
    monkeypatch.setattr(web.keyring, "set_password", lambda svc, user, pwd: saved.update({(svc, user): pwd}))
    (tmp_path / "rede").mkdir()
    r = c.post("/configuracoes", data={
        "analyst_name": "Kayo", "smtp_host": "mail.exemplo.com.br", "smtp_port": "465", "smtp_security": "ssl",
        "smtp_user": "kayo@exemplo.com.br", "smtp_password": "segredo123", "self_email": "kayo@exemplo.com.br",
        "self_whatsapp": "83 99999-0000", "history_dir": str(tmp_path / "rede"), "max_email_mb": "20",
        "start_with_windows": "on",
    })
    assert r.status_code == 200
    assert saved == {("pombo", "kayo@exemplo.com.br"): "segredo123"}
    assert "segredo123" not in (tmp_path / "cadastro.json").read_text(encoding="utf-8")
    s = store.load().settings
    assert s.smtp_host == "mail.exemplo.com.br" and s.self_whatsapp == "5583999990000" and not s.demo_mode
    assert (tmp_path / "appdata" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Pombo.cmd").exists()


def test_settings_bad_history_dir(env):
    c, *_ = env
    r = c.post("/configuracoes", data={"analyst_name": "Kayo", "smtp_port": "465", "smtp_security": "ssl",
                                       "history_dir": r"Z:\nao\existe", "max_email_mb": "20"})
    assert r.status_code == 422 and "Pasta do histórico não existe" in r.text


def test_qr_png(env):
    c, _, _, wa, _ = env
    assert c.get("/whatsapp/qr.png").status_code == 404
    wa._status = "aguardando_qr"
    assert c.get("/whatsapp/qr.png").content.startswith(b"\x89PNG")


def test_config_sem_refresh_da_pagina_inteira(env):
    c, _, _, wa, _ = env
    wa._status = "aguardando_qr"
    html = c.get("/configuracoes").text
    assert 'http-equiv="refresh"' not in html
    assert "/whatsapp/status" in html


def test_whatsapp_status(env):
    c, _, _, wa, _ = env
    wa._status = "aguardando_qr"
    assert c.get("/whatsapp/status").json() == {"status": "aguardando_qr"}
    wa._status = "conectado"
    assert c.get("/whatsapp/status").json() == {"status": "conectado"}
