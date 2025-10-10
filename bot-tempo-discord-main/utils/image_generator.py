import os
from PIL import Image, ImageDraw, ImageFont, ImageOps
from io import BytesIO
import requests

#importa a variável de configuração e as funções auxiliares
from ..config import ASSETS_DIR
from .helpers import (
    _load_font_prefer, fmt_hms, _truncate, 
    human_hours_minutes, _resize_and_crop_square
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
    bold_font_files = ["Poppins-Bold.ttf", "Inter-Bold.ttf", "arialbd.ttf"]
    regular_font_files = ["Poppins-Regular.ttf", "Inter-Regular.ttf", "arial.ttf"]
    name_font = _load_font_prefer(regular_font_files, int(w * NAME_FONT_REL))
    info_value_font = _load_font_prefer(regular_font_files, int(w * INFO_VALUE_FONT_REL))
    goal_font = _load_font_prefer(regular_font_files, int (w * GOAL_FONT_REL))

    #processa e desenha o avatar do usuário
    avatar_diam = int(w * AVATAR_DIAMETER_REL)
    try:
        if not avatar_bytes: raise ValueError("Bytes do avata não foram fornecidos.")
        av_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
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
    bar_width = int(w * GOAL_BAR_WIDTH_REL * 0.9)
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
        full_text = f"{goal_name_raw} {goal_time_str}"
        btn_font = _load_font_prefer(bold_font_files, max(12, int(w * GOAL_FONT_REL * 0.95)))

        try: #calcula o tamanho do texto
            tb = draw.textbbox((0,0), full_text, font=btn_font)
            text_w, text_h = tb[2] - tb[0], tb[3] - tb[1]
        except Exception: #fallback pra métodos mais antigos
            text_w, text_h = draw.textsize(full_text, font=btn_font)

        btn_pad_x = max(6, int(w * 0.006)); btn_pad_y = max(4, int(h * 0.008))
        btn_w = text_w + btn_pad_x * 2; btn_h = text_h + btn_pad_y * 2
        max_btn_w = bar_width - max(8, int(w * 0.01))

        if btn_w > max_btn_w:
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
            draw.rounded_rectangle(fill_box, radius=max(4, radius - 2), fill=BAR_FG_COLOR)

        percent_text = f"{int(progress * 100)}%"
        pct_x = bar_x + bar_width - inner_px - int(w * 0.012)
        pct_y = bar_y + bar_height // 2
        draw.text((pct_x, pct_y), percent_text, font=goal_font, fill= TEXT_COLOR, anchor="rm")

    buf = BytesIO()
    base.save(buf, format="PNG")
    buf.seak(0)
    return buf

def gerar_leaderboard_card(rows, guild= None, page: int = 1):
    """gera o cartão de ranking (leaderboard) com as melhores pontuações"""
    def fmt_hms_long(sec):
        s = int(sec or 0)
        d, s = divmod(s, 86400)
        h, s = divmod(s, 3600)
        m, s = divmod(s, 60)
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
            av_bytes = requests.get(url, timeout=4).content if url else None
        except:
            av_bytes = None

        circ = Image.new("RGBA", (avatar_inner_sz, avatar_inner_sz))
        if av_bytes:
            im = Image.open(BytesIO(av_bytes)).convert("RGBA")
            im = _resize_and_crop_square(im, avatar_inner_sz)
            mask = Image.new("L", (avatar_inner_sz, avatar_inner_sz), 0)
            ImageDraw.Draw(mask).ellipse((0, 0, avatar_inner_sz, avatar_inner_sz), fill=255)
            circ.paste(im, (0,0), mask)
        else:
            d = ImageDraw.Draw(circ)
            d.ellipse((0, 0, avatar_inner_sz, avatar_inner_sz), fill=(100,100,100,255))
            if initials:
                f = _load_font_prefer(["Inter-Bold.ttf", "arialbd.ttf"], max(12, int(avatar_inner_sz * 0.4)))
                d.text((avatar_inner_sz/2, avatar_inner_sz/2), initials, font=f, fill=(200,200,200,255), anchor="mm")
        canvas.paste(circ, (x0_avatar, y0_avatar), circ)

    podium_name_f = _load_font_prefer(["Inter-Bold.ttf", "arialbd.ttf"], 30)
    podium_time_f = _load_font_prefer(["Inter-Regular.ttf", "arial.ttf"], 24)
    list_name_f = _load_font_prefer(["Inter-Bold.ttf", "arialbd.ttf"], 22)
    list_time_f = _load_font_prefer(["Inter-Regular.ttf", "arial.ttf"], 18)

    podium_avatar_sz = [234, 236, 234]; podium_avatar_pos = [(184, 223), (500, 180), (816, 223)]
    podium_name_pos = [(181, 477), (500, 452), (819, 477)]; podium_time_pos = [(187, 561), (500, 560), (813, 561)]
    list_avatar_sz =  58; list_avatar_left_cx = 91; list_avatar_right_cx = 567; list_text_left_cx = 289; list_text_right_cx = 765
    list_start_y = 675; list_y_step = 92

    list_page_avatar_sz = 60; list_page_start_y = 112; list_page_y_step = 91; list_page_avatar_x = [91, 566]; list_page_text_x  = [284, 764]
    PER_COL = 10; PER_PAGE = PER_COL * 2

    base_filename = "BOTbereRank.png" if page == 1 else "BotbereRank2.png"
    template_path = os.path.join(ASSETS_DIR, "imgs", base_filename)
    base = Image.open(template_path).convert("RGBA")
    draw = ImageDraw.Draw(base)

    if page == 1:
        podium_slots_mapping = { 0: 1, 1: 0, 2: 2 }
        for i in range(3):
            rank_index_in_rows = podium_slots_mapping[i]
            if rank_index_in_rows < len(rows):
                k, sec = rows[rank_index_in_rows]
                name, url = resolve(k)
                init = "".join(p[0] for p in name.split()[:2]).upper()
                cx, cy = podium_avatar_pos[i]; sz = podium_avatar_sz[i]
                paste_avatar(base, cx, cy, sz, url, init)
                nm = _truncate(name, 15); draw.text(podium_name_pos[i], nm, font=podium_name_f, fill ="white", anchor="mm")
                ts = fmt_hms_long(sec); draw.text(podium_time_pos[i], ts, font=podium_time_f, fill="white", anchor="mm")

        for i in range(3, 9):
            if i < len(rows):
                k, sec = rows[i]
                name, url = resolve(k)
                init = "".join(p[0] for p in name.split()[:2]).upper()
                col = 0 if (i - 3) < 3 else 1
                row_in_col = (i - 3) % 3
                avatar_cx = list_avatar_left_cx if col == 0 else list_avatar_right_cx
                text_cx = list_text_left_cx if col == 0 else list_text_right_cx
                center_y = list_start_y + row_in_col * list_y_step
                paste_avatar(base, avatar_cx, center_y, list_avatar_sz, url, init)
                name_text = _truncate(name, 18); draw.text((text_cx, center_y - 12), name_text, font=list_name_f, fill="white", anchor="mm")
                time_text = fmt_hms_long(sec); draw.text((text_cx, center_y + 12), time_text, font=list_time_f, fill="#cccccc", anchor="mm")
    else:
        start_rank = 9 + (page - 2) * PER_PAGE
        display = rows[start_rank : start_rank + PER_PAGE]
        for i, (k, sec) in enumerate(display):
            name, url = resolve(k)
            init = "".join(p[0] for p in name.split()[:2]).upper()
            col = i // PER_COL
            row_in_col = i % PER_COL
            avatar_cx = list_page_avatar_x[col]; text_cx = list_page_text_x[col]
            center_y = list_page_start_y + row_in_col * list_page_y_step
            paste_avatar(base, avatar_cx, center_y, list_page_avatar_sz, url, init)
            rank_and_name = f"#{start_rank + i + 1} {_truncate(name, 18)}"
            draw.text((text_cx, center_y - 12), rank_and_name, font=list_name_f, fill="white", anchor="mm")
            time_text = fmt_hms_long(sec); draw.text((text_cx, center_y + 12), time_text, font=list_time_f, fill="#cccccc", anchor="mm")

    out = BytesIO()
    base.save(out, format="PNG")
    out.seek(0)
    return out