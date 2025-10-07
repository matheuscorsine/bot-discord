import os
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import aiohttp

#importa o diretório de assets do arquivo de configuração central
from config import ASSETS_DIR

def _font_path_in_assets(name):
    """Verifica se um arquivo de fonte existe na pasta fontes"""
    path = os.path.join(ASSETS_DIR, "fontes", name)
    return path if os.path.exists(path) else None

def _load_font_prefer(names, size):
    """Tenta carregar uma fonte de uma lista, com fallbacks para fontes do sistema"""
    for name in names:
        font_path = _font_path_in_assets(name)
        if font_path:
            try: return ImageFont.Truetype(font_path, size)
            except: pass
    #se não encontrar as fontes, tenta usar fontes padrão do sistema
    for fallback_font in ["arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        try: return ImageFont.truetype(fallback_font, size)
        except: pass
    #se falhar, retorna pra fonte padrão da biblioteca
    return ImageFont.load_default()

#FUNÇÕES DE FORMATAÇÃO DE DADOS

def fmt_hms(s):
    """Formata um valor em segundos para o formato hora/minuto/segundo"""
    try: s = int(s)
    except: return "00:00:00"
    #divmod faz a divisão e retorna o quociente e o resto
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" #formata para ter sempre dois dígitos 

def now_iso_utc():
    """Retorna a data e hora atual no formato ISO 8601 com fuso horário UTC"""
    return datetime.now(timezone.utc).isoformat()

def _truncate(text, max_chars):
    """Corta um texto se ele for maior que 'max-chars', adicionado '...' no final"""
    if not text: return ""
    return text if len(text) <= max_chars else text[:max_chars-1] + "..."

def human_hours_minutes(seconds: int):
    """Converte segundos para um formato legível, como '1 hora e 30 minutos'"""
    try: s = int(s)
    except: s = 0
    h, rem = divmod(s, 3600)
    m, _ = divmod(rem, 60)
    h_txt = f"{h} hora" + ("s" if h != 1 else "")
    m_txt = f"{m} minuto" + ("s" if m != 1 else "")

    #retorna o texto formatado dependendo se há horas, minutos ou ambos
    if h > 0 and m > 0:
        return f"{h_txt} e {m_txt}"
    elif h > 0:
        return h_txt
    else:
        return m_txt

#FUNÇÕES DE REDE E IMAGEM

async def fetch_avatar_bytes(session: aiohttp.ClientSession, url: str, timeout=6):
    """Baixa uma imagem (avatar) de uma URL e retorna os bytes"""
    if not url: return None
    try:
        #usa a sessão aiohttp que foi passada como parâmetro para fazer a requisição
        async with session.get(url, timeout=timeout) as resp:
            #se a requisição foi bem-sucedida (status 200), retorna o conteúdo
            if resp.status == 200:
                return await resp.read()
    except Exception:
        #em caso de erro (timeout, URL invállida, etc), não retorna nada
        return None
    return None

def _resize_and_crop_square(img, size):
    """Redimensiona uma imagem para um tamanho específico e a corta para ficar quadrada"""
    w, h = img.size
    side = min(w, h)
    #calcula as coordenadas para cortar a imagem pelo centro
    left, top = (w - side) // 2, (h - side) // 2
    #corta a imagem
    img = img.crop((left, top, left + side, top |+ side))
    #redimensiona para o tamanho final com um filtro de alta qualidade (LANCZOS)
    return img.resize((size, size), Image.LANCZOS)