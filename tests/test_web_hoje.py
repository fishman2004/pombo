from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient

from pombo.models import Registry, Settings
from pombo.store import Store
from pombo.web.app import create_app
from webfakes import FakeEngine, FakeWhatsApp, item

TODAY = date(2026, 10, 19)


def client(tmp_path, items=None, demo=False, wa_status="conectado"):
    store = Store(tmp_path / "cadastro.json")
    store.save(Registry(settings=Settings(demo_mode=demo)))
    engine = FakeEngine(items or {})
    app = create_app(engine, store, FakeWhatsApp(wa_status), today=lambda: TODAY)
    return TestClient(app, base_url="http://127.0.0.1:8765"), engine


def test_timeline_shows_items(tmp_path):
    c, _ = client(tmp_path, {TODAY: [item(18, 0, "enviado", "18:02", 2, 2)]})
    html = c.get("/").text
    assert "18:00" in html and "Vendas Diárias" in html and "✔ enviado 18:02" in html


def test_gave_up_offers_send_anyway(tmp_path):
    c, _ = client(tmp_path, {TODAY: [item(18, 0, "desistiu", "Vendas.xlsx: não atualizado hoje")]})
    html = c.get("/").text
    assert "Enviar mesmo assim" in html and "não atualizado" in html


def test_partial_shows_counts_and_retry(tmp_path):
    c, _ = client(tmp_path, {TODAY: [item(14, 0, "parcial", "timeout", 1, 2)]})
    html = c.get("/").text
    assert "enviado 1 de 2" in html and "Tentar de novo" in html


def test_send_now_posts_to_engine(tmp_path):
    c, engine = client(tmp_path)
    r = c.post("/envios/d1/enviar-agora", data={"scheduled": "2026-10-19T18:00"}, follow_redirects=False)
    assert r.status_code == 303
    assert engine.sent_now == [("d1", datetime(2026, 10, 19, 18, 0))]


def test_demo_banner(tmp_path):
    c, _ = client(tmp_path, demo=True)
    assert "Modo demonstração" in c.get("/").text


def test_whatsapp_disconnected_banner_links_to_qr(tmp_path):
    c, _ = client(tmp_path, wa_status="desconectado")
    html = c.get("/").text
    assert "WhatsApp desconectado" in html and 'href="/configuracoes#whatsapp"' in html


def test_history_locked_banner(tmp_path):
    c, _ = client(tmp_path)
    c.app.state.history_locked = True
    assert "Histórico travado" in c.get("/").text


def test_tomorrow_block(tmp_path):
    c, _ = client(tmp_path, {date(2026, 10, 20): [item(18, 0, "agendado", day=datetime(2026, 10, 20))]})
    html = c.get("/").text
    assert "Amanhã" in html and "○ agendado" in html


def test_cross_site_post_rejected(tmp_path):
    c, engine = client(tmp_path)
    r = c.post("/envios/d1/enviar-agora", headers={"Origin": "https://site-malicioso.com"})
    assert r.status_code == 403 and engine.sent_now == []


def test_foreign_host_rejected(tmp_path):
    c, _ = client(tmp_path)
    assert c.get("/", headers={"Host": "rebind.exemplo.com"}).status_code == 400
