# Sistema de Envio — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Programa local em Python que envia arquivos (planilhas) por e-mail e WhatsApp em horários agendados, só quando o arquivo foi atualizado, registrando tudo num histórico CSV.

**Architecture:** Um processo Python roda um servidor web local (FastAPI, só `127.0.0.1`) para as telas e uma thread de "motor" que a cada 30 s decide o que enviar. As regras de decisão são funções puras testáveis. O estado dos envios é **derivado do histórico CSV** (fonte única da verdade), então reiniciar o PC nunca causa reenvio. Canais (e-mail, WhatsApp) são peças trocáveis com a mesma interface.

**Tech Stack:** Python 3.12+, FastAPI + Uvicorn + Jinja2 + HTMX (arquivo local, sem build de JS), `smtplib` (stdlib), `keyring`, `win11toast`, `openpyxl` (só para gerar exemplos), biblioteca de WhatsApp escolhida na Task 1, pytest + httpx.

**Spec:** `docs/superpowers/specs/2026-10-18-sistema-envio-design.md`

## Global Constraints

- Python **3.12+**; deve rodar no Windows **sem administrador**. Nada de serviços do Windows, Agendador de Tarefas ou registro HKLM.
- Servidor web escuta **só em `127.0.0.1`**, porta **8765**.
- Interface em **português**; identificadores do código em **inglês**; comentários e documentação em **português**.
- Regra de atualização: arquivo modificado **hoje** *e* **depois do último envio bem-sucedido do mesmo envio**; todos os arquivos do envio precisam passar.
- Checagens de atualização em `agendado + 0, 15, 30, 45, 60 min`; se no de 60 min ainda não estiver pronto → `desistiu` + aviso **uma vez**.
- Falha de envio: **3 novas tentativas, a cada 5 min** (4 tentativas no total), depois aviso **uma vez**.
- Envio sem nenhum registro e com horário passado há **mais de 2 h** → `perdido`, não envia sozinho.
- Limite de anexos por e-mail: **20 MB** (configurável).
- Histórico: um CSV por analista por mês em `<pasta_historico>/<analista_slug>/<AAAA-MM>.csv`, codificação **`utf-8-sig`**, colunas nesta ordem: `data_hora, analista, envio, horario_agendado, canal, destinatario, arquivos, status, detalhe, envio_id` (as 9 da spec + `envio_id` acrescentada no fim). `status` ∈ `enviado | falhou | esperando | desistiu | perdido | demonstracao`. Só acrescentar colunas no fim, nunca reordenar.
- `horario_agendado` no CSV: `AAAA-MM-DD HH:MM` para rodadas agendadas e `manual AAAA-MM-DD HH:MM:SS` para manuais.
- Senha do e-mail só no Gerenciador de Credenciais do Windows (`keyring`, serviço `"sistema-envio"`, usuário = login SMTP). Nunca em arquivo.
- Cadastro, histórico, sessão do WhatsApp e dados reais **nunca** dentro do repositório. Pasta de dados: `%LOCALAPPDATA%\SistemaEnvio` (sobrescrevível pela variável `SISTEMA_ENVIO_DADOS`, usada nos testes).
- Repositório só com dados fictícios. Colunas dos exemplos = rotina 8081: `ID RCA, NOME RCA, NOME SUPERVISOR, NUMERO PEDIDO, POSICAO PED, DATA PEDIDO, ID CLIENTE, CLIENTE, ID PRODUTO, NOME PRODUTO, ID FORNECEDOR, NOME FORNECEDOR, QTDE CX, QTDE UND, VALOR, QTDE CX VENDIDA`.
- Campos de mensagem: `{saudacao}` (antes das 12h "Bom dia", antes das 18h "Boa tarde", senão "Boa noite"), `{data}` `dd/mm/aaaa`, `{hora}` `HH:MM`, `{arquivos}` (nomes separados por ", "). Campo desconhecido fica como está, sem erro.
- Commits sem linhas de atribuição.

## Review Focus

1. **Duas instâncias abertas** (duplo clique duas vezes no `iniciar.bat`): a segunda não pode iniciar outro motor, ou cada envio sai em dobro. Ela só abre o navegador na primeira e sai. *Teste na Task 9.*
2. **Histórico CSV aberto no Excel pelo chefe** (o arquivo fica travado): gravar não pode perder linha nem derrubar o programa, e a próxima rodada não pode reenviar por "não ver" o que já saiu. *Teste na Task 4.*
3. **Unidade de rede indisponível** (`S:` desconectada depois de reiniciar): conta como "arquivo não pronto" e entra na espera de 1 h. Não pode virar exceção na thread do motor. *Teste na Task 3.*
4. **Nomes com acento e parênteses** (`(DADOS) - 8081 - Descrição.xlsx` em `Área de Trabalho`): o anexo tem que chegar com o nome certo. *Teste na Task 5.*
5. **WhatsApp desconectado e e-mail funcionando:** o e-mail sai; o WhatsApp fica `esperando` ("WhatsApp desconectado") sem gastar as 4 tentativas, com aviso uma vez, e envia quando reconectar. *Teste na Task 7.*

---

## Estrutura de arquivos

