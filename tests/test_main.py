import socket

import pombo.__main__ as entry


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_acquire_returns_socket_when_free(monkeypatch):
    port = free_port()
    sock = entry.acquire_single_instance(port)
    try:
        assert sock is not None
        assert entry.acquire_single_instance(port) is None  # a mesma porta não pode ser pega duas vezes
    finally:
        sock.close()


def test_second_instance_exits_without_starting_engine(monkeypatch, tmp_path):
    # Review Focus 1: duplo clique duas vezes no iniciar.bat
    port = free_port()
    holder = entry.acquire_single_instance(port)
    opened, engines = [], []
    monkeypatch.setattr(entry, "PORT", port)
    monkeypatch.setattr(entry.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(entry, "Engine", lambda *a, **k: engines.append(1))
    monkeypatch.setenv("POMBO_DADOS", str(tmp_path))
    try:
        entry.main()
    finally:
        holder.close()
    assert opened == [f"http://127.0.0.1:{port}/"] and engines == []


def test_server_config_works_without_console(monkeypatch):
    # iniciar.bat usa pythonw: não há sys.stdout nem sys.stderr
    from fastapi import FastAPI

    monkeypatch.setattr("sys.stdout", None)
    monkeypatch.setattr("sys.stderr", None)
    entry.server_config(FastAPI())
