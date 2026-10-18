"""Prepara uma pasta de demonstração com cadastro e histórico fictícios.

Serve para apresentar o Pombo e tirar prints sem tocar em dados reais:

    set POMBO_DADOS=%TEMP%\\pombo-demo
    .venv\\Scripts\\python -m tools.seed_demo
    .venv\\Scripts\\python -m pombo
"""

import os
from datetime import datetime, time, timedelta
from pathlib import Path

from pombo.history import History, Row, run_label
from pombo.models import Contact, Dispatch, EmailList, Registry, Schedule, Settings, WhatsAppGroup
from pombo.paths import data_dir
from pombo.store import Store
from tools.make_examples import make_examples

ROOT = Path(__file__).resolve().parent.parent


def seed(now: datetime | None = None) -> Path:
    now = now or datetime.now()
    # nunca escreve na pasta real do Pombo: exige uma pasta própria para a demonstração
    if not os.environ.get("POMBO_DADOS"):
        raise SystemExit("Defina POMBO_DADOS com uma pasta só para a demonstração (veja o README).")
    base = data_dir()
    existing = base / "cadastro.json"
    if existing.exists() and not Store(existing).load().settings.demo_mode:
        raise SystemExit(f"{existing} tem um cadastro de verdade. Use outra pasta em POMBO_DADOS.")
    examples = base / "relatorios"
    make_examples(examples, rows=300)
    vendas, plano = examples / "Vendas.xlsx", examples / "Plano_Excelencia.xlsx"
    base_csv = examples / "(DADOS) - 8081 - Exemplo.csv"

    every_day = {0, 1, 2, 3, 4, 5, 6}
    hours = [time(h, 0) for h in (8, 12, 14, 18)]
    reg = Registry(
        settings=Settings(analyst_name="Analista Demo", self_email="analista@exemplo.com", demo_mode=True,
                          start_with_windows=False, history_dir=base / "historico"),
        contacts=[
            Contact(id="c1", name="Gestor Comercial", email="gestor@exemplo.com", whatsapp="5583900000001"),
            Contact(id="c2", name="Supervisora Norte", email="norte@exemplo.com"),
            Contact(id="c3", name="Supervisor Sul", email="sul@exemplo.com"),
        ],
        email_lists=[EmailList(id="l1", name="Gestão", contact_ids=["c1", "c2", "c3"])],
        whatsapp_groups=[WhatsAppGroup(id="120363000000000001@g.us", name="Comercial — Vendas"),
                         WhatsAppGroup(id="120363000000000002@g.us", name="Supervisores")],
        dispatches=[
            Dispatch(id="vendas", name="Vendas Diárias", files=[vendas], email_list_ids=["l1"],
                     whatsapp_group_ids=["120363000000000001@g.us"],
                     schedule=Schedule(weekdays=every_day, times=[hours[0], hours[3]]),
                     subject="Vendas atualizadas: {data}", message="{saudacao}! Segue o relatório de vendas atualizado em {data}."),
            Dispatch(id="plano", name="Plano de Excelência", files=[plano], email_contact_ids=["c1"],
                     whatsapp_group_ids=["120363000000000002@g.us"],
                     schedule=Schedule(weekdays=every_day, times=[hours[1]]),
                     subject="Plano de Excelência {data}", message="{saudacao}! Plano de Excelência de hoje."),
            Dispatch(id="base", name="Base 8081 (CSV)", files=[base_csv], email_list_ids=["l1"],
                     schedule=Schedule(weekdays=every_day, times=[hours[2]]),
                     subject="Base 8081 {data}", message="{saudacao}! Base completa em anexo."),
        ],
    )
    store = Store(base / "cadastro.json")
    store.save(reg)

    history = History(base / "historico", "Analista Demo", base / "historico-pendente.csv")
    history.load(now.date())
    today = now.date()

    def add(h, m, dispatch, name, channel, target, status, detail=""):
        scheduled = datetime.combine(today, time(h, 0))
        if scheduled > now:
            return
        history.append(Row(datetime.combine(today, time(h, m)), "Analista Demo", name,
                           run_label(scheduled, False), channel, target, "", status, detail, dispatch))

    add(8, 0, "vendas", "Vendas Diárias", "email", "Gestão", "demonstracao", "modo demonstração: nada foi enviado")
    add(8, 0, "vendas", "Vendas Diárias", "whatsapp", "Comercial — Vendas", "demonstracao", "modo demonstração: nada foi enviado")
    add(12, 1, "plano", "Plano de Excelência", "email", "Gestor Comercial", "demonstracao", "modo demonstração: nada foi enviado")
    add(12, 1, "plano", "Plano de Excelência", "whatsapp", "Supervisores", "falhou", "WhatsApp: tempo esgotado")
    add(14, 0, "base", "Base 8081 (CSV)", "", "", "esperando", "(DADOS) - 8081 - Exemplo.csv: não atualizado hoje (esperando até 15:00)")
    add(14, 59, "base", "Base 8081 (CSV)", "", "", "desistiu", "(DADOS) - 8081 - Exemplo.csv: não atualizado hoje")
    # o arquivo da base fica "velho" para a demonstração da espera fazer sentido
    old = (now - timedelta(days=1)).timestamp()
    os.utime(base_csv, (old, old))
    return base


if __name__ == "__main__":
    print("pasta de demonstração:", seed())
