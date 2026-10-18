import json
import os
from datetime import time
from pathlib import Path

import pytest

from pombo.models import Dispatch, Registry, Schedule, Settings
from pombo.paths import data_dir
from pombo.store import Store, new_id


def make_dispatch(**overrides) -> Dispatch:
    fields = dict(
        id="a1",
        name="Vendas Diárias",
        files=[Path(r"S:\Relatórios\(DADOS) - 8081 - Descrição.xlsx")],
        email_list_ids=[],
        email_contact_ids=[],
        whatsapp_contact_ids=[],
        whatsapp_group_ids=[],
        schedule=Schedule(weekdays={0, 1, 2, 3, 4}, times=[time(18, 0)]),
        subject="Vendas {data}",
        message="{saudacao}!",
    )
    fields.update(overrides)
    return Dispatch(**fields)


def empty_registry(**overrides) -> Registry:
    fields = dict(settings=Settings(), contacts=[], email_lists=[], whatsapp_groups=[], dispatches=[])
    fields.update(overrides)
    return Registry(**fields)


def test_load_missing_file_returns_empty_registry(tmp_path):
    reg = Store(tmp_path / "cadastro.json").load()
    assert reg.dispatches == [] and reg.settings.max_email_mb == 20


def test_roundtrip_keeps_accented_paths(tmp_path):
    s = Store(tmp_path / "cadastro.json")
    d = make_dispatch()
    s.save(empty_registry(dispatches=[d]))
    assert s.load().dispatches[0] == d
    # o JSON fica legível, com acentos de verdade
    assert "Descrição" in (tmp_path / "cadastro.json").read_text(encoding="utf-8")


def test_save_is_atomic(tmp_path, monkeypatch):
    s = Store(tmp_path / "cadastro.json")
    s.save(empty_registry(dispatches=[make_dispatch(name="Antigo")]))

    def boom(*_args, **_kwargs):
        raise OSError("disco cheio")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        s.save(empty_registry(dispatches=[make_dispatch(name="Novo")]))
    data = json.loads((tmp_path / "cadastro.json").read_text(encoding="utf-8"))
    assert data["dispatches"][0]["name"] == "Antigo"


def test_history_dir_default_and_override(tmp_path, monkeypatch):
    monkeypatch.setenv("POMBO_DADOS", str(tmp_path))
    s = Store(tmp_path / "cadastro.json")
    assert s.history_dir() == tmp_path / "historico"
    s.save(empty_registry(settings=Settings(history_dir=tmp_path / "rede")))
    assert s.history_dir() == tmp_path / "rede"


def test_data_dir_uses_env_and_creates_it(tmp_path, monkeypatch):
    target = tmp_path / "dados"
    monkeypatch.setenv("POMBO_DADOS", str(target))
    assert data_dir() == target and target.is_dir()


def test_new_id_is_short_and_unique():
    ids = {new_id() for _ in range(100)}
    assert len(ids) == 100 and all(len(i) == 8 for i in ids)
