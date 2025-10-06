import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv() #carrega as variáveis do arquivo .env pro sistema

TOKEN = os.getenv("DISCORD_TOKEN") #token de autent. do bot
BOT_PREFIX =  os.getenv("BOT_PREFIX", "!")

#caminhos dos arquivos e diretórios
DB_PATH = os.getenv("DB_PATH", "database.db")#caminho pro DbSql
ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets") #pasta das fontes e imgs
GOAL_SONG_LOCAL = os.path.join(ASSETS_DIR, "song", "goal_song.mp3") #caminho da musica !agro

#fuso horário
try:
    #utiliza biblioteca para fuso horário
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("America/Sao_Paulo")
except Exception:
    #se não encontrar a biblioteca
    LOCAL_TZ = timezone(timedelta(hours=-3))

#configurações de comportamento
CALLCARD_UPDATE_INTERVAL = int(os.getenv("CALLCARD_UPDATE_INTERVAL", 180)) #intervalo pra atualizar os cards de chamada (em segundos)
GOAL_SONG_YOUTUBE = os.getenv("GOAL_SONG_YOUTUBE", "https://youtu.be/TFdO7oqkMzI?si=EGgOx6bgvalpJ5i0")#link de fallback da música agro pesca jacaré

#executáveis externos
FFMPEG_EXECUTABLE = os.getenv("FFMPEG_ExECUTABLE") #caminho pro executável do FFMPEG (se não estiver no PATH)

os.makedirs(ASSETS_DIR, exist_ok=True) #garante de a pasta assets exista ao iniciar o bot