```
sistema-envio/
  sistema_envio/
    __init__.py
    __main__.py          # Task 9: inicia servidor + motor, instância única, abre navegador
    paths.py             # Task 2: pastas de dados
    models.py            # Task 2: Contact, EmailList, WhatsAppGroup, Dispatch, Settings, Registry
    store.py             # Task 2: lê/grava cadastro.json
    rules.py             # Task 3: regras puras (horários, atualização, mensagem, slots)
    files.py             # Task 3: checagem de arquivo (existe, vazio, travado, mtime)
    history.py           # Task 4: CSV de histórico
    channels/
      __init__.py        # Task 5: Channel, Target, SendError, ChannelUnavailable
      email.py           # Task 5
      whatsapp.py        # Task 6
    engine.py            # Task 7: motor
    alerts.py            # Task 8: notificação Windows + e-mail para si
    winsys.py            # Task 8: impedir suspensão, iniciar com o Windows
    web/
      app.py             # Tasks 10–12
      templates/         # Jinja2
      static/            # htmx.min.js (vendorizado), estilo.css
  tools/
    connection_test.py   # Task 1
    make_examples.py     # Task 13
  exemplos/              # Task 13 (fictícios)
  tests/
  docs/                  # Task 14
  instalar.bat  iniciar.bat  requirements.txt  requirements-dev.txt  .gitignore  README.md
```

---

### Task 1: Base do projeto + teste de conexão no PC da empresa

Primeiro risco do projeto (spec §10): a rede da empresa pode bloquear SMTP ou WhatsApp. Esta task decide a biblioteca de WhatsApp.

**Files:**
- Create: `.gitignore`, `requirements.txt`, `requirements-dev.txt`, `sistema_envio/__init__.py`, `tools/connection_test.py`, `docs/decisoes.md`, `tests/test_smoke.py`

**Interfaces:**
- Produces: decisão registrada em `docs/decisoes.md` ("Biblioteca de WhatsApp: X, porque…"), usada na Task 6.

- [ ] **Step 1:** `git init`. O `.gitignore` cobre: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.superpowers/`, `*.csv` fora de `exemplos/`, `*.xlsx` fora de `exemplos/`, `whatsapp-sessao*/`, `.env`.
- [ ] **Step 2:** `tests/test_smoke.py` com `def test_package_imports(): import sistema_envio`. Rodar `python -m pytest -q`. Esperado: `1 passed`.
- [ ] **Step 3:** Escrever `tools/connection_test.py` (script interativo, sem testes automáticos). Ele pergunta servidor, porta, segurança (SSL/STARTTLS), usuário e senha (`getpass`). Envia um e-mail com `exemplos/teste.txt` anexado para o próprio usuário e imprime `E-MAIL OK` ou o erro completo. Depois, para cada biblioteca candidata instalada, conecta por QR code (impresso no terminal ou salvo como PNG), lista os grupos e envia um documento para um número informado. Imprime `WHATSAPP OK (<biblioteca>)` ou o erro. Candidatas, nesta ordem: `neonize` (Python, protocolo whatsmeow); se falhar, `whatsapp-web.js` via um script Node de 20 linhas em `tools/wa_test.js`.
- [ ] **Step 4 (manual, pelo Kayo, no PC da empresa):** instalar o Python "só para mim", baixar a pasta, rodar `python tools/connection_test.py` com o número corporativo. Esperado: `E-MAIL OK` e `WHATSAPP OK (...)`. Anotar porta e segurança que funcionaram.
- [ ] **Step 5:** Registrar em `docs/decisoes.md`: biblioteca escolhida e motivo pelos critérios da spec §10.1, configuração SMTP que funcionou (sem senha) e problemas encontrados. Se nada passar, **parar e voltar ao Kayo** antes de seguir.
- [ ] **Step 6:** Commit `chore: base do projeto e teste de conexão`.

---

### Task 2: Modelos e cadastro

**Files:**
- Create: `sistema_envio/paths.py`, `sistema_envio/models.py`, `sistema_envio/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Produces:
  - `paths.data_dir() -> Path` (`SISTEMA_ENVIO_DADOS` ou `%LOCALAPPDATA%\SistemaEnvio`, criada se não existir)
  - Pydantic models:
    - `Contact(id: str, name: str, email: str | None = None, whatsapp: str | None = None)`
    - `EmailList(id: str, name: str, contact_ids: list[str])`
    - `WhatsAppGroup(id: str, name: str)`: `id` é o identificador vindo da biblioteca, nunca digitado
    - `Schedule(weekdays: set[int], times: list[time])`, com `weekdays` 0=segunda…6=domingo
    - `Dispatch(id: str, name: str, files: list[Path], email_list_ids: list[str], email_contact_ids: list[str], whatsapp_contact_ids: list[str], whatsapp_group_ids: list[str], schedule: Schedule, subject: str, message: str, use_bcc: bool = True, check_freshness: bool = True, active: bool = True)`
    - `Settings(analyst_name: str = "", smtp_host: str = "", smtp_port: int = 465, smtp_security: Literal["ssl","starttls"] = "ssl", smtp_user: str = "", self_email: str = "", self_whatsapp: str = "", history_dir: Path | None = None, max_email_mb: int = 20, demo_mode: bool = False, start_with_windows: bool = True)`
    - `Registry(settings: Settings, contacts: list[Contact], email_lists: list[EmailList], whatsapp_groups: list[WhatsAppGroup], dispatches: list[Dispatch])`
  - `Store(path: Path)` com `.load() -> Registry`, `.save(reg: Registry) -> None` (gravação atômica: arquivo temporário + `os.replace`) e `.history_dir() -> Path` (`settings.history_dir` ou `data_dir()/"historico"`)
  - `new_id() -> str` (uuid4 hex curto, 8 caracteres)

