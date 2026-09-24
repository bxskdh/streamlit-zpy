import streamlit as st
import json
import subprocess
import os
import tempfile
from pathlib import Path
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import glob

st.set_page_config(page_title="AB1测序分析", layout="wide")

st.title("🔬 AB1测序文件分析")
st.markdown("上传AB1测序文件，使用Tracy进行basecalling并可视化色谱图")

# ============ 文件上传 ============
uploaded_file = st.file_uploader("上传AB1文件", type=["ab1"])

# 用于存储处理结果
if 'ab1_result' not in st.session_state:
    st.session_state.ab1_result = None

if uploaded_file is not None:
    # 保存上传的文件到临时目录
    with tempfile.TemporaryDirectory() as tmpdir:
        ab1_path = os.path.join(tmpdir, uploaded_file.name)
        with open(ab1_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # 输出文件路径 - 使用完整文件名
        output_json = os.path.join(tmpdir, "tracy_output.json")
        output_prefix = os.path.join(tmpdir, "tracy_output")

        # 运行tracy basecall
        with st.spinner("正在运行Tracy basecall..."):
            try:
                # 尝试方式1: -o 指定完整json路径
                cmd1 = ["tracy", "basecall", "-o", output_json, ab1_path]
                result = subprocess.run(cmd1, capture_output=True, text=True, timeout=60)

                # 如果方式1失败，尝试方式2: 只指定前缀
                if result.returncode != 0 or not os.path.exists(output_json):
                    cmd2 = ["tracy", "basecall", "-o", output_prefix, ab1_path]
                    result = subprocess.run(cmd2, capture_output=True, text=True, timeout=60)

                # 如果还是失败，尝试方式3: 不指定-o，找默认输出
                if result.returncode != 0:
                    cmd3 = ["tracy", "basecall", ab1_path]
                    result = subprocess.run(cmd3, capture_output=True, text=True, timeout=60, cwd=tmpdir)

                if result.returncode != 0:
                    err_msg = "Tracy运行失败:\nstdout: " + result.stdout + "\nstderr: " + result.stderr
                    st.error(err_msg)
                    st.stop()

            except FileNotFoundError:
                st.error("未找到tracy命令，请确保Tracy已安装并加入PATH")
                st.stop()
            except Exception as e:
                st.error("运行出错: " + str(e))
                st.stop()

        # 查找生成的JSON文件（尝试多种可能的位置和命名）
        possible_paths = [
            output_json,
            output_prefix + ".json",
            os.path.join(tmpdir, "out.json"),
            os.path.join(os.getcwd(), "out.json"),
        ]

        # 也尝试在tmpdir中找任何json文件
        json_files = glob.glob(os.path.join(tmpdir, "*.json"))
        possible_paths.extend(json_files)

        json_path = None
        for p in possible_paths:
            if os.path.exists(p) and os.path.getsize(p) > 0:
                json_path = p
                break

        if json_path is None:
            # 列出tmpdir中的所有文件，帮助调试
            all_files = os.listdir(tmpdir)
            st.error("未找到JSON输出文件。临时目录内容: " + str(all_files))
            st.info("Tracy stdout: " + result.stdout)
            st.info("Tracy stderr: " + result.stderr)
            st.stop()

        st.info("找到输出文件: " + json_path)

        with open(json_path, "r") as f:
            data = json.load(f)

        # 保存到session_state
        st.session_state.ab1_result = data
        st.success("分析完成！")

# ============ 结果显示 ============
if st.session_state.ab1_result is not None:
    data = st.session_state.ab1_result

    # 提取序列
    primary_seq = data.get("primarySeq", "")
    secondary_seq = data.get("secondarySeq", "")

    # ============ 序列展示区域 ============
    st.markdown("---")
    st.subheader("📋 序列结果")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Primary Sequence（主序列）**")
        st.text_area("primary", primary_seq, height=150, label_visibility="collapsed")
        st.download_button(
            label="⬇️ 下载Primary Sequence",
            data=primary_seq,
            file_name="primary_sequence.txt",
            mime="text/plain",
            key="dl_primary"
        )

    with col2:
        st.markdown("**Secondary Sequence（次序列）**")
        st.text_area("secondary", secondary_seq, height=150, label_visibility="collapsed")
        st.download_button(
            label="⬇️ 下载Secondary Sequence",
            data=secondary_seq,
            file_name="secondary_sequence.txt",
            mime="text/plain",
            key="dl_secondary"
        )

    # ============ 混合碱基位点统计 ============
    st.markdown("---")
    st.subheader("🔀 混合碱基位点（Heterozygous Peaks）")

    basecalls = data.get("basecalls", {})
    hets = []
    for pos_str, call in basecalls.items():
        parts = call.split(":")
        if len(parts) == 2:
            idx, bases = parts
            base_list = bases.split("|")
            if len(base_list) > 1:
                hets.append({
                    "位置": int(idx),
                    "扫描坐标": int(pos_str),
                    "碱基": "|".join(base_list),
                    "碱基数": len(base_list)
                })

    if hets:
        import pandas as pd
        df_hets = pd.DataFrame(hets)
        st.dataframe(df_hets, use_container_width=True)
        st.caption("共发现 " + str(len(hets)) + " 个混合碱基位点")
    else:
        st.info("未发现混合碱基位点")

    # ============ 色谱图可视化 ============
    st.markdown("---")
    st.subheader("📊 色谱图（Chromatogram）")

    # 获取数据
    pos = data.get("pos", [])
    peakA = data.get("peakA", [])
    peakC = data.get("peakC", [])
    peakG = data.get("peakG", [])
    peakT = data.get("peakT", [])
    basecallPos = data.get("basecallPos", [])

    # 如果没有数据，提示
    if not pos or not peakA:
        st.warning("色谱数据缺失")
        st.stop()

    # 提供几种查看模式
    view_mode = st.radio("查看模式", ["全序列概览", "指定范围", "按碱基位置跳转"], horizontal=True)

    total_len = len(pos)

    if view_mode == "全序列概览":
        # 全序列概览 - 采样显示
        max_points = 5000
        step = max(1, total_len // max_points)

        pos_view = pos[::step]
        peakA_view = peakA[::step]
        peakC_view = peakC[::step]
        peakG_view = peakG[::step]
        peakT_view = peakT[::step]

        x_range = [pos_view[0], pos_view[-1]]

    elif view_mode == "指定范围":
        col_start, col_end = st.columns(2)
        with col_start:
            start_pos = st.number_input("起始扫描位置", min_value=1, max_value=total_len, value=1)
        with col_end:
            end_pos = st.number_input("结束扫描位置", min_value=1, max_value=total_len, value=min(500, total_len))

        start_idx = max(0, start_pos - 1)
        end_idx = min(total_len, end_pos)

        pos_view = pos[start_idx:end_idx]
        peakA_view = peakA[start_idx:end_idx]
        peakC_view = peakC[start_idx:end_idx]
        peakG_view = peakG[start_idx:end_idx]
        peakT_view = peakT[start_idx:end_idx]

        x_range = [pos_view[0], pos_view[-1]]

    else:  # 按碱基位置跳转
        seq_len = len(primary_seq)
        target_base = st.number_input("跳转到碱基位置", min_value=1, max_value=seq_len, value=1)

        if target_base <= len(basecallPos):
            center_pos = basecallPos[target_base - 1]
            window = 100

            start_idx = max(0, center_pos - window - 1)
            end_idx = min(total_len, center_pos + window)

            pos_view = pos[start_idx:end_idx]
            peakA_view = peakA[start_idx:end_idx]
            peakC_view = peakC[start_idx:end_idx]
            peakG_view = peakG[start_idx:end_idx]
            peakT_view = peakT[start_idx:end_idx]

            x_range = [pos_view[0], pos_view[-1]]
        else:
            st.error("碱基位置超出范围")
            st.stop()

    # 创建色谱图
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=pos_view, y=peakA_view,
        mode='lines',
        name='A (绿色)',
        line=dict(color='green', width=1),
        hovertemplate='Pos: %{x}<br>A: %{y}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=pos_view, y=peakC_view,
        mode='lines',
        name='C (蓝色)',
        line=dict(color='blue', width=1),
        hovertemplate='Pos: %{x}<br>C: %{y}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=pos_view, y=peakG_view,
        mode='lines',
        name='G (黑色)',
        line=dict(color='black', width=1),
        hovertemplate='Pos: %{x}<br>G: %{y}<extra></extra>'
    ))
    fig.add_trace(go.Scatter(
        x=pos_view, y=peakT_view,
        mode='lines',
        name='T (红色)',
        line=dict(color='red', width=1),
        hovertemplate='Pos: %{x}<br>T: %{y}<extra></extra>'
    ))

    # 添加碱基call的标注线
    if view_mode != "全序列概览":
        for i, bp in enumerate(basecallPos):
            if x_range[0] <= bp <= x_range[-1]:
                pos_str = str(bp)
                if pos_str in basecalls:
                    call_info = basecalls[pos_str]
                    parts = call_info.split(":")
                    if len(parts) == 2:
                        idx, bases = parts
                        base_list = bases.split("|")

                        if len(base_list) > 1:
                            anno_color = "purple"
                            anno_text = idx + ":" + bases
                        else:
                            base = base_list[0]
                            color_map = {"A": "green", "C": "blue", "G": "black", "T": "red"}
                            anno_color = color_map.get(base, "gray")
                            anno_text = idx + ":" + base

                        fig.add_vline(
                            x=bp,
                            line=dict(color=anno_color, width=1, dash="dot"),
                            opacity=0.5
                        )
                        fig.add_annotation(
                            x=bp,
                            y=max(max(peakA_view), max(peakC_view), max(peakG_view), max(peakT_view)) * 1.05,
                            text=anno_text,
                            showarrow=False,
                            font=dict(size=8, color=anno_color),
                            textangle=-90
                        )

    fig.update_layout(
        title="Sanger测序色谱图",
        xaxis_title="扫描位置",
        yaxis_title="信号强度",
        height=500,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=50, r=50, t=80, b=50)
    )

    st.plotly_chart(fig, use_container_width=True)

    # ============ 序列与色谱对照图 ============
    st.markdown("---")
    st.subheader("🧬 序列-色谱对照图")

    seq_len = len(primary_seq)
    col_s, col_e = st.columns(2)
    with col_s:
        seq_start = st.number_input("起始碱基", min_value=1, max_value=seq_len, value=1, key="seq_start")
    with col_e:
        seq_end = st.number_input("结束碱基", min_value=1, max_value=seq_len, value=min(50, seq_len), key="seq_end")

    if seq_start > seq_end:
        st.error("起始位置不能大于结束位置")
        st.stop()

    # 获取对应扫描范围
    start_idx = max(0, basecallPos[seq_start - 1] - 50 - 1) if seq_start <= len(basecallPos) else 0
    end_idx = min(total_len, basecallPos[min(seq_end - 1, len(basecallPos) - 1)] + 50) if seq_end <= len(basecallPos) else total_len

    pos_zoom = pos[start_idx:end_idx]
    pA_zoom = peakA[start_idx:end_idx]
    pC_zoom = peakC[start_idx:end_idx]
    pG_zoom = peakG[start_idx:end_idx]
    pT_zoom = peakT[start_idx:end_idx]

    fig2 = go.Figure()

    fig2.add_trace(go.Scatter(x=pos_zoom, y=pA_zoom, mode='lines', name='A', line=dict(color='green', width=1.5)))
    fig2.add_trace(go.Scatter(x=pos_zoom, y=pC_zoom, mode='lines', name='C', line=dict(color='blue', width=1.5)))
    fig2.add_trace(go.Scatter(x=pos_zoom, y=pG_zoom, mode='lines', name='G', line=dict(color='black', width=1.5)))
    fig2.add_trace(go.Scatter(x=pos_zoom, y=pT_zoom, mode='lines', name='T', line=dict(color='red', width=1.5)))

    # 添加每个碱基call的标注
    for i in range(seq_start - 1, min(seq_end, len(basecallPos))):
        bp = basecallPos[i]
        if start_idx <= bp <= end_idx:
            pos_str = str(bp)
            if pos_str in basecalls:
                call_info = basecalls[pos_str]
                parts = call_info.split(":")
                if len(parts) == 2:
                    idx, bases = parts
                    base_list = bases.split("|")

                    if len(base_list) > 1:
                        anno_color = "purple"
                        anno_text = bases
                    else:
                        base = base_list[0]
                        color_map = {"A": "green", "C": "blue", "G": "black", "T": "red"}
                        anno_color = color_map.get(base, "gray")
                        anno_text = base

                    fig2.add_vline(x=bp, line=dict(color=anno_color, width=2), opacity=0.3)
                    fig2.add_annotation(
                        x=bp,
                        y=max(max(pA_zoom), max(pC_zoom), max(pG_zoom), max(pT_zoom)) * 1.1,
                        text=anno_text,
                        showarrow=False,
                        font=dict(size=14, color=anno_color, family="Courier New"),
                        bgcolor="white",
                        bordercolor=anno_color,
                        borderwidth=1
                    )

    fig2.update_layout(
        title="碱基 " + str(seq_start) + " - " + str(seq_end) + " 的色谱图",
        xaxis_title="扫描位置",
        yaxis_title="信号强度",
        height=500,
        hovermode='x unified',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    st.plotly_chart(fig2, use_container_width=True)

    # 显示对应序列
    show_seq = primary_seq[seq_start - 1:seq_end]
    show_sec = secondary_seq[seq_start - 1:seq_end] if secondary_seq else ""

    st.markdown("**对应Primary序列片段：**")
    st.code(show_seq, language="text")
    if show_sec:
        st.markdown("**对应Secondary序列片段：**")
        st.code(show_sec, language="text")

    # ============ 原始JSON下载 ============
    st.markdown("---")
    st.subheader("💾 原始数据")
    json_str = json.dumps(data, indent=2)
    st.download_button(
        label="⬇️ 下载完整JSON结果",
        data=json_str,
        file_name="tracy_result.json",
        mime="application/json",
        key="dl_json"
    )
