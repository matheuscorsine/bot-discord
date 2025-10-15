import aiosqlite
from datetime import datetime, timezone, timedelta

# Importa o caminho do banco de dados do nosso arquivo de configuração
from config import DB_PATH
# Importa a função helper para obter o tempo atual em UTC
from utils.helpers import now_iso_utc

async def init_db():
    """Cria todas as tabelas do banco de dados se elas ainda não existirem."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Tabela para rastrear sessões de voz ativas
        await db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER, guild_id INTEGER, channel_id INTEGER, start_time TEXT,
            PRIMARY KEY(user_id,guild_id) )""")
        # Tabela para armazenar o tempo total acumulado de cada usuário
        await db.execute("""CREATE TABLE IF NOT EXISTS total_times (
            user_id INTEGER, guild_id INTEGER, total_seconds INTEGER,
            PRIMARY KEY(user_id,guild_id) )""")
        # Tabela para configurar canais de log (ex: logs de chamada, logs de metas)
        await db.execute("""CREATE TABLE IF NOT EXISTS log_channels (
            guild_id INTEGER, channel_type TEXT, channel_id INTEGER,
            PRIMARY KEY(guild_id,channel_type) )""")
        # Tabela para definir as metas do servidor
        await db.execute("""CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, name TEXT, 
            seconds_required INTEGER, role_id INTEGER, required_role_id INTEGER, 
            reset_on_weekly INTEGER DEFAULT 1, required_role_ids TEXT )""")
        # Tabela para registrar quais usuários já receberam a recompensa de cada meta
        await db.execute("""CREATE TABLE IF NOT EXISTS awarded_goals (
            user_id INTEGER, guild_id INTEGER, goal_id INTEGER, awarded_at TEXT,
            PRIMARY KEY(user_id,guild_id,goal_id) )""")
        # Tabela para a configuração do reset semanal de tempo
        await db.execute("""CREATE TABLE IF NOT EXISTS weekly_reset_config (
            guild_id INTEGER PRIMARY KEY, weekday INTEGER, hour INTEGER, minute INTEGER )""")
        # Tabela para guardar o estado do último reset
        await db.execute("""CREATE TABLE IF NOT EXISTS reset_state (
            guild_id INTEGER PRIMARY KEY, last_reset TEXT )""")
        # Tabela para listar canais onde os comandos do bot são proibidos
        await db.execute("""CREATE TABLE IF NOT EXISTS prohibited_channels (
            guild_id INTEGER, channel_id INTEGER, PRIMARY KEY(guild_id, channel_id) )""")
        # Tabela para armazenar o histórico semanal de tempo 
        await db.execute("""CREATE TABLE IF NOT EXISTS weekly_time_history (
            guild_id INTEGER, user_id INTEGER, total_seconds INTEGER, reset_date TEXT, pinned INTEGER DEFAULT 0, PRIMARY KEY(guild_id, user_id, reset_date))""")
        # Tabela para configurar canais de log de metas e retenção de histórico
        await db.execute("""CREATE TABLE IF NOT EXISTS history_config (
            guild_id INTEGER PRIMARY KEY, post_channel_id INTEGER, retention_days INTEGER DEFAULT 90)""")
        # Tabela para armazenar os sorteios ativos
        await db.execute("""CREATE TABLE IF NOT EXISTS giveaways (
            message_id INTEGER PRIMARY KEY, guild_id INTEGER NOT NULL, channel_id INTEGER NOT NULL, end_time TEXT NOT NULL, winner_count INTEGER NOT NULL,
            prize TEXT,required_roles TEXT)""")
        # Tabela para armazenar os participantes de cada sorteio
        await db.execute("""CREATE TABLE IF NOT EXISTS giveaway_participants (
            message_id INTEGER, user_id INTEGER, PRIMARY KEY (message_id, user_id))""")
        await db.commit()
<<<<<<< HEAD
        #tabela de histórico
        await db.execute("""CREATE TABLE IF NOT EXISTS weekly_time_history (
            guild_id INTEGER, user_id INTEGER, total_seconds INTEGER, PRIMARY KEY(guild_id, user_id))""")
=======


>>>>>>> 25ef76a395daef396a31e04fbabb33c249b193da
        
        # Tenta adicionar uma nova coluna à tabela 'goals' para compatibilidade com versões antigas.
        # Se a coluna já existir, a exceção será ignorada.
        try:
            await db.execute("ALTER TABLE goals ADD COLUMN required_role_ids TEXT")
            await db.commit()
        except:
            pass

