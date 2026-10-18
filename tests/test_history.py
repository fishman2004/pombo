import csv
from datetime import date, datetime

import pytest

import pombo.history as history_mod
from pombo.history import COLUMNS, History, HistoryLocked, Row, analyst_slug, run_label


def row(when, status="enviado", run="2026-10-19 18:00", target="Gestão", channel="email", dispatch_id="a1", detail=""):
    return Row(
        when=when, analyst="Kayo", dispatch_name="Vendas, \"Diárias\"", run=run, channel=channel,
        target=target, files="Vendas.xlsx", status=status, detail=detail, dispatch_id=dispatch_id,
    )


@pytest.fixture
def hist(tmp_path):
    h = History(tmp_path / "historico", "Kayo Ibiapino", tmp_path / "pendentes.csv")
    h.load(date(2026, 10, 19))
    return h


def test_slug_and_run_label():
    assert analyst_slug("Kayo Ibiápino") == "kayo-ibiapino"
    assert run_label(datetime(2026, 10, 19, 18, 0), manual=False) == "2026-10-19 18:00"
    assert run_label(datetime(2026, 10, 19, 18, 7, 3), manual=True) == "manual 2026-10-19 18:07:03"


def test_creates_monthly_file_with_bom_and_header(hist, tmp_path):
    hist.append(row(datetime(2026, 10, 19, 18, 2)))
    f = tmp_path / "historico" / "kayo-ibiapino" / "2026-10.csv"
    assert f.read_bytes().startswith(b"\xef\xbb\xbf")
    with f.open(encoding="utf-8-sig", newline="") as fh:
        lines = list(csv.reader(fh))
    assert tuple(lines[0]) == COLUMNS
    assert lines[1][2] == 'Vendas, "Diárias"'


def test_rows_for_run_and_last_success(hist):
    hist.append(row(datetime(2026, 10, 19, 18, 1), status="falhou"))
    hist.append(row(datetime(2026, 10, 19, 18, 6)))
    hist.append(row(datetime(2026, 10, 19, 18, 7), dispatch_id="b2"))
    assert [r.status for r in hist.rows_for_run("a1", "2026-10-19 18:00")] == ["falhou", "enviado"]
    assert hist.last_success("a1") == datetime(2026, 10, 19, 18, 6)
    assert hist.last_success("zz") is None


def test_demonstracao_counts_as_success(hist):
    hist.append(row(datetime(2026, 10, 19, 18, 1), status="demonstracao"))
    assert hist.last_success("a1") == datetime(2026, 10, 19, 18, 1)


def test_load_reads_previous_month_for_last_success(tmp_path):
    root = tmp_path / "historico"
    h1 = History(root, "Kayo", tmp_path / "p.csv")
    h1.load(date(2026, 9, 30))
    h1.append(row(datetime(2026, 9, 30, 18, 0), run="2026-09-30 18:00"))
    h2 = History(root, "Kayo", tmp_path / "p.csv")
    h2.load(date(2026, 10, 1))
    assert h2.last_success("a1") == datetime(2026, 9, 30, 18, 0)


def test_locked_csv_keeps_rows_and_flushes_later(hist, tmp_path, monkeypatch):
    # Review Focus 2: o chefe abriu o CSV no Excel
    monkeypatch.setattr(history_mod, "_append_csv", lambda *a, **k: (_ for _ in ()).throw(PermissionError("travado")))
    hist.append(row(datetime(2026, 10, 19, 18, 2)))  # não lança
    assert len(hist.rows_for_run("a1", "2026-10-19 18:00")) == 1
    assert (tmp_path / "pendentes.csv").exists()
    monkeypatch.undo()
    hist.flush()
    f = tmp_path / "historico" / "kayo-ibiapino" / "2026-10.csv"
    assert "Gestão" in f.read_text(encoding="utf-8-sig")
    assert not (tmp_path / "pendentes.csv").exists()


def test_load_raises_when_locked(tmp_path, monkeypatch):
    h = History(tmp_path / "historico", "Kayo", tmp_path / "p.csv")
    h.load(date(2026, 10, 19))
    h.append(row(datetime(2026, 10, 19, 18, 2)))
    monkeypatch.setattr(history_mod, "_read_csv", lambda *a, **k: (_ for _ in ()).throw(PermissionError("travado")))
    with pytest.raises(HistoryLocked):
        History(tmp_path / "historico", "Kayo", tmp_path / "p.csv").load(date(2026, 10, 19))


def test_pending_rows_survive_restart(tmp_path, monkeypatch):
    h = History(tmp_path / "historico", "Kayo", tmp_path / "p.csv")
    h.load(date(2026, 10, 19))
    monkeypatch.setattr(history_mod, "_append_csv", lambda *a, **k: (_ for _ in ()).throw(PermissionError("travado")))
    h.append(row(datetime(2026, 10, 19, 18, 2)))
    h2 = History(tmp_path / "historico", "Kayo", tmp_path / "p.csv")
    h2.load(date(2026, 10, 19))
    assert len(h2.rows_for_run("a1", "2026-10-19 18:00")) == 1


def test_rows_between(hist):
    hist.append(row(datetime(2026, 10, 17, 18, 0), run="2026-10-17 18:00"))
    hist.append(row(datetime(2026, 10, 19, 18, 0)))
    assert len(hist.rows_between(date(2026, 10, 18), date(2026, 10, 19))) == 1


def test_load_raises_when_root_unreachable(tmp_path, monkeypatch):
    from pathlib import Path

    def boom(self, *a, **k):
        raise OSError("unidade de rede indisponível")

    monkeypatch.setattr(Path, "mkdir", boom)
    with pytest.raises(HistoryLocked):
        History(tmp_path / "S" / "historico", "Kayo", tmp_path / "p.csv").load(date(2026, 10, 19))


def test_bad_rows_are_skipped(tmp_path):
    f = tmp_path / "historico" / "kayo" / "2026-10.csv"
    f.parent.mkdir(parents=True)
    f.write_text(
        ",".join(COLUMNS) + "\n"
        "2026-10-19 18:00:00,Kayo,Vendas,2026-10-19 18:00,email,Gestão,V.xlsx,enviado,,a1\n"
        "19/10/2026;lixo do Excel\n"
        "2026-10-19 18:0\n",
        encoding="utf-8-sig",
    )
    h = History(tmp_path / "historico", "Kayo", tmp_path / "p.csv")
    h.load(date(2026, 10, 19))
    assert len(h.rows_for_run("a1", "2026-10-19 18:00")) == 1


def test_target_key_column_and_old_rows(hist, tmp_path):
    assert COLUMNS[-1] == "destinatario_id"
    hist.append(Row(datetime(2026, 10, 19, 18, 2), "Kayo", "V", "2026-10-19 18:00", "email", "Gestão", "", "enviado", "", "a1", "list:l1"))
    h2 = History(tmp_path / "historico", "Kayo Ibiapino", tmp_path / "pendentes.csv")
    h2.load(date(2026, 10, 19))
    assert h2.rows_for_run("a1", "2026-10-19 18:00")[0].target_key == "list:l1"