- [ ] **Step 1: Testes**
```python
def test_load_missing_file_returns_empty_registry(tmp_path):
    reg = Store(tmp_path / "cadastro.json").load()
    assert reg.dispatches == [] and reg.settings.max_email_mb == 20

def test_roundtrip_keeps_accented_paths(tmp_path):
    s = Store(tmp_path / "cadastro.json")
    d = Dispatch(id="a1", name="Vendas Diárias",
                 files=[Path(r"S:\Relatórios\(DADOS) - 8081 - Descrição.xlsx")],
                 email_list_ids=[], email_contact_ids=[], whatsapp_contact_ids=[], whatsapp_group_ids=[],
                 schedule=Schedule(weekdays={0,1,2,3,4}, times=[time(18,0)]),
                 subject="Vendas {data}", message="{saudacao}!")
    s.save(Registry(settings=Settings(), contacts=[], email_lists=[], whatsapp_groups=[], dispatches=[d]))
    assert s.load().dispatches[0] == d

def test_save_is_atomic(tmp_path, monkeypatch):
    # se a gravação falhar no meio, o arquivo antigo continua intacto
    ...  # monkeypatch os.replace para lançar OSError; arquivo original deve continuar com o conteúdo anterior
```
- [ ] **Step 2:** `python -m pytest tests/test_store.py -v`. Esperado: FAIL (imports).
- [ ] **Step 3:** Implementar `paths.py`, `models.py` e `store.py` conforme as interfaces. JSON em UTF-8, `ensure_ascii=False`.
- [ ] **Step 4:** Rodar os testes. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: modelos e cadastro`.

---

### Task 3: Regras puras e checagem de arquivo

**Files:**
- Create: `sistema_envio/rules.py`, `sistema_envio/files.py`
- Test: `tests/test_rules.py`, `tests/test_files.py`

**Interfaces:**
- Produces (`rules.py`):
  - `runs_for_day(schedule: Schedule, day: date) -> list[datetime]`: horários do dia, ordenados; vazio se o dia da semana não estiver em `weekdays`
  - `is_fresh(mtime: datetime, now: datetime, last_success: datetime | None) -> bool`
  - `check_slots(scheduled: datetime) -> list[datetime]`: `scheduled + [0,15,30,45,60] min`
  - `is_missed(scheduled: datetime, now: datetime) -> bool`: `now - scheduled > 2h`
  - `next_retry_at(failures: list[datetime]) -> datetime | None`: `None` se `len(failures) >= 4`; senão `failures[-1] + 5 min`
  - `render(template: str, now: datetime, files: list[Path]) -> str`
  - `greeting(now: datetime) -> str`
- Produces (`files.py`):
  - `@dataclass FileStatus(path: Path, ready: bool, reason: str, mtime: datetime | None, size: int)`
  - `inspect(path: Path) -> FileStatus`: `reason` ∈ `"ok" | "não encontrado" | "inacessível" | "vazio" | "aberto no Excel"`; nunca lança exceção

- [ ] **Step 1: Testes de `rules`**
```python
def test_runs_only_on_selected_weekdays():
    s = Schedule(weekdays={0,1,2,3,4}, times=[time(18,0), time(14,0)])
    assert runs_for_day(s, date(2026,10,19)) == [datetime(2026,10,19,14), datetime(2026,10,19,18)]  # segunda
    assert runs_for_day(s, date(2026,10,18)) == []  # domingo

def test_fresh_requires_today_and_after_last_success():
    now = datetime(2026,10,19,18,0)
    assert is_fresh(datetime(2026,10,19,17,50), now, None)
    assert not is_fresh(datetime(2026,10,18,17,50), now, None)                          # ontem
    assert not is_fresh(datetime(2026,10,19,13,50), now, datetime(2026,10,19,14,0))     # já foi às 14h
    assert is_fresh(datetime(2026,10,19,17,50), now, datetime(2026,10,19,14,0))

def test_check_slots_every_15_min_for_1h():
    assert check_slots(datetime(2026,10,19,18)) == [datetime(2026,10,19,18,m) for m in (0,15,30,45)] + [datetime(2026,10,19,19,0)]

def test_missed_after_two_hours():
    sch = datetime(2026,10,19,18)
    assert not is_missed(sch, datetime(2026,10,19,19,59))
    assert is_missed(sch, datetime(2026,10,19,20,1))

def test_retry_three_more_times_every_5_min():
    t = datetime(2026,10,19,18)
    assert next_retry_at([t]) == t + timedelta(minutes=5)
    assert next_retry_at([t, t+timedelta(minutes=5), t+timedelta(minutes=10), t+timedelta(minutes=15)]) is None

def test_render_fields_and_unknown_kept():
    now = datetime(2026,10,19,18,2)
    out = render("{saudacao}! {data} {hora} {arquivos} {xyz}", now, [Path("Vendas.xlsx"), Path("Plano.xlsx")])
    assert out == "Boa noite! 19/10/2026 18:02 Vendas.xlsx, Plano.xlsx {xyz}"

def test_greeting_boundaries():
    assert greeting(datetime(2026,10,19,11,59)) == "Bom dia"
    assert greeting(datetime(2026,10,19,12,0)) == "Boa tarde"
    assert greeting(datetime(2026,10,19,18,0)) == "Boa noite"
