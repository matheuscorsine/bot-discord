import discord
from discord.ext import commands
import os
import shutil
import asyncio
import traceback
import subprocess

try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except Exception:
    YTDLP_AVAILABLE = False