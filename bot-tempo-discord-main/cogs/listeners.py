# Substitua todo o conteúdo de cogs/listeners.py por este

import discord
from discord.ext import commands, tasks
import asyncio
import traceback

from config import CALLCARD_UPDATE_INTERVAL
from core.database import (
    start_session, end_session, get_log_channel, total_time,
    current_session_time, get_rank, list_goals, has_awarded
)
from core.logic import _check_and_award_goals_for_user
from utils.helpers import fetch_avatar_bytes, fmt_hms, now_iso_utc
from utils.image_generator import gerar_stats_card

class Listeners(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_call_messages = {}
        self.update_call_cards.start()

    def cog_unload(self):
        self.update_call_cards.cancel()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if member.bot:
            return

        guild = member.guild
        now = now_iso_utc()

        is_join = before.channel is None and after.channel is not None
        is_leave = before.channel is not None and after.channel is None
        is_switch = before.channel is not None and after.channel is not None and before.channel.id != after.channel.id

        try:
            if is_leave or is_switch:
                start_iso = await end_session(member.id, guild.id, now)
                
                # --- CORREÇÃO 2: Verificação de metas ao sair ---
                await _check_and_award_goals_for_user(self.bot, member.id, guild.id)

                if start_iso:
                    duration = 0
                    try:
                        duration = int((datetime.fromisoformat(now.replace('Z', '+00:00')) - datetime.fromisoformat(start_iso.replace('Z', '+00:00'))).total_seconds())
                    except:
                        pass
                    total_after = await total_time(member.id, guild.id)
                    await self._mark_user_exit_and_cleanup(guild, member, duration, total_after)

            if is_join or is_switch:
                await start_session(member.id, guild.id, after.channel.id, now)
                await self._ensure_user_call_message(member)

        except Exception as e:
            print(f"!!! ERRO em on_voice_state_update: {e}")
            traceback.print_exc()

    async def _ensure_user_call_message(self, user: discord.Member):
        guild = user.guild
        gmap = self.active_call_messages.setdefault(guild.id, {})
        existing = gmap.get(user.id)

        try:
            total = await total_time(user.id, guild.id)
            current = await current_session_time(user.id, guild.id)
            rank = await get_rank(user.id, guild.id)

            # --- CORREÇÃO 1: Lógica de metas para o card ---
            goals_rows = await list_goals(guild.id)
            goals = []
            if goals_rows:
                effective_time = total + current
                for r in goals_rows:
                    gid, gname, greq, _, _, _, _ = r
                    awarded = await has_awarded(user.id, guild.id, gid)
                    greq_i = int(greq or 0)
                    prog = min(1.0, effective_time / greq_i) if greq_i > 0 else 0.0
                    goals.append({'id': gid, 'name': gname, 'required': greq_i, 'awarded': bool(awarded), 'progress': prog})

            avatar_bytes = await fetch_avatar_bytes(str(user.display_avatar.url))
            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(None, gerar_stats_card,
                user.display_name, total, current, avatar_bytes, rank, goals)

            ch_id = await get_log_channel(guild.id, "calllog")
            if not ch_id: return
            ch = guild.get_channel(ch_id)
            if not ch: return

            if existing:
                try:
                    await existing.edit(attachments=[discord.File(fp=buf, filename="stats.png")])
                except discord.NotFound:
                    gmap.pop(user.id, None)
                    await self._ensure_user_call_message(user)
            else:
                content = f"👋 **{user.display_name}** entrou na chamada."
                newmsg = await ch.send(content=content, file=discord.File(fp=buf, filename="stats.png"))
                self.active_call_messages[guild.id][user.id] = newmsg

        except Exception as e:
            print(f"Erro em _ensure_user_call_message: {e}")
            traceback.print_exc()

    async def _mark_user_exit_and_cleanup(self, guild, user, duration_seconds, total_after):
        gmap = self.active_call_messages.get(guild.id, {})
        msgobj = gmap.pop(user.id, None)
        if not msgobj: return
        
        try:
            rank = await get_rank(user.id, guild.id)
            avatar_bytes = await fetch_avatar_bytes(str(user.display_avatar.url))

            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(None, gerar_stats_card,
                user.display_name, total_after, 0, avatar_bytes, rank, []) # Mostra card zerado ao sair

            content = f"⏱️ **{user.display_name}** saiu — Duração: **{fmt_hms(duration_seconds)}**"
            await msgobj.edit(content=content, attachments=[discord.File(fp=buf, filename="exit.png")])
        except Exception as e:
            print(f"Erro em _mark_user_exit_and_cleanup: {e}")
            traceback.print_exc()

    @tasks.loop(seconds=CALLCARD_UPDATE_INTERVAL)
    async def update_call_cards(self):
        await self.bot.wait_until_ready()
        try:
            for guild in self.bot.guilds:
                call_log_id = await get_log_channel(guild.id, "calllog")
                if not call_log_id: continue
                
                current_voice_ids = {m.id for vc in guild.voice_channels for m in vc.members if not m.bot}
                for user_id in current_voice_ids:
                    member = guild.get_member(user_id)
                    if member:
                        # A verificação periódica de metas já acontece aqui
                        await _check_and_award_goals_for_user(self.bot, user_id, guild.id)
                        await self._ensure_user_call_message(member)
                
                guild_map = self.active_call_messages.get(guild.id, {})
                stale_ids = set(guild_map.keys()) - current_voice_ids
                for uid in stale_ids:
                    msgobj = guild_map.pop(uid, None)
                    if msgobj:
                        try: await msgobj.delete()
                        except: pass
        except Exception as e:
            print(f"Erro no loop de update_call_cards: {e}")
            traceback.print_exc()

async def setup(bot):
    await bot.add_cog(Listeners(bot))