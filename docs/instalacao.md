# Instalação passo a passo (sem administrador)

## 1. Python "só para mim"

1. Acesse [python.org/downloads](https://www.python.org/downloads/) e baixe o **Python 3.12 ou mais novo** para Windows.
2. Na primeira tela do instalador:
   - **desmarque** "Use admin privileges when installing py.exe";
   - **marque** "Add python.exe to PATH";
   - clique em **Install Now**. A instalação vai para a sua pasta de usuário e não pede administrador.
3. Se o Windows ainda abrir a Microsoft Store quando você digitar `python`: *Configurações › Aplicativos › Configurações avançadas de aplicativos › Aliases de execução do aplicativo*, e desligue `python.exe` e `python3.exe`.

## 2. Baixar o Pombo

No GitHub: botão verde **Code › Download ZIP**. Extraia numa pasta fixa, por exemplo `Documentos\Pombo`.
(Não deixe na pasta Downloads: o "Abrir com o Windows" aponta para essa pasta.)

## 3. Instalar

Dois cliques em **`instalar.bat`**. Ele cria um ambiente isolado (`.venv`) dentro da pasta do Pombo e baixa as bibliotecas. Leva 1 a 3 minutos.

## 4. Abrir

Dois cliques em **`iniciar.bat`**. O Pombo abre no navegador em `http://127.0.0.1:8765`.
Abrir de novo não cria uma segunda cópia: só mostra a tela.

## 5. Configurar

Siga [primeiro-uso.md](primeiro-uso.md).

## Atualizar para uma versão nova

Baixe o ZIP novo, extraia **por cima** da pasta antiga e rode `instalar.bat` de novo. Cadastro, histórico e sessão do WhatsApp ficam em `%LOCALAPPDATA%\Pombo` e não são apagados.

## Plano B: a TI bloqueou o Python

Dá para montar uma versão portátil, um ZIP que já traz o Python dentro (o "embeddable package" do python.org). Fica no roadmap, para quando for necessário.
