import asyncio
import aiohttp
from core.bot_setup import BotInitializer

async def main():
    """
    Ponto de entrada principal para inicializar e rodar o bot.
    """
    # Cria uma sessão aiohttp global para ser usada em todo o bot
    async with aiohttp.ClientSession() as session:
        # Inicializa o bot, passando a sessão http
        bot_initializer = BotInitializer(http_session=session)
        
        # Inicia o processo do bot
        await bot_initializer.run()

if __name__ == "__main__":
    try:
        # Executa a função main usando o loop de eventos do asyncio
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot encerrado pelo usuário.")