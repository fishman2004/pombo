"""Lê e grava o cadastro (cadastro.json)."""

import os
import tempfile
import uuid
from pathlib import Path

from .models import Registry
from .paths import data_dir


def new_id() -> str:
    return uuid.uuid4().hex[:8]


class Store:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Registry:
        if not self.path.exists():
            return Registry()
        return Registry.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, reg: Registry) -> None:
        # grava num arquivo temporário e troca de uma vez: se algo falhar, o cadastro antigo fica intacto
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(reg.model_dump_json(indent=2))
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    def history_dir(self) -> Path:
        return self.load().settings.history_dir or data_dir() / "historico"
