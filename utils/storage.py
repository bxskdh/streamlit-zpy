import json
import os
from pathlib import Path
import shutil

DATA_DIR = Path("data")
PROJECTS_DIR = DATA_DIR / "gel_projects"
MK_STANDARDS_FILE = DATA_DIR / "mk_standards.json"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(exist_ok=True)

# ---------- MK 标准管理 ----------
def load_mk_standards():
    defaults = {
        "Tris-Glycine 15%": [250, 150, 100, 70, 50, 40, 35, 25, 20, 15, 10],
        "Bis-Tris 4-20% MOPS Buffer": [235, 140, 95, 65, 50, 40, 35, 24, 21, 14, 10],
        "HEPES 15%": [245, 150, 100, 65, 48, 40, 35, 26, 22, 16, 13],
        "未知": [250, 150, 100, 75, 50, 37, 25, 20, 15, 10]
    }
    if MK_STANDARDS_FILE.exists():
        with open(MK_STANDARDS_FILE, 'r') as f:
            data = json.load(f)
        for key, val in defaults.items():
            if key not in data:
                data[key] = val
        save_mk_standards(data)
        return data
    else:
        save_mk_standards(defaults)
        return defaults

def save_mk_standards(standards):
    with open(MK_STANDARDS_FILE, 'w') as f:
        json.dump(standards, f, indent=2)

def add_mk_standard(name, values):
    standards = load_mk_standards()
    standards[name] = values
    save_mk_standards(standards)

def reset_mk_standards():
    if MK_STANDARDS_FILE.exists():
        MK_STANDARDS_FILE.unlink()
    return load_mk_standards()

# ---------- 项目存储 ----------
def list_projects():
    return sorted([p.name for p in PROJECTS_DIR.iterdir() if p.is_dir()])

def load_project(project_name):
    proj_dir = PROJECTS_DIR / project_name
    if not proj_dir.exists():
        return None
    json_path = proj_dir / "annotation.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path, 'r') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        # JSON 文件损坏，返回 None
        print(f"项目 '{project_name}' 的 JSON 文件损坏: {e}")
        return None

    # 将 offset_settings 的字符串键转换回元组
    if 'offset_settings' in data:
        converted = {}
        for key_str, value in data['offset_settings'].items():
            parts = key_str.split('_')
            if len(parts) == 2:
                idx = int(parts[0])
                typ = parts[1]  # 'label'
                converted[(idx, typ)] = tuple(value)
            elif len(parts) == 3:
                idx = int(parts[0])
                typ = parts[1]  # 'band'
                bi = int(parts[2])
                converted[(idx, typ, bi)] = tuple(value)
            else:
                # 兼容未知格式
                converted[key_str] = tuple(value)
        data['offset_settings'] = converted
    data['original_image'] = str(proj_dir / "original.jpg")
    data['annotated_image'] = str(proj_dir / "annotated.jpg")
    return data

def save_project(project_name, data, original_img, annotated_img=None):
    proj_dir = PROJECTS_DIR / project_name
    proj_dir.mkdir(exist_ok=True)
    original_img.save(proj_dir / "original.jpg", quality=95, subsampling=0)
    if annotated_img is not None:
        annotated_img.save(proj_dir / "annotated.jpg", quality=95, subsampling=0)
    json_data = data.copy()
    # 处理 offset_settings：将元组键转换为字符串键
    if 'offset_settings' in json_data:
        serialized = {}
        for key, value in json_data['offset_settings'].items():
            if isinstance(key, tuple):
                key_str = "_".join(str(k) for k in key)
                serialized[key_str] = list(value)  # 确保为列表
            else:
                serialized[str(key)] = list(value)
        json_data['offset_settings'] = serialized
    # 移除不需要保存的字段
    json_data.pop('original_image', None)
    json_data.pop('annotated_image', None)
    with open(proj_dir / "annotation.json", 'w') as f:
        json.dump(json_data, f, indent=2)

def delete_project(project_name):
    proj_dir = PROJECTS_DIR / project_name
    if proj_dir.exists():
        shutil.rmtree(proj_dir)
        return True
    return False
