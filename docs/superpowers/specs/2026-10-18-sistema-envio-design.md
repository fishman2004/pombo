# Sistema de Envio — Documento de Design

**Data:** 18/10/2026 · **Autor:** Kayo Ibiapino (analista de dados, Polybalas) · **Status:** aguardando aprovação

> Legenda: o que o Kayo decidiu está escrito como decisão. O que foi escolha do Claude (assistente) está marcado com **[escolha do Claude]** e pode ser contestado.

---

## 1. Por que existe

Todo dia útil, depois que a empresa fecha (17h30), o analista atualiza os relatórios em Excel e distribui à mão:

- **E-mail:** pelo Thunderbird, montando listas e copiando e colando sempre a mesma mensagem e o anexo.
- **WhatsApp:** reenviando o mesmo arquivo, um contato ou grupo por vez.

Isso leva **cerca de 10 minutos por rodada**, é repetitivo e **às vezes alguém fica de fora**. Existe ainda uma rodada que **ninguém faz**: uma atualização no meio do dia, por volta das 14h, porque toma tempo demais.

O sistema faz essa distribuição sozinho, no horário certo, para as pessoas certas, e **nunca manda número velho sem avisar**.

O projeto tem dois objetivos de mesmo peso:

1. **Resolver o problema real** do analista, com custo zero.
2. **Ser vitrine.** O projeto deve impressionar a Polybalas (para ser adotado pela equipe) e empresas futuras (portfólio). Por isso a **documentação faz parte do produto**.

## 2. Objetivos, não-objetivos e anti-objetivos

### Objetivos (esta versão)
- Cadastrar **envios**: quais arquivos, para quem (e-mail e WhatsApp), em quais dias e horários e com qual mensagem.
- Disparar os envios automaticamente no horário, e também na hora, por um botão.
- **Checar se o arquivo foi atualizado** antes de enviar (regra na seção 5.3).
- Registrar **cada envio num histórico** que pode ser lido depois por outras ferramentas (painel da equipe, hub "API").
- Mostrar o dia numa **linha do tempo**: o que saiu, o que está esperando, o que falhou e o que vem depois.
- Instalar e rodar no PC da empresa **sem permissão de administrador**.
- Repositório público no GitHub **apenas com dados fictícios**.

### Não-objetivos (ficam para depois, mas o desenho não impede)
- Atualizar os Excels/queries automaticamente (fase 2).
- Power BI (fase 3).
- Painel da equipe e hub "API" na TV (fase 4, ver seção 11).
- Vários usuários com login no mesmo programa.
- Rodar na nuvem ou com o PC desligado.
- Implementar a API oficial do WhatsApp (só documentada como caminho de upgrade).
- Envios de fim de semana fazem parte da rotina do analista. O agendador aceita qualquer dia; o repasse ao chefe é só documentado.

### Anti-objetivos (se acontecer, o projeto falhou mesmo "funcionando")
- **Mandar relatório desatualizado sem ninguém saber.**
- **Mandar para a pessoa ou o grupo errado.**
- **Vazar dados reais** (vendedores, clientes, valores) **ou senhas** no GitHub.
- **Ter o número de WhatsApp bloqueado** por comportamento de spam.
- Exigir administrador, servidor ou qualquer gasto.
- Ser tão complexo que o analista não consiga manter ou explicar numa entrevista.

## 3. Restrições

| Restrição | Consequência |
|---|---|
| Sem dinheiro | Só ferramentas gratuitas e de código aberto. |
| Desenvolvimento no PC pessoal, execução no PC da empresa | Instalação = baixar do GitHub + configurar + executar. Os dois PCs não se conectam. |
| Sem administrador no PC da empresa (mas pode instalar apps por usuário) | Python instalado "só para o usuário"; dependências dentro da pasta do projeto; início automático pela pasta "Inicializar" do usuário. |
| Sem acesso ao banco de dados (só Winthor/TARGIT → arquivos) | O sistema trabalha só com **pastas e arquivos**. |
| O analista está aprendendo a programar | Código simples, legível, comentado onde importa; construção em etapas pequenas. |
| Rede corporativa pode bloquear SMTP ou WhatsApp Web | **Primeira etapa da construção é testar isso no PC da empresa** (seção 10). |
| PC precisa estar ligado e o programa aberto no horário | O PC do analista **fica sempre ligado** (só reinicia às vezes). Por isso: o programa **inicia com o Windows** (ligado por padrão), **impede o PC de entrar em suspensão** enquanto roda (API do Windows, sem admin) **[escolha do Claude]** e recupera envios perdidos após reinício (seção 5.5). A limitação continua documentada para quem desliga o PC. |

