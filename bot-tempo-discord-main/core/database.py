import aiosqlite
from datetime import datetime, timezone

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
        await db.commit()
        
        # Tenta adicionar uma nova coluna à tabela 'goals' para compatibilidade com versões antigas.
        # Se a coluna já existir, a exceção será ignorada.
        try:
            await db.execute("ALTER TABLE goals ADD COLUMN required_role_ids TEXT")
            await db.commit()
        except:
            pass

async def start_session(user_id, guild_id, channel_id, start_time_iso):
    """Inicia e registra uma nova sessão de tempo para um usuário no banco de dados."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO sessions (user_id,guild_id,channel_id,start_time) VALUES (?,?,?,?)",
                         (user_id, guild_id, channel_id, start_time_iso))
        await db.commit()

async def end_session(user_id, guild_id, end_time_iso):
    """Finaliza uma sessão, calcula a duração e a adiciona ao tempo total do usuário."""
    start_iso, new_total = None, None
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT start_time FROM sessions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = await cur.fetchone()
        if not row: return None
        
        start_iso = row[0]
        try:
            start_dt = datetime.fromisoformat(start_iso)
            end_dt = datetime.fromisoformat(end_time_iso)
        except:
            start_dt, end_dt = None, None
        
        if start_dt and end_dt:
            duration = int((end_dt - start_dt).total_seconds())
            if duration < 0: duration = 0
            
            cur2 = await db.execute("SELECT total_seconds FROM total_times WHERE user_id=? AND guild_id=?", (user_id, guild_id))
            total_row = await cur2.fetchone()
            
            if total_row:
                new_total = int(total_row[0]) + duration
                await db.execute("UPDATE total_times SET total_seconds=? WHERE user_id=? AND guild_id=?", (new_total, user_id, guild_id))
            else:
                new_total = duration
                await db.execute("INSERT INTO total_times (user_id,guild_id,total_seconds) VALUES (?,?,?)", (user_id, guild_id, new_total))
            
            await db.execute("DELETE FROM sessions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
            await db.commit()
            
    # A chamada para _check_and_award_goals_for_user foi removida daqui.
    # Ela será feita no manipulador de eventos on_voice_state_update.
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
        return (int(row[0]), int(row[1]), int(row[2])) if row else (None, None, None)

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