async def start_session(user_id, guild_id, channel_id, start_time_iso):
    """Inicia uma nova sessão de voz para um usuário."""
    print(f"[DEBUG-TEMPO] start_session chamada para user: {user_id}") # DEBUG
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO sessions (user_id, guild_id, channel_id, start_time) VALUES (?, ?, ?, ?)",
                         (user_id, guild_id, channel_id, start_time_iso))
        await db.commit()
    print(f"[DEBUG-TEMPO] Sessão para user {user_id} inserida no banco de dados.")

async def end_session(user_id, guild_id, end_time_iso):
    """Finaliza uma sessão, calcula a duração e a adiciona ao tempo total do usuário."""
    start_iso = None
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT start_time FROM sessions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = await cur.fetchone()
        if not row:
            return None
        
        start_iso = row[0]
        try:
            # CORREÇÃO: Garante que a data/hora seja lida corretamente
            start_dt = datetime.fromisoformat(start_iso.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time_iso.replace('Z', '+00:00'))
            duration = int((end_dt - start_dt).total_seconds())

            if duration > 0:
                # Busca o tempo total atual
                cur2 = await db.execute("SELECT total_seconds FROM total_times WHERE user_id=? AND guild_id=?", (user_id, guild_id))
                total_row = await cur2.fetchone()
                current_total = total_row[0] if total_row else 0
                
                # Soma o novo tempo e salva
                new_total = current_total + duration
                await db.execute("INSERT OR REPLACE INTO total_times (user_id, guild_id, total_seconds) VALUES (?, ?, ?)",
                                 (user_id, guild_id, new_total))
        except (ValueError, TypeError) as e:
            # Se houver um erro no cálculo, pelo menos não perdemos a sessão
            print(f"AVISO: Não foi possível calcular a duração da sessão para {user_id}. Erro: {e}")

        # Remove a sessão ativa, pois ela já foi processada
        await db.execute("DELETE FROM sessions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        await db.commit()
            
    return start_iso

async def total_time(user_id, guild_id):
    """Retorna o tempo total acumulado de um usuário."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT total_seconds FROM total_times WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def current_session_time(user_id, guild_id):
    """Calcula a duração da sessão de voz ativa de um usuário."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT start_time FROM sessions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = await cur.fetchone()
        if not row: return 0
        
        try:
            start_time = datetime.fromisoformat(row[0])
        except:
            return 0
        
        last_reset = await get_last_reset(guild_id)
        if last_reset and start_time < last_reset:
            start_time = last_reset
            
        duration = int((datetime.now(timezone.utc) - start_time).total_seconds())
        return max(0, duration)

async def set_log_channel(guild_id: int, channel_id: int, channel_type: str):
    """Define um canal de log para uma função específica (ex: 'calllog')."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO log_channels (guild_id, channel_type, channel_id) VALUES (?, ?, ?)",
                         (guild_id, channel_type, channel_id))
        await db.commit()

async def get_log_channel(guild_id: int, channel_type: str):
    """Obtém o ID de um canal de log configurado."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT channel_id FROM log_channels WHERE guild_id=? AND channel_type=?", (guild_id, channel_type))
        row = await cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None

async def add_prohibited_channel(guild_id: int, channel_id: int):
    """Adiciona um canal à lista de canais proibidos para comandos."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO prohibited_channels (guild_id, channel_id) VALUES (?, ?)", (guild_id, channel_id))
        await db.commit()

async def remove_prohibited_channel(guild_id: int, channel_id: int):
    """Remove um canal da lista de canais proibidos."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM prohibited_channels WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
        await db.commit()

async def list_prohibited_channels(guild_id: int):
    """Retorna uma lista de todos os canais proibidos em um servidor."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT channel_id FROM prohibited_channels WHERE guild_id=?", (guild_id,))
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def is_channel_prohibited(guild_id: int, channel_id: int):
    """Verifica se um canal específico está na lista de proibidos."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM prohibited_channels WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
        return bool(await cur.fetchone())

async def add_goal(guild_id, name, seconds_required, reward_role_id=None, required_role_ids_csv=None, reset_on_weekly=1):
    """Adiciona uma nova meta ao banco de dados."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO goals (guild_id, name, seconds_required, role_id, required_role_ids, reset_on_weekly) VALUES (?,?,?,?,?,?)",
                         (guild_id, name, int(seconds_required), reward_role_id, required_role_ids_csv, int(reset_on_weekly)))
        await db.commit()

async def remove_goal(guild_id, goal_id):
    """Remove uma meta e todos os registros de premiação associados a ela."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM goals WHERE guild_id=? AND id=?", (guild_id, goal_id))
        await db.execute("DELETE FROM awarded_goals WHERE guild_id=? AND goal_id=?", (guild_id, goal_id))
        await db.commit()

