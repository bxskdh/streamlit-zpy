import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO, StringIO
import re
import sys

# 检查 Biopython 是否安装
try:
    from Bio.SeqUtils.ProtParam import ProteinAnalysis
except ImportError:
    st.error("未安装 Biopython，请运行：pip install biopython")
    st.stop()

# ======================== 计算核心函数 ========================

def clean_sequence(seq: str) -> str:
    """清理序列，只保留标准氨基酸字母，转为大写"""
    seq = seq.upper()
    seq = re.sub(r'[^A-Z]', '', seq)
    valid = set("ACDEFGHIKLMNPQRSTVWY")
    return ''.join([c for c in seq if c in valid])

def split_chains(seq_text: str) -> list:
    """将输入的序列文本拆分为多条链（支持换行、分号、逗号分隔）"""
    parts = re.split(r'[\n;,，]', seq_text)
    chains = []
    for part in parts:
        cleaned = clean_sequence(part.strip())
        if cleaned:
            chains.append(cleaned)
    return chains

def process_project(name: str, seq_text: str) -> dict:
    """
    处理一个项目：拆分为多条链，利用 Biopython 计算分子量、pI、消光系数
    """
    chains = split_chains(seq_text)
    if not chains:
        return None

    # 每条链单独计算分子量
    chain_mw_da = []
    for chain in chains:
        try:
            analysis = ProteinAnalysis(chain)
            mw = analysis.molecular_weight()  # Da
        except Exception:
            mw = 0.0
        chain_mw_da.append(mw)
    total_mw_da = sum(chain_mw_da)
    total_mw_kda = total_mw_da / 1000.0

    # 拼接所有链用于 pI 和消光系数
    full_seq = ''.join(chains)
    try:
        full_analysis = ProteinAnalysis(full_seq)
        pI = full_analysis.isoelectric_point()
        epsilon = full_analysis.molar_extinction_coefficient()
        epsilon = epsilon[0] if isinstance(epsilon, tuple) else epsilon
    except Exception:
        pI = 0.0
        epsilon = 0.0

    # Abs 0.1% (1 g/L) = ε / MW(Da)
    abs_0_1 = epsilon / total_mw_da if total_mw_da > 0 else 0.0

    # 分子量显示
    if len(chains) == 1:
        mw_str = f"{total_mw_kda:.1f}"
    else:
        chain_kda = [mw / 1000.0 for mw in chain_mw_da]
        if max(chain_kda) - min(chain_kda) < 0.05:
            chain_str = f"{chain_kda[0]:.1f}"
        else:
            chain_str = '/'.join([f"{c:.1f}" for c in chain_kda])
        mw_str = f"{total_mw_kda:.1f}（{chain_str}）"

    return {
        'name': name,
        'full_seq': full_seq,
        'total_mw_kda': total_mw_kda,
        'pI': pI,
        'abs': abs_0_1,
        'mw_str': mw_str,
        'num_chains': len(chains)
    }

# ======================== Streamlit 界面 ========================

st.set_page_config(page_title="蛋白性质计算", layout="wide")
st.title("🧬 蛋白理论性质计算 (Biopython)")
st.markdown("使用 Biopython 的 ProtParam 模块计算理论分子量、等电点和消光系数 (Abs 0.1%)")

PRESET_LABELS = ['His-hIgG1-FC', 'His-strep', 'hIgG4 Fc mut']

if 'input_mode' not in st.session_state:
    st.session_state.input_mode = '人工输入'
if 'projects' not in st.session_state:
    st.session_state.projects = [{'name': '', 'seq': ''}]
if 'labels' not in st.session_state:
    st.session_state.labels = [PRESET_LABELS[0]]
if 'custom_labels' not in st.session_state:
    st.session_state.custom_labels = ['']

def sync_labels():
    while len(st.session_state.labels) < len(st.session_state.projects):
        st.session_state.labels.append(PRESET_LABELS[0])
        st.session_state.custom_labels.append('')
    while len(st.session_state.labels) > len(st.session_state.projects):
        st.session_state.labels.pop()
        st.session_state.custom_labels.pop()
