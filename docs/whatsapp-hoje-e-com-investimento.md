# WhatsApp: hoje e com investimento

## Hoje: automação do WhatsApp comum (custo zero)

O Pombo conecta um número de WhatsApp como **"aparelho conectado"**, o mesmo recurso do WhatsApp Web, usando a biblioteca de código aberto [neonize](https://github.com/krypton-byte/neonize). Para quem recebe, é uma mensagem normal daquele número, com o arquivo anexado.

| A favor | Contra |
|---|---|
| Grátis | **Vai contra os termos de uso do WhatsApp**: o número pode ser bloqueado |
| Envia para **grupos comuns**, como os que o time já usa | Pode parar de funcionar quando o WhatsApp muda o protocolo, até a biblioteca ser atualizada |
| Nenhum cadastro, aprovação ou empresa intermediária | Depende do PC ligado com o Pombo aberto |
| Configuração em 1 minuto (ler um QR code) | Sem garantia nem suporte oficial |

**Como o risco é reduzido no Pombo:**
- Usa um **número corporativo dedicado**, nunca o pessoal: se houver bloqueio, o WhatsApp pessoal do analista não é atingido.
- Envia só para contatos e grupos cadastrados, com pausa entre mensagens.
- Uso interno, com pessoas que conhecem o número. **Não é ferramenta de disparo em massa.**
- Falha no WhatsApp **não derruba o e-mail**: os dois canais são independentes, e o analista é avisado.

## Com investimento: API oficial da Meta (WhatsApp Business Platform)

É o caminho oficial, estável e permitido. O que muda:

| Item | Como funciona |
|---|---|
| **Número** | Um número dedicado à API. Ele deixa de funcionar no app comum do WhatsApp. |
| **Cadastro** | Conta no Meta Business Manager, com **verificação da empresa** (CNPJ e documentos). |
| **Mensagens que a empresa inicia** | Só por **modelos (templates) aprovados pela Meta**. O envio diário de relatório se encaixa na categoria **utilidade**. |
| **Cobrança** | **Por mensagem entregue**, desde 1º/07/2025, conforme a categoria. No Brasil, a cobrança em reais começou em 1º/07/2026 ([fonte: Meta](https://developers.facebook.com/docs/whatsapp/pricing/)). |
| **Grupos** | Esse é o ponto fraco para o nosso caso. A API de grupos é restrita a contas oficiais e, segundo guias de mercado, limitada a **8 participantes por grupo**, sem poder adicionar pessoas diretamente ([fonte](https://www.unipile.com/whatsapp-group-api/), conferir na documentação da Meta). **Na prática, os envios passariam a ser individuais**, um por pessoa. |

### Quanto custaria (estimativa)

Valores de referência para o Brasil, **categoria utilidade**, como publicados por guias de mercado em 2026. O valor oficial e atualizado está na tabela de preços da Meta, que deve ser conferida antes de qualquer orçamento:

- Utilidade: **cerca de US$ 0,0068 por mensagem** ([blueticks](https://blueticks.co/blog/whatsapp-business-api-pricing-2026), [whautomate](https://whautomate.com/whatsapp-business-api-pricing-brazil)). Algumas fontes citam até US$ 0,008 ([boosend](https://boosend.ai/blog/whatsapp-business-api-pricing-2026)).
- Marketing (não se aplica a relatórios): cerca de US$ 0,0625 por mensagem ([zernio](https://zernio.com/blog/whatsapp-business-api-pricing)).

**Exemplo:** 2 rodadas por dia × 10 pessoas × 22 dias úteis = **440 mensagens/mês ≈ US$ 3 a 3,50 por mês** por analista, só de mensagens. Usando a Cloud API direto da Meta, não há mensalidade de intermediário. Com um provedor (BSP), costuma haver taxa de plataforma.

**Conclusão:** o custo das mensagens é baixo. O investimento real está no **processo**: verificação da empresa, número dedicado, aprovação de modelos e a troca dos grupos por envios individuais.

### Como migrar no código

O WhatsApp está isolado em `pombo/channels/whatsapp.py`, atrás da mesma interface do e-mail:

```python
class Channel(Protocol):
    name: str
    def send(self, target: Target, subject: str, message: str, files: list[Path], use_bcc: bool = True) -> None: ...
```

Migrar é **escrever um `WhatsAppCloudChannel`** com esse formato: subir o arquivo na API de mídia e enviar o modelo aprovado com o documento. Depois, basta registrá-lo no lugar do atual em `pombo/__main__.py`. Motor, histórico, telas e regras **não mudam**.

*Pesquisa de preços feita em 18/10/2026. Preços e regras da Meta mudam com frequência.*
