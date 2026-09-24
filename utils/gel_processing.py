import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

def draw_text_with_rotation(draw, xy, text, fill, font, angle=0, anchor='lt'):
    """绘制旋转文本，使用临时图像"""
    bbox = draw.textbbox((0, 0), text, font=font, anchor='lt')
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    temp = Image.new('RGBA', (tw, th), (0,0,0,0))
    temp_draw = ImageDraw.Draw(temp)
    temp_draw.text((0, 0), text, font=font, fill=fill)
    rotated = temp.rotate(angle, expand=1, resample=Image.BICUBIC)
    rw, rh = rotated.size
    anchor_map = {
        'lt': (0,0), 'mt': (-rw//2,0), 'rt': (-rw,0),
        'lm': (0,-rh//2), 'mm': (-rw//2,-rh//2), 'rm': (-rw,-rh//2),
        'lb': (0,-rh), 'mb': (-rw//2,-rh), 'rb': (-rw,-rh)
    }
    dx, dy = anchor_map.get(anchor, (0,0))
    draw._image.paste(rotated, (int(xy[0]+dx), int(xy[1]+dy)), rotated)

def draw_annotation(image_pil, lanes_data, mk_standards, chosen_mk,
                    label_offset=-10, rotation=0, font_name="Arial",
                    band_offset=15, font_size=12,
                    lane_color="#000000", band_color="#000000"):
    """
    绘制标注：胶道名称可旋转，kDa标注不旋转
    """
    img = image_pil.copy()
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(f"{font_name}.ttf", font_size)
    except:
        font = ImageFont.load_default()

    # 收集所有文本项
    text_items = []
    for lane in lanes_data:
        x = lane['x']
        name = lane['name']
        # 胶道名称：可旋转
        text_items.append((x, label_offset, name, lane_color, 'mt', rotation))
        if name.upper() == "MK" and chosen_mk in mk_standards:
            kda_list = mk_standards[chosen_mk]
            bands = lane.get('bands', [])
            for i, y in enumerate(bands):
                if i < len(kda_list):
                    kda_str = str(kda_list[i])
                    # kDa标注：不旋转，角度固定为0
                    text_items.append((x - band_offset, y, kda_str, band_color, 'rm', 0))

    # 计算顶部扩展量（考虑旋转）
    top_pad = 0
    for (x, y, text, color, anchor, ang) in text_items:
        bbox = draw.textbbox((0,0), text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # 旋转后的高度
        rot_h = int(th * abs(np.cos(np.radians(ang))) + tw * abs(np.sin(np.radians(ang)))) + 10
        if anchor in ('mt', 'rm'):
            min_y = y - rot_h // 2
        else:
            min_y = y
        if min_y < 0:
            top_pad = max(top_pad, -min_y + 30)  # 额外留白

    if top_pad > 0:
        new_img = Image.new('RGB', (img.width, img.height + top_pad), color='white')
        new_img.paste(img, (0, top_pad))
        img = new_img
        draw = ImageDraw.Draw(img)
        adjusted = []
        for (x, y, text, color, anchor, ang) in text_items:
            adjusted.append((x, y + top_pad, text, color, anchor, ang))
        text_items = adjusted

    # 绘制所有文本
    for (x, y, text, color, anchor, ang) in text_items:
        draw_text_with_rotation(draw, (x, y), text, fill=color, font=font,
                                angle=ang, anchor=anchor)

    return img