```
- [ ] **Step 2: Testes de `files`**: `inspect` retorna `ready=False` com `reason` certo para: arquivo inexistente; tamanho 0; existência de `~$Vendas.xlsx` na mesma pasta (`"aberto no Excel"`); `open(path, "r+b")` lançando `PermissionError` via monkeypatch (`"aberto no Excel"`); `OSError` ao consultar (simula `S:` desconectada) → `"inacessível"` (**Review Focus 3**); arquivo normal → `ready=True, reason="ok"`, `mtime` preenchido.
- [ ] **Step 3:** Rodar. Esperado: FAIL.
- [ ] **Step 4:** Implementar `rules.py` (`render` usa `str.format_map` com um dict que devolve `"{chave}"` para chaves ausentes) e `files.py`.
- [ ] **Step 5:** Rodar. Esperado: PASS.
- [ ] **Step 6:** Commit `feat: regras de agendamento, atualização e mensagem`.

---

### Task 4: Histórico CSV

**Files:**
- Create: `sistema_envio/history.py`
- Test: `tests/test_history.py`

**Interfaces:**
- Consumes: `Store.history_dir()`
- Produces:
  - `COLUMNS: tuple[str, ...]` (ordem da Global Constraints)
  - `@dataclass(frozen=True) Row(when: datetime, analyst: str, dispatch_name: str, run: str, channel: str, target: str, files: str, status: str, detail: str, dispatch_id: str)`. `run` é o texto de `horario_agendado`; `channel` ∈ `"email" | "whatsapp" | ""` (vazio em linhas da rodada inteira, como `esperando`/`desistiu`/`perdido` por arquivo)
  - `run_label(scheduled: datetime, manual: bool) -> str`
  - `class History(root: Path, analyst: str, pending_path: Path)`:
    - `.load(today: date) -> None`: lê o mês atual e o anterior para a memória; se o arquivo estiver travado, lança `HistoryLocked`
    - `.append(row: Row) -> None`: sempre entra na memória; tenta gravar no CSV. Se der `PermissionError`, grava em `pending_path` (local) e tenta de novo a cada `append`/`flush()`
    - `.flush() -> None`
    - `.rows_for_run(dispatch_id: str, run: str) -> list[Row]`
    - `.last_success(dispatch_id: str) -> datetime | None`: maior `when` com status `enviado` ou `demonstracao`
    - `.rows_between(start: date, end: date) -> list[Row]`
  - `analyst_slug(name: str) -> str`: minúsculas, sem acento, espaços viram `-`

- [ ] **Step 1: Testes**
  - `test_creates_monthly_file_with_bom_and_header`: depois de um `append`, o arquivo `kayo/2026-10.csv` começa com `b"\xef\xbb\xbf"`, a primeira linha é `COLUMNS` e o valor com vírgula e aspas faz o caminho de ida e volta pelo `csv`.
  - `test_rows_for_run_and_last_success`
  - `test_load_reads_previous_month_for_last_success`: sucesso em 30/09 é visível quando `today=2026-10-01`.
  - `test_locked_csv_keeps_rows_and_flushes_later` (**Review Focus 2**): monkeypatch faz a escrita no CSV lançar `PermissionError`. O `append` não lança; `rows_for_run` já vê a linha; `pending_path` contém a linha. Depois, sem o monkeypatch, `flush()` leva a linha ao CSV e esvazia o pendente.
  - `test_load_raises_when_locked`
  - `test_pending_rows_survive_restart`: novo `History` com o mesmo `pending_path` carrega os pendentes no `load`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar com o módulo `csv` (`newline=""`, `encoding="utf-8-sig"`, cabeçalho só em arquivo novo).
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: histórico de envios em CSV`.

---

### Task 5: Interface de canal + e-mail

**Files:**
- Create: `sistema_envio/channels/__init__.py`, `sistema_envio/channels/email.py`
- Test: `tests/test_email_channel.py`

**Interfaces:**
- Produces (`channels/__init__.py`):
  - `@dataclass(frozen=True) Target(channel: str, label: str, addresses: tuple[str, ...])`: para e-mail, `addresses` são os e-mails de uma lista/contato e `label` é o nome que vai para o histórico; para WhatsApp, um único id (número ou grupo)
  - `class SendError(Exception)`; `class ChannelUnavailable(SendError)` (canal fora do ar, não conta tentativa)
  - `class Channel(Protocol)`: `name: str`; `send(self, target: Target, subject: str, message: str, files: list[Path]) -> None` (lança `SendError`)
- Produces (`channels/email.py`): `EmailChannel(settings_getter: Callable[[], Settings], password_getter: Callable[[str], str | None])`; `name = "email"`. Lê as configurações a cada envio, então uma mudança na tela vale na hora.
- O `password_getter` real é `lambda user: keyring.get_password("sistema-envio", user)`, ligado na Task 9. Senha ausente → `SendError("senha do e-mail não configurada")`.

