"""Confere se um arquivo está pronto para ser enviado. Nunca lança exceção."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class FileStatus:
    path: Path
    ready: bool
    reason: str  # "ok" | "não encontrado" | "inacessível" | "vazio" | "aberto no Excel"
    mtime: datetime | None
    size: int


def inspect(path: Path) -> FileStatus:
    path = Path(path)

    def not_ready(reason: str, mtime: datetime | None = None, size: int = 0) -> FileStatus:
        return FileStatus(path, False, reason, mtime, size)

    try:
        st = path.stat()
    except FileNotFoundError:
        # unidade de rede fora do ar também chega aqui; a raiz sumida denuncia
        return not_ready("não encontrado" if Path(path.anchor or ".").exists() else "inacessível")
    except OSError:
        return not_ready("inacessível")

    mtime = datetime.fromtimestamp(st.st_mtime)
    if st.st_size == 0:
        return not_ready("vazio", mtime)
    # o Excel cria "~$Nome.xlsx" ao lado enquanto o arquivo está aberto
    if (path.parent / f"~${path.name}").exists():
        return not_ready("aberto no Excel", mtime, st.st_size)
    try:
        with open(path, "r+b"):
            pass
    except PermissionError:
        return not_ready("aberto no Excel", mtime, st.st_size)
    except OSError:
        return not_ready("inacessível", mtime, st.st_size)
    return FileStatus(path, True, "ok", mtime, st.st_size)
