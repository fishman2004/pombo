import pytest

from pombo.models import Registry, Settings
from pombo.store import Store
from tools.seed_demo import seed


def test_refuses_without_dedicated_folder(monkeypatch):
    monkeypatch.delenv("POMBO_DADOS", raising=False)
    with pytest.raises(SystemExit):
        seed()


def test_refuses_to_overwrite_real_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("POMBO_DADOS", str(tmp_path))
    Store(tmp_path / "cadastro.json").save(Registry(settings=Settings(analyst_name="Kayo")))
    with pytest.raises(SystemExit):
        seed()
    assert Store(tmp_path / "cadastro.json").load().settings.analyst_name == "Kayo"


def test_seeds_empty_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("POMBO_DADOS", str(tmp_path))
    seed()
    assert Store(tmp_path / "cadastro.json").load().settings.demo_mode