- [ ] **Step 1: Testes** (com um `FakeSMTP` via monkeypatch de `smtplib.SMTP_SSL`/`smtplib.SMTP`)
  - `test_sends_one_message_with_all_attachments_bcc`: `use_bcc=True` → `To` = o próprio remetente, destinatários reais no envelope (`send_message(..., to_addrs=...)`), nenhum em cabeçalho visível; 2 anexos.
  - `test_to_header_when_not_bcc`
  - `test_accented_attachment_filename` (**Review Focus 4**): arquivo `(DADOS) - 8081 - Descrição.xlsx` → `part.get_filename() == "(DADOS) - 8081 - Descrição.xlsx"`; tipo MIME `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
  - `test_over_size_limit_raises_send_error`: soma > `max_email_mb` → `SendError` com "maior que 20 MB"; nada é enviado.
  - `test_starttls_path`: `smtp_security="starttls"` usa `SMTP` + `starttls()`.
  - `test_network_error_becomes_send_error`: `OSError`/`smtplib.SMTPException` → `SendError`.
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar com `email.message.EmailMessage` + `add_attachment(..., filename=path.name)` + `mimetypes`.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: canal de e-mail`.

---

### Task 6: Canal de WhatsApp

**Files:**
- Create: `sistema_envio/channels/whatsapp.py`
- Test: `tests/test_whatsapp_channel.py`

**Interfaces:**
- Consumes: decisão da Task 1; `Target`, `SendError`, `ChannelUnavailable`
- Produces: `WhatsAppChannel(session_dir: Path)`, `name = "whatsapp"`, mais:
  - `.start() -> None`: conecta em segundo plano usando a sessão salva
  - `.status() -> Literal["conectado","desconectado","aguardando_qr"]`
  - `.qr_png() -> bytes | None`
  - `.list_groups() -> list[WhatsAppGroup]`
  - `.send(...)`: cada arquivo vai como documento; a `message` é a legenda do primeiro; pausa de **3 s** entre mensagens **[escolha do plano]**; lança `ChannelUnavailable` se `status() != "conectado"`
  - `normalize_phone(raw: str) -> str`: só dígitos, com `55` na frente se faltar (ex.: `"(83) 99999-0000"` → `"5583999990000"`)

- [ ] **Step 1: Testes**: `normalize_phone` (com/sem 55, com máscara); `send` com status desconectado → `ChannelUnavailable`; com um cliente falso injetado: 2 arquivos → 2 chamadas de documento, legenda só no primeiro, pausa chamada entre eles (injetar `sleep`).
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar envolvendo a biblioteca escolhida; o cliente real fica atrás de um pequeno adaptador interno para o teste injetar o falso. Sessão em `data_dir()/"whatsapp-sessao"`.
- [ ] **Step 4:** Rodar. Esperado: PASS.
- [ ] **Step 5 (manual):** script rápido conecta, lista grupos e envia um documento de teste para o número do Kayo. Esperado: arquivo chega com o nome correto.
- [ ] **Step 6:** Commit `feat: canal de WhatsApp`.

---

### Task 7: Motor

O coração do sistema. Todas as regras da spec §5.3–5.7 são verificadas aqui com relógio falso, canais falsos e arquivos em `tmp_path`.

**Files:**
- Create: `sistema_envio/engine.py`
- Test: `tests/test_engine.py`, `tests/fakes.py` (`FakeClock`, `FakeChannel(fail_times=0, unavailable=False)` que grava chamadas, `FakeAlerts`)

**Interfaces:**
- Consumes: `Store`, `History`, `rules.*`, `files.inspect`, `Channel`, `Target`
- Produces:
  - `class Alerts(Protocol)`: `notify(title: str, body: str) -> None`
  - `class Engine(store: Store, history: History, channels: dict[str, Channel], alerts: Alerts, clock: Callable[[], datetime] = datetime.now)`
    - `.tick() -> None`: thread-safe (`threading.Lock`); nunca deixa escapar exceção (registra em log e segue)
    - `.send_now(dispatch_id: str, scheduled: datetime | None = None) -> None`: `None` cria rodada manual; ignora a regra de atualização; nunca reenvia para alvos já com `enviado` naquela rodada
    - `.send_test(dispatch_id: str) -> list[tuple[str, str]]`: envia só para `self_email`/`self_whatsapp`, ignora atualização, **não grava histórico**; retorna `(canal, "ok" | erro)`
    - `.timeline(day: date) -> list[TimelineItem]`
    - `.targets_for(dispatch: Dispatch, reg: Registry) -> list[Target]`: um `Target` por lista de e-mail, um por contato de e-mail avulso, um por contato/grupo de WhatsApp
  - `@dataclass TimelineItem(scheduled: datetime, dispatch_id: str, dispatch_name: str, state: Literal["agendado","esperando","enviado","parcial","falhou","desistiu","perdido","manual"], detail: str, sent: int, total: int)`

**Comportamento por rodada (cada `tick`, para cada envio ativo e cada horário de hoje com `scheduled <= now`):**
1. Rodada sem nenhuma linha e `is_missed` → grava `perdido` (canal vazio) e não envia.
2. Se `check_freshness`: só avalia nos `check_slots` (guarda em memória o último slot avaliado por rodada; após reiniciar, avalia já no primeiro tick). Todos os arquivos `ready` e `is_fresh(mtime, now, history.last_success(id))`? Se não: na primeira vez grava `esperando` com o motivo; no slot de 60 min grava `desistiu` + `alerts.notify` **uma vez** e para.
3. Pronto: para cada alvo sem `enviado`/`demonstracao` nesta rodada, se a próxima tentativa já venceu (`next_retry_at` das falhas), envia. Em `demo_mode`, grava `demonstracao` sem chamar o canal. `SendError` grava `falhou`; na 4ª falha, `alerts.notify` uma vez. `ChannelUnavailable` grava `esperando` "WhatsApp desconectado" (não conta como falha), avisa uma vez por rodada e tenta de novo a cada 5 min.

