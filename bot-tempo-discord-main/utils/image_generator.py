import os
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIo
import requests

#importa a variável de configuração e as funções auxiliares
from config import ASSETS_DIR
from .helpers import (
    _load_font_prefer,
    fmt_hms,
    _truncate,
    human_hours_minutes,
    _resize_and_crop_square
)

def gerar_stats_card(username, total_seconds, current_seconds, avatar_bytes=None, rank=None, goals=None):
    """Gera o cartão de estatísticas de tempo para um usuário."""
    #Define constantes para posicionamento e estilo dos elementos na imagem
    AVATAR_CENTER_REL = (0.175, 0.50); AVATAR_DIAMETER_REL = 0.22
    NAME_CENTER_REL = (0.63, 0.28); NAME_FONT_REL = 0.045
    INFO_VALUE_Y_REL = 0.49; INFO_COL1_X_REL = 0.44; INFO_COL2_X_REL = 0.63; INFO_COL3_X_REL = 0.82; INFO_VALUE_FONT_REL = 0.025
    GOAL_BAR_Y_REL = 0.75; GOAL_BAR_CENTER_X_REL = 0.63; GOAL_BAR_WIDTH_REL = 0.55; GOAL_BAR_HEIGHT_REL = 0.06; GOAL_FONT_REL = 0.019
    TEXT_COLOR = (255, 255, 255, 255); TITLE_COLOR = (200, 200, 200, 255); BAR_BG_COLOR = (40, 40, 45, 255); BAR_FG_COLOR = (255, 255, 255, 255)

    try:
        #busca o caminho na pasta assets/imgs/
        template_path = os.path.join(ASSETS_DIR, "imgs", "BOTberengue.png")
        base = Image.open(template_path).convert("RGBA")
    except FileNotFoundError:

        #se o template não for encontrado, cria uma imagem de fundo padrão
        base = Image.new("RGBA", (1000, 320), (60, 50, 40, 255))

    w, h = base.size
    draw = ImageDraw.Draw(base)

    #carrega as fontes que serão usadas para desenhar o texto
    bold_fonts_files = ["Poppins-Bold.ttf", "Inter-Bold.ttf", "arialbd.ttf"]
    regular_font_files = ["Poppins-Regular.ttf", "Inter-Regular.ttf", "arial.ttf"]
    name_font = _load_font_prefer(regular_font_files, int(w * NAME_FONT_REL))
    info_value_font = _load_font_prefer(regular_font_files, int(w * INFO_VALUE_FONT_REL))
    goal_font = _load_font_prefer(regular_font_files, int (w * GOAL_FONT_REL))

    #processa e desenha o avatar do usuário
    avatar_diam = int(w * AVATAR_DIAMETER_REL)
    try:
        if not avatar_bytes: raise ValueError("Bytes do avata não foram fornecidos.")
        av_img = Image.open(BytesIo(avatar_bytes)).convert("RGBA")
        av = _resize_and_crop_square