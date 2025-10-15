import asyncio
import traceback
from datetime import datetime, timezone, timedelta
import discord
import aiosqlite

# Importa as configurações e funções de banco de dados necessárias
from config import DB_PATH, LOCAL_TZ
from core.database import get_reset_config, get_last_reset, set_last_reset, list_goals, get_log_channel

# Dicionário auxiliar para converter nomes de dias em números (0=Segunda, 6=Domingo)
_DIAS = {"seg":0,"ter":1,"qua":2,"qui":3,"sex":4,"sab":5,"dom":6}

def _parse_day(s: str):
    """Converte uma string de dia da semana (ex: 'seg', 'domingo', '5') para um inteiro."""
    s = s.strip().lower()
    if s.isdigit() and 0 <= int(s) <= 6:
        return int(s)
    for k, v in _DIAS.items():
        if k in s:
            return v
    return None

def _next_weekly_dt(now_utc: datetime, weekday: int, hour: int, minute: int):
    """Calcula a data e hora exatas do próximo reset, com base na configuração."""
    # Converte o tempo atual (UTC) para o fuso horário local (São Paulo)
    now_local = now_utc.astimezone(LOCAL_TZ)
    # Calcula quantos dias faltam para o próximo dia da semana do reset
    days_ahead = (weekday - now_local.weekday() + 7) % 7
    # Define a data alvo do reset
    target_date = (now_local + timedelta(days=days_ahead)).date()
    # Cria o objeto de data e hora completo para o reset no fuso local
    target_local = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=LOCAL_TZ)
    
    # Se a data/hora calculada já passou hoje, adiciona 7 dias para pegar a da próxima semana
    if target_local <= now_local:
        target_local += timedelta(days=7)
        
    # Converte a data e hora do reset de volta para UTC para comparações consistentes
    return target_local.astimezone(timezone.utc)

async def _weekly_reset_run_for_guild(guild: discord.Guild, bot_instance):
    try:
        now_utc = datetime.now(timezone.utc)

        # Finaliza as sessões ativas para garantir que todo o tempo seja contado
        active_user_ids = await get_active_sessions(guild.id)
        for user_id in active_user_ids:
            await end_session(user_id, guild.id, now_utc.isoformat())

        # Salva o ranking final da semana que acabou (substituindo o antigo)
        await save_last_week_ranking(guild.id)

        # Reseta os tempos para a nova semana
        rows_goals = await list_goals(guild.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM total_times WHERE guild_id=?", (guild.id,))
            resetable_goal_ids = [r[0] for r in rows_goals if r and r[5] == 1]
            if resetable_goal_ids:
                qmarks = ",".join("?" for _ in resetable_goal_ids)
                await db.execute(f"DELETE FROM awarded_goals WHERE guild_id=? AND goal_id IN ({qmarks})", (guild.id, *resetable_goal_ids))
            await db.commit()
        
        # Envia a notificação de reset no canal configurado
        log_channel_id = await get_log_channel(guild.id, "resetlog")
        if log_channel_id:
            channel = guild.get_channel(log_channel_id)
            if channel:
                await channel.send("🔁 **O ranking semanal de tempo em call foi resetado!**\nUse `!rankingsemanal` para ver os resultados finais da última semana.")

        await set_last_reset(guild.id, now_utc)
        print(f"[reset] Reset e arquivamento simplificado executados para a guilda {guild.id} ({guild.name}).")
    except Exception as e:
        print(f"[reset] Erro ao executar o reset para a guilda {getattr(guild,'id',None)}: {e}")
        traceback.print_exc()

async def weekly_reset_scheduler(bot):
    """Loop principal que roda em background e verifica se é hora de executar o reset."""
    # Espera até que o bot esteja totalmente conectado e pronto
    await bot.wait_until_ready()
    # Loop infinito que continua enquanto o bot estiver rodando
    while not bot.is_closed():
        # Pausa por 60 segundos antes da próxima verificação
        await asyncio.sleep(60)
        now_utc = datetime.now(timezone.utc)
        
        # Itera sobre todos os servidores em que o bot está
        for guild in bot.guilds:
            try:
                # Obtém a configuração de reset para o servidor atual
                wd, hh, mm = await get_reset_config(guild.id)
                # Se não houver configuração para este servidor, pula para o próximo
                if wd is None:
                    continue

                # Calcula a próxima data/hora de reset
                target_utc = _next_weekly_dt(now_utc, wd, hh, mm)
                # Obtém a data/hora do último reset
                last = await get_last_reset(guild.id)
                
                # Condição para executar o reset:
                # Se a hora atual já passou da hora alvo E (não houve reset anterior OU o último reset foi antes do alvo)
                if now_utc >= target_utc and (not last or last < target_utc):
                    await _weekly_reset_run_for_guild(guild)
            except Exception as e:
                print(f"Erro no scheduler para a guilda {guild.id}: {e}")