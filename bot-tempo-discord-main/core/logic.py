import traceback
from datetime import datetime

# Importa as funções do banco de dados que serão necessárias
from .database import (
    list_goals, has_awarded, mark_awarded, get_log_channel,
    total_time, current_session_time
)

# Importa a função de formatação de tempo
from utils.helpers import human_hours_minutes

async def check_and_award_goals_for_user(bot, user_id: int, guild_id: int):
    """
    Verifica todas as metas para um usuário específico, calcula seu tempo total
    e concede recompensas se aplicável.
    """
    try:
        guild = bot.get_guild(guild_id)
        if not guild: return

        member = guild.get_member(user_id)
        if not member:
            try:
                member = await guild.fetch_member(user_id)
            except:
                return # Membro não encontrado

        # --- LÓGICA DE CÁLCULO DE TEMPO ADICIONADA ---
        total = await total_time(user_id, guild_id)
        current = await current_session_time(user_id, guild_id)
        effective_time = total + current

        all_goals = await list_goals(guild_id)
        if not all_goals:
            return

        for goal_row in all_goals:
            goal_id, name, seconds_required, reward_role_id, _, _, required_role_ids_csv = goal_row
            
            if await has_awarded(user_id, guild_id, goal_id):
                continue

            if effective_time >= seconds_required:
                # Verifica se o membro tem os cargos de requisito
                if required_role_ids_csv:
                    req_ids = {int(rid.strip()) for rid in required_role_ids_csv.split(',')}
                    member_role_ids = {role.id for role in member.roles}
                    if not req_ids.issubset(member_role_ids):
                        continue # Pula esta meta se não tiver os requisitos

                # Marca como concluída e dá a recompensa
                await mark_awarded(user_id, guild_id, goal_id)
                if reward_role_id:
                    role = guild.get_role(reward_role_id)
                    if role:
                        await member.add_roles(role, reason="Meta de tempo atingida")

                # Envia a notificação
                goallog_id = await get_log_channel(guild_id, "goallog")
                ch = guild.get_channel(goallog_id) if goallog_id else None
                if ch:
                    role_txt = f"<@&{reward_role_id}>" if reward_role_id else "N/A"
                    time_txt = human_hours_minutes(seconds_required)
                    msg = (
                        f"🎉 **{member.mention}** acaba de concluir a meta **'{name}'**!\n"
                        f"Tempo necessário: **{time_txt}** | Recompensa: {role_txt}"
                    )
                    await ch.send(msg, allowed_mentions=discord.AllowedMentions(users=True, roles=False))

    except Exception as e:
        print(f"!!! ERRO em check_and_award_goals_for_user: {e}")
        traceback.print_exc()