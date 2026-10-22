import os
import time as systime
from datetime import date, datetime, time

import pytest

from pombo.models import Dispatch, Schedule, Snapshot
from pombo.snapshot import (SnapshotError, SnapshotRuns, build_parts, col_index, col_letter, parse_columns,
                            read_groups, summary, to_number)
from tools.make_phd import make_phd

THU = date(2026, 10, 22)  # quinta: o resultado de "ontem" é a quarta, 21/10


@pytest.fixture(scope="module")
def phd(tmp_path_factory):
    return make_phd(tmp_path_factory.mktemp("phd") / "PHD.xlsx", until=date(2026, 10, 26))


def cfg(source, **kw) -> Snapshot:
    base = dict(source=source, header_row=15, columns=["B", "C", "D", "E"], day_columns="F:AJ", day_row=14,
                split_column="E", name_column="D")
    return Snapshot(**{**base, **kw})


def dispatch(snapshot, message="{valor}: {acima} na meta", subject="PHD {valor}") -> Dispatch:
    return Dispatch(id="d1", name="PHD", schedule=Schedule(weekdays={3}, times=[time(9)]), subject=subject,
                    message=message, snapshot=snapshot)


def test_columns():
    assert [col_index(x) for x in ("A", "Z", "AA", "AJ")] == [0, 25, 26, 35]
    assert [col_letter(i) for i in (0, 25, 26, 35)] == ["A", "Z", "AA", "AJ"]
    assert parse_columns("b, D:E;ak") == ["B", "D", "E", "AK"]
    with pytest.raises(SnapshotError):
        parse_columns("B, 12")


def test_numbers_written_as_text():
    assert to_number("3,50") == 3.5 and to_number("1.234,5") == 1234.5 and to_number(7) == 7.0
    assert to_number("") is None and to_number(None) is None and to_number("ok") is None


def test_week_of_yesterday_until_today(phd):
    ref, groups = read_groups(cfg(phd), THU)
    assert ref == date(2026, 10, 21)
    [g1, g2, g3] = groups
    assert [g.value for g in groups] == ["S-LT (MARINA COUTO)", "S-AG (RAFAEL DUARTE)", "S-ST (LUANA PRADO)"]
    assert [len(g.rows) for g in groups] == [8, 9, 12]
    days = [c for c in g1.columns if c.day]
    assert [(c.title, c.day.day) for c in days] == [("SEG", 19), ("TER", 20), ("QUA", 21), ("QUI", 22)]
    assert [c.title for c in g1.columns[:4]] == ["ÁREA", "ID", "SUPERVISOR", "AREA"]


def test_monday_looks_at_saturday_and_hides_sunday(phd):
    ref, [g, *_] = read_groups(cfg(phd), date(2026, 10, 26))
    assert ref == date(2026, 10, 24)
    assert [c.day.day for c in g.columns if c.day] == [19, 20, 21, 22, 23, 24]
    _, [g, *_] = read_groups(cfg(phd, hide_sundays=False), date(2026, 10, 26))
    assert [c.day.day for c in g.columns if c.day] == [19, 20, 21, 22, 23, 24, 25]


def test_today_reference_on_monday_shows_only_monday(phd):
    ref, [g, *_] = read_groups(cfg(phd, reference="hoje"), date(2026, 10, 19))
    assert ref == date(2026, 10, 19) and [c.day.day for c in g.columns if c.day] == [19]


def test_only_some_values_in_given_order(phd):
    _, groups = read_groups(cfg(phd, split_values=["s-st (luana prado)", "S-LT (MARINA COUTO)", "NÃO EXISTE"]), THU)
    assert [g.value for g in groups] == ["S-ST (LUANA PRADO)", "S-LT (MARINA COUTO)"]


def test_without_split_everything_is_one_print(phd):
    _, groups = read_groups(cfg(phd, split_column=""), THU)
    assert len(groups) == 1 and len(groups[0].rows) == 29


def test_metric_is_week_average_until_reference(phd):
    _, [g, *_] = read_groups(cfg(phd), THU)
    days = [i for i, c in enumerate(g.columns) if c.day and c.day <= date(2026, 10, 21)]
    row = g.rows[0]
    assert g.metrics[0] == pytest.approx(sum(row[i] for i in days) / 3)


