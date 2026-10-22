# Limitações conhecidas

O que o Pombo **não** faz hoje, e o que fazer a respeito.

## O PC precisa estar ligado e o Pombo aberto

O Pombo roda no PC do analista. No horário do envio, o PC precisa estar ligado e o programa aberto.

- O Pombo **abre junto com o Windows** (Configurações) e **impede o PC de entrar em suspensão** enquanto roda.
- Se o PC foi reiniciado, ao abrir o Pombo envia o que ficou para trás nas **últimas 2 horas**. Depois disso, a rodada aparece como "perdida" na tela, com o botão "Enviar agora".
- Para quem desliga o PC ao sair: deixe-o ligado no horário dos envios ou programe o envio para antes de sair.
- **Próximo passo** (quando houver investimento): rodar o Pombo num servidor ou numa máquina virtual sempre ligada.

## Fins de semana

O Pombo aceita qualquer dia da semana, mas os relatórios só ficam atualizados se alguém atualizar os Excels. Para cobrir sábado e domingo:

1. Quem trabalha no fim de semana (por exemplo, o gestor) atualiza os arquivos na mesma pasta.
2. O envio cadastrado com sábado/domingo marcado sai sozinho, se o PC com o Pombo estiver ligado.
3. Se o arquivo não for atualizado, o Pombo **não envia** e avisa: nada de números de sexta circulando como se fossem de sábado.

Com a fase 2 (atualização automática), essa dependência diminui.

## WhatsApp

- Depende de uma automação não oficial do WhatsApp. Ver [whatsapp-hoje-e-com-investimento.md](whatsapp-hoje-e-com-investimento.md).
- O número conectado precisa **fazer parte** dos grupos de destino.
- Se o celular do número corporativo ficar muitos dias sem internet, o WhatsApp pode desconectar os aparelhos. O Pombo avisa e mostra o QR code para reconectar.

## E-mail

- O limite de anexos é **20 MB por e-mail** (configurável). Servidores de e-mail costumam recusar mensagens maiores.
- A senha fica no Gerenciador de Credenciais do Windows **do usuário**. Outro usuário do mesmo PC não a vê.

## Print da planilha

- O Pombo lê os **valores que o Excel salvou**. Fórmulas recalculadas e não salvas não aparecem: salve a planilha depois de atualizar.
- O desenho da imagem é do Pombo (cores do PHD, cabeçalho azul-escuro), não uma cópia da formatação da planilha.
- As colunas de dia usam o **dia do mês** da linha indicada (ou a data, se a linha tiver datas). Numa semana que vira o mês, aparecem só os dias que estão na planilha do mês de referência.
- No e-mail, cada parte vai como uma mensagem com a imagem anexa.

## Outros

- Uma pessoa por instalação. O painel da equipe é a [fase 4 do roadmap](roadmap.md).
- Mudar a pasta do histórico só vale depois de fechar e abrir o Pombo.
