import asyncio
import logging
import aiohttp
from config import TOKEN
from core.database import init_db
from core.bot_setup import BotInitializer

#configura um log básico para ver os eventos do discord.py no console
logging.basicConfig(level=logging.INFO)

async def main():
    """
    função principal que inicializa o banco de dados e o bot
    """

    #garante que as tabelas do banco de dados existam antes de tudo
    await init_db()

    #cria uma sessão aiohttp que será usada pelo bot para downloads
    #o 'async with' garante que a sessão seja fechada corretamente no final
    async with aiohttp.ClientSession() as session:
        #cria a instância principal do bot, passando a sessão criada
        bot_runner = BotInitializer(http_session=session)

        #inicia o bot e lida com o desligamento 
        await bot_runner.run()

if __name__ == "__main__":
    # Executa a função principal do bot
    #o tratamento de keyboardInterrupt está na função main em bot_setup.py
    asyncio.run(main())