## 4. Como funciona (visão geral)

```
 Pasta de relatórios        ┌───────────── Sistema de Envio (roda no PC do analista) ─────────────┐
 definitivos (rede ou       │                                                                      │
 local)                     │  Tela (navegador, só localhost)                                      │
  Vendas.xlsx  ───────────► │   linha do tempo · cadastro de envios · contatos · histórico         │
  Plano.xlsx                │                                                                      │
                            │  Agendador ──► Checagem de atualização ──► Canais de envio           │
                            │                                             ├─ E-mail (SMTP)         │
                            │                                             └─ WhatsApp (peça        │
                            │                                                trocável)             │
                            │                         │                                            │
                            │                         ▼                                            │
                            │               Histórico de envios (CSV) ─────────────────────────────┼──► futuro: painel
                            └──────────────────────────────────────────────────────────────────────┘     da equipe / hub "API"
```

### 4.1 Escolhas de tecnologia **[escolha do Claude]**
- **Python 3.12+.** Já instalado. É a linguagem padrão em dados e a melhor para controlar o Excel na fase 2.
- **Tela web local**, aberta no navegador e servida só em `127.0.0.1`. Nada fica exposto na rede. Isso também prepara o hub da TV, que será uma página web.
- **E-mail:** biblioteca padrão do Python (`smtplib` / `email`), sem dependência extra.
- **Senhas:** guardadas no **Gerenciador de Credenciais do Windows** (biblioteca `keyring`, sem admin), nunca em arquivo de texto. A opção menor seria um arquivo `.env` ignorado pelo Git; o Gerenciador de Credenciais custa pouco a mais e conta pontos na apresentação.
- **Agendador:** dentro do próprio programa (ex.: APScheduler), sem o Agendador de Tarefas do Windows.
- Framework web, biblioteca de agendamento exata e estilo visual: **ficam com o construtor**, respeitando "simples de aprender" e "sem etapa de build de JavaScript".

### 4.2 Peça trocável de canal **[escolha do Claude]**
E-mail e WhatsApp são **canais**. Cada canal é uma peça com a mesma forma: recebe a mensagem, os arquivos e um destinatário e devolve "enviado" ou "falhou + motivo". O resto do sistema não sabe como cada canal funciona por dentro.

Isso não é generalização por capricho: é o argumento central da documentação. **Migrar para a API oficial do WhatsApp é trocar uma peça, não refazer o sistema.** O mesmo vale para trocar de servidor de e-mail.

## 5. Comportamento

### 5.1 Envio (o cadastro)
Cada envio tem:
- **Nome**, ex.: "Vendas Diárias".
- **Arquivos:** um ou mais caminhos fixos. Os arquivos são sobrescritos a cada atualização, no padrão de nome do analista, ex.: `(DADOS) - 8081 - Descrição`. Caminhos de rede (`S:\...` ou `\\servidor\...`) são aceitos.
- **Destinatários:** contatos e listas de e-mail; contatos e grupos de WhatsApp.
- **Quando:** dias da semana + um ou mais horários (ex.: seg–sex, 18:00; futuramente também 14:00).
- **Mensagem:** texto com campos automáticos: `{saudacao}` (Bom dia/Boa tarde/Boa noite), `{data}`, `{hora}`, `{arquivos}`. **Assunto do e-mail** também com esses campos.
- **Checagem de atualização:** ligada por padrão; pode ser desligada para arquivos que não mudam todo dia.
- **Ativo/pausado.**

