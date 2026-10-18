from datetime import date, time
from pathlib import Path

from fastapi.testclient import TestClient

from pombo.models import Contact, EmailList, Registry, Settings, WhatsAppGroup
from pombo.store import Store
from pombo.web.app import create_app
from webfakes import FakeEngine, FakeWhatsApp


def setup(tmp_path):
    store = Store(tmp_path / "cadastro.json")
    store.save(Registry(
        settings=Settings(),
        contacts=[Contact(id="c1", name="Ana", email="ana@exemplo.com", whatsapp="5583999990000")],
        email_lists=[EmailList(id="l1", name="Gestão", contact_ids=["c1"])],
        whatsapp_groups=[WhatsAppGroup(id="123@g.us", name="Comercial")],
    ))
    engine = FakeEngine()
    c = TestClient(create_app(engine, store, FakeWhatsApp(), today=lambda: date(2026, 10, 19)))
    return c, store, engine


def form(tmp_path, **overrides):
    f = tmp_path / "Vendas.xlsx"
    f.write_bytes(b"x")
    data = {
        "id": "", "name": "Vendas Diárias", "files": str(f), "email_list_ids": ["l1"],
        "whatsapp_group_ids": ["123@g.us"], "weekdays": ["0", "1", "2", "3", "4"],
        "times": "18:00, 14:00", "subject": "Vendas {data}", "message": "{saudacao}! Segue o relatório.",
        "use_bcc": "on", "check_freshness": "on", "active": "on",
    }
    data.update(overrides)
    return data


def test_create_and_list(tmp_path):
    c, store, _ = setup(tmp_path)
    r = c.post("/envios", data=form(tmp_path), follow_redirects=False)
    assert r.status_code == 303
    [d] = store.load().dispatches
    assert d.name == "Vendas Diárias" and d.schedule.weekdays == {0, 1, 2, 3, 4}
    assert d.schedule.times == [time(14, 0), time(18, 0)]
    assert d.email_list_ids == ["l1"] and d.whatsapp_group_ids == ["123@g.us"] and d.use_bcc and d.active
    assert "Vendas Diárias" in c.get("/envios").text


def test_edit_keeps_id_and_unchecked_boxes_turn_off(tmp_path):
    c, store, _ = setup(tmp_path)
    c.post("/envios", data=form(tmp_path))
    d = store.load().dispatches[0]
    data = form(tmp_path, id=d.id, name="Vendas Noite")
    del data["active"]
    c.post("/envios", data=data)
    [d2] = store.load().dispatches
    assert d2.id == d.id and d2.name == "Vendas Noite" and not d2.active


def test_validation_messages(tmp_path):
    c, store, _ = setup(tmp_path)
    r = c.post("/envios", data=form(tmp_path, name="", times="25:00", files="", weekdays=[], email_list_ids=[], whatsapp_group_ids=[]))
    assert r.status_code == 422
    for msg in ["Dê um nome ao envio", "Informe pelo menos um arquivo", "Escolha pelo menos um destinatário",
                "Escolha pelo menos um dia", "Horário inválido: 25:00"]:
        assert msg in r.text
    assert store.load().dispatches == []


def test_missing_file_is_only_a_warning(tmp_path):
    c, store, _ = setup(tmp_path)
    r = c.post("/envios", data=form(tmp_path, files=r"S:\Relatorios\Nao existe.xlsx"))
    assert r.status_code == 200 and len(store.load().dispatches) == 1
    assert "não encontrado" in r.text or "inacessível" in r.text


def test_quotes_from_copy_as_path_are_removed(tmp_path):
    c, store, _ = setup(tmp_path)
    f = tmp_path / "Vendas.xlsx"
    f.write_bytes(b"x")
    c.post("/envios", data=form(tmp_path, files=f'"{f}"'))
    assert store.load().dispatches[0].files == [f]


def test_delete(tmp_path):
    c, store, _ = setup(tmp_path)
    c.post("/envios", data=form(tmp_path))
    d = store.load().dispatches[0]
    c.post(f"/envios/{d.id}/excluir")
    assert store.load().dispatches == []


def test_send_test_shows_results(tmp_path):
    c, store, engine = setup(tmp_path)
    c.post("/envios", data=form(tmp_path))
    d = store.load().dispatches[0]
    r = c.post(f"/envios/{d.id}/testar")
    assert engine.tested == [d.id]
    assert "WhatsApp desconectado" in r.text and "e-mail: ok" in r.text


def test_new_form_lists_options(tmp_path):
    c, _, _ = setup(tmp_path)
    html = c.get("/envios/novo").text
    assert "Gestão" in html and "Comercial" in html and "Ana" in html and "{saudacao}" in html
