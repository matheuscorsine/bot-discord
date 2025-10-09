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

    # (Os métodos _detect_ffmpeg_executable e _play_song_in_vc ficam aqui)
    def _detect_ffmpeg_executable(self):
        """Encontra o executável do ffmpeg no sistema."""
        for name in ("ffmpeg", "ffmpeg.exe"):
            w = shutil.which(name)
            if w: return w
        if FFMPEG_EXECUTABLE and os.path.exists(FFMPEG_EXECUTABLE):
            return FFMPEG_EXECUTABLE
        return "ffmpeg"

    async def _play_song_in_vc(self, guild, channel):
        """Conecta a um canal de voz e toca a música configurada."""
        voice_client = None
        try:
            me = guild.me if guild else None
            if not channel or not isinstance(channel, discord.VoiceChannel): return False
            if me and (not me.guild_permissions.connect or not me.guild_permissions.speak): return False
            
            voice_client = discord.utils.get(self.bot.voice_clients, guild=guild)
            
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
            ffmpeg_exec = self._detect_ffmpeg_executable()
            
            async def _disconnect_safe(vc):
                if vc and vc.is_connected():
                    try: await vc.disconnect()
                    except: pass
            
            def _after_play(err):
                if err: print(f"Erro ao tocar música: {err}")
                fut = asyncio.run_coroutine_threadsafe(_disconnect_safe(voice_client), self.bot.loop)
                try: fut.result(timeout=15)
                except: pass
            
            if os.path.exists(GOAL_SONG_LOCAL):
                try:
                    source = discord.FFmpegPCMAudio(GOAL_SONG_LOCAL, executable=ffmpeg_exec, **ffmpeg_opts)
                    voice_client.play(source, after=_after_play)
                    return True
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
                            voice_client.play(source, after=_after_play)
                            return True
                except Exception as e:
                    print(f"yt-dlp falhou ao extrair stream: {e}")
            
            await _disconnect_safe(voice_client)
            return False
        except Exception:
            traceback.print_exc()
            if voice_client and voice_client.is_connected():
                try: await voice_client.disconnect()
                except: pass
            return False

    #Comandos de Música

    @commands.command(name="agro")
    async def agro_cmd(self, ctx):
        """Toca a música especial no canal de voz do autor."""
        member = ctx.author
        if not member.voice or not member.voice.channel:
            await ctx.reply("Você precisa estar em um canal de voz para usar este comando.", mention_author=True)
            return

        await ctx.reply("Entrando no canal para tocar o som...", mention_author=True, delete_after=10)
        
        # Chama o método auxiliar que contém a lógica de tocar a música
        played = await self._play_song_in_vc(ctx.guild, member.voice.channel)
        
        if played:
            song_name = "AGRO PESCA JACARÉ" if os.path.exists(GOAL_SONG_LOCAL) else GOAL_SONG_YOUTUBE
            await ctx.send(f"🎶 Tocando agora: **{song_name}**")
        else:
            await ctx.send("❌ Não consegui tocar a música — verifique o console para erros.")

    @commands.command(name="sair", aliases=["stop", "leave"])
    async def sair_cmd(self, ctx):
        """Faz o bot sair do canal de voz."""
        voice_client = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        if voice_client and voice_client.is_connected():
            await voice_client.disconnect()
            await ctx.reply("Desconectado do canal de voz.", mention_author=True)
        else:
            await ctx.reply("O bot não está em um canal de voz.", mention_author=True)

# Função obrigatória que permite que o bot carregue este Cog
async def setup(bot):
    await bot.add_cog(MusicCommands(bot))