**Contatos:** nome, e-mail (opcional) e WhatsApp (opcional). **Listas de e-mail:** grupos de contatos com nome. **Grupos de WhatsApp:** escolhidos na lista de grupos da conta conectada, nunca digitados à mão, para evitar errar o destino.

### 5.2 Como cada canal entrega
- **E-mail:** um único e-mail para a lista, com todos os arquivos anexados. Destinatários em **Para** ou **Cco** (definido por envio). Remetente: a conta do analista no servidor `mail.polybalas.com.br`.
- **WhatsApp:** para cada contato/grupo, envia os arquivos como documento, com a mensagem como legenda do primeiro arquivo. Remetente: o **número corporativo** do analista (decisão do Kayo), conectado como "aparelho conectado". O número pessoal nunca é usado, então um eventual bloqueio não atinge o WhatsApp pessoal. Esse número precisa fazer parte dos grupos de destino.
- Antes de enviar, confere se o arquivo existe, não está vazio, não está aberto/travado pelo Excel e cabe no limite do servidor de e-mail. **[escolha do Claude: 20 MB por e-mail, configurável]**

### 5.3 Regra do arquivo atualizado (decidida pelo Kayo)
No horário do envio:
1. Se o arquivo foi **atualizado**, envia.
2. Se não, **não envia**. Confere de novo **a cada 15 minutos, por até 1 hora**.
3. Se depois de 1 hora continua desatualizado: **desiste e avisa só o analista**, com notificação do Windows + e-mail para ele mesmo. Na linha do tempo aparece o botão **"Enviar mesmo assim"**.

**O que conta como "atualizado"** **[escolha do Claude]**: o arquivo foi modificado **hoje** *e* **depois do último envio bem-sucedido desse mesmo envio**. Isso importa quando houver duas rodadas no dia (14h e 18h): o arquivo atualizado ao meio-dia não pode "passar" de novo às 18h sem ter sido atualizado outra vez. Com vários arquivos, **todos** precisam estar atualizados.

### 5.4 Falhas
- Cada destinatário tem resultado próprio. Se o e-mail sai e o WhatsApp falha, o histórico mostra exatamente isso.
- Falha de rede ou servidor: tenta de novo **3 vezes, a cada 5 minutos** **[escolha do Claude]**. Depois disso, avisa o analista do mesmo jeito que na regra 5.3.
- **Nunca reenvia o que já saiu.** Um novo disparo manda só para quem falhou.
- WhatsApp desconectado (sessão expirou): o envio fica "esperando conexão", o analista é avisado e a tela mostra o QR code para reconectar.

### 5.5 Programa fechado ou PC desligado no horário **[escolha do Claude]**
Ao abrir, o programa procura envios de **hoje** que deveriam ter saído e não saíram:
- Se o horário passou **há menos de 2 horas**, executa agora, seguindo a regra 5.3.
- Se passou mais do que isso, **não envia sozinho**: marca como "perdido" na linha do tempo e oferece "Enviar agora".

### 5.6 Proteções contra bloqueio do WhatsApp
- Pausa de alguns segundos entre mensagens (valor exato fica com o construtor).
- Só envia para contatos e grupos cadastrados.
- Envio de teste "só para mim" disponível em todo cadastro.
- A documentação deixa claro: é para uso interno, com pessoas que conhecem o número. Não serve para disparo em massa.

### 5.7 Modo demonstração **[escolha do Claude]**
Uma chave na configuração faz o programa executar tudo (agendar, checar, montar mensagens, gravar histórico) **sem enviar de verdade**. Serve para apresentar o projeto, testar no PC pessoal e gravar vídeos para o portfólio sem perturbar ninguém.

## 6. Telas

Escolha do Kayo: **a tela principal é a linha do tempo do dia** (ver rascunho em `.superpowers/brainstorm/`).