- [ ] **Step 1: Testes** (relógio a partir de segunda 19/10/2026; envio seg–sex 18:00 com 1 lista de e-mail e 1 grupo de WhatsApp)
```python
def test_sends_at_time_when_fresh(): ...            # mtime 17:50; tick 17:59 → 0 envios; tick 18:00 → 2 envios, 2 linhas "enviado"
def test_stale_waits_and_sends_on_next_slot(): ...  # mtime ontem; tick 18:00 → 0 envios + 1 "esperando"; mtime=18:10; tick 18:10 → 0; tick 18:15 → 2
def test_gives_up_after_one_hour_alerts_once(): ... # mtime ontem; tick a cada minuto 18:00..19:10 → 0 envios, 1 "desistiu", alerts.calls == 1
def test_second_round_needs_new_update(): ...       # horários 14:00 e 18:00; mtime 13:50; 14:00 enviado; 18:00 → "esperando"
def test_all_files_must_be_fresh(): ...             # 2 arquivos, 1 velho → espera
def test_never_resends_after_restart(): ...         # histórico já tem "enviado" para a lista; novo Engine; tick 18:01 → só o grupo é enviado
def test_retries_three_times_every_5_min(): ...     # canal e-mail sempre falha; ticks 18:00..18:30 → 4 tentativas (18:00, 18:05, 18:10, 18:15), alerts == 1
def test_missed_run_not_sent_after_two_hours(): ... # sem linhas; primeiro tick 20:01 → "perdido", 0 envios; outro cenário: primeiro tick 19:59 → envia
def test_demo_mode_records_without_sending(): ...   # canais com 0 chamadas; linhas "demonstracao"; depois disso a rodada conta como concluída
def test_send_now_ignores_freshness_and_skips_sent(): ...
def test_paused_dispatch_does_nothing(): ...
def test_whatsapp_unavailable_email_still_sent(): ...  # Review Focus 5: e-mail "enviado"; whatsapp "esperando" sem contar falha; alerts == 1; reconectado às 18:05 → enviado
def test_tick_survives_unexpected_exception(): ...  # canal lança RuntimeError → tick não propaga; próxima rodada segue
def test_timeline_states(): ...                     # agendado / esperando / enviado / parcial / desistiu / perdido no mesmo dia
```
- [ ] **Step 2:** Rodar. Esperado: FAIL.
- [ ] **Step 3:** Implementar `engine.py`. As decisões ficam em funções pequenas que chamam `rules`; o estado vem de `history.rows_for_run`.
- [ ] **Step 4:** Rodar todos os testes. Esperado: PASS.
- [ ] **Step 5:** Commit `feat: motor de envios`.

---

### Task 8: Avisos e integração com o Windows

**Files:**
- Create: `sistema_envio/alerts.py`, `sistema_envio/winsys.py`
- Test: `tests/test_alerts.py`, `tests/test_winsys.py`

**Interfaces:**
- Produces:
  - `UserAlerts(settings_getter: Callable[[], Settings], email: EmailChannel | None, toast: Callable[[str, str], None])` implementa `Alerts`: chama o toast **e** envia um e-mail para `self_email`; falha de um não impede o outro, e nenhuma falha propaga
  - `winsys.keep_awake() -> None`: `ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)`; não faz nada fora do Windows
  - `winsys.startup_file() -> Path`: `%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SistemaEnvio.cmd`
  - `winsys.set_start_with_windows(enabled: bool, project_dir: Path) -> None`: cria/remove esse `.cmd` (conteúdo: `start "" /min "<project_dir>\iniciar.bat"`)

- [ ] **Step 1: Testes**: `UserAlerts` com toast que lança exceção ainda envia o e-mail; sem `self_email` só faz o toast; `set_start_with_windows` com `APPDATA` apontando para `tmp_path` cria e remove o arquivo com o conteúdo esperado.
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar (toast real: `win11toast.notify`). **Step 4:** Rodar → PASS.
- [ ] **Step 5:** Commit `feat: avisos e integração com o Windows`.

---

### Task 9: Inicialização, instância única e scripts de instalação

**Files:**
- Create: `sistema_envio/__main__.py`, `instalar.bat`, `iniciar.bat`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: tudo acima; `web.app.create_app(engine, store, whatsapp) -> FastAPI` (Task 10)
- Produces:
  - `acquire_single_instance(port: int = 8765) -> socket.socket | None`: faz bind em `127.0.0.1:port`; `None` se já estiver em uso
  - `main() -> None`: se `acquire_single_instance()` retornar `None`, abre `http://127.0.0.1:8765` no navegador e sai, **sem criar Engine** (**Review Focus 1**). Senão: `keep_awake()`; carrega o histórico (se `HistoryLocked`, tenta de novo a cada 30 s sem iniciar o motor, e a tela mostra o aviso); inicia o WhatsApp; inicia a thread do motor (`tick` a cada 30 s); sobe o Uvicorn usando o socket já aberto; abre o navegador.
- `instalar.bat`: `python -m venv .venv` e depois `.venv\Scripts\pip install -r requirements.txt`; mensagens em português; pausa no fim.
- `iniciar.bat`: `.venv\Scripts\pythonw.exe -m sistema_envio`.

