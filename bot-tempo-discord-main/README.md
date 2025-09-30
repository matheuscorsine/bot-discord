# Bot de Monitoramento de Tempo para Discord

Um bot completo em Python (`discord.py`) para monitorar o tempo de usuários em canais de voz, com um sistema de ranking visual, metas com recompensas em cargos e muito mais.

---

## O que está no Repositório

Arquivos e pastas essenciais incluídos:

-   **`bot.py`**: O código-fonte principal e completo do bot. Contém toda a lógica de funcionamento.
-   **`requirements.txt`**: A lista de todas as bibliotecas Python necessárias para rodar o bot.
-   **`.env.example`**: Um arquivo de exemplo para as variáveis de ambiente. Você deve renomeá-lo para `.env` e adicionar sua token.
-   **`assets/`**: Pasta contendo as fontes usadas para gerar as imagens.
-   **`BOTberengue.png`**: Template para o cartão de status do comando `!tempo`.
-   **`BOTbereRank.png`**: Template para a primeira página do ranking (`!top_tempo`).
-   **`BOTbereRank2.png`**: Template para as páginas seguintes do ranking.
-   **`goal_song.mp3`**: Arquivo de áudio local para o comando `!agro`.

> **Atenção:** Este repositório **não** contém o arquivo `.env` com a token do bot por razões de segurança. Siga as instruções abaixo para configurar o seu.

---

## Como Rodar o Bot (Passo a Passo)

Siga estes passos em um ambiente Linux (recomendado para hospedagem) ou Windows.

**1. Baixe o Código:**
Clone o repositório para a sua máquina ou servidor.
```bash
git clone [https://github.com/Ruankinu/bot-tempo-discord.git](https://github.com/Ruankinu/bot-tempo-discord.git)
cd bot-tempo-discord
```

**2. Crie e Ative um Ambiente Virtual (Recomendado):**
* No Linux/macOS:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
* No Windows:
    ```bash
    python -m venv venv
    .\venv\Scripts\activate
    ```

**3. Instale as Dependências:**
Use o `pip` para instalar todas as bibliotecas listadas no `requirements.txt`.
```bash
pip install -r requirements.txt
```

**4. Configure suas Variáveis de Ambiente:**
Copie o arquivo de exemplo e adicione sua token do Discord.
* No Linux/macOS:
    ```bash
    cp .env.example .env
    ```
* No Windows:
    ```bash
    copy .env.example .env
    ```
   Depois, abra o novo arquivo `.env` com um editor de texto e coloque sua token:
   ```
   DISCORD_TOKEN=SUA_TOKEN_SECRETA_AQUI
   ```

**5. Rode o Bot:**
```bash
python bot.py
```

---

## Configuração Inicial no Discord (Obrigatório)

Para o bot funcionar corretamente no seu servidor, um administrador precisa fazer o seguinte:

1.  **Convidar o Bot:** Use o link de convite com as permissões corretas (principalmente `Gerenciar Cargos`, `Enviar Mensagens` e `Anexar Arquivos`).
2.  **Configurar Canais de Log:**
    * `!setcalllog #canal-de-logs-de-voz` - Para os cartões de entrada/saída.
    * `!setgoallog #canal-de-logs-de-metas` - Para os avisos de metas e resets.
3.  **Hierarquia de Cargos:** Garanta que o cargo do bot esteja em uma posição **acima** dos cargos que ele vai dar como recompensa de meta.
