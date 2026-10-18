# Decisões técnicas

Registro curto das escolhas que mudam o projeto, com o motivo de cada uma.

## Biblioteca de WhatsApp: `neonize` (provisória até o teste no PC da empresa)

- **O que é:** biblioteca Python que fala o protocolo do WhatsApp (baseada no *whatsmeow*, em Go), sem abrir navegador.
- **Por quê:** é Python puro (não precisa instalar Node), já traz a DLL para Windows, instala sem administrador e envia **documentos para grupos e contatos** (`send_document`). Também lista os grupos da conta (`get_joined_groups`) e mantém a sessão num arquivo local, então o QR code só é lido uma vez.
- **Testado no PC pessoal:** instalação e importação com Python 3.14 no Windows.
- **Falta confirmar:** conexão e envio pela rede da empresa (`tools/connection_test.py`).
- **Plano B:** se não passar na rede da empresa, trocar só a peça `pombo/channels/whatsapp.py` por uma baseada em `whatsapp-web.js` (Node). O resto do sistema não muda.

## E-mail: SMTP do servidor da empresa

- Biblioteca padrão do Python (`smtplib`), sem dependência extra.
- A porta e o tipo de segurança (SSL na 465 ou STARTTLS na 587) são confirmados no teste de conexão e ficam na tela de Configurações.

## Estado dos envios = histórico CSV

O programa não guarda um "estado" separado: ele sabe o que já saiu lendo o próprio histórico. Por isso, reiniciar o PC no meio de uma rodada nunca causa reenvio.
