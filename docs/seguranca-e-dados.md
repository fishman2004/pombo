# Segurança e dados

## Onde fica cada coisa

| O quê | Onde | Vai para o GitHub? |
|---|---|---|
| Código, documentação, testes | pasta do projeto | Sim |
| Dados de exemplo (**fictícios**, mesmas colunas da rotina 8081) | `exemplos/` | Sim |
| Cadastro de envios e contatos | `%LOCALAPPDATA%\Pombo\cadastro.json` | **Não** |
| Histórico de envios | pasta configurável (local ou rede) | **Não** |
| Sessão do WhatsApp | `%LOCALAPPDATA%\Pombo\whatsapp-sessao\` | **Não** |
| Senha do e-mail | **Gerenciador de Credenciais do Windows** | **Não** (nunca fica em arquivo) |
| Relatórios reais | onde já estão hoje; o Pombo só lê | **Não** |
| Telefones e e-mails reais | só no cadastro local | **Não** (nem na documentação) |

O `.gitignore` bloqueia `*.csv`, `*.xlsx`, `*.db` e pastas de sessão fora de `exemplos/`, para nenhum dado real ser publicado por engano.

## Rede

- As telas abrem **só em `127.0.0.1`**. Nenhum outro computador da rede consegue acessá-las.
- O Pombo só se conecta a dois lugares: o **servidor de e-mail** da empresa (SMTP com SSL/STARTTLS) e os **servidores do WhatsApp**.
- Sem nuvem, sem telemetria, sem terceiros.

## Senha

A senha do e-mail é digitada uma vez em Configurações e vai direto para o Gerenciador de Credenciais do Windows (`keyring`). Ela não aparece de volta na tela, não fica no `cadastro.json` e não vai para o log.

## Para conferir antes de publicar

Rode localmente, digitando os padrões na hora (nunca salve essa lista no repositório):

```bat
git grep -n -i -E "dominio-da-empresa|numero-corporativo|nome-de-colega"
git ls-files | findstr /i ".csv .xlsx"
```

O primeiro comando não deve encontrar nada. O segundo só pode listar arquivos de `exemplos/`.

## Antes de ligar os envios reais

Apresente o Pombo ao gestor e, se a empresa exigir, à TI. Esta documentação foi escrita para essa conversa.
