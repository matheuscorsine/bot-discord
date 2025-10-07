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
        av = _resize_and_crop_square(av_img, avatar_diam)
    except Exception:
        #se não tiver avatar, cria um círculo cinza com as inciais do nome
        av = Image.new("RGBA", (avatar_diam, avatar_diam), (200, 200, 200, 255))
        ad = ImageDraw.Draw(av)
        initials = "".join([p[0] for p in (username or "U").split()[:2]]).upper()
        fbig = _load_font_prefer(bold_font_files, avatar_diam // 2)
        ad.text((avatar_diam/2, avatar_diam/2), initials, font=fbig, fill=(60,60,65,255), anchor="mm")

    #cria uma mascará circular para o avatar e a cola na imagem base
    avatar_cx, avatar_cy = int(w * AVATAR_CENTER_REL[0]), int(h * AVATAR_CENTER_REL[1])
    avatar_x, avatar_y = avatar_cx - avatar_diam // 2, avatar_cy - avatar_diam // 2
    mask = Image.new("L", (avatar_diam, avatar_diam), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((0, 0, avatar_diam, avatar_diam), fill=255)
    base.paste(av, (avatar_x, avatar_y), mask)

    #função interna para simplificar o desenho de texto centralizado
    def draw_centered_text(coords_rel, text, font, fill=TEXT_COLOR):
        cx, cy = int(w * coords_rel[0]), int(h * coords_rel[1])
        draw.text((cx, cy), text, font=font, fill=fill, anchor="mm")
    
    #desenha o nome e as informações de tempo e ranking
    draw_centered_text(NAME_CENTER_REL, _truncate(username or "Usuário", 20), name_font)
    draw_centered_text((INFO_COL1_X_REL, INFO_VALUE_Y_REL), fmt_hms(current_seconds or 0), info_value_font)
    draw_centered_text((INFO_COL2_X_REL, INFO_VALUE_Y_REL), f"#{rank}" if rank else "-", info_value_font)
    draw_centered_text((INFO_COL3_X_REL, INFO_VALUE_Y_REL), fmt_hms(total_seconds or 0), info_value_font)

    #lógica pra desenhar a barra de progresso da próxima meta
    next_goal = next((g for g in goals if not g.get('awarded')), None) if isinstance(goals, list) else None
    bar_witdh = int(w * GOAL_BAR_WIDTH_REL * 0.9)
    bar_height = max(12, int (h * GOAL_BAR_HEIGHT_REL * 0.55))
    bar_cx = int(w * GOAL_BAR_CENTER_X_REL)
    bar_y = int(h * (GOAL_BAR_Y_REL - 0.045))
    bar_x = bar_cx - bar_width // 2
    radius = max(6, int(h * 0.03))

    if not next_goal:
        draw.text((bar_cx, bar_y + bar_height // 2), "Nenhuma meta ativa", font=goal_font, fill=TITLE_COLOR, anchor="mm")
    else:
        goal_name_raw = str(next_goal.get('name', 'Meta'))
        goal_req_secs = next_goal.get('required', 0)
        goal_time_str = f"({human_hours_minutes(goal_req_secs)})"
        full_next = f"{goal_name_raw} {goal_time_str}"
        btn_font = _load_font_prefer(bold_font_files, max(12, int(w * GOAL_FONT_REL * 0.95)))

        try: #calcula o tamanho do texto
            tb = draw.textbbox((0,0), full_text, font=btn_font)
            text_w, text_h = tb[2] - tb[0], tb[3] - tb[1]
        except Exception: #fallback pra métodos mais antigos
            text_w, text_h = draw.textsize(full_next, font=btn_font)

        btn_pad_x = max(6, int(W * 0.006)); btn_pad_y = max(4, int(h * 0.008))
        btn_w = text_w + btn_pad_x * 2; btn_h = text_h + btn_pad_y * 2
        max_btn_w = bar_width - max(8, int(w * 0.01))

        if btn-w > max_btn_w:
            btn_w = max_btn_w
            approx_char_w = max(6, text_w / max(1, len(full_text)))
            max_chars = max(4, int((btn_w - btn_pad_x * 2) / approx_char_w))
            display_text = _truncate(full_text, max_chars)
        else:
            display_text = _truncate(full_text, 50)

        gap = int(h * 0.006)
        btn_x = bar_x + max(4, int(w * 0.004)); btn_y = bar_y - btn_h - gap
        btn_radius = max(6, btn_h // 2)
        draw.rounded_rectangle((btn_x, btn_y, btn_x + btn_w, btn_y, + btn_h), radius=btn_radius, fill=BAR_BG_COLOR)
        draw.text((btn_x + btn_w / 2, btn_y + btn_h / 2), display_text, font=btn_font, fill=TEXT_COLOR, anchor="mm")

        draw.rounded_rectangle((bar_x, bar_y, bar_x + bar_width, bar_y + bar_height), radius=radius, fill= BAR_BG_COLOR)
        progress = float(next_goal.get('progress', 0.0))
        progress = max(0.0, min(1.0, progress))

        inner_px = max(6, int(w * 0.006)); inner_py = max(3, int(bar_height * 0.12))
        usable_width = bar_width - inner_px * 2
        fill_width = int(usable_width * progress)

        if fill_width > 0:
            fill_box = (bar_x + inner_px, bar_y + inner_py, bar_x + inner_px + fill_width, bar_y + bar_height - inner_py)
            draw.rounded_rectangle(fill_box, radius=ma(4, radius - 2), fill=BAR_FG_COLOR)

        percent_text = f"{int(progress * 100)}%"
        pct_x = bar_x + bar_width - inner_px - int(w * 0.012)
        pct_y = bar_y + ba_height // 2
        draw.text((pct_x, pct_y), percent_text, font=goal_font, fill= TEXT_COLOR, anchor="rm")

    buf = BytesIO()
    base.save(buf, format="PNG")
    buf.seak(0)
    return buf
#def gerar leaderboard card