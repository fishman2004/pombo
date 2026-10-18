from pathlib import Path

from pombo.alerts import UserAlerts
from pombo.channels import SendError
from pombo.models import Settings
from pombo import winsys


class RecordingEmail:
    def __init__(self, fail=False):
        self.fail = fail
        self.sent = []

    def send(self, target, subject, message, files, use_bcc=True):
        if self.fail:
            raise SendError("sem rede")
        self.sent.append((target.addresses, subject, message))


def test_toast_failure_still_sends_email():
    email = RecordingEmail()

    def broken_toast(title, body):
        raise RuntimeError("sem notificações")

    UserAlerts(lambda: Settings(self_email="eu@exemplo.com"), email, broken_toast).notify("Título", "Corpo")
    assert email.sent == [(("eu@exemplo.com",), "Título", "Corpo")]


def test_without_self_email_only_toast():
    toasts, email = [], RecordingEmail()
    UserAlerts(lambda: Settings(), email, lambda t, b: toasts.append(t)).notify("Título", "Corpo")
    assert toasts == ["Título"] and email.sent == []


def test_email_failure_does_not_propagate():
    toasts = []
    UserAlerts(lambda: Settings(self_email="eu@x"), RecordingEmail(fail=True), lambda t, b: toasts.append(t)).notify("T", "C")
    assert toasts == ["T"]


def test_start_with_windows_creates_and_removes(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    project = Path(r"C:\Pombo")
    winsys.set_start_with_windows(True, project)
    f = winsys.startup_file()
    assert f == tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "Pombo.cmd"
    assert f.read_text(encoding="oem").strip() == 'start "" /min "C:\\Pombo\\iniciar.bat"'
    winsys.set_start_with_windows(False, project)
    assert not f.exists()


def test_startup_file_handles_accented_path(tmp_path, monkeypatch):
    # o cmd.exe lê .cmd na página de código OEM, não em UTF-8
    monkeypatch.setenv("APPDATA", str(tmp_path))
    winsys.set_start_with_windows(True, Path(r"C:\Users\usuario\Área de Trabalho\pombo"))
    assert "Área de Trabalho" in winsys.startup_file().read_text(encoding="oem")


def test_keep_awake_does_not_crash():
    winsys.keep_awake()
