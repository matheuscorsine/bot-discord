import discord
from discord.ext import commands
import asyncio
import aiosqlite

from core.database import (
    total_time, current_session_time, get_rank, list_goals, has_awarded, get_last_week_ranking
)
from utils.helpers import fetch_avatar_bytes
from utils.image_generator import gerar_stats_card, gerar_leaderboard_card
from utils.views import RankingView
from config import DB_PATH, BOT_PREFIX

class GeneralCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="tempo", aliases=['t'])
    async def tempo_cmd(self, ctx, user: discord.Member = None):
        """Mostra o cartão de estatísticas de tempo para um usuário."""
        user = user or ctx.author
        try:
            total = await total_time(user.id, ctx.guild.id)
            current = await current_session_time(user.id, ctx.guild.id)
            rank = await get_rank(user.id, ctx.guild.id)

            # --- LÓGICA DE METAS ADICIONADA AQUI ---
            goals_rows = await list_goals(ctx.guild.id)
            goals = []
            if goals_rows:
                effective_time = total + current
                for r in goals_rows:
                    gid, gname, greq, _, _, _, _ = r
                    awarded = await has_awarded(user.id, ctx.guild.id, gid)
                    greq_i = int(greq or 0)
                    prog = min(1.0, effective_time / greq_i) if greq_i > 0 else 0.0
                    goals.append({'id': gid, 'name': gname, 'required': greq_i, 'awarded': bool(awarded), 'progress': prog})
            
            avatar_bytes = await fetch_avatar_bytes(str(user.display_avatar.url))
            
            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(None, gerar_stats_card,
                user.display_name, total, current, avatar_bytes, rank, goals
            )
            await ctx.reply(file=discord.File(fp=buf, filename=f"tempo_{user.id}.png"), mention_author=True)

        except Exception as e:
            await ctx.reply("❌ Erro ao gerar o cartão de tempo.", mention_author=True)
            print(f"Erro no !tempo: {e}")
            traceback.print_exc()

    @commands.command(name="top_tempo", aliases=['top_time', 'top_ranking', 'top'])
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

    @commands.command(name="rankingsemanal", aliases=["lastweek"])
    async def last_week_ranking_cmd(self, ctx):
        """Mostra o ranking de tempo em call da última semana completa."""
        await ctx.typing() # Mostra "Bot is typing..." para o usuário saber que está processando
        rows = await get_last_week_ranking(ctx.guild.id)
        
        if not rows:
            await ctx.reply("O ranking da semana passada ainda não está disponível.", mention_author=True)
            return
            
        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(None, gerar_leaderboard_card, rows, ctx.guild, 1)
        
        await ctx.reply(
            content="🏆 **Ranking Semanal** 🏆",
            file=discord.File(fp=buf, filename="ranking_semanal_passado.png"),
            mention_author=True
        )

# Função obrigatória que permite que o bot carregue este Cog
async def setup(bot):
    await bot.add_cog(GeneralCommands(bot))