1. **Hoje (principal):** horários do dia em ordem, com o status de cada envio: ✔ enviado (hora, quantos destinatários), ⏳ esperando atualização (até que horas), ✖ falhou (motivo), ○ agendado, ⚠ perdido. Botões de contexto: "Enviar mesmo assim", "Tentar de novo", "Enviar agora". Mostra também o que vem amanhã.
2. **Envios:** lista + formulário de cadastro (seção 5.1), com "Enviar teste só para mim".
3. **Contatos:** contatos, listas de e-mail e grupos de WhatsApp.
4. **Histórico:** tabela filtrável (data, envio, canal, destinatário, status).
5. **Configurações:** nome do analista, conta de e-mail (servidor, porta, segurança; a senha vai para o Gerenciador de Credenciais), conexão do WhatsApp (QR code), pasta do histórico, modo demonstração, iniciar com o Windows.

Interface em **português**.

## 7. Dados e arquivos

| O quê | Onde | Vai para o GitHub? |
|---|---|---|
| Código, documentação, testes | pasta do projeto | Sim |
| Dados fictícios de exemplo (espelham a base real) | `exemplos/` | Sim |
| Cadastro de envios e contatos | pasta de dados do usuário, fora do código **[escolha do Claude]** | Não |
| Histórico de envios | pasta configurável (local hoje, rede compartilhada depois) | Não |
| Sessão do WhatsApp | pasta de dados do usuário | Não |
| Números de telefone e e-mails reais | só no cadastro local | Não (nem na documentação) |
| Senha do e-mail | Gerenciador de Credenciais do Windows | Não |
| Relatórios reais | onde já estão hoje (o programa só lê) | Não |

O `.gitignore` também cobre `.superpowers/`, a pasta de rascunhos visuais.

### 7.1 Histórico de envios: o contrato com o futuro
Um arquivo **CSV** por analista por mês, ex.: `historico/kayo/2026-10.csv` **[escolha do Claude]**. É CSV porque o chefe pode abrir no Excel, o Power BI lê direto e vários PCs podem gravar cada um no seu arquivo dentro de uma pasta de rede, sem banco de dados. Codificação UTF-8 com BOM, para o Excel abrir os acentos certos.

Uma linha por **destinatário por tentativa**, com colunas:
`data_hora, analista, envio, horario_agendado, canal, destinatario, arquivos, status, detalhe`
com `status` ∈ `enviado | falhou | esperando | desistiu | perdido | demonstracao`.

Esse formato é o que o painel da equipe e o hub "API" vão ler. **Mudanças nele devem ser compatíveis com versões anteriores** (só acrescentar colunas no final).

### 7.2 Dados fictícios
Um gerador cria planilhas e um CSV de exemplo com **as mesmas colunas da rotina 8081**:
`ID RCA, NOME RCA, NOME SUPERVISOR, NUMERO PEDIDO, POSICAO PED, DATA PEDIDO, ID CLIENTE, CLIENTE, ID PRODUTO, NOME PRODUTO, ID FORNECEDOR, NOME FORNECEDOR, QTDE CX, QTDE UND, VALOR, QTDE CX VENDIDA`
com nomes, clientes e valores **inventados**. Nenhum nome real aparece no repositório.

## 8. Instalação (o que o usuário final vê)

1. Instalar o Python "só para mim", sem admin. O README tem passo a passo com prints.
2. Baixar o projeto do GitHub (zip ou `git clone`).
3. Dois cliques em `instalar.bat`: cria o ambiente e instala as dependências dentro da pasta.
4. Dois cliques em `iniciar.bat`: abre o programa no navegador.
5. Na tela de Configurações: conta de e-mail, QR code do WhatsApp, nome do analista e "iniciar com o Windows".

Uma versão 100% portátil, com o Python embutido no zip, **fica como plano B** se a TI bloquear a instalação do Python.

## 9. Documentação (parte do produto)