- [ ] **Step 1: Testes**: `test_second_instance_exits_without_starting_engine`: segura a porta com um socket e chama `main()` com `webbrowser.open` e o construtor do `Engine` monkeypatchados. O navegador é chamado uma vez e o `Engine` nunca. Também `test_acquire_returns_socket_when_free`.
- [ ] **Step 2:** Rodar → FAIL. **Step 3:** Implementar. **Step 4:** Rodar → PASS.
- [ ] **Step 5 (manual):** numa pasta limpa, rodar `instalar.bat` e depois `iniciar.bat` duas vezes. Esperado: uma única janela/aba e um único processo `pythonw` com o motor.
- [ ] **Step 6:** Commit `feat: inicialização e instalação`.

---

### Task 10: Tela "Hoje" (linha do tempo)

**Files:**
- Create: `sistema_envio/web/app.py`, `web/templates/base.html`, `web/templates/hoje.html`, `web/templates/_timeline.html`, `web/static/htmx.min.js` (baixado de uma versão fixa e commitado), `web/static/estilo.css`
- Test: `tests/test_web_hoje.py`

**Interfaces:**
- Produces: `create_app(engine: Engine, store: Store, whatsapp: WhatsAppChannel | None) -> FastAPI`, com as rotas:
  - `GET /`: linha do tempo de hoje + bloco "Amanhã"; o menu tem Hoje · Envios · Contatos · Histórico · Configurações; faixa de aviso quando `demo_mode`, WhatsApp desconectado (com link "Reconectar" para o QR em Configurações) ou histórico travado
  - `GET /partials/timeline`: o mesmo trecho, recarregado pelo HTMX a cada 30 s
  - `POST /envios/{dispatch_id}/enviar-agora` (form `scheduled` opcional, ISO): chama `engine.send_now` e devolve o trecho atualizado
- Texto dos estados: `agendado` "○ agendado", `esperando` "⏳ esperando atualização (até HH:MM)", `enviado` "✔ enviado HH:MM", `parcial` "◐ enviado X de Y", `falhou` "✖ falhou: <motivo>", `desistiu` "⏳ não atualizado", `perdido` "⚠ perdido". Botões: "Enviar mesmo assim" (esperando/desistiu), "Tentar de novo" (falhou/parcial), "Enviar agora" (perdido e em todo item).

- [ ] **Step 1: Testes** (`TestClient` + `Engine` falso que devolve itens fixos): `GET /` contém "18:00", "Vendas Diárias" e "✔ enviado 18:02"; um item `desistiu` mostra "Enviar mesmo assim"; um `POST` de enviar-agora chama `send_now` com o id certo; com `demo_mode` aparece "Modo demonstração"; o servidor nunca é criado com host diferente de `127.0.0.1` (verificado na Task 9).
- [ ] **Step 2:** FAIL → **Step 3:** implementar → **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: tela Hoje`.

---

### Task 11: Tela "Envios" (cadastro + teste)

**Files:**
- Modify: `sistema_envio/web/app.py`
- Create: `web/templates/envios.html`, `web/templates/envio_form.html`
- Test: `tests/test_web_envios.py`

**Interfaces:**
- Rotas: `GET /envios`, `GET /envios/novo`, `GET /envios/{id}`, `POST /envios` (cria ou atualiza; campo `id` vazio = novo), `POST /envios/{id}/excluir`, `POST /envios/{id}/testar` (chama `engine.send_test` e mostra o resultado por canal).
- Formulário: nome; arquivos (um caminho por linha); listas e contatos de e-mail e contatos e grupos de WhatsApp (checkboxes vindos do cadastro); dias (seg…dom); horários (`HH:MM` separados por vírgula); assunto; mensagem (com a ajuda dos campos `{saudacao} {data} {hora} {arquivos}`); "Destinatários em cópia oculta"; "Só enviar se o arquivo foi atualizado"; "Ativo".
- Validação no servidor, com a mensagem em português exibida no formulário: nome obrigatório; ≥1 arquivo; ≥1 destinatário; ≥1 dia; horário inválido → "Horário inválido: 25:00". Arquivo que não existe **agora** gera só um aviso, não um erro, porque a unidade de rede pode estar fora.

- [ ] **Step 1: Testes**: criar via POST e conferir em `store.load()`; editar mantendo o id; validações acima com status 422 e a mensagem; excluir; testar chama `send_test`.
- [ ] **Step 2:** FAIL → **Step 3:** implementar → **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: cadastro de envios`.

---

### Task 12: Telas "Contatos", "Histórico" e "Configurações"

**Files:**
- Modify: `sistema_envio/web/app.py`
- Create: `web/templates/contatos.html`, `web/templates/historico.html`, `web/templates/configuracoes.html`
- Test: `tests/test_web_outros.py`

**Interfaces:**
- **Contatos:** CRUD de `Contact` (WhatsApp passa por `normalize_phone`; precisa de e-mail ou WhatsApp); CRUD de `EmailList`; `POST /grupos/atualizar` substitui `whatsapp_groups` por `whatsapp.list_groups()` (grupos não podem ser digitados). Excluir um contato ou grupo usado por um envio → erro "Usado em: Vendas Diárias".
- **Histórico:** `GET /historico?de=AAAA-MM-DD&ate=AAAA-MM-DD&envio=&canal=&status=`; padrão: últimos 7 dias; tabela da mais recente para a mais antiga.
- **Configurações:** campos de `Settings`. A senha vai por `keyring.set_password("sistema-envio", smtp_user, senha)` e nunca é gravada nem reexibida (o campo fica vazio = mantém a atual). O botão "Testar e-mail" manda para `self_email`. O WhatsApp mostra o status + QR (`GET /whatsapp/qr.png`). "Iniciar com o Windows" chama `set_start_with_windows`. Pasta do histórico: um texto com um caminho que precisa existir e ser gravável.