def test_metric_from_a_column(phd):
    _, [g, *_] = read_groups(cfg(phd, metric_column="AK", extra_columns=["AK"]), THU)
    assert g.columns[-1].title == "MÉDIA"
    assert g.metrics[0] == g.rows[0][-1]


def test_summary_counts_and_worst(phd):
    c = cfg(phd)
    ref, [g, *_] = read_groups(c, THU)
    g.metrics = [6, 5, 4.5, 1, 0, 7, 2, None]
    g.names = ["A", "B", "C", "D", "E", "F", "G", "H"]
    s = summary(g, c, ref)
    assert (s["linhas"], s["acima"], s["abaixo"], s["limite"]) == ("8", "3", "4", "5")
    assert s["piores"] == "🔻 E\n🔻 D\n🔻 G\n🔻 C\n🔻 B" and s["qtd_piores"] == "5"
    assert s["melhores"].splitlines()[0] == "🔺 F"
    assert s["referencia"] == "21/10/2026"
    wed = next(i for i, col in enumerate(g.columns) if col.day == ref)
    assert s["total_dia"] == str(sum(r[wed] for r in g.rows))


def test_build_parts_images_and_texts(phd, tmp_path):
    d = dispatch(cfg(phd, title="PHD · {valor}"), message="Resultado do dia: {referencia}\n{valor}\n{piores}")
    parts = build_parts(d, datetime(2026, 10, 22, 9, 0), tmp_path)
    assert [p.key for p in parts] == ["s-lt-marina-couto", "s-ag-rafael-duarte", "s-st-luana-prado"]
    assert parts[0].subject == "PHD S-LT (MARINA COUTO)"
    assert parts[0].text.startswith("Resultado do dia: 21/10/2026\nS-LT (MARINA COUTO)\n🔻 ")
    from PIL import Image

    with Image.open(parts[2].image) as img:
        assert img.format == "PNG" and img.width > 600 and img.height > 12 * 40


def test_clear_errors(phd, tmp_path):
    now = datetime(2026, 10, 22, 9, 0)
    with pytest.raises(SnapshotError, match="não encontrada"):
        build_parts(dispatch(cfg(tmp_path / "sumiu.xlsx")), now, tmp_path / "a")
    with pytest.raises(SnapshotError, match="aba \"Outra\""):
        build_parts(dispatch(cfg(phd, sheet="Outra")), now, tmp_path / "b")
    with pytest.raises(SnapshotError, match="nenhuma linha"):
        build_parts(dispatch(cfg(phd, split_values=["NINGUÉM"])), now, tmp_path / "c")


def test_dates_in_day_row(tmp_path):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Vendedor", "Equipe", datetime(2026, 10, 19), datetime(2026, 10, 20), datetime(2026, 10, 21)])
    ws.append(["Ana", "X", 5, 2, 0])
    ws.append(["Bia", "X", 1, 1, 1])
    path = tmp_path / "datas.xlsx"
    wb.save(path)
    c = Snapshot(source=path, header_row=1, columns=["A"], day_columns="C:E", day_row=1, split_column="B")
    ref, [g] = read_groups(c, THU)
    assert [col.day.day for col in g.columns if col.day] == [19, 20, 21]
    assert summary(g, c, ref)["piores"] == "🔻 Bia\n🔻 Ana"


def test_runs_are_kept_and_reused(phd, tmp_path):
    runs = SnapshotRuns(tmp_path / "recortes")
    d = dispatch(cfg(phd))
    built = runs.build(d, "2026-10-22 09:00", datetime(2026, 10, 22, 9, 0))
    loaded = runs.load("d1", "2026-10-22 09:00")
    assert loaded == built and all(p.image.is_file() for p in loaded)
    assert runs.load("d1", "2026-10-22 15:00") is None


def test_old_runs_are_cleaned(phd, tmp_path):
    runs = SnapshotRuns(tmp_path / "recortes")
    d = dispatch(cfg(phd))
    runs.build(d, "2026-09-01 09:00", datetime(2026, 9, 1, 9, 0))
    old = runs.folder("d1", "2026-09-01 09:00")
    past = systime.time() - 40 * 86400
    os.utime(old, (past, past))
    runs.build(d, "2026-10-22 09:00", datetime(2026, 10, 22, 9, 0))
    assert not old.exists() and runs.load("d1", "2026-10-22 09:00")
