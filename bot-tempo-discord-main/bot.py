
import os
import re
import asyncio
import aiosqlite
from datetime import datetime, timezone, timedelta
import discord
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import aiohttp
import traceback
import shutil
import subprocess

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except Exception:
    YTDLP_AVAILABLE = False

# ===================================================================================
# CONFIGURAÇÃO E VARIÁVEIS GLOBAIS
# ===================================================================================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
BOT_PREFIX = os.getenv("BOT_PREFIX", "!")
DB_PATH = os.getenv("DB_PATH", "data.db")
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=-3))

CALLCARD_UPDATE_INTERVAL = int(os.getenv("CALLCARD_UPDATE_INTERVAL", 180))
GOAL_SONG_YOUTUBE = os.getenv("GOAL_SONG_YOUTUBE", "https://youtu.be/TFdO7oqkMzI?si=EGgOx6bgvalpJ5i0")
GOAL_SONG_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "goal_song.mp3")
FFMPEG_EXECUTABLE = os.getenv("FFMPEG_EXECUTABLE")

os.makedirs(ASSETS_DIR, exist_ok=True)
http_session: aiohttp.ClientSession = None
active_call_messages = {}

# ===================================================================================
# FUNÇÕES AUXILIARES (HELPERS)
# ===================================================================================

def _font_path_in_assets(name):
    p = os.path.join(ASSETS_DIR, name)
    return p if os.path.exists(p) else None

