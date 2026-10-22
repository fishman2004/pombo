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
    c = TestClient(create_app(engine, store, FakeWhatsApp(), today=lambda: date(2026, 10, 19)), base_url="http://127.0.0.1:8765")
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
    r = c.post("/envios", data=form(tmp_path, name="", times="25:00", files="", message="", weekdays=[], email_list_ids=[], whatsapp_group_ids=[]))
    assert r.status_code == 422
    for msg in ["Dê um nome ao envio", "Sem arquivo, o envio manda só o texto", "Escolha pelo menos um destinatário",
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


def snapshot_form(tmp_path, **overrides):
    planilha = tmp_path / "PHD.xlsx"
    planilha.write_bytes(b"x")
    data = form(tmp_path, files="", sn_on="on", sn_source=f'"{planilha}"', sn_header_row="15", sn_columns="b:e",
                sn_day_columns="f:aj", sn_day_row="14", sn_reference="ontem", sn_hide_sundays="on",
                sn_split_column="e", sn_name_column="D", sn_threshold="4,5", sn_worst_count="5",
                sn_split_values="S-LT (MARINA COUTO)\n\nS-ST (LUANA PRADO)\n", message="{valor}: {piores}")
    data.update(overrides)
    return data


def test_create_dispatch_with_print(tmp_path):
    c, store, _ = setup(tmp_path)
    r = c.post("/envios", data=snapshot_form(tmp_path), follow_redirects=False)
    assert r.status_code == 303
    [d] = store.load().dispatches
    sn = d.snapshot
    assert d.files == [] and d.watched_files == [tmp_path / "PHD.xlsx"]
    assert (sn.header_row, sn.columns, sn.day_columns, sn.day_row) == (15, ["B", "C", "D", "E"], "F:AJ", 14)
    assert (sn.split_column, sn.name_column, sn.threshold, sn.worst_count) == ("E", "D", 4.5, 5)
    assert sn.split_values == ["S-LT (MARINA COUTO)", "S-ST (LUANA PRADO)"] and sn.hide_sundays
    page = c.get(f"/envios/{d.id}").text
    assert 'value="4,5"' in page and "Pré-visualizar o print" in page
    assert "print de PHD.xlsx" in c.get("/envios").text


def test_print_validation(tmp_path):
    c, store, _ = setup(tmp_path)
    r = c.post("/envios", data=snapshot_form(tmp_path, sn_source="", sn_header_row="quinze", sn_columns="B, 12",
                                             sn_day_row="", sn_split_column="E5", sn_threshold="muito"))
    assert r.status_code == 422
    for msg in ["informe o caminho da planilha", "Linha do cabeçalho", "Colunas fixas", "Linha com o dia do mês",
                "Um print por", "Meta por dia"]:
        assert msg in r.text
    assert store.load().dispatches == []


def test_turning_print_off_keeps_a_plain_dispatch(tmp_path):
    c, store, _ = setup(tmp_path)
    data = snapshot_form(tmp_path)
    del data["sn_on"]
    data["files"] = str(tmp_path / "PHD.xlsx")
    c.post("/envios", data=data)
    assert store.load().dispatches[0].snapshot is None


def test_preview_shows_each_part(tmp_path):
    from pombo.snapshot import Part

    c, store, engine = setup(tmp_path)
    c.post("/envios", data=snapshot_form(tmp_path))
    d = store.load().dispatches[0]
    img = tmp_path / "01.png"
    img.write_bytes(b"\x89PNG-fake")
    engine.preview_parts = [Part("s-lt", "S-LT", "PHD S-LT", "S-LT: 🔻 Ana", img)]
    r = c.post(f"/envios/{d.id}/previa")
    assert r.status_code == 200 and "S-LT: 🔻 Ana" in r.text and f"/envios/{d.id}/previa/0.png" in r.text
    assert c.get(f"/envios/{d.id}/previa/0.png").content == b"\x89PNG-fake"
    assert c.get(f"/envios/{d.id}/previa/1.png").status_code == 404


def test_preview_error_is_shown(tmp_path):
    c, store, engine = setup(tmp_path)
    c.post("/envios", data=snapshot_form(tmp_path))
    d = store.load().dispatches[0]

    def broken(_):
        raise RuntimeError("aba \"PHD\" não existe")
    engine.preview = broken
    r = c.post(f"/envios/{d.id}/previa")
    assert "Não consegui montar o print" in r.text
