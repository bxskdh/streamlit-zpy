import streamlit as st
import os
from PIL import Image, ImageDraw, ImageFont
from datetime import datetime

# 导入工具模块
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.gel_db import (
    load_annotations, get_annotation_by_id, save_annotation, 
    delete_annotation, GEL_IMAGES_DIR
)
from utils.gel_image import get_font, create_annotated_image

st.set_page_config(page_title="胶图标注管理", layout="wide")

st.title("📝 凝胶电泳图标注管理")
st.markdown("查看、修改和删除已保存的凝胶电泳标注项目。")

# ========== 状态管理 ==========
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "confirm_delete" not in st.session_state:
    st.session_state.confirm_delete = None

# ========== 主界面 ==========
annotations = load_annotations()

if len(annotations) == 0:
    st.info("📭 暂无保存的标注项目。请先在「胶图自动标注」页面创建。")
    st.stop()

# ========== 展示所有项目（网格视图） ==========
if st.session_state.editing_id is None:
    st.subheader("📂 所有标注项目")
    
    # 搜索/筛选
    search = st.text_input("🔍 搜索项目名称", placeholder="输入名称过滤...")
    
    filtered = annotations
    if search:
        filtered = [a for a in annotations if search.lower() in a.get("name", "").lower()]
    
    if len(filtered) == 0:
        st.warning("未找到匹配的项目")
        st.stop()
    
    # 网格展示
    cols = st.columns(3)
    for i, ann in enumerate(filtered):
        with cols[i % 3]:
            with st.container(border=True):
                # 显示缩略图
                img_path = ann.get("image_path", "")
                if os.path.exists(img_path):
                    st.image(img_path, use_container_width=True)
                else:
                    st.error("图片文件丢失")
                
                st.markdown(f"**{ann.get('name', '未命名')}**")
                st.caption(f"创建: {ann.get('created_at', '')[:10]}")
                st.caption(f"胶道数: {len(ann.get('lane_names', []))}")
                
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    if st.button("✏️ 编辑", key=f"edit_{ann['id']}", use_container_width=True):
                        st.session_state.editing_id = ann["id"]
                        st.session_state.confirm_delete = None
                        st.rerun()
                with col_b2:
                    if st.button("🗑️ 删除", key=f"del_{ann['id']}", use_container_width=True):
                        st.session_state.confirm_delete = ann["id"]
                        st.rerun()
                
                # 删除确认
                if st.session_state.confirm_delete == ann["id"]:
                    st.warning("⚠️ 确定要删除此项目吗？此操作不可撤销！")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("✅ 确认删除", key=f"confirm_del_{ann['id']}", 
                                   type="primary", use_container_width=True):
                            delete_annotation(ann["id"])
                            st.session_state.confirm_delete = None
                            st.success("已删除")
                            st.rerun()
                    with c2:
                        if st.button("❌ 取消", key=f"cancel_del_{ann['id']}", use_container_width=True):
                            st.session_state.confirm_delete = None
                            st.rerun()

