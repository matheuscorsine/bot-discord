import discord
from discord.ext import commands
import re
import traceback
import asyncio

from config import BOT_PREFIX
from datetime import datetime, timezone
from core.database import (
    set_log_channel, add_goal, remove_goal, list_goals, get_goal, mark_awarded,
    set_reset_config, get_reset_config, total_time, current_session_time,
    add_prohibited_channel, remove_prohibited_channel, list_prohibited_channels,
    get_awarded_users, update_goal_reset_flag, get_log_channel,
    set_history_config, get_all_history_dates, get_history_by_date, toggle_pin_history
)
from core.scheduler import _weekly_reset_run_for_guild, _parse_day
from utils.helpers import fmt_hms, human_hours_minutes
from utils.image_generator import gerar_leaderboard_card

class AdminCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(administrator=True)
    @commands.command(name="ajuda_adm")
    async def admin_help_cmd(self, ctx):
        """Exibe o painel de ajuda para comandos de administrador."""
        p = BOT_PREFIX
        embed = discord.Embed(title="🔑 Comandos de Administrador 🔑", description="Gerencie as configurações, metas e canais do bot.", color=discord.Color.orange())
        
        embed.add_field(name="--- ⚙️ Configuração ---", value=(f"`{p}setcalllog #canal` - **(OBRIGATÓRIO)** Onde os cards de stats aparecerão.\n" f"`{p}setgoallog #canal` - **(OBRIGATÓRIO)** Onde as notificações de metas serão enviadas."), inline=False)
        embed.add_field(name="--- 🎯 Metas ---", value=(f"**`{p}add_goal <nome> <segundos> [@recompensa] [@requisito1]...`**\n" f"↳ **`<nome>`**: Se tiver espaços, use aspas. Ex: `\"Meta Semanal\"`.\n" f"↳ **`<segundos>`**: Tempo necessário. Ex: 1 hora = `3600`.\n" f"↳ **`[@recompensa]`**: O primeiro @cargo mencionado é o que o membro ganha.\n" f"↳ **`[@requisito]`**: Todos os @cargos seguintes são os que o membro precisa ter.\n\n" f"`{p}remove_goal <id>` - Remove uma meta.\n" f"`{p}list_goals` - Lista todas as metas.\n" f"`{p}check_goal <id>` - Mostra quem completou e menciona quem falta.\n" f"`{p}notify_goal <id>` - Dá o cargo e notifica todos que já completaram a meta."), inline=False)
        embed.add_field(name="--- 🔁 Reset ---", value=(f"`{p}setreset <dia> <HH:MM>` - Configura o reset. Ex: `{p}setreset dom 22:00`.\n" f"`{p}showreset` - Mostra a configuração do reset.\n" f"`{p}forcereset` - Força o reset imediatamente."), inline=False)
        embed.add_field(name="--- ⛔ Moderação ---", value=(f"`{p}proibir_canal #canal` - Bloqueia comandos no canal.\n" f"`{p}permitir_canal #canal` - Desbloqueia o canal.\n" f"`{p}listar_proibidos` - Lista os canais bloqueados."), inline=False)
        await ctx.reply(embed=embed, mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="helpadv")
    async def helpadv_cmd(self, ctx):
        await self.admin_help_cmd(ctx)

    @commands.has_permissions(administrator=True)
    @commands.command(name="setcalllog")
    async def set_call_log_cmd(self, ctx, channel: discord.TextChannel):
        await set_log_channel(ctx.guild.id, channel.id, "calllog")
        await ctx.reply(f"Canal de logs de chamadas definido para {channel.mention}", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="setgoallog")
    async def set_goal_log_cmd(self, ctx, channel: discord.TextChannel):
        await set_log_channel(ctx.guild.id, channel.id, "goallog")
        await ctx.reply(f"Canal de logs de metas definido para {channel.mention}", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="add_goal")
    async def add_goal_cmd(self, ctx, *, params: str):
        toks = params.split()
        seconds_idx = -1
        for i, t in enumerate(toks):
            if re.fullmatch(r"\d+", t):
                seconds_idx = i
                break
        if seconds_idx == -1:
            await ctx.reply("Uso inválido. Faltou o número de segundos.", mention_author=True)
            return
        name = " ".join(toks[:seconds_idx]).strip()
        if name.startswith('"') and name.endswith('"'): name = name[1:-1]
        if not name:
            await ctx.reply("Nome da meta vazio.", mention_author=True)
            return
        seconds = int(toks[seconds_idx])
        mentions = [int(m.group(1)) for t in toks[seconds_idx+1:] if (m := re.match(r"^<@&?(\d+)>$", t))]
        reward_role_id = mentions[0] if mentions else None
        required_role_ids = mentions[1:] if len(mentions) > 1 else []
        required_role_ids_csv = ",".join(map(str, required_role_ids)) if required_role_ids else None
        reset_flag_str = next((t for t in toks[seconds_idx+1:] if t.lower() in ("true", "false")), "true")
        reset_flag = 1 if reset_flag_str.lower() == "true" else 0
        try:
            await add_goal(ctx.guild.id, name, seconds, reward_role_id, required_role_ids_csv, reset_flag)
            rr_txt = f"<@&{reward_role_id}>" if reward_role_id else "—"
            req_txt = ' / '.join([f'<@&{rid}>' for rid in required_role_ids]) if required_role_ids else "—"
            await ctx.reply(f"✅ Meta '{name}' adicionada ({fmt_hms(seconds)}). Resetável: {bool(reset_flag)}\nRecompensa: {rr_txt}\nRequisito(s): {req_txt}", mention_author=True)
        except Exception as e:
            await ctx.reply("Erro ao adicionar meta.", mention_author=True)
            traceback.print_exc()

    @commands.has_permissions(administrator=True)
    @commands.command(name="remove_goal")
    async def remove_goal_cmd(self, ctx, goal_id: int):
        await remove_goal(ctx.guild.id, goal_id)
        await ctx.reply(f"Meta id {goal_id} removida.", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="list_goals", aliases=["list_goal"])
    async def list_goals_cmd(self, ctx):
        rows = await list_goals(ctx.guild.id)
        if not rows:
            await ctx.reply("Nenhuma meta configurada.", mention_author=True)
            return
        lines = []
        for r in rows:
            gid, name, greq, reward_role_id, _, reset_on, required_role_ids_csv = r
            role_txt = f"<@&{reward_role_id}>" if reward_role_id else "—"
            req_txt = " / ".join(f"<@&{x.strip()}>" for x in required_role_ids_csv.split(',')) if required_role_ids_csv else "—"
            lines.append(f"**ID {gid}:** {name} ({fmt_hms(greq)}) | Recompensa: {role_txt} | Requisito(s): {req_txt} | Resetável: {bool(reset_on)}")
        await ctx.reply("📋 **Metas configuradas:**\n" + "\n".join(lines), mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="notify_goal")
    async def notify_goal_cmd(self, ctx, goal_id: int):
        guild = ctx.guild
        goal = await get_goal(guild.id, goal_id)
        if not goal:
            await ctx.reply(f"❌ Meta com ID {goal_id} não encontrada.", mention_author=True)
            return
        goallog_id = await get_log_channel(guild.id, "goallog")
        ch = guild.get_channel(goallog_id) if goallog_id else None
        if not ch:
            await ctx.reply("❌ O canal de log de metas (`goallog`) não está configurado.", mention_author=True)
            return
        _, name, seconds_required, reward_role_id, _, _, _ = goal
        role_to_give = guild.get_role(reward_role_id) if reward_role_id else None
        initial_message = await ctx.reply(f"⚙️ Verificando e notificando a meta '{name}'. Isso pode demorar...")
        newly_awarded = []
        for member in guild.members:
            if member.bot or (role_to_give and role_to_give in member.roles):
                continue
            total = await total_time(member.id, guild.id)
            current = await current_session_time(member.id, guild.id)
            if (total + current) >= seconds_required:
                if role_to_give:
                    try:
                        await member.add_roles(role_to_give, reason=f"Comando !notify_goal por {ctx.author}")
                        await mark_awarded(member.id, guild.id, goal_id)
                        newly_awarded.append(member)
                    except Exception as e:
                        print(f"Erro ao dar cargo para {member.display_name}: {e}")
        awarded_user_ids = await get_awarded_users(guild.id, goal_id)
        if not awarded_user_ids:
            await initial_message.edit(content=f"ℹ️ Verificação concluída. Ninguém completou a meta '{name}' ainda.")
            return
        await initial_message.edit(content=f"✅ {len(newly_awarded)} novo(s) membro(s) receberam o cargo. Notificando todos os {len(awarded_user_ids)} vencedores em {ch.mention}.")
        success_count = 0; fail_count = 0
        for i, user_id in enumerate(awarded_user_ids):
            try:
                member = guild.get_member(user_id) or await guild.fetch_member(user_id)
                if not member:
                    fail_count += 1
                    continue
                ord_num = i + 1
                role_txt = f"<@&{reward_role_id}>" if reward_role_id else "N/A"
                time_txt = human_hours_minutes(seconds_required)
                msg = (f"<a:1937verifycyan:1155565499002925167> O(a) {member.mention} completou a meta!\n\n" f"- Informações da Meta:\n" f"- Cargo: {role_txt}\n" f"- Tempo: **{time_txt}**\n" f"- Este membro foi o **{ord_num}º** membro a concluir esta meta.")
                await ch.send(msg, allowed_mentions=discord.AllowedMentions(users=True, roles=False))
                success_count += 1
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Erro ao notificar user {user_id} para meta {goal_id}: {e}")
                fail_count += 1
        await ctx.send(f"🎉 Notificações enviadas! {success_count} com sucesso, {fail_count} falhas.")

    @commands.has_permissions(administrator=True)
    @commands.command(name="set_goal_reset")
    async def set_goal_reset_cmd(self, ctx, goal_id: int, val: str):
        goal = await get_goal(ctx.guild.id, goal_id)
        if not goal:
            await ctx.reply("Meta não encontrada.", mention_author=True)
            return
        v_bool = str(val).lower() in ("1", "true", "yes", "y", "sim")
        await update_goal_reset_flag(ctx.guild.id, goal_id, v_bool)
        await ctx.reply(f"Meta {goal_id} `reset_on_weekly` definida para `{v_bool}`", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="setreset")
    async def setreset_cmd(self, ctx, dia: str, hora: str):
        wd = _parse_day(dia)
        if wd is None:
            await ctx.reply("Dia inválido. Use seg, ter, qua, qui, sex, sab, dom.", mention_author=True)
            return
        try:
            hh, mm = map(int, hora.split(":"))
            if not (0 <= hh < 24 and 0 <= mm < 60): raise ValueError()
        except:
            await ctx.reply("Horário inválido. Use HH:MM (formato 24h).", mention_author=True)
            return
        await set_reset_config(ctx.guild.id, wd, hh, mm)
        dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
        await ctx.reply(f"Reset semanal definido para toda **{dias[wd]}** às **{hh:02d}:{mm:02d}** (Horário de Brasília).", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="showreset")
    async def showreset_cmd(self, ctx):
        wd, hh, mm = await get_reset_config(ctx.guild.id)
        if wd is None:
            await ctx.reply("O reset semanal ainda não foi configurado. Use `!setreset`.", mention_author=True)
            return
        dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
        await ctx.reply(f"O reset semanal está configurado para toda **{dias[wd]}** às **{hh:02d}:{mm:02d}** (Horário de Brasília).", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="forcereset")
    async def forcereset_cmd(self, ctx):
        await ctx.reply("Forçando o reset semanal... Isso pode levar um momento.", mention_author=True)
        await _weekly_reset_run_for_guild(ctx.guild, self.bot)
        await ctx.send("Reset forçado executado com sucesso.")

    @commands.has_permissions(administrator=True)
    @commands.command(name="check_goal")
    async def check_goal_cmd(self, ctx, goal_id: int):
        processing_message = await ctx.reply(f"🔍 Verificando a meta {goal_id} para todos os membros. Aguarde...")
        guild = ctx.guild
        goal = await get_goal(guild.id, goal_id)
        if not goal:
            await processing_message.edit(content=f"❌ Meta com ID {goal_id} não encontrada.")
            return
        gid, name, greq, _, _, _, required_role_ids_csv = goal
        completed_list = []
        not_completed_list = []
        mentions_to_send = []
        for member in guild.members:
            if member.bot:
                continue
            if required_role_ids_csv:
                try:
                    req_ids = {int(rid.strip()) for rid in required_role_ids_csv.split(',')}
                    member_role_ids = {role.id for role in member.roles}
                    if not req_ids.intersection(member_role_ids):
                        continue 
                except (ValueError, TypeError):
                    continue
            total = await total_time(member.id, guild.id)
            current = await current_session_time(member.id, guild.id)
            effective_time = total + current
            if effective_time >= (greq or 0):
                completed_list.append(f"- {member.display_name} ({fmt_hms(effective_time)})")
            else:
                not_completed_list.append(f"- {member.display_name} ({fmt_hms(effective_time)})")
                mentions_to_send.append(member.mention)
        embed = discord.Embed(title=f"Verificação da Meta: #{gid} - {name}", description=f"**Tempo necessário:** {human_hours_minutes(greq)}", color=discord.Color.gold())
        if completed_list:
            completed_text = "\n".join(completed_list[:25])
            if len(completed_list) > 25:
                completed_text += f"\n... e mais {len(completed_list) - 25}."
            embed.add_field(name=f"✅ Membros que Completaram ({len(completed_list)})", value=completed_text, inline=False)
        else:
            embed.add_field(name="✅ Membros que Completaram", value="Ninguém completou esta meta ainda.", inline=False)
        if not_completed_list:
            not_completed_text = "\n".join(not_completed_list[:25])
            if len(not_completed_list) > 25:
                not_completed_text += f"\n... e mais {len(not_completed_list) - 25}."
            embed.add_field(name=f"❌ Membros que Faltam ({len(not_completed_list)})", value=not_completed_text, inline=False)
        await processing_message.edit(content="", embed=embed)
        if mentions_to_send:
            mention_string = " ".join(mentions_to_send)
            chunks = [mention_string[i:i + 1900] for i in range(0, len(mention_string), 1900)]
            for i, chunk in enumerate(chunks):
                prefix = "**Marcação de quem falta:**\n" if i == 0 else ""
                await ctx.send(f"{prefix}{chunk}", allowed_mentions=discord.AllowedMentions(users=True))

    @commands.has_permissions(administrator=True)
    @commands.command(name="proibir_canal")
    async def prohibit_channel_cmd(self, ctx, channel: discord.TextChannel):
        await add_prohibited_channel(ctx.guild.id, channel.id)
        await ctx.reply(f"Comandos (exceto de admin) agora estão proibidos em {channel.mention}.", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="permitir_canal")
    async def allow_channel_cmd(self, ctx, channel: discord.TextChannel):
        await remove_prohibited_channel(ctx.guild.id, channel.id)
        await ctx.reply(f"Comandos agora estão permitidos em {channel.mention}.", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="listar_proibidos")
    async def list_prohibited_cmd(self, ctx):
        ids = await list_prohibited_channels(ctx.guild.id)
        if not ids:
            await ctx.reply("Nenhum canal com comandos proibidos.", mention_author=True)
            return
        mentions = [f"<#{cid}>" for cid in ids]
        await ctx.reply("Canais proibidos para comandos de membros:\n" + "\n".join(mentions), mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="set_historico", aliases=["sethistory"])
    async def set_history_cmd(self, ctx, canal: discord.TextChannel, dias_para_manter: int = 90):
        """Define o canal para postagem automática do ranking e por quantos dias o histórico é mantido."""
        await set_history_config(ctx.guild.id, canal.id, dias_para_manter)
        await ctx.reply(f"✅ Configuração do histórico salva!\n- Rankings semanais serão postados em: {canal.mention}\n- Histórico será mantido por: **{dias_para_manter} dias**.", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="historico", aliases=["history"])
    async def history_cmd(self, ctx, data: str = None):
        """Exibe o ranking de uma semana passada. Se nenhuma data for fornecida, lista as disponíveis."""
        dates = await get_all_history_dates(ctx.guild.id)
        if not dates:
            await ctx.reply("Nenhum histórico semanal foi encontrado.", mention_author=True)
            return

        if data is None:
            formatted_dates = []
            for iso_date in dates[:15]:
                try:
                    dt_obj = datetime.fromisoformat(iso_date.replace('Z', '+00:00'))
                    formatted_dates.append(f"`{dt_obj.strftime('%Y-%m-%d')}`")
                except:
                    continue
            
            embed = discord.Embed(title="🗓️ Histórico de Rankings Semanais",
                                  description="Use `!historico <data>` com uma das datas abaixo (formato AAAA-MM-DD).\n\n" + "\n".join(formatted_dates),
                                  color=discord.Color.blue())
            await ctx.reply(embed=embed, mention_author=True)
            return

        # Busca a data mais próxima da fornecida pelo usuário
        target_date_iso = None
        for iso_date in dates:
            if iso_date.startswith(data):
                target_date_iso = iso_date
                break
        
        if not target_date_iso:
            await ctx.reply(f"❌ Data não encontrada. Use o formato `AAAA-MM-DD` de uma das datas listadas em `!historico`.", mention_author=True)
            return

        rows = await get_history_by_date(ctx.guild.id, target_date_iso)
        if not rows:
            await ctx.reply(f"Não foram encontrados dados para a data `{data}`.", mention_author=True)
            return

        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(None, gerar_leaderboard_card, rows, ctx.guild, 1)
        
        dt_obj = datetime.fromisoformat(target_date_iso.replace('Z', '+00:00'))
        await ctx.reply(
            content=f"**Exibindo ranking da semana de {dt_obj.strftime('%d/%m/%Y')}**",
            file=discord.File(fp=buf, filename=f"historico_{data}.png"),
            mention_author=True
        )

    @commands.has_permissions(administrator=True)
    @commands.command(name="fixar_historico", aliases=["pinhistory"])
    async def pin_history_cmd(self, ctx, data: str):
        """Impede que o ranking de uma semana específica seja apagado automaticamente."""
        dates = await get_all_history_dates(ctx.guild.id)
        target_date_iso = next((d for d in dates if d.startswith(data)), None)
        if not target_date_iso:
            await ctx.reply(f"❌ Data não encontrada. Use o formato `AAAA-MM-DD`.", mention_author=True)
            return
        
        await toggle_pin_history(ctx.guild.id, target_date_iso, True)
        await ctx.reply(f"📌 O histórico da semana `{data}` foi fixado e não será apagado automaticamente.", mention_author=True)

    @commands.has_permissions(administrator=True)
    @commands.command(name="desafixar_historico", aliases=["unpinhistory"])
    async def unpin_history_cmd(self, ctx, data: str):
        """Permite que o ranking de uma semana específica volte a ser apagado após o tempo de retenção."""
        dates = await get_all_history_dates(ctx.guild.id)
        target_date_iso = next((d for d in dates if d.startswith(data)), None)
        if not target_date_iso:
            await ctx.reply(f"❌ Data não encontrada. Use o formato `AAAA-MM-DD`.", mention_author=True)
            return
        
        await toggle_pin_history(ctx.guild.id, target_date_iso, False)
        await ctx.reply(f"🔓 O histórico da semana `{data}` foi desafixado.", mention_author=True)

# Função obrigatória que permite que o bot carregue este Cog
async def setup(bot):
    await bot.add_cog(AdminCommands(bot))