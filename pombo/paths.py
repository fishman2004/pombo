"""Onde o Pombo guarda os dados do usuário (sempre fora da pasta do código)."""

import os
from pathlib import Path


def data_dir() -> Path:
    # POMBO_DADOS existe para os testes e para quem quiser outra pasta
    custom = os.environ.get("POMBO_DADOS")
    base = Path(custom) if custom else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Pombo"
    base.mkdir(parents=True, exist_ok=True)
    return base