# ========== 编辑单个项目 ==========
else:
    ann = get_annotation_by_id(st.session_state.editing_id)
    
    if ann is None:
        st.error("项目不存在或已被删除")
        st.session_state.editing_id = None
        st.rerun()
    
    # 返回按钮
    if st.button("⬅️ 返回项目列表"):
        st.session_state.editing_id = None
        st.rerun()
    
    st.subheader(f"✏️ 编辑: {ann.get('name', '未命名')}")
    
    # 加载原始图像（如果有的话，否则用已保存的标注图作为基础）
    # 这里我们需要重新从原始数据生成，因为原始大图可能没有保存
    # 实际使用时，建议同时保存原始图像
    
    # 尝试加载已保存的标注图作为编辑基础
    img_path = ann.get("image_path", "")
    if os.path.exists(img_path):
        base_image = Image.open(img_path).convert("RGB")
    else:
        st.error("图片文件丢失，无法编辑")
        st.stop()
    
    # ========== 编辑面板 ==========
    col_edit, col_preview = st.columns([1, 2])
    
    with col_edit:
        st.markdown("### 胶道标注修改")
        
        # 字体
        font_options = ["Arial", "Times New Roman", "Courier New", 
                       "SimHei (黑体)", "SimSun (宋体)", "Microsoft YaHei (微软雅黑)"]
        current_font = ann.get("font_name", "Arial")
        try:
            font_idx = font_options.index(current_font)
        except ValueError:
            font_idx = 0
        
        new_font = st.selectbox("字体", font_options, index=font_idx)
        
        # 胶道标注参数
        lane_dist = st.slider("胶道标注距离", 5, 50, ann.get("lane_label_distance", 15))
        lane_angle = st.slider("胶道标注角度", -45, 45, ann.get("lane_label_angle", 0))
        kda_dist = st.slider("kDa标注距离", 5, 50, ann.get("kda_label_distance", 10))
        
        st.divider()
        st.markdown("### 胶道名称")
        
        lane_names = ann.get("lane_names", []).copy()
        lane_boxes = ann.get("lane_boxes", [])
        marker_idx = ann.get("marker_lane_idx")
        
        new_names = []
        for i, (name, box) in enumerate(zip(lane_names, lane_boxes)):
            is_marker = (i == marker_idx)
            label = f"胶道 {i+1}" + (" (Marker)" if is_marker else "")
            new_name = st.text_input(label, value=name, key=f"edit_name_{i}_{ann['id']}")
            new_names.append(new_name)
        
        # Marker条带kDa修改
        marker_bands = ann.get("marker_bands", [])
        if marker_bands and marker_idx is not None:
            st.divider()
            st.markdown("### Marker kDa 校准")
            
            new_bands = []
            for i, band in enumerate(marker_bands):
                c1, c2 = st.columns([2, 1])
                with c1:
                    new_kda = st.number_input(
                        f"条带 {i+1} (y≈{int(band['y'])})", 
                        value=float(band['kda']) if isinstance(band['kda'], (int, float)) else 0,
                        step=1.0,
                        key=f"edit_kda_{i}_{ann['id']}"
                    )
                with c2:
                    unit = band.get('unit', 'kDa')
                    new_unit = st.text_input("单位", value=unit, key=f"edit_unit_{i}_{ann['id']}")
                
                new_band = dict(band)
                new_band['kda'] = new_kda
                new_band['unit'] = new_unit
                new_bands.append(new_band)
            
            marker_bands = new_bands
        
        st.divider()
        
        # 保存修改
        if st.button("💾 保存修改", type="primary", use_container_width=True):
            # 重新生成图片
            annotated = create_annotated_image(
                base_image,  # 这里应该用原始图像，但用标注图也可以
                new_names,
                lane_boxes,
                marker_idx,
                ann.get("marker_type"),
                marker_bands,
                new_font,
                lane_dist,
                lane_angle,
                kda_dist,
                show_lane_boxes=False
            )
            
            # 保存图片
            annotated.save(img_path, "PNG")
            
            # 更新数据
            updated_ann = dict(ann)
            updated_ann.update({
                "lane_names": new_names,
                "marker_bands": marker_bands,
                "font_name": new_font,
                "lane_label_distance": lane_dist,
                "lane_label_angle": lane_angle,
                "kda_label_distance": kda_dist,
                "updated_at": datetime.now().isoformat()
            })
            
            save_annotation(updated_ann)
            st.success("✅ 修改已保存")
            st.rerun()
    
    with col_preview:
        st.markdown("### 实时预览")
        
        # 实时生成预览
        annotated = create_annotated_image(
            base_image,
            new_names if 'new_names' in dir() else ann.get("lane_names", []),
            lane_boxes,
            marker_idx,
            ann.get("marker_type"),
            marker_bands if 'marker_bands' in dir() else ann.get("marker_bands", []),
            new_font if 'new_font' in dir() else ann.get("font_name", "Arial"),
            lane_dist if 'lane_dist' in dir() else ann.get("lane_label_distance", 15),
            lane_angle if 'lane_angle' in dir() else ann.get("lane_label_angle", 0),
            kda_dist if 'kda_dist' in dir() else ann.get("kda_label_distance", 10),
            show_lane_boxes=False
        )
        
        st.image(annotated, use_container_width=True)
        
        # 下载按钮
        buf = io.BytesIO()
        annotated.save(buf, format="PNG")
        st.download_button(
            "⬇️ 下载标注图",
            buf.getvalue(),
            file_name=f"{ann.get('name', 'gel')}_annotated.png",
            mime="image/png"
        )
