import builtins
from pathlib import Path

from pombo.files import inspect


def test_ok_file(tmp_path):
    f = tmp_path / "Vendas.xlsx"
    f.write_bytes(b"conteudo")
    st = inspect(f)
    assert st.ready and st.reason == "ok" and st.mtime is not None and st.size == 8


def test_missing_file(tmp_path):
    st = inspect(tmp_path / "nao_existe.xlsx")
    assert not st.ready and st.reason == "não encontrado"


def test_empty_file(tmp_path):
    f = tmp_path / "Vendas.xlsx"
    f.write_bytes(b"")
    assert inspect(f).reason == "vazio"


def test_excel_lock_file_means_open(tmp_path):
    f = tmp_path / "Vendas.xlsx"
    f.write_bytes(b"x")
    (tmp_path / "~$Vendas.xlsx").write_bytes(b"lock")
    st = inspect(f)
    assert not st.ready and st.reason == "aberto no Excel"


def test_permission_error_means_open(tmp_path, monkeypatch):
    f = tmp_path / "Vendas.xlsx"
    f.write_bytes(b"x")
    real_open = builtins.open

    def fake_open(path, mode="r", *args, **kwargs):
        if Path(path) == f and "+" in mode:
            raise PermissionError("em uso")
        return real_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", fake_open)
    assert inspect(f).reason == "aberto no Excel"


def test_unreachable_network_drive(tmp_path, monkeypatch):
    # Review Focus 3: unidade S: desconectada não pode virar exceção
    f = tmp_path / "Vendas.xlsx"

    def boom(self, *args, **kwargs):
        raise OSError("O caminho de rede não foi encontrado")

    monkeypatch.setattr(Path, "stat", boom)
    st = inspect(f)
    assert not st.ready and st.reason == "inacessível"