def _load_font_prefer(names, size):
    for n in names:
        ap = _font_path_in_assets(n)
        if ap:
            try: return ImageFont.truetype(ap, size)
            except: pass
    for f in ["arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try: return ImageFont.truetype(f, size)
        except: pass
    return ImageFont.load_default()

def fmt_hms(s):
    try: s = int(s)
    except: return "00:00:00"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"

def now_iso_utc():
    return datetime.now(timezone.utc).isoformat()

def _truncate(text, max_chars):
    if not text: return ""
    return text if len(text) <= max_chars else text[:max_chars-1] + "…"

def human_hours_minutes(seconds: int):
    try: s = int(seconds)
    except: s = 0
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    h_txt = f"{h} hora" + ("s" if h != 1 else "")
    m_txt = f"{m} minuto" + ("s" if m != 1 else "")
    return f"{h_txt} e {m_txt}"

async def fetch_avatar_bytes(url, timeout=6):
    global http_session
    if not url: return None
    if http_session is None or http_session.closed:
        http_session = aiohttp.ClientSession()
    try:
        async with http_session.get(url, timeout=timeout) as resp:
            if resp.status == 200: return await resp.read()
    except:
        return None
    return None

def _resize_and_crop_square(img, size):
    w,h = img.size
    side = min(w,h)
    left, top = (w - side)//2, (h - side)//2
    img = img.crop((left, top, left+side, top+side))
    return img.resize((size,size), Image.LANCZOS)

# ===================================================================================
# GERADORES DE IMAGEM
# ===================================================================================

def gerar_stats_card(username, total_seconds, current_seconds, avatar_bytes=None, rank=None, goals=None):
    AVATAR_CENTER_REL = (0.175, 0.50); AVATAR_DIAMETER_REL = 0.22
    NAME_CENTER_REL = (0.63, 0.28); NAME_FONT_REL = 0.045
    INFO_VALUE_Y_REL = 0.49; INFO_COL1_X_REL = 0.44; INFO_COL2_X_REL = 0.63; INFO_COL3_X_REL = 0.82; INFO_VALUE_FONT_REL = 0.025
    GOAL_BAR_Y_REL = 0.75; GOAL_BAR_CENTER_X_REL = 0.63; GOAL_BAR_WIDTH_REL = 0.55; GOAL_BAR_HEIGHT_REL = 0.06; GOAL_FONT_REL = 0.019
    TEXT_COLOR = (255, 255, 255, 255); TITLE_COLOR = (200, 200, 200, 255); BAR_BG_COLOR = (40, 40, 45, 255); BAR_FG_COLOR = (255, 255, 255, 255)
    
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        template_path = os.path.join(script_dir, "BOTberengue.png")
        base = Image.open(template_path).convert("RGBA")
    except FileNotFoundError:
        base = Image.new("RGBA", (1000, 320), (60, 50, 40, 255))
    
    w, h = base.size; draw = ImageDraw.Draw(base)
    bold_font_files = ["Poppins-Bold.ttf", "Inter-Bold.ttf", "arialbd.ttf"]; regular_font_files = ["Poppins-Regular.ttf", "Inter-Regular.ttf", "arial.ttf"]
    name_font = _load_font_prefer(bold_font_files, int(w * NAME_FONT_REL)); info_value_font = _load_font_prefer(regular_font_files, int(w * INFO_VALUE_FONT_REL)); goal_font = _load_font_prefer(regular_font_files, int(w * GOAL_FONT_REL))
    
    avatar_diam = int(w * AVATAR_DIAMETER_REL)
    try:
        if not avatar_bytes: raise ValueError("Bytes do avatar não foram obtidos.")
        av = Image.open(BytesIO(avatar_bytes)).convert("RGBA"); av = _resize_and_crop_square(av, avatar_diam)
    except Exception:
        av = Image.new("RGBA", (avatar_diam, avatar_diam), (200, 200, 200, 255)); ad = ImageDraw.Draw(av)
        initials = "".join([p[0] for p in (username or "U").split()[:2]]).upper()
        fbig = _load_font_prefer(bold_font_files, avatar_diam // 2)
        ad.text((avatar_diam/2, avatar_diam/2), initials, font=fbig, fill=(60,60,65,255), anchor="mm")
    
    avatar_cx, avatar_cy = int(w * AVATAR_CENTER_REL[0]), int(h * AVATAR_CENTER_REL[1]); avatar_x, avatar_y = avatar_cx - avatar_diam // 2, avatar_cy - avatar_diam // 2
    mask = Image.new("L", (avatar_diam, avatar_diam), 0); md = ImageDraw.Draw(mask)
    md.ellipse((0, 0, avatar_diam, avatar_diam), fill=255); base.paste(av, (avatar_x, avatar_y), mask)
    
    def draw_centered_text(coords_rel, text, font, fill=TEXT_COLOR):
        cx, cy = int(w * coords_rel[0]), int(h * coords_rel[1]); draw.text((cx, cy), text, font=font, fill=fill, anchor="mm")
    
    draw_centered_text(NAME_CENTER_REL, _truncate(username or "Usuário", 20), name_font)
    draw_centered_text((INFO_COL1_X_REL, INFO_VALUE_Y_REL), fmt_hms(current_seconds or 0), info_value_font)
    draw_centered_text((INFO_COL2_X_REL, INFO_VALUE_Y_REL), f"#{rank}" if rank else "-", info_value_font)
    draw_centered_text((INFO_COL3_X_REL, INFO_VALUE_Y_REL), fmt_hms(total_seconds or 0), info_value_font)
    
    next_goal = next((g for g in goals if not g.get('awarded')), None) if isinstance(goals, list) else None
    bar_width = int(w * GOAL_BAR_WIDTH_REL * 0.9); bar_height = max(12, int(h * GOAL_BAR_HEIGHT_REL * 0.55)); bar_cx = int(w * GOAL_BAR_CENTER_X_REL)
    bar_y = int(h * (GOAL_BAR_Y_REL - 0.045)); bar_x = bar_cx - bar_width // 2; radius = max(6, int(h * 0.03))
    
    if not next_goal:
        draw.text((bar_cx, bar_y + bar_height // 2), "Nenhuma meta ativa", font=goal_font, fill=TITLE_COLOR, anchor="mm")
    else:
        goal_name_raw = str(next_goal.get('name', 'Meta')); goal_req_secs = next_goal.get('required', 0)
        goal_time_str = f"({human_hours_minutes(goal_req_secs)})"; full_text = f"{goal_name_raw} {goal_time_str}"
        btn_font = _load_font_prefer(bold_font_files, max(12, int(w * GOAL_FONT_REL * 0.95)))
        try: tb = draw.textbbox((0, 0), full_text, font=btn_font); text_w = tb[2] - tb[0]; text_h = tb[3] - tb[1]
        except Exception: text_w, text_h = btn_font.getsize(full_text)
        btn_pad_x = max(6, int(w * 0.006)); btn_pad_y = max(4, int(h * 0.008)); btn_w = text_w + btn_pad_x * 2; btn_h = text_h + btn_pad_y * 2
        max_btn_w = bar_width - max(8, int(w * 0.01))
        if btn_w > max_btn_w:
            btn_w = max_btn_w; approx_char_w = max(6, text_w / max(1, len(full_text)))
            max_chars = max(4, int((btn_w - btn_pad_x*2) / approx_char_w)); display_text = _truncate(full_text, max_chars)
        else:
            display_text = _truncate(full_text, 50)
        gap = int(h * 0.006); btn_x = bar_x + max(4, int(w * 0.004)); btn_y = bar_y - btn_h - gap; btn_radius = max(6, btn_h // 2)
        draw.rounded_rectangle((btn_x, btn_y, btn_x + btn_w, btn_y + btn_h), radius=btn_radius, fill=BAR_BG_COLOR)
        draw.text((btn_x + btn_w / 2, btn_y + btn_h / 2), display_text, font=btn_font, fill=TEXT_COLOR, anchor="mm")
        
        draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), radius=radius, fill=BAR_BG_COLOR)
        progress = float(next_goal.get('progress', 0.0)); progress = max(0.0, min(1.0, progress))
        inner_px = max(6, int(w * 0.006)); inner_py = max(3, int(bar_height * 0.12)); usable_width = bar_width - inner_px * 2; fill_width = int(usable_width * progress)
        if fill_width > 0:
            fill_box = (bar_x + inner_px, bar_y + inner_py, bar_x + inner_px + fill_width, bar_y + bar_height - inner_py)
            draw.rounded_rectangle(fill_box, radius=max(4, radius - 2), fill=BAR_FG_COLOR)
        
        percent_text = f"{int(progress * 100)}%"; pct_x = bar_x + bar_width - inner_px - int(w * 0.012); pct_y = bar_y + bar_height // 2 - 5
        draw.text((pct_x, pct_y), percent_text, font=goal_font, fill=TEXT_COLOR, anchor="rm")

    buf = BytesIO(); base.save(buf, format="PNG"); buf.seek(0)
    return buf

def gerar_leaderboard_card(rows, guild=None, page: int = 1, top_template_path: str = "BOTbereRank.png", list_template_path: str = "BOTbereRank2.png") -> BytesIO:
    def fmt_hms_long(sec):
        s = int(sec or 0); d, s = divmod(s, 86400); h, s = divmod(s, 3600); m, s = divmod(s, 60)
        if d > 0: return f"{d}d {h}h {m}m"
        if h > 0: return f"{h}h {m}m {s}s"
        return f"{m}m {s}s"
    
    def resolve(key):
        name, avatar_url = str(key), None
        if guild and (isinstance(key, int) or (isinstance(key, str) and key.isdigit())):
            m = guild.get_member(int(key))
            if m: name, avatar_url = m.display_name, str(getattr(m, "display_avatar", m).url)
        return name, avatar_url

    def paste_avatar(canvas, cx, cy, sz, url, initials=""):
        avatar_inner_sz = int(sz * 0.96)
        x0_avatar, y0_avatar = int(cx - avatar_inner_sz / 2), int(cy - avatar_inner_sz / 2)
        try:
            import requests
            av_bytes = requests.get(url, timeout=4).content if url else None
        except:
            av_bytes = None
        circ = Image.new("RGBA", (avatar_inner_sz, avatar_inner_sz))
        if av_bytes:
            im = Image.open(BytesIO(av_bytes)).convert("RGBA")
            im = _resize_and_crop_square(im, avatar_inner_sz)
            mask = Image.new("L", (avatar_inner_sz, avatar_inner_sz), 0); ImageDraw.Draw(mask).ellipse((0, 0, avatar_inner_sz, avatar_inner_sz), fill=255)
            circ.paste(im, (0, 0), mask)
        else:
            d = ImageDraw.Draw(circ); d.ellipse((0, 0, avatar_inner_sz, avatar_inner_sz), fill=(100, 100, 100, 255))
            if initials: f = _load_font_prefer(["Inter-Bold.ttf", "arialbd.ttf"], max(12, int(avatar_inner_sz * 0.4))); d.text((avatar_inner_sz/2, avatar_inner_sz/2), initials, font=f, fill=(200,200,200,255), anchor="mm")
        canvas.paste(circ, (x0_avatar, y0_avatar), circ)
    
    podium_name_f = _load_font_prefer(["Inter-Bold.ttf", "arialbd.ttf"], 30); podium_time_f = _load_font_prefer(["Inter-Regular.ttf", "arial.ttf"], 24)
    list_name_f = _load_font_prefer(["Inter-Bold.ttf", "arialbd.ttf"], 22); list_time_f = _load_font_prefer(["Inter-Regular.ttf", "arial.ttf"], 18)
    
    podium_avatar_sz = [234, 236, 234]; podium_avatar_pos = [(184, 223), (500, 180), (1000 - 184, 23)]
    podium_name_pos = [(181, 477), (500, 452), (1000 - 181, 477)]; podium_time_pos = [(187, 561), (500, 560), (1000 - 187, 561)]
    list_avatar_sz = 58; list_avatar_left_cx = 91; list_avatar_right_cx = 567; list_text_left_cx = 289; list_text_right_cx = 765
    list_start_y = 675; list_y_step = 92
    
    list_page_avatar_sz = 60; list_page_start_y = 112; list_page_y_step = 91; list_page_avatar_x = [91, 566]; list_page_text_x = [284, 764]
    PER_COL = 10; PER_PAGE = PER_COL * 2
    
    tpl_path = top_template_path if page == 1 else list_template_path
    base = Image.open(tpl_path).convert("RGBA"); draw = ImageDraw.Draw(base)
    
    if page == 1:
        podium_slots_mapping = { 0: 1, 1: 0, 2: 2 }
        for i in range(3):
            rank_index_in_rows = podium_slots_mapping[i]
            if rank_index_in_rows < len(rows):
                k, sec = rows[rank_index_in_rows]; name, url = resolve(k); init = "".join(p[0] for p in name.split()[:2]).upper()
                cx, cy = podium_avatar_pos[i]; sz = podium_avatar_sz[i]
                paste_avatar(base, cx, cy, sz, url, init)
                nm = _truncate(name, 15); draw.text(podium_name_pos[i], nm, font=podium_name_f, fill="white", anchor="mm")
                ts = fmt_hms_long(sec); draw.text(podium_time_pos[i], ts, font=podium_time_f, fill="white", anchor="mm")
        for i in range(3, 9):
            if i < len(rows):
                k, sec = rows[i]; name, url = resolve(k); init = "".join(p[0] for p in name.split()[:2]).upper()
                col = 0 if (i - 3) < 3 else 1; row_in_col = (i - 3) % 3
                avatar_cx = list_avatar_left_cx if col == 0 else list_avatar_right_cx; text_cx = list_text_left_cx if col == 0 else list_text_right_cx
                center_y = list_start_y + row_in_col * list_y_step
                paste_avatar(base, avatar_cx, center_y, list_avatar_sz, url, init)
                name_text = _truncate(name, 18); draw.text((text_cx, center_y - 12), name_text, font=list_name_f, fill="white", anchor="mm")
                time_text = fmt_hms_long(sec); draw.text((text_cx, center_y + 12), time_text, font=list_time_f, fill="#cccccc", anchor="mm")
    else:
        start_rank = 9 + (page - 2) * PER_PAGE; display = rows[start_rank : start_rank + PER_PAGE]
        for i, (k, sec) in enumerate(display):
            name, url = resolve(k); init = "".join(p[0] for p in name.split()[:2]).upper()
            col = i // PER_COL; row_in_col = i % PER_COL
            avatar_cx = list_page_avatar_x[col]; text_cx = list_page_text_x[col]
            center_y = list_page_start_y + row_in_col * list_page_y_step
            paste_avatar(base, avatar_cx, center_y, list_page_avatar_sz, url, init)
            rank_and_name = f"#{start_rank + i + 1}  {_truncate(name, 18)}"
            draw.text((text_cx, center_y - 12), rank_and_name, font=list_name_f, fill="white", anchor="mm")
            time_text = fmt_hms_long(sec); draw.text((text_cx, center_y + 12), time_text, font=list_time_f, fill="#cccccc", anchor="mm")
            
    out = BytesIO(); base.save(out, format="PNG"); out.seek(0)
    return out

# ===================================================================================
# LÓGICA DO BANCO DE DADOS (DB)
# ===================================================================================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS sessions (
            user_id INTEGER, guild_id INTEGER, channel_id INTEGER, start_time TEXT,
            PRIMARY KEY(user_id,guild_id) )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS total_times (
            user_id INTEGER, guild_id INTEGER, total_seconds INTEGER,
            PRIMARY KEY(user_id,guild_id) )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS log_channels (
            guild_id INTEGER, channel_type TEXT, channel_id INTEGER,
            PRIMARY KEY(guild_id,channel_type) )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS goals (
            id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER, name TEXT, 
            seconds_required INTEGER, role_id INTEGER, required_role_id INTEGER, 
            reset_on_weekly INTEGER DEFAULT 1, required_role_ids TEXT )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS awarded_goals (
            user_id INTEGER, guild_id INTEGER, goal_id INTEGER, awarded_at TEXT,
            PRIMARY KEY(user_id,guild_id,goal_id) )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS weekly_reset_config (
            guild_id INTEGER PRIMARY KEY, weekday INTEGER, hour INTEGER, minute INTEGER )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS reset_state (
            guild_id INTEGER PRIMARY KEY, last_reset TEXT )""")
        await db.execute("""CREATE TABLE IF NOT EXISTS prohibited_channels (
            guild_id INTEGER, channel_id INTEGER, PRIMARY KEY(guild_id, channel_id) )""")
        await db.commit()
        try:
            await db.execute("ALTER TABLE goals ADD COLUMN required_role_ids TEXT")
            await db.commit()
        except: pass

async def start_session(user_id, guild_id, channel_id, start_time_iso):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO sessions (user_id,guild_id,channel_id,start_time) VALUES (?,?,?,?)",
                         (user_id, guild_id, channel_id, start_time_iso))
        await db.commit()

async def end_session(user_id, guild_id, end_time_iso):
    start_iso, new_total = None, None
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT start_time FROM sessions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = await cur.fetchone()
        if not row: return None
        start_iso = row[0]
        try: start_dt, end_dt = datetime.fromisoformat(start_iso), datetime.fromisoformat(end_time_iso)
        except: start_dt, end_dt = None, None
        
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

    if new_total is not None:
        try:
            await _check_and_award_goals_for_user(user_id, guild_id, new_total, current_seconds=0)
        except Exception as e:
            print(f"!!! ERRO AO EXECUTAR A CHECAGEM DE METAS: {e}"); traceback.print_exc()
            
    return start_iso

async def total_time(user_id, guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT total_seconds FROM total_times WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = await cur.fetchone()
        return int(row[0]) if row else 0

async def current_session_time(user_id, guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT start_time FROM sessions WHERE user_id=? AND guild_id=?", (user_id, guild_id))
        row = await cur.fetchone()
        if not row: return 0
        try: start_time = datetime.fromisoformat(row[0])
        except: return 0
        last_reset = await get_last_reset(guild_id)
        if last_reset and start_time < last_reset:
            start_time = last_reset
        duration = int((datetime.now(timezone.utc) - start_time).total_seconds())
        return max(0, duration)

async def set_log_channel(guild_id: int, channel_id: int, channel_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO log_channels (guild_id, channel_type, channel_id) VALUES (?, ?, ?)",
                         (guild_id, channel_type, channel_id))
        await db.commit()

async def get_log_channel(guild_id: int, channel_type: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT channel_id FROM log_channels WHERE guild_id=? AND channel_type=?", (guild_id, channel_type))
        row = await cur.fetchone()
        return int(row[0]) if row and row[0] is not None else None

async def add_prohibited_channel(guild_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO prohibited_channels (guild_id, channel_id) VALUES (?, ?)", (guild_id, channel_id))
        await db.commit()

async def remove_prohibited_channel(guild_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM prohibited_channels WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
        await db.commit()

async def list_prohibited_channels(guild_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT channel_id FROM prohibited_channels WHERE guild_id=?", (guild_id,))
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def is_channel_prohibited(guild_id: int, channel_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM prohibited_channels WHERE guild_id=? AND channel_id=?", (guild_id, channel_id))
        return bool(await cur.fetchone())

async def add_goal(guild_id, name, seconds_required, reward_role_id=None, required_role_ids_csv=None, reset_on_weekly=1):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO goals (guild_id, name, seconds_required, role_id, required_role_ids, reset_on_weekly) VALUES (?,?,?,?,?,?)",
                         (guild_id, name, int(seconds_required), reward_role_id, required_role_ids_csv, int(reset_on_weekly)))
        await db.commit()

async def remove_goal(guild_id, goal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM goals WHERE guild_id=? AND id=?", (guild_id, goal_id))
        await db.execute("DELETE FROM awarded_goals WHERE guild_id=? AND goal_id=?", (guild_id, goal_id))
        await db.commit()

async def list_goals(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,name,seconds_required,role_id,required_role_id,reset_on_weekly,required_role_ids FROM goals WHERE guild_id=? ORDER BY seconds_required ASC",
                               (guild_id,))
        return await cur.fetchall()

async def get_goal(guild_id, goal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT id,name,seconds_required,role_id,required_role_id,reset_on_weekly,required_role_ids FROM goals WHERE guild_id=? AND id=?",
                               (guild_id, goal_id))
        return await cur.fetchone()

async def mark_awarded(user_id, guild_id, goal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO awarded_goals (user_id,guild_id,goal_id,awarded_at) VALUES (?,?,?,?)",
                         (user_id, guild_id, goal_id, now_iso_utc()))
        await db.commit()

async def has_awarded(user_id, guild_id, goal_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT 1 FROM awarded_goals WHERE user_id=? AND guild_id=? AND goal_id=?", (user_id, guild_id, goal_id))
        return bool(await cur.fetchone())

async def set_reset_config(guild_id, weekday, hour, minute):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO weekly_reset_config (guild_id,weekday,hour,minute) VALUES (?,?,?,?)",
                         (guild_id, weekday, hour, minute))
        await db.commit()

async def get_reset_config(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT weekday,hour,minute FROM weekly_reset_config WHERE guild_id=?", (guild_id,))
        row = await cur.fetchone()
        return (int(row[0]), int(row[1]), int(row[2])) if row else (0,0,0)

async def get_last_reset(guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_reset FROM reset_state WHERE guild_id=?", (guild_id,))
        row = await cur.fetchone()
        if row and row[0]:
            try: return datetime.fromisoformat(row[0])
            except: return None
        return None

async def set_last_reset(guild_id, dt: datetime):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR REPLACE INTO reset_state (guild_id,last_reset) VALUES (?,?)", (guild_id, dt.isoformat()))
        await db.commit()

# ===================================================================================
# LÓGICA PRINCIPAL DO BOT
# ===================================================================================


async def _check_and_award_goals_for_user(user_id, guild_id, total_seconds, current_seconds=0):
    rows = await list_goals(guild_id)
    if not rows: return
    try:
        guild = bot.get_guild(guild_id)
        if not guild: return
        member = guild.get_member(user_id) or await guild.fetch_member(user_id)
        if not member: return
    except Exception as e:
        print(f"Erro ao buscar membro em _check_and_award_goals_for_user: {e}")
        return
    
    for r in rows:
        try:
            goal_id, name, seconds_required, reward_role_id, _, _, required_role_ids_csv = r
            if await has_awarded(user_id, guild_id, goal_id):
                continue
            
            effective = int(total_seconds) + int(current_seconds)
            if effective < int(seconds_required or 0):
                continue

            if required_role_ids_csv:
                req_ids = {int(rid.strip()) for rid in required_role_ids_csv.split(',')}
                member_role_ids = {role.id for role in member.roles}
                if not req_ids.intersection(member_role_ids):
                    continue

            await mark_awarded(user_id, guild_id, goal_id)
            if reward_role_id:
                try:
                    role = guild.get_role(int(reward_role_id))
                    if role: await member.add_roles(role, reason="Meta atingida")
                except Exception as e:
                    print(f"Erro ao dar cargo da meta '{name}': {e}")

            goallog_id = await get_log_channel(guild_id, "goallog")
            ch = guild.get_channel(goallog_id) if goallog_id else None
            if ch:
                try:
                    ord_num = 1
                    try:
                        async with aiosqlite.connect(DB_PATH) as db:
                            cur = await db.execute("SELECT COUNT(*) FROM awarded_goals WHERE guild_id=? AND goal_id=?", (guild_id, goal_id))
                            crow = await cur.fetchone()
                            if crow: ord_num = int(crow[0])
                    except: pass
                    
                    role_txt = f"<@&{reward_role_id}>" if reward_role_id else "N/A"
                    time_txt = human_hours_minutes(seconds_required)

                    # --- MUDANÇA AQUI: Usa a menção da pessoa ---
                    msg = (
                        f"<a:1937verifycyan:1155565499002925167> O(a) {member.mention} acabou de concluir uma meta.\n\n"
                        f"- Informações da Meta:\n"
                        f"- Cargo: {role_txt}\n"
                        f"- Tempo: **{time_txt}**\n"
                        f"- Este membro foi o **{ord_num}º** membro a concluir a meta."
                    )
                    # Garante que só vai pingar o usuário, e não o cargo (se o cargo for mencionável)
                    await ch.send(msg, allowed_mentions=discord.AllowedMentions(users=True, roles=False))
                except Exception as e:
                    traceback.print_exc()
        except Exception:
            continue

def _detect_ffmpeg_executable():
    for name in ("ffmpeg", "ffmpeg.exe"):
        w = shutil.which(name)
        if w: return w
    if FFMPEG_EXECUTABLE and os.path.exists(FFMPEG_EXECUTABLE):
        return FFMPEG_EXECUTABLE
    return "ffmpeg"

async def _play_song_in_vc(guild, channel):
    voice_client = None
    try:
        me = guild.me if guild else None
        if not channel or not isinstance(channel, discord.VoiceChannel): return False
        if me and (not me.guild_permissions.connect or not me.guild_permissions.speak): return False
        voice_client = discord.utils.get(bot.voice_clients, guild=guild)
        try:
            if voice_client and voice_client.is_connected():
                if voice_client.channel != channel: await voice_client.move_to(channel)
            else:
                voice_client = await channel.connect(timeout=10.0)
        except Exception:
            try:
                if voice_client: await voice_client.disconnect(force=True)
                voice_client = await channel.connect(timeout=10.0)
            except Exception: return False
        
        ffmpeg_opts = {'options': '-vn -hide_banner -loglevel error'}
        ffmpeg_exec = _detect_ffmpeg_executable()
        
        async def _disconnect_safe(vc):
            if vc and vc.is_connected():
                try: await vc.disconnect()
                except: pass
        
        def _after_play(err):
            if err: print(f"Erro ao tocar música: {err}")
            fut = asyncio.run_coroutine_threadsafe(_disconnect_safe(voice_client), bot.loop)
            try: fut.result(timeout=15)
            except: pass
        
        if os.path.exists(GOAL_SONG_LOCAL):
            try:
                source = discord.FFmpegPCMAudio(GOAL_SONG_LOCAL, executable=ffmpeg_exec, **ffmpeg_opts)
                voice_client.play(source, after=_after_play); return True
            except Exception as e:
                print(f"Falha ao tocar arquivo local: {e}")
        
        if YTDLP_AVAILABLE:
            try:
                ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(GOAL_SONG_YOUTUBE, download=False)
                    stream_url = info.get('url')
                    if stream_url:
                        source = discord.FFmpegPCMAudio(stream_url, executable=ffmpeg_exec, **ffmpeg_opts)
                        voice_client.play(source, after=_after_play); return True
            except Exception as e:
                print(f"yt-dlp falhou ao extrair stream: {e}")
        
        await _disconnect_safe(voice_client); return False
    except Exception:
        traceback.print_exc()
        if voice_client and voice_client.is_connected():
            try: await voice_client.disconnect()
            except: pass
        return False

# ===================================================================================
# TAREFAS AGENDADAS (SCHEDULER)
# ===================================================================================

_DIAS = {"seg":0,"ter":1,"qua":2,"qui":3,"sex":4,"sab":5,"dom":6}
def _parse_day(s: str):
    s = s.strip().lower()
    if s.isdigit() and 0 <= int(s) <= 6: return int(s)
    for k, v in _DIAS.items():
        if k in s: return v
    return None

def _next_weekly_dt(now_utc: datetime, weekday: int, hour: int, minute: int):
    now_local = now_utc.astimezone(LOCAL_TZ)
    days_ahead = (weekday - now_local.weekday() + 7) % 7
    target_date = (now_local + timedelta(days=days_ahead)).date()
    target_local = datetime(target_date.year, target_date.month, target_date.day, hour, minute, tzinfo=LOCAL_TZ)
    if target_local <= now_local:
        target_local += timedelta(days=7)
    return target_local.astimezone(timezone.utc)

async def _weekly_reset_run_for_guild(guild: discord.Guild):
    try:
        rows = await list_goals(guild.id)
        goallog_id = await get_log_channel(guild.id, "goallog")
        ch = guild.get_channel(goallog_id) if goallog_id else None

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM total_times WHERE guild_id=?", (guild.id,))
            resetable_goal_ids = [r[0] for r in rows if r and int(r[5]) == 1]
            if resetable_goal_ids:
                qmarks = ",".join("?" for _ in resetable_goal_ids)
                await db.execute(f"DELETE FROM awarded_goals WHERE guild_id=? AND goal_id IN ({qmarks})", (guild.id, *resetable_goal_ids))
            await db.commit()
        
        if ch: await ch.send("🔁 Reset semanal executado. O tempo de voz de todos os membros foi zerado.")
        
        await set_last_reset(guild.id, datetime.now(timezone.utc))
        print(f"[reset] Reset executado para guild {guild.id} ({guild.name}).")
    except Exception as e:
        print(f"[reset] Erro ao executar reset para guild {getattr(guild,'id',None)}: {e}")
        traceback.print_exc()

async def weekly_reset_scheduler():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(60)
        now_utc = datetime.now(timezone.utc)
        for guild in bot.guilds:
            try:
                wd, hh, mm = await get_reset_config(guild.id)
                target_utc = _next_weekly_dt(now_utc, wd, hh, mm)
                last = await get_last_reset(guild.id)
                if now_utc >= target_utc and (not last or last < target_utc):
                    await _weekly_reset_run_for_guild(guild)
            except Exception as e:
                print(f"Erro no scheduler para guild {guild.id}: {e}")

# ===================================================================================
# DEFINIÇÃO DO BOT E VIEW
# ===================================================================================

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=BOT_PREFIX, intents=intents, help_command=None)

class RankingView(discord.ui.View):
    def __init__(self, ctx, rows, total_pages):
        super().__init__(timeout=180.0)
        self.ctx = ctx; self.rows = rows; self.page = 1; self.total_pages = total_pages
        self.message = None; self.update_buttons()

    def update_buttons(self):
        self.children[0].disabled = self.page == 1
        self.children[2].disabled = self.page == self.total_pages
        self.children[1].label = f"{self.page} / {self.total_pages}"

    async def update_message(self, interaction: discord.Interaction):
        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(None, gerar_leaderboard_card, self.rows, self.ctx.guild, self.page)
        f = discord.File(fp=buf, filename=f"ranking_pagina_{self.page}.png")
        await interaction.response.edit_message(attachments=[f], view=self)

    @discord.ui.button(emoji="⬅️", style=discord.ButtonStyle.blurple)
    async def previous_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 1:
            self.page -= 1; self.update_buttons(); await self.update_message(interaction)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.grey, disabled=True)
    async def page_display(self, interaction: discord.Interaction, button: discord.ui.Button): pass

    @discord.ui.button(emoji="➡️", style=discord.ButtonStyle.blurple)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.total_pages:
            self.page += 1; self.update_buttons(); await self.update_message(interaction)
            
    async def on_timeout(self):
        for item in self.children: item.disabled = True
        if self.message:
            try: await self.message.edit(view=self)
            except discord.errors.NotFound: pass

# ===================================================================================
# EVENTOS E TAREFAS DO BOT
# ===================================================================================

@bot.event
async def on_ready():
    await init_db()
    print(f"{bot.user} está online!")
    bot.loop.create_task(weekly_reset_scheduler())
    bot.loop.create_task(update_call_cards())

@bot.event
async def on_message(message: discord.Message):
    if message.author.bot: return
    if message.content.strip().lower() == "tome":
        try: await message.reply(f"Tome, <@602542180309008404>", allowed_mentions=discord.AllowedMentions(users=True))
        except: pass
    await bot.process_commands(message)

@bot.check
async def _global_channel_block_check(ctx: commands.Context):
    if ctx.guild is None or (hasattr(ctx.author, 'guild_permissions') and ctx.author.guild_permissions.administrator):
        return True
    try:
        return not await is_channel_prohibited(ctx.guild.id, ctx.channel.id)
    except:
        return True

@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        try: await ctx.reply("❌ Comandos estão proibidos neste canal.", mention_author=True, delete_after=10)
        except: pass
    elif isinstance(error, commands.MissingPermissions):
        try: await ctx.reply("Você não tem permissão para usar este comando.", mention_author=True)
        except: pass
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        print(f"[command-error] Comando: {ctx.command} | Usuário: {ctx.author.id} | Erro: {error}")
        traceback.print_exception(type(error), error, error.__traceback__)

@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot: return
    guild = member.guild; now = now_iso_utc()
    
    is_join = before.channel is None and after.channel is not None
    is_leave = before.channel is not None and after.channel is None
    is_switch = before.channel and after.channel and before.channel.id != after.channel.id
    
    if is_leave or is_switch:
        start_iso = await end_session(member.id, guild.id, now)
        duration = 0
        if start_iso:
            try: duration = int((datetime.fromisoformat(now) - datetime.fromisoformat(start_iso)).total_seconds())
            except: pass
        total_after = await total_time(member.id, guild.id)
        await _mark_user_exit_and_cleanup(guild, member, duration, total_after)

    if is_join or is_switch:
        await start_session(member.id, guild.id, after.channel.id, now)
        total = await total_time(member.id, guild.id)
        current = await current_session_time(member.id, guild.id)
        rank = await get_rank(member.id, guild.id)
        await _ensure_user_call_message(guild, member, total, current, rank)

async def _ensure_user_call_message(guild, user, total, current, rank):
    gmap = active_call_messages.setdefault(guild.id, {})
    existing = gmap.get(user.id)
    try:
        goals_rows = await list_goals(guild.id); goals = []
        if goals_rows:
            for r in goals_rows:
                gid, gname, greq, _, _, _, _ = r
                awarded = await has_awarded(user.id, guild.id, gid)
                effective = int(total or 0) + int(current or 0)
                greq_i = int(greq or 0)
                prog = min(1.0, effective / greq_i) if greq_i > 0 else 0.0
                goals.append({'id': gid, 'name': gname, 'required': greq_i, 'awarded': bool(awarded), 'progress': prog})

        avatar_url = str(getattr(user, "display_avatar", user).url)
        avatar_bytes = await fetch_avatar_bytes(avatar_url)

        loop = asyncio.get_running_loop()
        buf = await loop.run_in_executor(None, gerar_stats_card,
            user.display_name, total, current, avatar_bytes, rank, goals
        )

        ch_id = await get_log_channel(guild.id, "calllog")
        if not ch_id: return
        ch = guild.get_channel(ch_id)
        if not ch: return

        if existing:
            try:
                await existing.edit(attachments=[discord.File(fp=buf, filename="stats.png")])
            except discord.errors.NotFound:
                gmap.pop(user.id, None)
                await _ensure_user_call_message(guild, user, total, current, rank)
        else:
            content = f"👋 **{user.display_name}** entrou na chamada."
            newmsg = await ch.send(content=content, file=discord.File(fp=buf, filename="stats.png"))
            active_call_messages[guild.id][user.id] = newmsg
    except Exception as e:
        print(f"Erro em _ensure_user_call_message: {e}")
        traceback.print_exc()

async def _mark_user_exit_and_cleanup(guild, user, duration_seconds, total_after):
    gmap = active_call_messages.get(guild.id, {})
    msgobj = gmap.pop(user.id, None)
    try:
        if msgobj:
            goals_rows = await list_goals(guild.id); goals = []
            if goals_rows:
                for r in goals_rows:
                    gid, gname, greq, _, _, _, _ = r
                    awarded = await has_awarded(user.id, guild.id, gid)
                    greq_i = int(greq or 0)
                    prog = min(1.0, total_after / greq_i) if greq_i > 0 else 0.0
                    goals.append({'id': gid, 'name': gname, 'required': greq_i, 'awarded': bool(awarded), 'progress': prog})

            avatar_url = str(getattr(user, "display_avatar", user).url)
            avatar_bytes = await fetch_avatar_bytes(avatar_url)
            rank = await get_rank(user.id, guild.id)

            loop = asyncio.get_running_loop()
            buf = await loop.run_in_executor(None, gerar_stats_card,
                user.display_name, total_after, 0, avatar_bytes, rank, goals
            )

            content = f"⏱️ **{user.display_name}** saiu — Duração: **{fmt_hms(duration_seconds)}**"
            try:
                await msgobj.edit(content=content, attachments=[discord.File(fp=buf, filename="exit.png")])
            except Exception:
                
                pass
    except Exception as e:
        print(f"Erro em _mark_user_exit_and_cleanup: {e}")
        traceback.print_exc()



async def update_call_cards():
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(CALLCARD_UPDATE_INTERVAL)
        try:
            for guild in bot.guilds:
                call_log_id = await get_log_channel(guild.id, "calllog")
                if not call_log_id: continue
                current_voice_ids = {m.id for vc in guild.voice_channels for m in vc.members if not m.bot}

                for user_id in current_voice_ids:
                    member = guild.get_member(user_id)
                    if member:
                        total = await total_time(user_id, guild.id)
                        current = await current_session_time(user_id, guild.id)
                        rank = await get_rank(user_id, guild.id)

                        
                        try:
                            await _check_and_award_goals_for_user(user_id, guild.id, total, current_seconds=current)
                        except Exception as e:
                            print(f"Erro ao checar metas em update_call_cards: {e}")

                        await _ensure_user_call_message(guild, member, total, current, rank)

                guild_map = active_call_messages.get(guild.id, {})
                stale_ids = set(guild_map.keys()) - current_voice_ids
                for uid in stale_ids:
                    msgobj = guild_map.pop(uid, None)
                    if msgobj:
                        try: await msgobj.delete()
                        except: pass
        except Exception as e:
            print(f"Erro no loop de update_call_cards: {e}")
            traceback.print_exc()


async def get_rank(user_id, guild_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM total_times WHERE guild_id=? ORDER BY total_seconds DESC", (guild_id,))
        rows = await cur.fetchall()
        for i, r in enumerate(rows, start=1):
            if r[0] == user_id: return i
        return None

# ===================================================================================
# COMANDOS DO BOT
# ===================================================================================



@bot.command(name="tempo")
async def tempo_cmd(ctx, user: discord.Member = None):
    user = user or ctx.author
    total = await total_time(user.id, ctx.guild.id)
    current = await current_session_time(user.id, ctx.guild.id)
    rank = await get_rank(user.id, ctx.guild.id)
    
    goals_rows = await list_goals(ctx.guild.id)
    goals = []
    if goals_rows:
        for r in goals_rows:
            gid, gname, greq, _, _, _, _ = r
            awarded = await has_awarded(user.id, ctx.guild.id, gid)
            effective = int(total or 0) + int(current or 0)
            prog = min(1.0, effective / greq) if greq and greq > 0 else 1.0
            goals.append({'id': gid, 'name': gname, 'required': greq, 'awarded': bool(awarded), 'progress': prog})

    avatar_bytes = await fetch_avatar_bytes(str(user.display_avatar.url))
    
    try:
        loop = asyncio.get_running_loop()

        buf = await loop.run_in_executor(None, gerar_stats_card,
            user.display_name, total, current, avatar_bytes, rank, goals
        )
        await ctx.reply(file=discord.File(fp=buf, filename=f"tempo_{user.id}.png"))
    except Exception as e:
        await ctx.reply("Erro ao gerar o cartão de tempo.", mention_author=True)
        print(f"Erro no !tempo: {e}")

@bot.command(name="top_tempo", aliases=['top_time', 'top_ranking'])
async def top_tempo_cmd(ctx):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id, total_seconds FROM total_times WHERE guild_id=? ORDER BY total_seconds DESC", (ctx.guild.id,))
        rows = await cur.fetchall()
    if not rows:
        await ctx.reply("Ainda não há ninguém no ranking.", mention_author=True); return
    
    PER_PAGE = 20
    if len(rows) <= 9: total_pages = 1
    else: total_pages = 1 + (len(rows) - 9 + PER_PAGE - 1) // PER_PAGE
    
    loop = asyncio.get_running_loop()
    buf = await loop.run_in_executor(None, gerar_leaderboard_card, rows, ctx.guild, 1)
    
    view = RankingView(ctx=ctx, rows=rows, total_pages=total_pages)
    message = await ctx.reply(f"🏆 **Ranking de Tempo em Chamada**", file=discord.File(fp=buf, filename="ranking_pagina_1.png"), view=view, mention_author=True)
    view.message = message



@bot.command(name="ajuda")
async def member_help_cmd(ctx):
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

@bot.command(name="help")
async def help_cmd(ctx):
    await member_help_cmd.callback(ctx)

@commands.has_permissions(administrator=True)
@bot.command(name="ajuda_adm")
async def admin_help_cmd(ctx):
    p = BOT_PREFIX
    embed = discord.Embed(title="🔑 Comandos de Administrador 🔑", description="Gerencie as configurações, metas e canais do bot.", color=discord.Color.orange())
    
    embed.add_field(name="--- ⚙️ Configuração ---", value=(
        f"`{p}setcalllog #canal` - **(OBRIGATÓRIO)** Onde os cards de stats aparecerão.\n"
        f"`{p}setgoallog #canal` - **(OBRIGATÓRIO)** Onde as notificações de metas serão enviadas."
    ), inline=False)
    
    embed.add_field(name="--- 🎯 Metas ---", value=(
        f"**`{p}add_goal <nome> <segundos> [@recompensa] [@requisito1] [@requisito2]...`**\n"
        f"↳ **`<nome>`**: Se tiver espaços, use aspas. Ex: `\"Meta Semanal\"`.\n"
        f"↳ **`<segundos>`**: Tempo necessário. Ex: 1 hora = `3600`.\n"
        f"↳ **`[@recompensa]`**: O primeiro @cargo mencionado é o que o membro ganha.\n"
        f"↳ **`[@requisito]`**: Todos os @cargos seguintes são os que o membro precisa ter para a meta contar. Pode adicionar vários.\n\n"
        f"`{p}remove_goal <id>` - Remove uma meta.\n"
        f"`{p}list_goals` - Lista todas as metas.\n"
        f"`{p}check_goal <id>` - Mostra quem completou e menciona quem falta.\n"
        f"`{p}notify_goal <id>` - Dá o cargo e notifica todos que já completaram a meta."
    ), inline=False)

    embed.add_field(name="--- 🎵 Música ---", value=(
        f"`{p}agro` - Toca a música especial no seu canal de voz.\n"
        f"`{p}sair` - Faz o bot sair do canal de voz."
    ), inline=False)
    
    embed.add_field(name="--- 🔁 Reset ---", value=(
        f"`{p}setreset <dia> <HH:MM>` - Configura o reset. Ex: `{p}setreset dom 22:00`.\n"
        f"`{p}showreset` - Mostra a configuração do reset.\n"
        f"`{p}forcereset` - Força o reset imediatamente."
    ), inline=False)
    
    embed.add_field(name="--- ⛔ Moderação ---", value=(
        f"`{p}proibir_canal #canal` - Bloqueia comandos no canal.\n"
        f"`{p}permitir_canal #canal` - Desbloqueia o canal.\n"
        f"`{p}listar_proibidos` - Lista os canais bloqueados."
    ), inline=False)
    
    await ctx.reply(embed=embed, mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="helpadv")
async def helpadv_cmd(ctx):
    await admin_help_cmd.callback(ctx)

@commands.has_permissions(administrator=True)
@bot.command(name="setcalllog")
async def set_call_log_cmd(ctx, channel: discord.TextChannel):
    await set_log_channel(ctx.guild.id, channel.id, "calllog")
    await ctx.reply(f"Canal de logs de chamadas definido para {channel.mention}", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="setgoallog")
async def set_goal_log_cmd(ctx, channel: discord.TextChannel):
    await set_log_channel(ctx.guild.id, channel.id, "goallog")
    await ctx.reply(f"Canal de logs de metas definido para {channel.mention}", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="add_goal")
async def add_goal_cmd(ctx, *, params: str):
    toks = params.split()
    seconds_idx = -1
    for i, t in enumerate(toks):
        if re.fullmatch(r"\d+", t):
            seconds_idx = i; break
    if seconds_idx == -1:
        await ctx.reply("Uso inválido. Faltou o número de segundos.", mention_author=True); return
        
    name = " ".join(toks[:seconds_idx]).strip()
    if name.startswith('"') and name.endswith('"'): name = name[1:-1]
    if not name:
        await ctx.reply("Nome da meta vazio.", mention_author=True); return

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
        await ctx.reply("Erro ao adicionar meta.", mention_author=True); traceback.print_exc()

@commands.has_permissions(administrator=True)
@bot.command(name="remove_goal")
async def remove_goal_cmd(ctx, goal_id: int):
    await remove_goal(ctx.guild.id, goal_id)
    await ctx.reply(f"Meta id {goal_id} removida.", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="list_goals", aliases=["list_goal"])
async def list_goals_cmd(ctx):
    rows = await list_goals(ctx.guild.id)
    if not rows:
        await ctx.reply("Nenhuma meta configurada.", mention_author=True); return
    lines = []
    for r in rows:
        gid, name, greq, reward_role_id, _, reset_on, required_role_ids_csv = r
        role_txt = f"<@&{reward_role_id}>" if reward_role_id else "—"
        req_txt = " / ".join(f"<@&{x.strip()}>" for x in required_role_ids_csv.split(',')) if required_role_ids_csv else "—"
        lines.append(f"**ID {gid}:** {name} ({fmt_hms(greq)}) | Recompensa: {role_txt} | Requisito(s): {req_txt} | Resetável: {bool(reset_on)}")
    await ctx.reply("📋 **Metas configuradas:**\n" + "\n".join(lines), mention_author=True)



@commands.has_permissions(administrator=True)
@bot.command(name="notify_goal")
async def notify_goal_cmd(ctx, goal_id: int):
    guild = ctx.guild
    goal = await get_goal(guild.id, goal_id)
    if not goal:
        await ctx.reply(f"❌ Meta com ID {goal_id} não encontrada.", mention_author=True); return

    goallog_id = await get_log_channel(guild.id, "goallog")
    ch = guild.get_channel(goallog_id) if goallog_id else None
    if not ch:
        await ctx.reply("❌ O canal de log de metas (`goallog`) não está configurado.", mention_author=True); return

    _, name, seconds_required, reward_role_id, _, _, _ = goal
    role_to_give = guild.get_role(reward_role_id) if reward_role_id else None

    initial_message = await ctx.reply(f"⚙️ Verificando e notificando a meta '{name}'. Isso pode demorar...")

    newly_awarded = []
    for member in guild.members:
        if member.bot or (role_to_give and role_to_give in member.roles):
            continue
        total = await total_time(member.id, guild.id); current = await current_session_time(member.id, guild.id)
        if (total + current) >= seconds_required:
            if role_to_give:
                try:
                    await member.add_roles(role_to_give, reason=f"Comando !notify_goal por {ctx.author}")
                    await mark_awarded(member.id, guild.id, goal_id)
                    newly_awarded.append(member)
                except Exception as e:
                    print(f"Erro ao dar cargo para {member.display_name}: {e}")

    awarded_user_ids = []
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM awarded_goals WHERE guild_id=? AND goal_id=?", (guild.id, goal_id))
        rows = await cur.fetchall()
        if rows: awarded_user_ids = [row[0] for row in rows]
    
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

            msg = (
                f"<a:1937verifycyan:1155565499002925167> O(a) {member.mention} completou a meta!\n\n"
                f"- Informações da Meta:\n"
                f"- Cargo: {role_txt}\n"
                f"- Tempo: **{time_txt}**\n"
                f"- Este membro foi o **{ord_num}º** membro a concluir esta meta."
            )
            
            await ch.send(msg, allowed_mentions=discord.AllowedMentions(users=True, roles=False))
            success_count += 1
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Erro ao notificar user {user_id} para meta {goal_id}: {e}"); fail_count += 1
            
    await ctx.send(f"🎉 Notificações enviadas! {success_count} com sucesso, {fail_count} falhas.")


    

@commands.has_permissions(administrator=True)
@bot.command(name="set_goal_reset")
async def set_goal_reset_cmd(ctx, goal_id: int, val: str):
    goal = await get_goal(ctx.guild.id, goal_id)
    if not goal:
        await ctx.reply("Meta não encontrada.", mention_author=True); return
    v = 1 if str(val).lower() in ("1","true","yes","y","sim") else 0
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE goals SET reset_on_weekly=? WHERE guild_id=? AND id=?", (v, ctx.guild.id, goal_id))
        await db.commit()
    await ctx.reply(f"Meta {goal_id} reset_on_weekly definida para {bool(v)}", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="setreset")
async def setreset_cmd(ctx, dia: str, hora: str):
    wd = _parse_day(dia)
    if wd is None:
        await ctx.reply("Dia inválido. Use seg, ter, qua, qui, sex, sab, dom.", mention_author=True); return
    try:
        hh, mm = map(int, hora.split(":"))
        if not (0 <= hh < 24 and 0 <= mm < 60): raise ValueError()
    except:
        await ctx.reply("Horário inválido. Use HH:MM (24h).", mention_author=True); return

    await set_reset_config(ctx.guild.id, wd, hh, mm)
    dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    await ctx.reply(f"Reset semanal definido para {dias[wd]} {hh:02d}:{mm:02d} (Horário de Brasília).", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="showreset")
async def showreset_cmd(ctx):
    wd, hh, mm = await get_reset_config(ctx.guild.id)
    dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    await ctx.reply(f"Reset semanal: {dias[wd]} {hh:02d}:{mm:02d} (Horário de Brasília).", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="forcereset")
async def forcereset_cmd(ctx):
    await _weekly_reset_run_for_guild(ctx.guild)
    await ctx.reply("Reset forçado executado.", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="check_goal")
async def check_goal_cmd(ctx, goal_id: int):
    """Verifica quem completou ou não uma meta específica e menciona todos que faltam."""
 
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

    embed = discord.Embed(
        title=f"Verificação da Meta: #{gid} - {name}",
        description=f"**Tempo necessário:** {human_hours_minutes(greq)}",
        color=discord.Color.gold()
    )


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

@bot.command(name="agro")
async def agro_cmd(ctx):
    member = ctx.author
    if not member.voice or not member.voice.channel:
        await ctx.reply("Você precisa estar em um canal de voz para usar este comando.", mention_author=True)
        return

    await ctx.reply("Entrando no canal para tocar o som...", mention_author=True, delete_after=10)
    
    played = await _play_song_in_vc(ctx.guild, member.voice.channel)
    
    
    if played:
      
        song_name = "AGRO PESCA JACARÉ" if os.path.exists(GOAL_SONG_LOCAL) else GOAL_SONG_YOUTUBE
        await ctx.send(f"🎶 Tocando agora: **{song_name}**")
    else:
        await ctx.send("❌ Não consegui tocar a música — verifique o console para erros.")

@bot.command(name="sair", aliases=["stop", "leave"])
async def sair_cmd(ctx):
    """Faz o bot sair do canal de voz."""
    voice_client = discord.utils.get(bot.voice_clients, guild=ctx.guild)
    if voice_client and voice_client.is_connected():
        await voice_client.disconnect()
        await ctx.reply("Desconectado do canal de voz.", mention_author=True)
    else:
        await ctx.reply("O bot não está em um canal de voz.", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="proibir_canal")
async def prohibit_channel_cmd(ctx, channel: discord.TextChannel):
    await add_prohibited_channel(ctx.guild.id, channel.id)
    await ctx.reply(f"Comandos (exceto de admin) agora proibidos em {channel.mention}.", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="permitir_canal")
async def allow_channel_cmd(ctx, channel: discord.TextChannel):
    await remove_prohibited_channel(ctx.guild.id, channel.id)
    await ctx.reply(f"Comandos agora permitidos em {channel.mention}.", mention_author=True)

@commands.has_permissions(administrator=True)
@bot.command(name="listar_proibidos")
async def list_prohibited_cmd(ctx):
    ids = await list_prohibited_channels(ctx.guild.id)
    if not ids:
        await ctx.reply("Nenhum canal proibido.", mention_author=True); return
    mentions = [f"<#{cid}>" for cid in ids]
    await ctx.reply("Canais proibidos para comandos:\n" + "\n".join(mentions), mention_author=True)

# ===================================================================================
# INICIALIZAÇÃO
# ===================================================================================

async def main():
    await init_db()
    try:
        await bot.start(TOKEN)
    except KeyboardInterrupt:
        print("Encerrando tasks...")
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for task in tasks: task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if http_session and not http_session.closed:
            await http_session.close()
        await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot encerrado.")