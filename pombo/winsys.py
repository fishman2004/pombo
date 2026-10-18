"""Integração com o Windows, tudo sem administrador."""

import os
import sys
from pathlib import Path

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001


def keep_awake() -> None:
    # impede o PC de suspender enquanto o Pombo roda (a tela ainda pode apagar)
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)


def startup_file() -> Path:
    return Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Pombo.cmd"


def set_start_with_windows(enabled: bool, project_dir: Path) -> None:
    f = startup_file()
    if enabled:
        f.parent.mkdir(parents=True, exist_ok=True)
        # o cmd.exe lê arquivos .cmd na página de código OEM; em UTF-8 "Área" viraria lixo
        encoding = "oem" if sys.platform == "win32" else "utf-8"
        f.write_text(f'start "" /min "{Path(project_dir) / "iniciar.bat"}"\n', encoding=encoding)
    else:
        f.unlink(missing_ok=True)
