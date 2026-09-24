"""凝胶电泳图像处理核心算法"""
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.signal import find_peaks
from typing import List, Tuple, Dict, Any, Optional
import os
import easyocr

def pil_to_cv2(pil_image: Image.Image) -> np.ndarray:
    rgb = np.array(pil_image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def cv2_to_pil(cv2_image: np.ndarray) -> Image.Image:
    rgb = cv2.cvtColor(cv2_image, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def compute_projection(image: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    h, w = gray.shape
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    h_proj = np.mean(blurred, axis=0)
    h_proj_inv = h_proj.max() - h_proj
    h_proj_smooth = np.convolve(h_proj_inv, np.ones(5)/5, mode='same')
    sobelx = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
    sobelx = np.abs(sobelx)
    edge_proj = np.mean(sobelx, axis=0)
    edge_proj = np.convolve(edge_proj, np.ones(3)/3, mode='same')
    return h_proj_smooth, edge_proj


def find_peaks_and_valleys(projection: np.ndarray,
                          min_distance: int = 20,
                          peak_prominence_ratio: float = 0.1,
                          valley_prominence_ratio: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
    pmax = projection.max()
    std = np.std(projection)
    pad_width = min_distance
    padded = np.pad(projection, (pad_width, pad_width), mode='minimum')
    
    peaks_pad, _ = find_peaks(padded, distance=min_distance,
                              prominence=max(std * peak_prominence_ratio, pmax * 0.02))
    peaks = peaks_pad[(peaks_pad >= pad_width) & (peaks_pad < pad_width + len(projection))] - pad_width
    
    valleys_pad, _ = find_peaks(-padded, distance=min_distance,
                                prominence=max(std * valley_prominence_ratio, pmax * 0.01))
    valleys = valleys_pad[(valleys_pad >= pad_width) & (valleys_pad < pad_width + len(projection))] - pad_width
    
    check_window = min(5, len(projection) // 10)
    if len(projection) > check_window + 1:
        if projection[0] > np.max(projection[1:check_window+1]):
            peaks = np.concatenate([[0], peaks]) if len(peaks) == 0 or peaks[0] != 0 else peaks
        if projection[-1] > np.max(projection[-check_window-1:-1]):
            peaks = np.concatenate([peaks, [len(projection)-1]]) if len(peaks) == 0 or peaks[-1] != len(projection)-1 else peaks
    
    peaks = np.unique(peaks)
    valleys = np.unique(valleys)
    return peaks, valleys


def _score_offset(offset: float, w: int, n_lanes: int,
                  peaks: np.ndarray, valleys: np.ndarray,
                  projection: np.ndarray, edge_proj: np.ndarray) -> float:
    score = 0
    lane_width = w / n_lanes
    for i in range(n_lanes + 1):
        b = offset + i * lane_width
        b_int = int(b)
        if b_int < 0 or b_int >= w:
            score -= 1000
            continue
        score -= projection[b_int] * 2.0
        if len(valleys) > 0:
            nearest_valley_dist = min(abs(v - b_int) for v in valleys)
            score -= nearest_valley_dist * 0.5
        score += edge_proj[b_int] * 0.3
    for i in range(n_lanes):
        center = offset + (i + 0.5) * lane_width
        c_int = int(center)
        if c_int < 0 or c_int >= w:
            continue
        if len(peaks) > 0:
            nearest_peak_dist = min(abs(p - c_int) for p in peaks)
            score -= nearest_peak_dist * 0.3
    return score


def _split_by_uniform_constraint(w: int, n_lanes: int,
                                 peaks: np.ndarray, valleys: np.ndarray,
                                 projection: np.ndarray,
                                 edge_proj: np.ndarray,
                                 manual_offset: float = 0) -> List[Tuple[int, int]]:
    lane_width = w / n_lanes
    best_offset = 0
    best_score = -np.inf
    search_range = np.linspace(0, lane_width, min(100, int(lane_width) + 1))
    for offset in search_range:
        score = _score_offset(offset, w, n_lanes, peaks, valleys, projection, edge_proj)
        if score > best_score:
            best_score = score
            best_offset = offset
    
    final_offset = best_offset + manual_offset
    while final_offset < -lane_width / 2:
        final_offset += lane_width
    while final_offset > lane_width / 2:
        final_offset -= lane_width
    
    lanes = []
    for i in range(n_lanes):
        x1 = int(final_offset + i * lane_width)
        x2 = int(final_offset + (i + 1) * lane_width)
        x1 = max(0, x1)
        x2 = min(w, x2)
        lanes.append((x1, x2))
    return lanes


def detect_lanes_smart(
    image: np.ndarray,
    expected_lanes: Optional[int] = None,
    min_lane_width: int = 20,
    manual_offset: float = 0
) -> Tuple[List[Tuple[int, int]], np.ndarray, np.ndarray, np.ndarray]:
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    h, w = gray.shape
    
    projection, edge_proj = compute_projection(image)
    peaks, valleys = find_peaks_and_valleys(projection, min_distance=min_lane_width)
    
    if expected_lanes is None:
        if len(peaks) >= 2:
            peak_distances = np.diff(peaks)
            median_dist = np.median(peak_distances)
            extra_lanes = 0
            for peak in peaks:
                half_height = projection[peak] * 0.5
                left = peak
                while left > 0 and projection[left] > half_height:
                    left -= 1
                right = peak
                while right < w - 1 and projection[right] > half_height:
                    right += 1
                width = right - left
                if width > 1.5 * median_dist:
                    extra_lanes += int(round(width / median_dist)) - 1
            n_gaps = sum(1 for d in peak_distances if d > 1.6 * median_dist)
            expected_lanes = len(peaks) + n_gaps + extra_lanes
            expected_lanes = max(len(peaks), min(expected_lanes, 20))
        else:
            expected_lanes = max(1, w // 100)
    
    lanes = _split_by_uniform_constraint(w, expected_lanes, peaks, valleys, projection, edge_proj, manual_offset)
    return lanes, projection, peaks, valleys


def get_projection_viz(image: np.ndarray, lanes: List[Tuple[int, int]],
                       projection: np.ndarray, peaks: np.ndarray, valleys: np.ndarray,
                       expected_lanes: Optional[int] = None) -> np.ndarray:
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()
    h, w = gray.shape
    viz_h = 220
    viz = np.ones((viz_h, w, 3), dtype=np.uint8) * 255
    
    proj_norm = projection / (projection.max() + 1e-8)
    for x in range(w - 1):
        y1 = int(viz_h - 30 - proj_norm[x] * (viz_h - 50))
        y2 = int(viz_h - 30 - proj_norm[x + 1] * (viz_h - 50))
        cv2.line(viz, (x, y1), (x + 1, y2), (100, 100, 100), 1)
    
    for p in peaks:
        if 0 <= p < w:
            y = int(viz_h - 30 - proj_norm[p] * (viz_h - 50))
            cv2.circle(viz, (p, y), 5, (0, 180, 0), -1)
    
    for v in valleys:
        if 0 <= v < w:
            y = int(viz_h - 30 - proj_norm[v] * (viz_h - 50))
            cv2.circle(viz, (v, y), 5, (0, 0, 220), -1)
    
    for start, end in lanes:
        cv2.rectangle(viz, (start, 5), (end, viz_h - 5), (0, 160, 255), 2)
        cv2.line(viz, (start, 0), (start, viz_h), (0, 160, 255), 1)
        cv2.line(viz, (end, 0), (end, viz_h), (0, 160, 255), 1)
    
    info = f"Peaks:{len(peaks)} Valleys:{len(valleys)} Lanes:{len(lanes)}"
    if expected_lanes:
        info += f" (Expected:{expected_lanes})"
    cv2.putText(viz, info, (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)
    return viz


def draw_lane_overlay(image: Image.Image, lanes: List[Tuple[int, int]],
                     selected_idx: Optional[int] = None,
                     peaks: Optional[np.ndarray] = None,
                     valleys: Optional[np.ndarray] = None) -> Image.Image:
    img = image.copy().convert('RGBA')
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw_o = ImageDraw.Draw(overlay)
    draw = ImageDraw.Draw(img)
    w, h = img.size
    
    colors = [(255, 0, 0, 100), (0, 255, 0, 100), (0, 0, 255, 100),
              (255, 255, 0, 100), (255, 0, 255, 100), (0, 255, 255, 100),
              (255, 128, 0, 100), (128, 0, 255, 100), (0, 128, 128, 100),
              (200, 100, 0, 100), (100, 200, 0, 100), (0, 100, 200, 100)]
    
    for i, (x1, x2) in enumerate(lanes):
        color = colors[i % len(colors)]
        alpha = 150 if i == selected_idx else 80
        fill_color = (*color[:3], alpha)
        draw_o.rectangle([x1, 0, x2, h], fill=fill_color)
        line_color = (255, 0, 0) if i == selected_idx else color[:3]
        draw.line([(x1, 0), (x1, h)], fill=line_color, width=2)
        draw.line([(x2, 0), (x2, h)], fill=line_color, width=2)
        mid_x = (x1 + x2) // 2
        draw.text((mid_x - 8, h // 2 - 10), f"{i+1}", fill=(255, 255, 255),
                 font=get_font("Arial", 18))
    
    img = Image.alpha_composite(img, overlay)
    if peaks is not None:
        for p in peaks:
            if 0 <= p < w:
                draw.line([(p, 0), (p, 12)], fill=(0, 200, 0), width=2)
    if valleys is not None:
        for v in valleys:
            if 0 <= v < w:
                draw.line([(v, 0), (v, 12)], fill=(200, 0, 0), width=2)
    return img.convert('RGB')


# ========== 条带检测 ==========

def compute_band_projection(image: np.ndarray, lane_box: Tuple[int, int]) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
    x1, x2 = lane_box
    lane_region = gray[:, x1:x2]
    v_proj = np.mean(lane_region, axis=1)
    v_proj = v_proj.max() - v_proj
    v_proj = np.convolve(v_proj, np.ones(3)/3, mode='same')
    return v_proj


def find_band_peaks_and_valleys(v_proj: np.ndarray,
                                min_distance: int = 5,
                                peak_prominence_ratio: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
    pmax = v_proj.max()
    std = np.std(v_proj)
    pad_width = min_distance
    padded = np.pad(v_proj, (pad_width, pad_width), mode='minimum')
    
    peaks_pad, _ = find_peaks(padded, distance=min_distance,
                              prominence=max(std * peak_prominence_ratio, pmax * 0.01))
    peaks = peaks_pad[(peaks_pad >= pad_width) & (peaks_pad < pad_width + len(v_proj))] - pad_width
    
    valleys_pad, _ = find_peaks(-padded, distance=min_distance,
                                prominence=max(std * peak_prominence_ratio * 0.5, pmax * 0.005))
    valleys = valleys_pad[(valleys_pad >= pad_width) & (valleys_pad < pad_width + len(v_proj))] - pad_width
    
    check_window = min(3, len(v_proj) // 20)
    if len(v_proj) > check_window + 1:
        if v_proj[0] > np.max(v_proj[1:check_window+1]):
            peaks = np.concatenate([[0], peaks]) if len(peaks) == 0 or peaks[0] != 0 else peaks
        if v_proj[-1] > np.max(v_proj[-check_window-1:-1]):
            peaks = np.concatenate([peaks, [len(v_proj)-1]]) if len(peaks) == 0 or peaks[-1] != len(v_proj)-1 else peaks
    
    peaks = np.unique(peaks)
    valleys = np.unique(valleys)
    return peaks, valleys


def _split_bands_by_peaks(v_proj: np.ndarray, peaks: np.ndarray, valleys: np.ndarray,
                          expected_bands: Optional[int] = None) -> List[Tuple[int, int, float]]:
    h = len(v_proj)
    
    if expected_bands is not None and expected_bands > 0:
        band_height = h / expected_bands
        
        if len(peaks) == expected_bands:
            centers = peaks.copy()
        elif len(peaks) > expected_bands:
            peak_intensities = [(p, float(v_proj[p])) for p in peaks]
            peak_intensities = sorted(peak_intensities, key=lambda x: x[1], reverse=True)[:expected_bands]
            centers = np.array(sorted([p for p, _ in peak_intensities]))
        else:
            centers = []
            for i in range(expected_bands):
                ideal = (i + 0.5) * band_height
                region_peaks = [p for p in peaks if abs(p - ideal) < band_height * 0.6]
                if region_peaks:
                    center = int(np.mean(region_peaks))
                elif len(peaks) > 0:
                    nearest = min(peaks, key=lambda p: abs(p - ideal))
                    if abs(nearest - ideal) < band_height * 0.8:
                        center = nearest
                    else:
                        center = int(ideal)
                else:
                    center = int(ideal)
                centers.append(center)
            centers = np.array(sorted(centers))
        
        bands = []
        for center in centers:
            center = int(center)
            center = max(0, min(h - 1, center))
            peak_val = v_proj[center]
            half = peak_val * 0.25
            
            y1 = center
            while y1 > 0 and v_proj[y1] > half:
                y1 -= 1
            y2 = center
            while y2 < h - 1 and v_proj[y2] > half:
                y2 += 1
            
            max_h = min(30, int(band_height * 0.5))
            if y2 - y1 > max_h:
                y1 = max(0, center - max_h // 2)
                y2 = min(h - 1, center + max_h // 2)
            if y2 - y1 < 3:
                y1 = max(0, center - 3)
                y2 = min(h - 1, center + 3)
            
            intensity = float(peak_val)
            bands.append((y1, y2, intensity))
        return bands
    
    if len(peaks) == 0:
        return []
    
    bands = []
    for peak in peaks:
        peak_val = v_proj[peak]
        half = peak_val * 0.25
        
        y1 = peak
        while y1 > 0 and v_proj[y1] > half:
            y1 -= 1
        y2 = peak
        while y2 < h - 1 and v_proj[y2] > half:
            y2 += 1
        
        max_h = 25
        if y2 - y1 > max_h:
            center = (y1 + y2) // 2
            y1 = max(0, center - max_h // 2)
            y2 = min(h - 1, center + max_h // 2)
        if y2 - y1 < 3:
            y1 = max(0, peak - 3)
            y2 = min(h - 1, peak + 3)
        
        intensity = float(peak_val)
        bands.append((y1, y2, intensity))
    
    bands = sorted(bands, key=lambda x: x[0])
    merged = []
    for b in bands:
        if not merged:
            merged.append(b)
        else:
            last = merged[-1]
            overlap = min(b[1], last[1]) - max(b[0], last[0])
            if overlap > (last[1] - last[0]) * 0.4:
                if b[2] > last[2]:
                    merged[-1] = (min(last[0], b[0]), max(last[1], b[1]), max(last[2], b[2]))
            else:
                merged.append(b)
    
    return merged


def detect_bands_in_lane(image: np.ndarray, lane_box: Tuple[int, int],
                         min_band_height: int = 3,
                         sensitivity: float = 0.25,
                         expected_bands: Optional[int] = None) -> Dict[str, Any]:
    v_proj = compute_band_projection(image, lane_box)
    peak_prom = max(0.01, sensitivity * 0.15)
    peaks, valleys = find_band_peaks_and_valleys(v_proj, min_distance=max(3, min_band_height),
                                                  peak_prominence_ratio=peak_prom)
    bands = _split_bands_by_peaks(v_proj, peaks, valleys, expected_bands)
    
    return {
        "projection": v_proj,
        "peaks": peaks,
        "valleys": valleys,
        "bands": bands,
        "n_detected_peaks": len(peaks)
    }


def get_band_projection_viz(v_proj: np.ndarray, bands: List[Tuple[int, int, float]],
                            peaks: np.ndarray, valleys: np.ndarray,
                            expected_bands: Optional[int] = None,
                            lane_height: int = None) -> np.ndarray:
    h = len(v_proj)
    viz_w = 250
    viz = np.ones((h, viz_w, 3), dtype=np.uint8) * 255
    
    proj_norm = v_proj / (v_proj.max() + 1e-8)
    
    for y in range(h - 1):
        x1 = int(20 + proj_norm[y] * (viz_w - 40))
        x2 = int(20 + proj_norm[y + 1] * (viz_w - 40))
        cv2.line(viz, (x1, y), (x2, y + 1), (100, 100, 100), 1)
    
    for p in peaks:
        if 0 <= p < h:
            x = int(20 + proj_norm[p] * (viz_w - 40))
            cv2.circle(viz, (x, p), 5, (0, 180, 0), -1)
    
    for v in valleys:
        if 0 <= v < h:
            x = int(20 + proj_norm[v] * (viz_w - 40))
            cv2.circle(viz, (x, v), 5, (0, 0, 220), -1)
    
    for y1, y2, intensity in bands:
        cv2.rectangle(viz, (5, y1), (viz_w - 5, y2), (255, 128, 0), 2)
        mid_y = (y1 + y2) // 2
        cv2.putText(viz, f"{mid_y}", (viz_w - 45, mid_y + 4), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 128, 0), 1)
    
    info = f"P:{len(peaks)} V:{len(valleys)} B:{len(bands)}"
    if expected_bands:
        info += f" (E:{expected_bands})"
    cv2.putText(viz, info, (5, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)
    
    return viz


def detect_bands_from_reference(ref_image: np.ndarray, lane_box: Tuple[int, int] = None,
                                 min_band_height: int = 5,
                                 expected_bands: Optional[int] = None) -> List[Tuple[int, int, float]]:
    if lane_box:
        result = detect_bands_in_lane(ref_image, lane_box, min_band_height, sensitivity=0.2, expected_bands=expected_bands)
        return result["bands"]
    lanes, _, _, _ = detect_lanes_smart(ref_image, expected_lanes=None)
    all_bands = []
    for lane in lanes:
        result = detect_bands_in_lane(ref_image, lane, min_band_height, sensitivity=0.2, expected_bands=expected_bands)
        all_bands.append((lane, result["bands"]))
    if all_bands:
        best = max(all_bands, key=lambda x: len(x[1]))
        return best[1]
    return []


def map_bands_to_kda(band_positions: List[Tuple[int, int, float]],
                     marker_bands: List[float],
                     image_height: int) -> Dict[int, float]:
    if len(band_positions) == 0 or len(marker_bands) == 0:
        return {}
    centers = [(b[0] + b[1]) / 2 for b in band_positions]
    sorted_kda = sorted(marker_bands, reverse=True)
    mapping = {}
    used_kda = set()
    for i, center in enumerate(centers):
        best_kda = None
        best_dist = float('inf')
        for kda in sorted_kda:
            if kda in used_kda:
                continue
            dist = abs(i - sorted_kda.index(kda))
            if dist < best_dist:
                best_dist = dist
                best_kda = kda
        if best_kda is not None:
            mapping[i] = best_kda
            used_kda.add(best_kda)
    return mapping


def get_font(font_name: str, size: int):
    font_map = {
        "Arial": ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"],
        "Times New Roman": ["times.ttf", "Times New Roman.ttf", "DejaVuSerif.ttf"],
        "Courier New": ["cour.ttf", "Courier New.ttf", "DejaVuSansMono.ttf"],
        "SimHei (黑体)": ["simhei.ttf", "NotoSansCJK-Bold.ttc"],
        "SimSun (宋体)": ["simsun.ttc", "NotoSerifCJK-Regular.ttc"],
        "Microsoft YaHei (微软雅黑)": ["msyh.ttc", "NotoSansCJK-Regular.ttc"]
    }
    
    system_paths = [
        "/usr/share/fonts/truetype/dejavu/",
        "/usr/share/fonts/truetype/liberation/",
        "/usr/share/fonts/truetype/noto/",
        "/System/Library/Fonts/",
        "C:/Windows/Fonts/",
        "/usr/share/fonts/",
    ]
    
    candidates = font_map.get(font_name, [font_name])
    
    for fp in candidates:
        try:
            return ImageFont.truetype(fp, size)
        except:
            pass
    
    for sp in system_paths:
        for fp in candidates:
            full = os.path.join(sp, fp)
            try:
                return ImageFont.truetype(full, size)
            except:
                pass
    
    fallback_fonts = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    for fp in fallback_fonts:
        try:
            return ImageFont.truetype(fp, size)
        except:
            pass
    
    return ImageFont.load_default()


def annotate_gel_image(
    image: Image.Image,
    lanes: List[Dict[str, Any]],
    marker_lane_idx: Optional[int],
    marker_bands: Optional[List[Dict[str, Any]]],
    font_name: str = "Arial",
    lane_label_y_offset: int = 15,
    lane_label_x_offset: int = 0,
    lane_label_angle: int = 0,
    kda_label_x_offset: int = 10,
    kda_label_y_offset: int = 0,
    lane_fine_offsets: Optional[Dict[int, Dict[str, int]]] = None,
    band_fine_offsets: Optional[Dict[int, Dict[str, int]]] = None,
    show_lane_boxes: bool = False
) -> Image.Image:
    lane_fine_offsets = lane_fine_offsets or {}
    band_fine_offsets = band_fine_offsets or {}
    
    orig_w, orig_h = image.size
    top_pad = 120
    right_pad = 250
    left_pad = 80
    
    new_w = orig_w + left_pad + right_pad
    new_h = orig_h + top_pad
    canvas = Image.new('RGB', (new_w, new_h), (255, 255, 255))
    canvas.paste(image, (left_pad, top_pad))
    
    draw = ImageDraw.Draw(canvas)
    
    lane_font_size = max(16, min(28, orig_w // 35))
    kda_font_size = max(12, min(20, orig_w // 45))
    lane_font = get_font(font_name, lane_font_size)
    kda_font = get_font(font_name, kda_font_size)
    
    lane_color = (0, 0, 0)
    kda_color = (0, 0, 0)
    box_color = (0, 150, 255)
    
    for i, lane in enumerate(lanes):
        x1_orig, x2_orig = lane["box"]
        x1 = x1_orig + left_pad
        x2 = x2_orig + left_pad
        name = lane.get("name", f"Lane {i+1}")
        if not name:
            continue
        
        fine = lane_fine_offsets.get(i, {})
        fine_x = fine.get("x", 0)
        fine_y = fine.get("y", 0)
        
        center_x = (x1 + x2) / 2 + fine_x + lane_label_x_offset
        center_y = lane_label_y_offset + fine_y
        
        bbox = draw.textbbox((0, 0), name, font=lane_font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        
        if lane_label_angle != 0:
            pad = 10
            txt_img = Image.new('RGBA', (text_w + pad * 2, text_h + pad * 2), (255, 255, 255, 0))
            txt_draw = ImageDraw.Draw(txt_img)
            txt_draw.text((pad, pad), name, fill=lane_color, font=lane_font)
            rotated = txt_img.rotate(-lane_label_angle, expand=True, resample=Image.BICUBIC)
            paste_x = int(center_x - rotated.width / 2)
            paste_y = int(center_y - rotated.height / 2)
            canvas.paste(rotated, (paste_x, paste_y), rotated)
        else:
            draw.text((center_x - text_w / 2, center_y), name, fill=lane_color, font=lane_font)
        
        if show_lane_boxes:
            draw.rectangle([x1, top_pad, x2, top_pad + orig_h], outline=box_color, width=1)
    
    if marker_lane_idx is not None and marker_bands and 0 <= marker_lane_idx < len(lanes):
        lane = lanes[marker_lane_idx]
        x1_orig, x2_orig = lane["box"]
        x1 = x1_orig + left_pad
        x2 = x2_orig + left_pad
        
        for bidx, band in enumerate(marker_bands):
            y_center_orig = band["y"]
            y_center = y_center_orig + top_pad
            kda = band["kda"]
            unit = band.get("unit", "kDa")
            
            fine = band_fine_offsets.get(bidx, {})
            fine_x = fine.get("x", 0)
            fine_y = fine.get("y", 0)
            
            label = f"{kda}{unit}" if unit != "kDa" else f"{kda}"
            bbox = draw.textbbox((0, 0), label, font=kda_font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            
            label_x = x1 - kda_label_x_offset - text_w + fine_x
            label_y = y_center - text_h / 2 + fine_y + kda_label_y_offset
            
            label_x = max(5, label_x)
            draw.text((label_x, label_y), label, fill=kda_color, font=kda_font)
    
    return canvas


def create_annotated_image(
    original_image: Image.Image,
    lane_names: List[str],
    lane_boxes: List[Tuple[int, int]],
    marker_lane_idx: Optional[int],
    marker_type: Optional[str],
    marker_bands_data: Optional[List[Dict]],
    font_name: str = "Arial",
    lane_label_y_offset: int = 15,
    lane_label_x_offset: int = 0,
    lane_label_angle: int = 0,
    kda_label_x_offset: int = 10,
    kda_label_y_offset: int = 0,
    lane_fine_offsets: Optional[Dict[int, Dict[str, int]]] = None,
    band_fine_offsets: Optional[Dict[int, Dict[str, int]]] = None,
    show_lane_boxes: bool = False
) -> Image.Image:
    lanes = []
    for i, (box, name) in enumerate(zip(lane_boxes, lane_names)):
        lanes.append({
            "box": box,
            "name": name,
            "is_marker": (i == marker_lane_idx)
        })
    return annotate_gel_image(
        original_image, lanes, marker_lane_idx, marker_bands_data,
        font_name, lane_label_y_offset, lane_label_x_offset, lane_label_angle,
        kda_label_x_offset, kda_label_y_offset,
        lane_fine_offsets, band_fine_offsets, show_lane_boxes
    )

def ocr_marker_numbers(image: Image.Image) -> list[float]:
    """
    使用 EasyOCR 识别 Marker 标准图中的 kDa 数字
    返回：从上到下排序的数字列表
    """
    reader = easyocr.Reader(['en'], gpu=False, verbose=False)
    np_img = np.array(image)
    results = reader.readtext(np_img, detail=1)

    numbers = []
    for bbox, text, conf in results:
        # 只保留数字和小数点
        cleaned = ''.join(c for c in text if c.isdigit() or c == '.')
        if not cleaned:
            continue
        try:
            val = float(cleaned)
            # 计算边界框中心 y（用于排序）
            ys = [p[1] for p in bbox]
            center_y = sum(ys) / len(ys)
            numbers.append((center_y, val))
        except ValueError:
            continue

    # 从上到下排序
    numbers.sort(key=lambda x: x[0])
    return [v for _, v in numbers]
