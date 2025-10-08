import discord
from discord.ext import commands
import os
import shutil
import asyncio
import traceback

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    YTDLP_AVAILABLE = False

# Importa as configurações de música do arquivo central
from config import GOAL_SONG_LOCAL, GOAL_SONG_YOUTUBE, FFMPEG_EXECUTABLE

class MusicCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _detect_ffmpeg_executable(self):
        """Encontra o executável do ffmpeg no sistema."""
        # Procura por 'ffmpeg' ou 'ffmpeg.exe' no PATH do sistema
        for name in ("ffmpeg", "ffmpeg.exe"):
            w = shutil.which(name)
            if w: return w
        # Se não encontrar, usa o caminho definido no .env, se existir
        if FFMPEG_EXECUTABLE and os.path.exists(FFMPEG_EXECUTABLE):
            return FFMPEG_EXECUTABLE
        # Como último recurso, tenta chamar 'ffmpeg' diretamente
        return "ffmpeg"

    async def _play_song_in_vc(self, guild, channel):
        """Conecta a um canal de voz e toca a música configurada."""
        voice_client = None
        try:
            me = guild.me if guild else None
            if not channel or not isinstance(channel, discord.VoiceChannel): return False
            if me and (not me.guild_permissions.connect or not me.guild_permissions.speak): return False
            
            # Obtém o cliente de voz atual do bot no servidor
            voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
            
            # Conecta ou move para o canal de voz do usuário
            try:
                if voice_client and voice_client.is_connected():
                    if voice_client.channel != channel: await voice_client.move_to(channel)
                else:
                    voice_client = await channel.connect(timeout=10.0)
            except Exception:
                # Se a conexão falhar, tenta forçar a desconexão e reconectar
                try:
                    if voice_client: await voice_client.disconnect(force=True)
                    voice_client = await channel.connect(timeout=10.0)
                except Exception: return False
            
            # Configurações para o FFMPEG para otimizar a reprodução de áudio
            ffmpeg_opts = {'options': '-vn -hide_banner -loglevel error'}
            ffmpeg_exec = self._detect_ffmpeg_executable()
            
            # Função para desconectar de forma segura após a música terminar
            async def _disconnect_safe(vc):
                if vc and vc.is_connected():
                    try: await vc.disconnect()
                    except: pass
            
            # Função de callback que será chamada quando a música acabar
            def _after_play(err):
                if err: print(f"Erro ao tocar música: {err}")
                # Agenda a desconexão no loop de eventos principal do bot
                fut = asyncio.run_coroutine_threadsafe(_disconnect_safe(voice_client), self.bot.loop)
                try: fut.result(timeout=15)
                except: pass
            
            # Tenta tocar o arquivo de música local primeiro
            if os.path.exists(GOAL_SONG_LOCAL):
                try:
                    source = discord.FFmpegPCMAudio(GOAL_SONG_LOCAL, executable=ffmpeg_exec, **ffmpeg_opts)
                    voice_client.play(source, after=_after_play)
                    return True
                except Exception as e:
                    print(f"Falha ao tocar arquivo local: {e}")
            
            # Se o arquivo local falhar ou não existir, tenta baixar do YouTube
            if YTDLP_AVAILABLE:
                try:
                    ydl_opts = {'format': 'bestaudio/best', 'quiet': True, 'noplaylist': True}
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(GOAL_SONG_YOUTUBE, download=False)
                        stream_url = info.get('url')
                        if stream_url:
                            source = discord.FFmpegPCMAudio(stream_url, executable=ffmpeg_exec, **ffmpeg_opts)
                            voice_client.play(source, after=_after_play)
                            return True
                except Exception as e:
                    print(f"yt-dlp falhou ao extrair stream: {e}")
            
            # Se ambas as opções falharem, desconecta
            await _disconnect_safe(voice_client)
            return False
        except Exception:
            traceback.print_exc()
            if voice_client and voice_client.is_connected():
                try: await voice_client.disconnect()
                except: pass
            return False

# Esta função é necessária para que o bot possa carregar este arquivo como um Cog
async def setup(bot):
    await bot.add_cog(MusicCommands(bot))