import discord
from discord.ext import commands
import asyncio
import aiosqlite

from ..core.database import (
    total_time, current_session_time, get_rank, list_goals, has_awarded
)
from ..utils.helpers import fetch_avatar_bytes
from ..utils.image_generator import gerar_stats_card, gerar_leaderboard_card
from ..utils.views import RankingView
from ..config import DB_PATH, BOT_PREFIX

class GeneralCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="tempo")
    async def tempo_cmd(self, ctx, user: discord.Member = None):
        """Mostra o cartão de estatísticas de tempo de um usuário."""
        # Se nenhum usuário for mencionado, usa o autor do comando
        user = user or ctx.author
        
        # Busca os dados de tempo do banco de dados
        total = await total_time(user.id, ctx.guild.id)
        current = await current_session_time(user.id, ctx.guild.id)
        rank = await get_rank(user.id, ctx.guild.id)
        
        # Coleta os dados das metas para exibir no cartão
        goals_rows = await list_goals(ctx.guild.id)
        goals = []
        if goals_rows:
            for r in goals_rows:
                gid, gname, greq, _, _, _, _ = r
                awarded = await has_awarded(user.id, ctx.guild.id, gid)
                effective = int(total or 0) + int(current or 0)
                prog = min(1.0, effective / greq) if greq and greq > 0 else 1.0
                goals.append({'id': gid, 'name': gname, 'required': greq, 'awarded': bool(awarded), 'progress': prog})

        # Baixa o avatar do usuário
        avatar_bytes = await fetch_avatar_bytes(self.bot.http_session, str(user.display_avatar.url))
        
        try:
            # Gera a imagem do cartão em uma thread separada para não bloquear o bot
            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(None, gerar_stats_card,
                user.display_name, total, current, avatar_bytes, rank, goals
            )
            # Envia a imagem como resposta
            await ctx.reply(file=discord.File(fp=buf, filename=f"tempo_{user.id}.png"))
        except Exception as e:
            await ctx.reply("Erro ao gerar o cartão de tempo.", mention_author=True)
            print(f"Erro no !tempo: {e}")

    @commands.command(name="top_tempo", aliases=['top_time', 'top_ranking'])
    async def top_tempo_cmd(self, ctx):
        """Exibe o ranking de tempo em chamada do servidor."""
        # Conecta ao DB para buscar os dados do ranking
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute("SELECT user_id, total_seconds FROM total_times WHERE guild_id=? ORDER BY total_seconds DESC", (ctx.guild.id,))
            rows = await cur.fetchall()
        
        if not rows:
            await ctx.reply("Ainda não há ninguém no ranking.", mention_author=True)
            return
        
        # Calcula o número total de páginas para a navegação
        PER_PAGE = 20
        if len(rows) <= 9:
            total_pages = 1
        else:
            total_pages = 1 + (len(rows) - 9 + PER_PAGE - 1) // PER_PAGE
        
        # Gera a imagem da primeira página do ranking
        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(None, gerar_leaderboard_card, rows, ctx.guild, 1)
        
        # Cria a View com os botões e a envia junto com a imagem
        view = RankingView(ctx=ctx, rows=rows, total_pages=total_pages)
        message = await ctx.reply(f"🏆 **Ranking de Tempo em Chamada**", file=discord.File(fp=buf, filename="ranking_pagina_1.png"), view=view, mention_author=True)
        view.message = message

    @commands.command(name="ajuda")
    async def member_help_cmd(self, ctx):
        """Exibe o painel de ajuda para comandos gerais."""
        p = BOT_PREFIX
        embed = discord.Embed(title="✨ Comandos do Bot ✨", description="Aqui estão os comandos disponíveis para você.", color=discord.Color.blue())
        
        embed.add_field(
            name="--- 📊 Comandos Gerais ---",
            value=(
                f"`{p}tempo [@usuário]` - Mostra seu cartão de estatísticas.\n"
                f"`{p}top_tempo` - Exibe o ranking do servidor (use as setas para navegar)."
            ),
            inline=False
        )
        
        embed.add_field(
            name="--- 🎵 Comandos de Música ---",
            value=(
                f"`{p}agro` - Toca a música especial no seu canal de voz.\n"
                f"`{p}sair` - Faz o bot sair do canal de voz e parar a música."
            ),
            inline=False
        )
        
        embed.set_footer(text=f"Para ver os comandos de administrador, use {p}ajuda_adm")
        await ctx.reply(embed=embed, mention_author=True)

    @commands.command(name="help")
    async def help_cmd(self, ctx):
        """Alias para o comando !ajuda."""
        # Chama o outro comando de ajuda diretamente
        await self.member_help_cmd(ctx)

# Função obrigatória que permite que o bot carregue este Cog
async def setup(bot):
    await bot.add_cog(GeneralCommands(bot))