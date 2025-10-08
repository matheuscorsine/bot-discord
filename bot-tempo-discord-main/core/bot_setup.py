# Caminho: core/bot_setup.py

import discord
from discord.ext import commands
import os
import traceback

# Importa as configurações e o agendador
from config import TOKEN, BOT_PREFIX
from .scheduler import weekly_reset_scheduler
# (Mais tarde, adicionaremos os eventos aqui)

class BotInitializer:
    """
    Classe central para criar, configurar e executar o bot do Discord.
    """
    def __init__(self, http_session):
        # Define as 'Intenções' (Intents) do bot. 
        # Intents especificam quais tipos de eventos o bot precisa receber do Discord.
        # 'all()' é o mais simples, mas pode ser otimizado para apenas o que é necessário.
        intents = discord.Intents.all()
        
        # O objeto 'bot' agora é 'self.bot', um atributo desta classe.
        self.bot = commands.Bot(
            command_prefix=BOT_PREFIX, 
            intents=intents, 
            help_command=None # Desativa o comando de ajuda padrão para usarmos o nosso.
        )
        
        # Armazena a sessão aiohttp para que possa ser usada em outras partes do bot (Cogs)
        self.bot.http_session = http_session
        
        # Cria um dicionário no bot para rastrear mensagens ativas de chamada
        self.bot.active_call_messages = {}

        # Adiciona os handlers de eventos (on_ready, on_command_error, etc.) ao bot
        self._add_events()

    def _add_events(self):
        """Adiciona os handlers de eventos ao bot."""
        @self.bot.event
        async def on_ready():
            # Esta função é chamada uma vez quando o bot está online e pronto.
            print(f"{self.bot.user} está online!")
            # Inicia as tarefas que rodam em background
            self.bot.loop.create_task(weekly_reset_scheduler(self.bot))
            # Adicionaremos a inicialização do DB e outras tarefas aqui.

        @self.bot.event
        async def on_command_error(ctx, error):
            """Handler global para tratar erros de comando."""
            if isinstance(error, commands.CheckFailure):
                try: await ctx.reply("❌ Comandos estão proibidos neste canal.", mention_author=True, delete_after=10)
                except discord.HTTPException: pass
            elif isinstance(error, commands.MissingPermissions):
                try: await ctx.reply("Você não tem permissão para usar este comando.", mention_author=True)
                except discord.HTTPException: pass
            elif isinstance(error, commands.CommandNotFound):
                pass # Ignora silenciosamente comandos que não existem
            else:
                # Para outros erros, imprime os detalhes no console para depuração
                print(f"[command-error] Comando: {ctx.command} | Usuário: {ctx.author.id} | Erro: {error}")
                traceback.print_exception(type(error), error, error.__traceback__)
        
    async def _load_cogs(self):
        """Encontra e carrega todas as extensões (cogs) da pasta 'cogs'."""
        cogs_path = 'cogs'
        for filename in os.listdir(cogs_path):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    cog_name = f'{cogs_path}.{filename[:-3]}'
                    await self.bot.load_extension(cog_name)
                    print(f"Cog '{filename[:-3]}' carregado com sucesso.")
                except Exception as e:
                    print(f"Falha ao carregar o cog {filename[:-3]}: {e}")
                    traceback.print_exc()

    async def run(self):
        """Inicia o cliente do bot e conecta ao Discord."""
        # O 'async with' gerencia a conexão e desconexão do bot de forma segura
        async with self.bot:
            await self._load_cogs()
            await self.bot.start(TOKEN)