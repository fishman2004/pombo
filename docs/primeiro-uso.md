# Primeiro uso num PC novo (roteiro)

Siga na ordem. Leva cerca de 20 minutos. Se algum passo falhar, **pare e anote a mensagem de erro inteira**.

## Antes de tudo: o PC deixa sair e-mail e WhatsApp?

Redes de empresa às vezes bloqueiam programas que enviam e-mail ou acessam o WhatsApp. Teste antes de configurar o resto:

1. Instale o Pombo ([instalacao.md](instalacao.md)), passos 1 a 3.
2. Na pasta do Pombo, clique na barra de endereço do Explorador, digite `cmd` e Enter. Depois rode:
   ```bat
   .venv\Scripts\python tools\connection_test.py
   ```
3. **E-mail:** informe servidor, porta, segurança, usuário e senha. Pegue esses dados no Thunderbird: *Configurações da conta › Servidor de saída (SMTP)*. Esperado: `E-MAIL OK` e um e-mail na sua caixa de entrada.
   - Se falhar com a porta 465/SSL, tente a 587/STARTTLS.
4. **WhatsApp:** um QR code aparece no terminal. No celular do **número corporativo**: *WhatsApp › Aparelhos conectados › Conectar aparelho* e leia o código. Esperado: a lista dos seus grupos e `WHATSAPP OK`, e o arquivo de teste chegando ao número que você informar.
5. Anote **qual porta e segurança funcionaram**. Se algum dos dois falhar, o plano B está em [decisoes.md](decisoes.md).

## Configurar o Pombo

1. Abra o Pombo (`iniciar.bat`).
2. **Configurações**, com o **Modo demonstração ligado** por enquanto:
   - seu nome, seu e-mail e seu WhatsApp (para receber avisos e testes);
   - servidor, porta, segurança, usuário e senha do e-mail que funcionaram no teste;
   - "Abrir o Pombo junto com o Windows" ligado;
   - salve e clique em **Enviar e-mail de teste para mim**.
3. Ainda em Configurações, leia o **QR code do WhatsApp** com o celular do número corporativo.
4. **Contatos:** cadastre as pessoas (e-mail e/ou WhatsApp), crie as listas de e-mail (ex.: "Gestão") e clique em **Buscar grupos no WhatsApp**.
5. **Envios › Novo envio:** por exemplo "Vendas Diárias", com o caminho do arquivo real, destinatários, seg–sex às 18:00 e a mensagem. Salve.
6. Clique em **Enviar teste só para mim**. Confira no seu e-mail e no seu WhatsApp se o anexo chegou com o nome certo.

## Ensaio em modo demonstração

Com o modo demonstração **ligado**, espere o próximo horário de envio. Na tela **Hoje**, a rodada deve aparecer como enviada. No **Histórico**, as linhas aparecem como `demonstracao`. Nada foi enviado de verdade.

## Ligar de verdade

1. **Apresente ao gestor** antes (o README e [ganho-de-tempo.md](ganho-de-tempo.md) ajudam).
2. Configurações: **desligue o Modo demonstração**.
3. Acompanhe a primeira rodada real das 18h pela tela **Hoje**.
4. Reinicie o PC uma vez e confira que o Pombo abre sozinho e **não reenvia** nada.