- [ ] **Step 1: Testes**: telefone normalizado ao salvar; contato sem e-mail e sem WhatsApp → 422; excluir contato em uso → mensagem com o nome do envio; `atualizar grupos` com WhatsApp falso; filtro do histórico por status; salvar configurações chama `keyring.set_password` (monkeypatch) e o `cadastro.json` **não contém** a senha; pasta de histórico inexistente → 422.
- [ ] **Step 2:** FAIL → **Step 3:** implementar → **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: contatos, histórico e configurações`.

---

### Task 13: Dados de exemplo fictícios + demonstração

**Files:**
- Create: `tools/make_examples.py`, `exemplos/(DADOS) - 8081 - Exemplo.csv`, `exemplos/Vendas.xlsx`, `exemplos/Plano_Excelencia.xlsx`
- Test: `tests/test_examples.py`

**Interfaces:**
- `make_examples(out_dir: Path, rows: int = 500, seed: int = 42) -> list[Path]`: gera o CSV com as 16 colunas da 8081 (separador `;`, `utf-8-sig`, data `dd/mm/aaaa`, valor com vírgula decimal, como o Winthor exporta) e duas planilhas resumidas (vendas por RCA; por fornecedor). Nomes de RCAs, supervisores, clientes, produtos e fornecedores vêm de listas inventadas no próprio script.

- [ ] **Step 1: Testes**: cabeçalho idêntico às 16 colunas; 500 linhas; mesma seed → mesmo arquivo; nenhum nome das listas aparece num conjunto de "nomes proibidos" (o teste lê os nomes reais de uma variável de ambiente opcional, `EXEMPLOS_PROIBIDOS`, para o Kayo rodar localmente; vazio = pula).
- [ ] **Step 2:** FAIL → **Step 3:** implementar → **Step 4:** PASS e gerar os arquivos.
- [ ] **Step 5:** Commit `feat: dados de exemplo fictícios`.

---

### Task 14: Documentação (parte do produto)

**Files:**
- Create/modify: `README.md`, `docs/arquitetura.md`, `docs/whatsapp-hoje-e-com-investimento.md`, `docs/ganho-de-tempo.md`, `docs/limitacoes.md`, `docs/roadmap.md`, `docs/seguranca-e-dados.md`, `docs/imagens/` (prints em modo demonstração com os exemplos)

Conteúdo exigido pela spec §9 e §11:
- **README:** problema, solução, GIF/prints, instalação em 5 passos (spec §8), link para cada doc.
- **arquitetura:** o diagrama da spec §4 + o caminho de um envio (agendador → checagem → canal → histórico) + a peça trocável de canal.
- **whatsapp-hoje-e-com-investimento:** automação atual vs. API oficial da Meta (número dedicado, verificação, modelos aprovados, preço por conversa no Brasil **pesquisado na data, com link da fonte**, limitações com grupos) e "migrar = escrever outra classe com a interface `Channel`".
- **ganho-de-tempo:** ~10 min × ~21 dias úteis ≈ 3,5 h/mês ≈ 42 h/ano por analista + a rodada das 14h que passa a ser possível; tabela para a empresa preencher com o número de analistas.
- **limitacoes:** PC ligado e programa aberto; fins de semana (como o chefe pode assumir); dependência do WhatsApp Web; uso interno, não disparo em massa.
- **roadmap:** fases 2–4, incluindo o hub "API" e o histórico CSV como fonte.
- **seguranca-e-dados:** o que nunca vai para o GitHub e onde fica cada coisa (tabela da spec §7).

- [ ] **Step 1:** Escrever os documentos.
- [ ] **Step 2:** Verificar que nenhum dado real vazou. O Kayo roda localmente `git grep -n -i -E "<padrões>"` com o domínio de e-mail da empresa, o número corporativo e os nomes de colegas/clientes, digitando na hora. Os padrões **nunca** são escritos em arquivo do repositório. Esperado: nenhum resultado além de menções intencionais. Conferir também com `git ls-files` que não há `.csv`/`.xlsx` fora de `exemplos/`.
- [ ] **Step 3:** Commit `docs: documentação do projeto`.

---

### Task 15: Aceite no PC da empresa (manual)

- [ ] **Step 1:** No PC da empresa, instalar pela documentação do README, seguindo só ela. Anotar e corrigir no README qualquer passo que travar.
- [ ] **Step 2:** Ligar o **modo demonstração**, cadastrar "Vendas Diárias" apontando para o arquivo real e esperar um horário. Esperado: linha do tempo `enviado` com linhas `demonstracao` no histórico e nenhuma mensagem enviada de verdade.
- [ ] **Step 3:** "Enviar teste só para mim". Esperado: e-mail e WhatsApp chegam ao Kayo com o anexo certo.
- [ ] **Step 4:** Desligar a demonstração com os destinatários reais, **depois de apresentar ao gestor** (spec §10). Acompanhar a primeira rodada das 18h.
- [ ] **Step 5:** Reiniciar o PC e conferir que o programa volta sozinho e não reenvia nada.
- [ ] **Step 6:** Publicar no GitHub (repositório criado pelo Kayo) depois de rodar de novo a verificação da Task 14 Step 2.
