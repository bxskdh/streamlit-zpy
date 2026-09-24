"""凝胶电泳标注系统的数据持久化模块"""
import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any

DATA_DIR = "data"
GEL_IMAGES_DIR = os.path.join(DATA_DIR, "gel_images")
ANNOTATIONS_FILE = os.path.join(DATA_DIR, "annotations.json")
MARKERS_FILE = os.path.join(DATA_DIR, "markers.json")          # 用户自定义Marker
MK_STANDARDS_FILE = os.path.join(DATA_DIR, "mk_standards.json")  # 预设标准库

os.makedirs(GEL_IMAGES_DIR, exist_ok=True)

DEFAULT_MARKERS = {
    "Tris-Glycine 15%": {
        "bands": [250, 150, 100, 70, 50, 40, 35, 25, 20, 15, 10],
        "description": "Tris-Glycine 15%", "unit": "kDa"
    },
    "Bis-Tris 4-20% MOPS Buffer": {
        "bands": [235, 140, 95, 65, 50, 40, 35, 24, 21, 14, 10],
        "description": "Bis-Tris 4-20% MOPS Buffer", "unit": "kDa"
    },
    "HEPES 15%": {
        "bands": [245, 150, 100, 65, 48, 40, 35, 26, 22, 16, 13],
        "description": "HEPES 15%", "unit": "kDa"
    },
    "未知": {
        "bands": [250, 150, 100, 75, 50, 37, 25, 20, 15, 10],
        "description": "未知", "unit": "kDa"
    }
}


def load_markers() -> Dict[str, Any]:
    """加载Marker：mk_standards.json预设 + markers.json自定义"""
    markers = {}
    
    # 1. 加载预设标准库
    if os.path.exists(MK_STANDARDS_FILE):
        try:
            with open(MK_STANDARDS_FILE, 'r', encoding='utf-8') as f:
                standards = json.load(f)
            for name, bands in standards.items():
                if isinstance(bands, list):
                    markers[name] = {
                        "bands": bands,
                        "description": name,
                        "unit": "kDa",
                        "source": "preset"
                    }
        except Exception:
            pass
    
    if not markers:
        markers = {k: {**v, "source": "preset"} for k, v in DEFAULT_MARKERS.items()}
        try:
            with open(MK_STANDARDS_FILE, 'w', encoding='utf-8') as f:
                json.dump({k: v["bands"] for k, v in DEFAULT_MARKERS.items()}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    
    # 2. 加载用户自定义
    if os.path.exists(MARKERS_FILE):
        try:
            with open(MARKERS_FILE, 'r', encoding='utf-8') as f:
                custom = json.load(f)
            for name, data in custom.items():
                markers[name] = {**data, "source": "custom"}
        except Exception:
            pass
    
    return markers


def save_preset_marker(name: str, bands: List[float], description: str = "", unit: str = "kDa"):
    """保存到 mk_standards.json 预设库"""
    standards = {}
    if os.path.exists(MK_STANDARDS_FILE):
        with open(MK_STANDARDS_FILE, 'r', encoding='utf-8') as f:
            standards = json.load(f)
    standards[name] = bands
    with open(MK_STANDARDS_FILE, 'w', encoding='utf-8') as f:
        json.dump(standards, f, ensure_ascii=False, indent=2)


def save_custom_marker(name: str, bands: List[float], description: str = "", unit: str = "kDa"):
    """保存到 markers.json 自定义库"""
    markers = {}
    if os.path.exists(MARKERS_FILE):
        with open(MARKERS_FILE, 'r', encoding='utf-8') as f:
            markers = json.load(f)
    markers[name] = {
        "bands": bands, "description": description, "unit": unit,
        "custom": True, "created_at": datetime.now().isoformat()
    }
    with open(MARKERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(markers, f, ensure_ascii=False, indent=2)


def delete_custom_marker(name: str):
    if not os.path.exists(MARKERS_FILE):
        return
    with open(MARKERS_FILE, 'r', encoding='utf-8') as f:
        markers = json.load(f)
    if name in markers:
        del markers[name]
        with open(MARKERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(markers, f, ensure_ascii=False, indent=2)


def load_annotations() -> List[Dict[str, Any]]:
    if not os.path.exists(ANNOTATIONS_FILE):
        return []
    with open(ANNOTATIONS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_annotation(annotation: Dict[str, Any]) -> str:
    annotations = load_annotations()
    if "id" not in annotation or not annotation["id"]:
        existing_ids = [a.get("id", "") for a in annotations]
        for i in range(1, 10000):
            new_id = f"p{i}"
            if new_id not in existing_ids:
                annotation["id"] = new_id
                break
    
    updated = False
    for i, ann in enumerate(annotations):
        if ann.get("id") == annotation.get("id"):
            annotations[i] = annotation
            updated = True
            break
    if not updated:
        annotations.append(annotation)
    
    with open(ANNOTATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(annotations, f, ensure_ascii=False, indent=2)
    
    return annotation["id"]


def get_annotation_by_id(aid: str) -> Optional[Dict[str, Any]]:
    for ann in load_annotations():
        if ann.get("id") == aid:
            return ann
    return None


def delete_annotation(aid: str):
    annotations = load_annotations()
    annotations = [a for a in annotations if a.get("id") != aid]
    with open(ANNOTATIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(annotations, f, ensure_ascii=False, indent=2)
    img_path = os.path.join(GEL_IMAGES_DIR, f"{aid}.png")
    if os.path.exists(img_path):
        os.remove(img_path)


def get_next_default_name() -> str:
    annotations = load_annotations()
    existing = set()
    for ann in annotations:
        name = ann.get("name", "")
        if name.startswith("p") and name[1:].isdigit():
            existing.add(int(name[1:]))
    for i in range(1, 10000):
        if i not in existing:
            return f"p{i}"
    return "p1"