async def list_goals(guild_id):
    """Retorna uma lista de todas as metas de um servidor, ordenadas por tempo."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,name,seconds_required,role_id,required_role_id,reset_on_weekly,required_role_ids FROM goals WHERE guild_id=? ORDER BY seconds_required ASC",
                               (guild_id,))
        return await cur.fetchall()

async def get_goal(guild_id, goal_id):
    """Obtém os dados de uma meta específica pelo seu ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,name,seconds_required,role_id,required_role_id,reset_on_weekly,required_role_ids FROM goals WHERE guild_id=? AND id=?",
                               (guild_id, goal_id))
        return await cur.fetchone()

async def mark_awarded(user_id, guild_id, goal_id):
    """Marca que um usuário completou e recebeu a recompensa de uma meta."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO awarded_goals (user_id,guild_id,goal_id,awarded_at) VALUES (?,?,?,?)",
                         (user_id, guild_id, goal_id, now_iso_utc()))
        await db.commit()

async def has_awarded(user_id, guild_id, goal_id):
    """Verifica se um usuário já recebeu a recompensa de uma meta."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM awarded_goals WHERE user_id=? AND guild_id=? AND goal_id=?", (user_id, guild_id, goal_id))
        return bool(await cur.fetchone())

async def set_reset_config(guild_id, weekday, hour, minute):
    """Define a configuração (dia e hora) para o reset semanal de tempo."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO weekly_reset_config (guild_id,weekday,hour,minute) VALUES (?,?,?,?)",
                         (guild_id, weekday, hour, minute))
        await db.commit()

async def get_reset_config(guild_id):
    """Obtém a configuração do reset semanal de um servidor."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT weekday,hour,minute FROM weekly_reset_config WHERE guild_id=?", (guild_id,))
        row = await cur.fetchone()
        return (int(row[0]), int(row[1]), int(row[2])) if row else (0, 0, 0)

async def get_last_reset(guild_id):
    """Obtém a data e hora do último reset semanal executado."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_reset FROM reset_state WHERE guild_id=?", (guild_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try: return datetime.fromisoformat(row[0])
            except: return None
        return None

async def set_last_reset(guild_id, dt: datetime):
    """Registra a data e hora de um reset semanal no banco de dados."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO reset_state (guild_id,last_reset) VALUES (?,?)", (guild_id, dt.isoformat()))
        await db.commit()

async def get_rank(user_id, guild_id):
    """Consulta o banco de dados para encontrar a posição (rank) de um usuário com base no tempo total."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Pede todos os usuários da guilda, ordenados do maior tempo para o menor
        cur = await db.execute("SELECT user_id FROM total_times WHERE guild_id=? ORDER BY total_seconds DESC", (guild_id,))
        rows = await cur.fetchall()
        # Itera sobre os resultados para encontrar a posição do usuário solicitado
        for i, r in enumerate(rows, start=1):
            if r[0] == user_id:
                return i # Retorna a posição (rank)
    return None # Retorna None se o usuário não estiver no ranking

async def update_goal_reset_flag(guild_id: int, goal_id: int, reset_flag: bool):
    """Atualiza a propriedade 'reset_on_weekly' de uma meta específica."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Converte o booleano (True/False) para inteiro (1/0) para salvar no DB
        flag_as_int = 1 if reset_flag else 0
        await db.execute("UPDATE goals SET reset_on_weekly=? WHERE guild_id=? AND id=?",
                         (flag_as_int, guild_id, goal_id))
        await db.commit()

async def get_awarded_users(guild_id: int, goal_id: int):
    """Retorna uma lista de IDs de usuários que já receberam a recompensa de uma meta."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM awarded_goals WHERE guild_id=? AND goal_id=?", (guild_id, goal_id))
        rows = await cur.fetchall()
        # Retorna uma lista de IDs, por exemplo: [12345, 67890]
        return [r[0] for r in rows]

<<<<<<< HEAD
async def save_last_week_ranking(guild_id: int):
    """Salva o ranking atual como o ranking da última semana, apagando o anterior."""
=======
async def archive_weekly_times(guild_id, reset_date_iso):
    """Copia os tempos atuais da tabela total_times para a tabela de histórico."""
>>>>>>> 25ef76a395daef396a31e04fbabb33c249b193da
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id, total_seconds FROM total_times WHERE guild_id=?", (guild_id,))
        rows = await cursor.fetchall()

<<<<<<< HEAD
        # Limpa o histórico antigo e insere o novo de uma vez (transação)
        await db.execute("DELETE FROM weekly_time_history WHERE guild_id=?", (guild_id,))
        if rows:
            to_insert = [(guild_id, user_id, total_seconds) for user_id, total_seconds in rows]
            await db.executemany("INSERT INTO weekly_time_history (guild_id, user_id, total_seconds) VALUES (?, ?, ?)", to_insert)
        await db.commit()

async def get_last_week_ranking(guild_id: int):
    """Busca o ranking da última semana salva."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id, total_seconds FROM weekly_time_history WHERE guild_id=? ORDER BY total_seconds DESC", (guild_id,))
