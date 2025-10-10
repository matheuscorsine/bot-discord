import discord
from discord.ext import commands, tasks
import traceback
from datetime import datetime
import asyncio

# Importações dos módulos
from ..core.database import (
    end_session, total_time, start_session, current_session_time, get_rank,
    list_goals, has_awarded, get_log_channel
)
from ..core.logic import check_and_award_goals_for_user
from ..utils.helpers import now_iso_utc, fetch_avatar_bytes, fmt_hms
from ..utils.image_generator import gerar_stats_card
from ..config import CALLCARD_UPDATE_INTERVAL

class ListenerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_call_cards.start() # Inicia a tarefa em background assim que o Cog é carregado

    def cog_unload(self):
        self.update_call_cards.cancel() # Garante que a tarefa pare se o Cog for descarregado

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """
        Listener que monitora as mudanças nos estados de voz dos membros (entrar, sair, mudar de canal).
        """
        if member.bot: return # Ignora outros bots

        guild = member.guild
        now = now_iso_utc()
        
        # Determina o tipo de ação do usuário
        is_join = before.channel is None and after.channel is not None
        is_leave = before.channel is not None and after.channel is None
        is_switch = before.channel and after.channel and before.channel.id != after.channel.id
        
        # Se o usuário saiu de um canal ou trocou de canal
        if is_leave or is_switch:
            start_iso = await end_session(member.id, guild.id, now)
            duration = 0
            if start_iso:
                try:
                    duration = int((datetime.fromisoformat(now) - datetime.fromisoformat(start_iso)).total_seconds())
                except:
                    pass
            
            total_after = await total_time(member.id, guild.id)
            # Atualiza o cartão de status do usuário para saída
            await self._mark_user_exit_and_cleanup(guild, member, duration, total_after)
            # Verifica se o usuário atingiu alguma meta ao sair
            await check_and_award_goals_for_user(self.bot, member.id, guild.id, total_after, current_seconds=0)

        # Se o usuário entrou em um canal ou trocou de canal
        if is_join or is_switch:
            await start_session(member.id, guild.id, after.channel.id, now)
            total = await total_time(member.id, guild.id)
            current = await current_session_time(member.id, guild.id)
            rank = await get_rank(member.id, guild.id)
            # Cria ou atualiza o cartão de status do usuário para "entrada"
            await self._ensure_user_call_message(guild, member, total, current, rank)

    async def _ensure_user_call_message(self, guild, user, total, current, rank):
        """Cria ou edita a mensagem com o cartão de status de um usuário em chamada."""
        gmap = self.bot.active_call_messages.setdefault(guild.id, {})
        existing = gmap.get(user.id)
        
        try:
            # Coleta informações sobre as metas para exibir na imagem
            goals_rows = await list_goals(guild.id)
            goals = []
            if goals_rows:
                for r in goals_rows:
                    gid, gname, greq, _, _, _, _ = r
                    awarded = await has_awarded(user.id, guild.id, gid)
                    effective = int(total or 0) + int(current or 0)
                    greq_i = int(greq or 0)
                    prog = min(1.0, effective / greq_i) if greq_i > 0 else 0.0
                    goals.append({'id': gid, 'name': gname, 'required': greq_i, 'awarded': bool(awarded), 'progress': prog})

            # Baixa o avatar do usuário
            avatar_url = str(getattr(user, "display_avatar", user).url)
            avatar_bytes = await fetch_avatar_bytes(self.bot.http_session, avatar_url)

            # Gera a imagem do cartão de status
            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(None, gerar_stats_card,
                user.display_name, total, current, avatar_bytes, rank, goals
            )

            # Encontra o canal de log para enviar a mensagem
            ch_id = await get_log_channel(guild.id, "calllog")
            if not ch_id: return
            ch = guild.get_channel(ch_id)
            if not ch: return

            # Se já existe uma mensagem para este usuário, edita-a
            if existing:
                try:
                    await existing.edit(attachments=[discord.File(fp=buf, filename="stats.png")])
                except discord.errors.NotFound:
                    # Se a mensagem foi apagada, remove da nossa lista e tenta criar uma nova
                    gmap.pop(user.id, None)
                    await self._ensure_user_call_message(guild, user, total, current, rank)
            # Se não existe, cria uma nova mensagem
            else:
                content = f"👋 **{user.display_name}** entrou na chamada."
                newmsg = await ch.send(content=content, file=discord.File(fp=buf, filename="stats.png"))
                self.bot.active_call_messages[guild.id][user.id] = newmsg
        except Exception as e:
            print(f"Erro em _ensure_user_call_message: {e}")
            traceback.print_exc()

    async def _mark_user_exit_and_cleanup(self, guild, user, duration_seconds, total_after):
        """Atualiza a mensagem de um usuário que saiu da chamada."""
        gmap = self.bot.active_call_messages.get(guild.id, {})
        msgobj = gmap.pop(user.id, None)
        
        try:
            if msgobj:
                goals_rows = await list_goals(guild.id)
                goals = []
                if goals_rows:
                    for r in goals_rows:
                        gid, gname, greq, _, _, _, _ = r
                        awarded = await has_awarded(user.id, guild.id, gid)
                        greq_i = int(greq or 0)
                        prog = min(1.0, total_after / greq_i) if greq_i > 0 else 0.0
                        goals.append({'id': gid, 'name': gname, 'required': greq_i, 'awarded': bool(awarded), 'progress': prog})

                avatar_url = str(getattr(user, "display_avatar", user).url)
                avatar_bytes = await fetch_avatar_bytes(self.bot.http_session, avatar_url)
                rank = await get_rank(user.id, guild.id)

                loop = asyncio.get_running_loop()
                buf = await loop.run_in_executor(None, gerar_stats_card,
                    user.display_name, total_after, 0, avatar_bytes, rank, goals
                )

                content = f"⏱️ **{user.display_name}** saiu — Duração: **{fmt_hms(duration_seconds)}**"
                try:
                    # Edita a mensagem final com o tempo da sessão e o cartão atualizado
                    await msgobj.edit(content=content, attachments=[discord.File(fp=buf, filename="exit.png")])
                except Exception:
                    pass
        except Exception as e:
            print(f"Erro em _mark_user_exit_and_cleanup: {e}")
            traceback.print_exc()

    @tasks.loop(seconds=CALLCARD_UPDATE_INTERVAL)
    async def update_call_cards(self):
        """Tarefa em background que atualiza periodicamente os cartões de todos os usuários em chamada."""
        try:
            for guild in self.bot.guilds:
                call_log_id = await get_log_channel(guild.id, "calllog")
                if not call_log_id: continue

                # Pega uma lista de todos os usuários (não-bots) em canais de voz no servidor
                current_voice_ids = {m.id for vc in guild.voice_channels for m in vc.members if not m.bot}

                # Atualiza o cartão de cada usuário em chamada
                for user_id in current_voice_ids:
                    member = guild.get_member(user_id)
                    if member:
                        total = await total_time(user_id, guild.id)
                        current = await current_session_time(user_id, guild.id)
                        rank = await get_rank(user_id, guild.id)
                        
                        # Verifica se o usuário atingiu alguma meta durante a atualização
                        await check_and_award_goals_for_user(self.bot, user_id, guild.id, total, current_seconds=current)
                        # Atualiza a imagem do cartão
                        await self._ensure_user_call_message(guild, member, total, current, rank)

                # Limpa mensagens de usuários que não estão mais em chamada (por algum erro ou reinício)
                guild_map = self.bot.active_call_messages.get(guild.id, {})
                stale_ids = set(guild_map.keys()) - current_voice_ids
                for uid in stale_ids:
                    msgobj = guild_map.pop(uid, None)
                    if msgobj:
                        try: await msgobj.delete()
                        except: pass
        except Exception as e:
            print(f"Erro no loop de update_call_cards: {e}")
            traceback.print_exc()

    @update_call_cards.before_loop
    async def before_update_call_cards(self):
        """Espera o bot estar pronto antes de iniciar a tarefa em background."""
        await self.bot.wait_until_ready()

# Função necessária para carregar o Cog
async def setup(bot):
    await bot.add_cog(ListenerCog(bot))