"""Teste de conexão: roda no PC da empresa ANTES de usar o Pombo.

Verifica se a rede deixa sair e-mail (SMTP) e WhatsApp. Uso:

    .venv\\Scripts\\python tools\\connection_test.py

Nada aqui fica salvo, exceto a sessão de teste do WhatsApp (pasta ignorada pelo Git).
"""

import getpass
import smtplib
import ssl
import sys
import threading
from email.message import EmailMessage
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent / "exemplos" / "teste.txt"


def ask(label: str, default: str = "") -> str:
    value = input(f"{label}{f' [{default}]' if default else ''}: ").strip()
    return value or default


def test_email() -> None:
    print("\n=== E-MAIL ===")
    host = ask("Servidor SMTP (veja no Thunderbird: Configurações > Servidor de saída)")
    security = ask("Segurança: ssl ou starttls", "ssl")
    port = int(ask("Porta", "465" if security == "ssl" else "587"))
    user = ask("Usuário (seu e-mail)")
    password = getpass.getpass("Senha (não aparece enquanto digita): ")

    msg = EmailMessage()
    msg["From"] = user
    msg["To"] = user
    msg["Subject"] = "Pombo: teste de conexão"
    msg.set_content("Se você recebeu isto, o Pombo consegue enviar e-mails deste PC.")
    msg.add_attachment(SAMPLE.read_bytes(), maintype="text", subtype="plain", filename=SAMPLE.name)

    try:
        if security == "ssl":
            server = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30)
        else:
            server = smtplib.SMTP(host, port, timeout=30)
            server.starttls(context=ssl.create_default_context())
        with server:
            server.login(user, password)
            server.send_message(msg)
        print(f"E-MAIL OK ({host}:{port} {security}). Confira sua caixa de entrada.")
    except Exception as exc:  # o objetivo aqui é mostrar qualquer erro por inteiro
        print(f"E-MAIL FALHOU: {type(exc).__name__}: {exc}")


def test_whatsapp() -> None:
    print("\n=== WHATSAPP (biblioteca neonize) ===")
    try:
        from neonize.client import NewClient
        from neonize.events import ConnectedEv
        from neonize.utils.jid import build_jid
    except Exception as exc:
        print(f"WHATSAPP FALHOU ao carregar a biblioteca: {type(exc).__name__}: {exc}")
        return

    session = HERE.parent / "whatsapp-sessao-teste"
    session.mkdir(exist_ok=True)
    connected = threading.Event()
    client = NewClient(str(session / "teste.db"))

    @client.event(ConnectedEv)
    def _on_connected(_client, _event) -> None:
        connected.set()

    print("Abra o WhatsApp do número CORPORATIVO > Aparelhos conectados > Conectar aparelho")
    print("e leia o QR code que vai aparecer abaixo (pode levar alguns segundos).")
    threading.Thread(target=client.connect, daemon=True).start()
    if not connected.wait(timeout=180):
        print("WHATSAPP FALHOU: não conectou em 3 minutos (rede bloqueada ou QR não lido).")
        return

    try:
        groups = client.get_joined_groups()
        print(f"Conectado. {len(groups)} grupo(s) encontrados:")
        for g in groups[:15]:
            print(f"  - {g.GroupName.Name}")
        phone = ask("Número para receber o arquivo de teste (só dígitos, com DDD)")
        digits = "".join(c for c in phone if c.isdigit())
        if not digits.startswith("55"):
            digits = "55" + digits
        client.send_document(
            build_jid(digits),
            SAMPLE.read_bytes(),
            caption="Pombo: teste de conexão",
            filename=SAMPLE.name,
            mimetype="text/plain",
        )
        print("WHATSAPP OK (neonize). Confira se o arquivo chegou.")
    except Exception as exc:
        print(f"WHATSAPP FALHOU ao enviar: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    print("Pombo: teste de conexão deste PC")
    what = sys.argv[1] if len(sys.argv) > 1 else "tudo"
    if what in ("tudo", "email"):
        test_email()
    if what in ("tudo", "whatsapp"):
        test_whatsapp()
    input("\nFim. Copie o resultado acima e pressione Enter para sair.")