=======
        if not rows:
            return

        to_insert = [(guild_id, user_id, total_seconds, reset_date_iso) for user_id, total_seconds in rows]
        await db.executemany("INSERT OR REPLACE INTO weekly_time_history (guild_id, user_id, total_seconds, reset_date) VALUES (?, ?, ?, ?)", to_insert)
        await db.commit()

async def get_weekly_history(guild_id):
    """Busca o ranking da última semana arquivada."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT MAX(reset_date) FROM weekly_time_history WHERE guild_id=?", (guild_id,))
        latest_date_row = await cursor.fetchone()
        
        if not latest_date_row or not latest_date_row[0]:
            return None, []

        latest_date = latest_date_row[0]
        cursor = await db.execute("SELECT user_id, total_seconds FROM weekly_time_history WHERE guild_id=? AND reset_date=? ORDER BY total_seconds DESC", (guild_id, latest_date))
        rows = await cursor.fetchall()
        return latest_date, rows

async def set_history_config(guild_id: int, channel_id: int, retention_days: int):
    """Define ou atualiza as configurações do histórico semanal."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO history_config (guild_id, post_channel_id, retention_days) VALUES (?, ?, ?)",
                         (guild_id, channel_id, retention_days))
        await db.commit()

async def get_history_config(guild_id: int):
    """Busca as configurações do histórico semanal."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT post_channel_id, retention_days FROM history_config WHERE guild_id=?", (guild_id,))
        return await cursor.fetchone()

async def get_all_history_dates(guild_id: int):
    """Retorna uma lista de todas as datas de reset arquivadas."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT DISTINCT reset_date FROM weekly_time_history WHERE guild_id=? ORDER BY reset_date DESC", (guild_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def get_history_by_date(guild_id: int, reset_date_iso: str):
    """Busca o ranking de uma data específica."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id, total_seconds FROM weekly_time_history WHERE guild_id=? AND reset_date=? ORDER BY total_seconds DESC", (guild_id, reset_date_iso))
        return await cursor.fetchall()

async def toggle_pin_history(guild_id: int, reset_date_iso: str, pin_status: bool):
    """Fixa ou desafixa um registro de histórico semanal."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE weekly_time_history SET pinned = ? WHERE guild_id=? AND reset_date=?",
                         (1 if pin_status else 0, guild_id, reset_date_iso))
        await db.commit()

async def cleanup_old_history(guild_id: int, retention_days: int):
    """Apaga registros de histórico mais antigos que o período de retenção que não estão fixados."""
    async with aiosqlite.connect(DB_PATH) as db:
        # A data limite é calculada em TEXT no formato ISO, que é comparável
        limit_date = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
        await db.execute("DELETE FROM weekly_time_history WHERE guild_id=? AND reset_date < ? AND pinned = 0",
                         (guild_id, limit_date))
        await db.commit()

async def get_active_sessions(guild_id: int):
    """Retorna todas as sessões de voz ativas para uma guilda."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM sessions WHERE guild_id=?", (guild_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
    
async def add_giveaway(message_id, guild_id, channel_id, end_time, winner_count, prize, required_roles_csv):
    """Adiciona um novo sorteio ao banco de dados."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO giveaways (message_id, guild_id, channel_id, end_time, winner_count, prize, required_roles) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (message_id, guild_id, channel_id, end_time.isoformat(), winner_count, prize, required_roles_csv)
        )
        await db.commit()

async def remove_giveaway(message_id):
    """Remove um sorteio e seus participantes do banco de dados."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM giveaways WHERE message_id=?", (message_id,))
        await db.execute("DELETE FROM giveaway_participants WHERE message_id=?", (message_id,))
        await db.commit()

async def add_giveaway_participant(message_id, user_id):
    """Adiciona um participante a um sorteio."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO giveaway_participants (message_id, user_id) VALUES (?, ?)", (message_id, user_id))
        await db.commit()

async def get_giveaway_participants(message_id):
    """Retorna uma lista de todos os participantes de um sorteio."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM giveaway_participants WHERE message_id=?", (message_id,))
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

async def get_active_giveaways():
    """Retorna todos os sorteios que ainda não terminaram."""
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute("SELECT * FROM giveaways WHERE end_time > ?", (now,))
        return await cursor.fetchall()

async def get_finished_giveaways():
    """Retorna todos os sorteios cujo tempo já acabou."""
    async with aiosqlite.connect(DB_PATH) as db:
        now = datetime.now(timezone.utc).isoformat()
        cursor = await db.execute("SELECT * FROM giveaways WHERE end_time <= ?", (now,))
>>>>>>> 25ef76a395daef396a31e04fbabb33c249b193da
        return await cursor.fetchall()