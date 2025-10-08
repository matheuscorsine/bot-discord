import discord
import traceback
import aiosqlite

# Importa as funções do banco de dados
from .database import list_goals, has_awarded, mark_awarded, get_log_channel
# Importa as configurações e helpers necessários
from config import DB_PATH
from utils.helpers import human_hours_minutes

async def check_and_award_goals_for_user(bot, user_id, guild_id, total_seconds, current_seconds=0):
    """
    Verifica todas as metas para um usuário específico e concede recompensas se os critérios forem atendidos.
    Esta função é chamada quando uma sessão de voz termina ou durante a atualização periódica.
    """
    rows = await list_goals(guild_id)
    if not rows: # Se não há metas configuradas no servidor, não faz nada.
        return

    try:
        # Obtém os objetos de Guilda e Membro do Discord a partir dos seus IDs
        guild = bot.get_guild(guild_id)
        if not guild: return
        member = guild.get_member(user_id) or await guild.fetch_member(user_id)
        if not member: return
    except Exception as e:
        print(f"Erro ao buscar membro em check_and_award_goals_for_user: {e}")
        return
    
    # Itera sobre cada meta configurada no servidor
    for r in rows:
        try:
            goal_id, name, seconds_required, reward_role_id, _, _, required_role_ids_csv = r
            
            # Pula para a próxima meta se o usuário já recebeu esta recompensa
            if await has_awarded(user_id, guild_id, goal_id):
                continue
            
            # Calcula o tempo total efetivo do usuário (acumulado + sessão atual)
            effective_time = int(total_seconds) + int(current_seconds)
            
            # Pula se o tempo do usuário ainda não atingiu o necessário para a meta
            if effective_time < int(seconds_required or 0):
                continue

            # Se a meta exige cargos específicos, verifica se o usuário os possui
            if required_role_ids_csv:
                # Converte a string de IDs de cargos em um conjunto de inteiros
                req_ids = {int(rid.strip()) for rid in required_role_ids_csv.split(',')}
                member_role_ids = {role.id for role in member.roles}
                # Se não houver cargos em comum, o usuário não cumpre o requisito
                if not req_ids.intersection(member_role_ids):
                    continue

            # Se todas as verificações passaram, marca a meta como concluída no DB
            await mark_awarded(user_id, guild_id, goal_id)
            
            # Se a meta tem um cargo de recompensa, tenta adicioná-lo ao membro
            if reward_role_id:
                try:
                    role = guild.get_role(int(reward_role_id))
                    if role: await member.add_roles(role, reason="Meta de tempo em call atingida")
                except Exception as e:
                    print(f"Erro ao dar cargo da meta '{name}': {e}")

            # Envia uma mensagem de notificação no canal de log de metas
            goallog_id = await get_log_channel(guild_id, "goallog")
            ch = guild.get_channel(goallog_id) if goallog_id else None
            if ch:
                try:
                    # Conta quantos membros já concluíram esta meta para saber a posição
                    ord_num = 1
                    try:
                        async with aiosqlite.connect(DB_PATH) as db:
                            cur = await db.execute("SELECT COUNT(*) FROM awarded_goals WHERE guild_id=? AND goal_id=?", (guild_id, goal_id))
                            crow = await cur.fetchone()
                            if crow: ord_num = int(crow[0])
                    except: 
                        pass
                    
                    role_txt = f"<@&{reward_role_id}>" if reward_role_id else "N/A"
                    time_txt = human_hours_minutes(seconds_required)

                    # Monta a mensagem de parabéns
                    msg = (
                        f"<a:1937verifycyan:1155565499002925167> O(a) {member.mention} acabou de concluir uma meta.\n\n"
                        f"- Informações da Meta:\n"
                        f"- Cargo: {role_txt}\n"
                        f"- Tempo: **{time_txt}**\n"
                        f"- Este membro foi o **{ord_num}º** membro a concluir a meta."
                    )
                    
                    # Envia a mensagem, permitindo mencionar apenas o usuário (e não o cargo)
                    await ch.send(msg, allowed_mentions=discord.AllowedMentions(users=True, roles=False))
                except Exception as e:
                    traceback.print_exc()
        except Exception:
            # Se ocorrer um erro em uma meta, continua para a próxima
            continue