sync_labels()

mode = st.radio("选择输入方式", ['人工输入', '上传表格'], horizontal=True)
st.session_state.input_mode = mode

if mode == '人工输入':
    st.subheader("✏️ 人工输入项目")
    st.caption("每个项目可输入多条序列，**每条链占一行**（也支持用逗号、分号分隔）")

    to_remove = None
    for i, proj in enumerate(st.session_state.projects):
        cols = st.columns([2, 4, 2, 1])
        with cols[0]:
            proj['name'] = st.text_input(f"项目名称 #{i+1}", value=proj['name'], key=f"name_{i}")
        with cols[1]:
            proj['seq'] = st.text_area(f"序列 (多链换行)", value=proj['seq'], height=80, key=f"seq_{i}")
        with cols[2]:
            label_options = PRESET_LABELS + ['自定义']
            sel_idx = label_options.index(st.session_state.labels[i]) if st.session_state.labels[i] in PRESET_LABELS else len(PRESET_LABELS)
            selected = st.selectbox(f"标签 #{i+1}", label_options, index=sel_idx, key=f"label_sel_{i}")
            if selected == '自定义':
                custom = st.text_input("自定义标签", value=st.session_state.custom_labels[i], key=f"custom_{i}")
                st.session_state.custom_labels[i] = custom
                st.session_state.labels[i] = custom if custom else '自定义'
            else:
                st.session_state.labels[i] = selected
                st.session_state.custom_labels[i] = ''
        with cols[3]:
            if st.button("🗑️", key=f"del_{i}"):
                to_remove = i
        st.markdown("---")

    if to_remove is not None:
        del st.session_state.projects[to_remove]
        del st.session_state.labels[to_remove]
        del st.session_state.custom_labels[to_remove]
        st.experimental_rerun()

    col_add1, col_add2 = st.columns([1, 5])
    with col_add1:
        if st.button("➕ 添加项目"):
            st.session_state.projects.append({'name': '', 'seq': ''})
            st.session_state.labels.append(PRESET_LABELS[0])
            st.session_state.custom_labels.append('')
            st.experimental_rerun()
    with col_add2:
        if st.button("🧹 清空所有"):
            st.session_state.projects = [{'name': '', 'seq': ''}]
            st.session_state.labels = [PRESET_LABELS[0]]
            st.session_state.custom_labels = ['']
            st.experimental_rerun()

else:
    st.subheader("📂 上传表格")
    st.caption("表格应包含两列：`抗体名称` 和 `氨基酸序列`。空名称行将继承上一行项目。")
    uploaded_file = st.file_uploader("上传 CSV 或 Excel 文件", type=['csv', 'xlsx', 'xls'])

    if uploaded_file is not None:
        try:
            # ========== 关键修改：强制以字符串类型读取 ==========
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file, dtype=str)          # 全部读为字符串
            else:
                df = pd.read_excel(uploaded_file, engine='openpyxl', dtype=str)  # Excel 也强制字符串

            if df.shape[1] < 2:
                st.error("表格至少需要两列")
            else:
                df = df.iloc[:, :2]
                df.columns = ['name', 'seq']
                # 前向填充空名称（空值在字符串中表现为空字符串或 "nan"）
                df['name'] = df['name'].replace('nan', '').fillna(method='ffill')
                # 去除空序列行（空字符串或仅空白）
                df = df[df['seq'].notna() & (df['seq'].astype(str).str.strip() != '')]
                if df.empty:
                    st.warning("未读取到有效序列")
                else:
                    # 按名称分组，合并同一项目的序列（用换行连接）
                    grouped = df.groupby('name', as_index=False).agg({'seq': lambda x: '\n'.join(x.astype(str).tolist())})
                    # 名称已经是字符串，无需再转
                    st.session_state.projects = []
                    st.session_state.labels = []
                    st.session_state.custom_labels = []
                    for _, row in grouped.iterrows():
                        st.session_state.projects.append({'name': row['name'], 'seq': row['seq']})
                        st.session_state.labels.append(PRESET_LABELS[0])
                        st.session_state.custom_labels.append('')
                    st.success(f"成功解析 {len(st.session_state.projects)} 个项目")
                    st.dataframe(grouped, use_container_width=True)
        except Exception as e:
            st.error(f"读取文件失败: {e}")