Em português, no repositório:
- **README:** o problema, a solução, prints/GIF, instalação em 5 passos.
- **Ganho de tempo:** ~10 min por rodada × ~21 dias úteis ≈ **3,5 h/mês ≈ 42 h/ano por analista** só na rodada das 18h, sem contar os erros evitados e a rodada das 14h que passa a ser possível. O documento mostra a conta, para a empresa adaptar ao número de analistas.
- **Arquitetura:** o diagrama da seção 4, explicado.
- **WhatsApp: hoje vs. com investimento.** Por que a automação do WhatsApp Web (custo zero), quais os riscos (termos de uso, bloqueio, quebra quando o WhatsApp muda) e como migrar para a **API oficial da Meta**: número dedicado, verificação da empresa, modelos de mensagem aprovados, cobrança por conversa e limitações com grupos. **Valores e regras devem ser pesquisados na data da escrita**, com a fonte citada. Destaque: a migração é trocar uma peça (seção 4.2).
- **Limitações conhecidas:** PC ligado e programa aberto; fins de semana (como o chefe pode assumir); dependência do WhatsApp Web.
- **Roadmap:** seção 11.
- **Segurança e dados:** o que nunca vai para o GitHub e por quê.

## 10. Riscos e como reduzi-los

| Risco | Redução |
|---|---|
| Rede da empresa bloqueia SMTP (portas 465/587) ou WhatsApp Web | **Etapa 1 da construção:** um script mínimo de teste que manda um e-mail e uma mensagem de WhatsApp **do PC da empresa**, antes de construir o resto. |
| Biblioteca de WhatsApp quebra quando o WhatsApp muda | Canal isolado (4.2); falha vira aviso, não perda silenciosa; documentação explica. |
| Número bloqueado | Seção 5.6. |
| Excel com o arquivo aberto na hora do envio | Checagem antes de enviar (5.2); conta como "não pronto" e entra na espera da regra 5.3. |
| TI bloqueia instalação do Python | Plano B portátil (seção 8). |
| Empresa não sabia que há automação rodando no PC dela | **[escolha do Claude]** Apresentar ao gestor antes de ligar os envios reais; a documentação deste projeto é o material para essa conversa. |

### 10.1 WhatsApp: escolha da biblioteca (fica com o construtor, depois de um teste prático)
Candidatas conhecidas: bibliotecas Python que falam o protocolo do WhatsApp sem navegador (ex.: as baseadas em *whatsmeow*), ou bibliotecas Node que controlam o WhatsApp Web (ex.: *whatsapp-web.js*). Critérios, nessa ordem:
1. Funciona **sem admin** no PC da empresa e passa pela rede corporativa.
2. Envia **documento para grupo** e para contato.
3. Mantém a sessão depois de reiniciar o PC, sem pedir QR code de novo.
4. Lista os grupos da conta, para a tela de contatos.
5. Prefira Python puro; trazer o Node só se for claramente mais confiável.

## 11. Roadmap (aparece na documentação)

1. **Envio automático:** este documento.
2. **Atualização automática dos Excels** antes do envio: abrir, atualizar as queries, salvar. **Isso libera a rodada das 14h.**
3. **Power BI:** usar a base CSV da rotina 8081 como fonte.
4. **Painel da equipe → Hub "API" (Analistas da Polybalas Integrados):** um app na TV da sala que mostra, por analista: presença, envios feitos (lidos do histórico, seção 7.1), tarefas em andamento, status de reunião e avisos sonoros na tela (ex.: "enviar o PHD", "transferir pedidos") com confirmação de feito. Cada analista configura o próprio perfil. O histórico de envios gravado na rede compartilhada é a **primeira fonte de dados** desse hub.

## 12. Fica a critério do construtor
- Framework web, biblioteca de agendamento e biblioteca de notificações do Windows.
- Biblioteca de WhatsApp (pelos critérios de 10.1).
- Estrutura de pastas do código e formato do arquivo de cadastro.
- Estilo visual, dentro de: claro, legível, em português, linha do tempo como tela principal.
- Pausa exata entre mensagens de WhatsApp.
- Nomes no código: **[escolha do Claude]** identificadores em inglês, comentários e documentação em português.

## 13. Testes
- Testes automáticos (pytest) para as regras que mais podem errar: "arquivo atualizado" (5.3, incluindo duas rodadas no dia), envio perdido (5.5), "nunca reenviar o que já saiu" (5.4), campos da mensagem e gravação do histórico.
- Canais testados com versões falsas (sem enviar de verdade).
- Teste manual de ponta a ponta no **modo demonstração** e depois com o "Enviar teste só para mim".
