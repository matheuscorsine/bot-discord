import discord
from discord.ext import commands
import os
import traceback

from config import TOKEN, BOT_PREFIX
from .database import init_db, is_channel_prohibited
from .scheduler import weekly_reset_scheduler

class BotInitializer:
    """
    Classe central para criar, configurar e executar o bot do Discord.
    """
    def __init__(self, http_session):
        # Define as 'Intenções' (Intents) do bot. 
        # Intents especificam quais tipos de eventos o bot precisa receber do Discord.
        intents = discord.Intents.all()
        
        # Cria a instância do bot e a armazena em 'self.bot'
        self.bot = commands.Bot(
            command_prefix=BOT_PREFIX, 
            intents=intents, 
            help_command=None # Desativa o comando de ajuda padrão para usarmos o nosso
        )
        
        # Anexa a sessão HTTP e o dicionário de mensagens ao bot para acesso em outros módulos
        self.bot.http_session = http_session
        self.bot.active_call_messages = {}

        # Chama o método que adiciona todos os eventos
        self._add_events()

    def _add_events(self):
        """Adiciona os handlers de eventos e verificadores globais ao bot."""
        @self.bot.event
        async def on_ready():
            # Esta função é chamada uma vez quando o bot está online e pronto.
            await init_db() # Garante que o banco de dados e as tabelas existam
            print(f"{self.bot.user} está online!")
            # Inicia o agendador de reset semanal em background
            self.bot.loop.create_task(weekly_reset_scheduler(self.bot))

        @self.bot.event
        async def on_message(message: discord.Message):
            # Esta função é chamada para cada mensagem que o bot pode ver.
            if message.author.bot:
                return # Ignora mensagens de outros bots para evitar loops.
            
            # Uma pequena funcionalidade de resposta a uma mensagem específica
            if message.content.strip().lower() == "tome":
                try:
                    await message.reply(f"Tome, <@602542180309008404>", allowed_mentions=discord.AllowedMentions(users=True))
                except:
                    pass
            
            # Linha crucial que faz o bot verificar se a mensagem é um comando.
            await self.bot.process_commands(message)

        @self.bot.check
        async def _global_channel_block_check(ctx: commands.Context):
            """Um verificador global que roda antes da execução de QUALQUER comando."""
            # Sempre permite comandos em mensagens diretas (DMs) ou para administradores.
            if ctx.guild is None or (hasattr(ctx.author, 'guild_permissions') and ctx.author.guild_permissions.administrator):
                return True
            try:
                # Verifica no banco de dados se o canal atual está na lista de proibidos.
                return not await is_channel_prohibited(ctx.guild.id, ctx.channel.id)
            except:
                # Em caso de erro na verificação, permite o comando como medida de segurança.
                return True
                
        @self.bot.event
        async def on_command_error(ctx, error):
            """Handler global que captura e trata erros de comandos."""
            if isinstance(error, commands.CheckFailure):
                try: await ctx.reply("❌ Comandos estão proibidos neste canal.", mention_author=True, delete_after=10)
                except discord.HTTPException: pass
            elif isinstance(error, commands.MissingPermissions):
                try: await ctx.reply("Você não tem permissão para usar este comando.", mention_author=True)
                except discord.HTTPException: pass
            elif isinstance(error, commands.CommandNotFound):
                pass # Ignora silenciosamente comandos que não existem.
            else:
                # Para todos os outros erros, imprime os detalhes no console para depuração.
                print(f"[command-error] Comando: {ctx.command} | Usuário: {ctx.author.id} | Erro: {error}")
                traceback.print_exception(type(error), error, error.__traceback__)
        
    async def _load_cogs(self):
        """Encontra e carrega todas as extensões (cogs) da pasta 'cogs'."""
        cogs_path = 'cogs'
        for filename in os.listdir(cogs_path):
            if filename.endswith('.py') and not filename.startswith('__'):
                try:
                    extension_name = f'{cogs_path}.{filename[:-3]}'
                    await self.bot.load_extension(extension_name)
                    print(f"Cog '{extension_name}' carregado com sucesso.")
                except Exception as e:
                    print(f"Falha ao carregar o cog {extension_name}: {e}")
                    traceback.print_exc()

    async def run(self):
        """Inicia o cliente do bot e conecta ao Discord."""
        # O 'async with' gerencia a conexão e desconexão do bot de forma segura.
        async with self.bot:
            await self._load_cogs()
            await self.bot.start(TOKEN)