st.markdown("---")
st.subheader("📊 计算结果")

if st.button("🚀 计算", use_container_width=True):
    if not st.session_state.projects:
        st.warning("没有项目可计算")
    else:
        valid_projects = []
        for i, proj in enumerate(st.session_state.projects):
            name = str(proj['name']).strip()
            seq = str(proj['seq']).strip()
            if not name:
                st.warning(f"项目 #{i+1} 缺少名称，已跳过")
                continue
            if not seq:
                st.warning(f"项目 '{name}' 序列为空，已跳过")
                continue
            valid_projects.append((i, name, seq))

        if not valid_projects:
            st.warning("没有有效项目")
        else:
            results = []
            with st.spinner("计算中，请稍候..."):
                for idx, name, seq in valid_projects:
                    result = process_project(name, seq)
                    if result is None:
                        st.warning(f"项目 '{name}' 无有效序列，已跳过")
                        continue
                    label = st.session_state.labels[idx] if idx < len(st.session_state.labels) else ''
                    if label == '自定义' and st.session_state.custom_labels[idx]:
                        label = st.session_state.custom_labels[idx]
                    elif label == '自定义':
                        label = ''
                    results.append({
                        '项目名称': result['name'],
                        '蛋白标签/抗体亚型': label,
                        '理论分子量(KDa)': result['mw_str'],
                        '等电点': round(result['pI'], 3),
                        'Abs 0.1% (=1 g/l)': round(result['abs'], 4)
                    })

            if results:
                output_df = pd.DataFrame(results)
                st.success(f"计算完成，共 {len(results)} 个项目")
                st.dataframe(output_df, use_container_width=True, hide_index=True)

                col1, col2 = st.columns(2)
                with col1:
                    csv_buffer = StringIO()
                    output_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    csv_str = csv_buffer.getvalue()
                    st.download_button(
                        label="⬇️ 下载为 CSV",
                        data=csv_str,
                        file_name="protein_properties.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with col2:
                    excel_buffer = BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        output_df.to_excel(writer, index=False, sheet_name="Properties")
                    excel_buffer.seek(0)
                    st.download_button(
                        label="⬇️ 下载为 Excel",
                        data=excel_buffer,
                        file_name="protein_properties.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )
            else:
                st.error("没有成功计算出任何项目")

with st.expander("📖 使用说明"):
    st.markdown("""
    **功能简介**
    - 使用 Biopython 的 ProtParam 模块计算：
      - 理论分子量 (KDa)
      - 等电点 (pI)
      - 消光系数 (Abs 0.1% = 1 g/L)
    - 支持多链蛋白（抗体、融合蛋白等），每条链占一行或用逗号/分号分隔。

    **输入方式**
    1. **人工输入**：逐个添加项目，每个项目可输入多行序列（每行一条链）。
    2. **上传表格**：上传 CSV 或 Excel 文件，需包含两列：`抗体名称` 和 `氨基酸序列`。空名称行会自动继承上一行项目名称。

    **蛋白标签/抗体亚型**
    - 每个项目可单独选择标签（预设：His-hIgG1-FC、His-strep、hIgG4 Fc mut）
    - 支持自定义输入

    **输出格式**
    - 表格包含：项目名称、标签、理论分子量(KDa)、等电点、Abs 0.1%
    - 支持下载为 CSV 或 Excel 文件

    **依赖**
    - 需要安装 Biopython：`pip install biopython`
    """)
