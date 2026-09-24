import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO, StringIO

def process_single_file(file_obj):
    """处理单个xls文件，返回处理后的DataFrame"""
    df = pd.read_excel(file_obj, sheet_name=0, header=None)
    
    # 从G行（0-based 23）开始，向上取6行（G,F,E,D,C,B）
    # 列4-8（0-based 3-7）和列9-13（0-based 8-12）
    group1 = df.iloc[18:24].iloc[::-1].iloc[:, 3:8]   # G-F-E-D-C-B，列4-8
    group2 = df.iloc[18:24].iloc[::-1].iloc[:, 8:13]  # G-F-E-D-C-B，列9-13
    
    # 转置：6行5列 -> 5行6列
    group1_t = group1.T.reset_index(drop=True)
    group2_t = group2.T.reset_index(drop=True)
    
    # 合并两组数据（横向拼接）
    combined_data = pd.concat([group1_t, group2_t], axis=1)
    
    return combined_data

def build_output_table(all_data_list, param1=100, param2=300, virus_dilution=80, virus_control=326.5, start_dilution=400, compact_mode=False):
    """将多个文件的数据合并成一个大表格"""
    total_data = pd.concat(all_data_list, axis=1).reset_index(drop=True)
    
    num_data_cols = total_data.shape[1]
    num_data_rows = total_data.shape[0]  # 5
    
    # 计算D值和L值
    d_value = np.log10(param1) - np.log10(param2)
    l_value = np.log10(1.0 / start_dilution)
    
    # 输出表格列数：2参数列 + num_data_cols（数据连续填）
    output_cols = 2 + num_data_cols
    
    # 行数计算：
    # 0: id行
    # 1-5: 数据行 (5行)
    # 6: 空行
    # 7-11: 平均值行 (5行)
    # 12: 空行
    # 13-17: 参数行（5个参数纵向排列，每行同时填公式计算值）
    # 18: 空行
    # 19: S值行
    # 20: 空行
    # 21: lgTCID50行
    # 22: 中和抗体滴度行
    output_rows = 23
    
    # 用空字符串初始化（避免None）
    output_df = pd.DataFrame('', index=range(output_rows), columns=range(output_cols))
    
    # ========== 第0行：ID行 ==========
    output_df.iloc[0, 0] = "二免二"
    
    # 构建id：格式1-1, 1-2...每5个进一
    ids = []
    group_num = 1
    item_num = 1
    for i in range(num_data_cols):
        ids.append(f"{group_num}-{item_num}")
        item_num += 1
        if item_num > 5:
            item_num = 1
            group_num += 1
    
    # 第0行（id行）：从第2列开始，隔一列填一个id
    for i, id_val in enumerate(ids):
        col_idx = 2 + i * 2  # 隔列：2, 4, 6, 8...
        if col_idx < output_cols:
            output_df.iloc[0, col_idx] = id_val
    
    # ========== 第1-5行：数据行 ==========
    output_df.iloc[1, 0] = str(param1)
    output_df.iloc[2, 0] = str(param2)
    
    for row_idx in range(num_data_rows):
        for col_idx in range(num_data_cols):
            out_col = 2 + col_idx  # 连续：2, 3, 4, 5...
            val = total_data.iloc[row_idx, col_idx]
            if pd.notna(val):
                if isinstance(val, float) and val == int(val):
                    output_df.iloc[1 + row_idx, out_col] = str(int(val))
                else:
                    output_df.iloc[1 + row_idx, out_col] = str(val)
    
    # ========== 第6行：空行 ==========
    
    # ========== 第7-11行：平均值行 ==========
    avg_start_row = 7
    id_cols = [2 + i * 2 for i in range(num_data_cols) if 2 + i * 2 < output_cols]
    
    for id_col in id_cols:
        for row_idx in range(num_data_rows):
            current_val_str = output_df.iloc[1 + row_idx, id_col]
            right_col = id_col + 1
            right_val_str = output_df.iloc[1 + row_idx, right_col] if right_col < output_cols else ''
            
            try:
                current_val = float(current_val_str) if current_val_str != '' else None
            except:
                current_val = None
            
            try:
                right_val = float(right_val_str) if right_val_str != '' else None
            except:
                right_val = None
            
            if current_val is not None and right_val is not None:
                avg = (current_val + right_val) / 2
                if avg == int(avg):
                    avg_str = str(int(avg))
                else:
                    avg_str = f"{avg:.1f}"
                output_df.iloc[avg_start_row + row_idx, id_col] = avg_str
    
    # ========== 第12行：空行 ==========
    
    # ========== 第13-17行：参数行（纵向排列，同时填公式计算值） ==========
    param_names = ["病毒稀释", "病毒对照", "d值", "起始稀释倍数", "L值"]
    param_values = [str(virus_dilution), str(virus_control), 
                    f"{d_value:.8f}".rstrip('0').rstrip('.'), 
                    str(start_dilution), 
                    f"{l_value:.8f}".rstrip('0').rstrip('.')]
    
    for i in range(5):
        output_df.iloc[13 + i, 0] = param_names[i]
        output_df.iloc[13 + i, 1] = param_values[i]
    
    # 同时在这5行中填公式计算值（从第2列开始，隔列填在id列位置）
    # 公式：(病毒对照 - 平均数) / 病毒对照
    # 如果结果为负数，则不显示（留空），且S值求和时不包括该值
    for i, id_col in enumerate(id_cols):
        for row_idx in range(num_data_rows):
            avg_val_str = output_df.iloc[7 + row_idx, id_col]
            try:
                avg_val = float(avg_val_str) if avg_val_str != '' else None
            except:
                avg_val = None
            
            if avg_val is not None:
                result = (virus_control - avg_val) / virus_control
                # 如果结果为正数或零，才填入；负数则留空
                if result >= 0:
                    result_str = f"{result:.8f}".rstrip('0').rstrip('.')
                    output_df.iloc[13 + row_idx, id_col] = result_str
                # 如果result < 0，不填入任何值，保持为空字符串''
    
    # ========== 第18行：空行 ==========
    
    # ========== 第19行：S值行 ==========
    output_df.iloc[19, 1] = "S值"
    
    for id_col in id_cols:
        s_sum = 0.0
        has_value = False
        for row_idx in range(5):
            val_str = output_df.iloc[13 + row_idx, id_col]
            try:
                val = float(val_str) if val_str != '' else None
            except:
                val = None
            # 只累加非负数值（空字符串或负数已被过滤）
            if val is not None and val >= 0:
                s_sum += val
                has_value = True
        
        if has_value:
            s_str = f"{s_sum:.8f}".rstrip('0').rstrip('.')
            output_df.iloc[19, id_col] = s_str
    
    # ========== 第20行：空行 ==========
    
    # ========== 第21行：lgTCID50行 ==========
    output_df.iloc[21, 1] = "lgTCID50"
    
    for id_col in id_cols:
        s_val_str = output_df.iloc[19, id_col]
        try:
            s_val = float(s_val_str) if s_val_str != '' else None
        except:
            s_val = None
        
        if s_val is not None:
            result = l_value + d_value * (s_val - 0.5)
            result_str = f"{result:.8f}".rstrip('0').rstrip('.')
            output_df.iloc[21, id_col] = result_str
    
    # ========== 第22行：中和抗体滴度行 ==========
    # 公式：1 / (10 ^ 上一行该列数值)，不保留小数位
    output_df.iloc[22, 1] = "中和抗体滴度"
    
    for id_col in id_cols:
        lg_val_str = output_df.iloc[21, id_col]
        try:
            lg_val = float(lg_val_str) if lg_val_str != '' else None
        except:
            lg_val = None
        
        if lg_val is not None:
            result = 1.0 / (10 ** lg_val)
            # 不保留小数位
            result_str = str(int(round(result)))
            output_df.iloc[22, id_col] = result_str
    
    # ========== 紧凑模式处理 ==========
    # 如果启用紧凑模式，将第7-22行（计算结果行）中的数据左移，去掉空列
    # 但保持前6行（0-5行）不变
    if compact_mode:
        # 列数保持原始列数不变，确保原始数据全部展示
        compact_cols = output_cols  # 保持原始列数

        # 创建新的紧凑DataFrame
        compact_df = pd.DataFrame('', index=range(output_rows), columns=range(compact_cols))

        # 复制前7行完全保持原样（包括全部原始数据和空行）
        for row in range(7):
            for col in range(output_cols):
                compact_df.iloc[row, col] = output_df.iloc[row, col]

        # 从第7行开始，把id列的值左移紧凑排列
        for row in range(7, output_rows):
            # 复制前两列
            for col in range(2):
                compact_df.iloc[row, col] = output_df.iloc[row, col]
            # 把id列的值紧凑排列（从第2列开始连续填）
            for i, id_col in enumerate(id_cols):
                compact_df.iloc[row, 2 + i] = output_df.iloc[row, id_col]
            # 右侧多余的列保持为空字符串''（由初始化保证）

        return compact_df
    return output_df

# ============ Streamlit 界面 ============
st.set_page_config(page_title="表格处理_lj", layout="wide")

st.title("📊 表格处理_lj")
st.markdown("上传ImmunoSpot Results.xls文件，提取inclusive sheet数据并转换格式")

# 参数输入
st.subheader("⚙️ 参数设置")
col1, col2, col3 = st.columns(3)
with col1:
    param1 = st.number_input("二免二（1）", value=100, step=1)
with col2:
    param2 = st.number_input("二免二（2）", value=300, step=1)
with col3:
    virus_dilution = st.number_input("病毒稀释", value=80, step=1)

col4, col5, col6 = st.columns(3)
with col4:
    virus_control = st.number_input("病毒对照", value=326.5, step=0.5)
with col5:
    start_dilution = st.number_input("起始稀释倍数", value=400, step=1)
with col6:
    # D值和L值只读显示
    d_value = np.log10(param1) - np.log10(param2)
    l_value = np.log10(1.0 / start_dilution)
    st.text_input("d值（自动计算）", value=f"{d_value:.8f}".rstrip('0').rstrip('.'), disabled=True)
    st.text_input("L值（自动计算）", value=f"{l_value:.8f}".rstrip('0').rstrip('.'), disabled=True)

# 展示模式选择
st.subheader("📐 展示模式")
compact_mode = st.radio(
    "选择计算结果展示方式",
    options=["隔列展示（原始）", "紧凑展示（去除空列）"],
    index=0,
    help="隔列展示：计算结果保留在原始id列位置，右侧空列保留\n紧凑展示：第8-23行计算结果去除空列，向左紧凑排列，前6行保持不变"
)

uploaded_files = st.file_uploader(
    "上传一个或多个 .xls 文件",
    type=["xls", "xlsx"],
    accept_multiple_files=True
)

if uploaded_files:
    all_data = []
    file_names = []
    
    for file in uploaded_files:
        try:
            data = process_single_file(file)
            all_data.append(data)
            file_names.append(file.name)
            st.success(f"✅ 成功处理: {file.name} (提取 {data.shape[1]} 列数据)")
        except Exception as e:
            st.error(f"❌ 处理 {file.name} 失败: {str(e)}")
    
    if all_data:
        # 构建输出表格
        is_compact = (compact_mode == "紧凑展示（去除空列）")
        output_df = build_output_table(
            all_data, 
            param1=param1, 
            param2=param2,
            virus_dilution=virus_dilution,
            virus_control=virus_control,
            start_dilution=start_dilution,
            compact_mode=is_compact
        )
        
        st.markdown("---")
        st.subheader("📋 处理结果")
        
        # 显示表格（添加水平滚动条）
        st.dataframe(
            output_df,
            use_container_width=False,
            hide_index=True,
            height=700,
            width=1800
        )
        
        # 转换为CSV下载
        csv_buffer = StringIO()
        output_df.to_csv(csv_buffer, index=False, header=False, encoding='utf-8')
        csv_str = csv_buffer.getvalue()
        
        col1, col2 = st.columns(2)
        with col1:
            st.download_button(
                label="⬇️ 下载为 CSV",
                data=csv_str,
                file_name="processed_results.csv",
                mime="text/csv",
                use_container_width=True
            )
        
        with col2:
            # Excel下载
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                output_df.to_excel(writer, index=False, header=False, sheet_name="Results")
            excel_buffer.seek(0)
            
            st.download_button(
                label="⬇️ 下载为 Excel",
                data=excel_buffer,
                file_name="processed_results.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        # 显示统计信息
        st.markdown("---")
        st.subheader("📊 统计信息")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("处理文件数", len(file_names))
        with col2:
            st.metric("总数据列数", output_df.shape[1] - 2)
        with col3:
            st.metric("总数据行数", output_df.shape[0])
        
        with st.expander("🔍 查看文件列表"):
            for i, name in enumerate(file_names, 1):
                st.write(f"{i}. {name}")

else:
    st.info("👆 请上传 .xls 或 .xlsx 文件以开始处理")
    
    # 使用说明
    with st.expander("📖 使用说明"):
        st.markdown("""
        **处理流程：**
        1. 读取上传文件的第一个sheet（inclusive）
        2. 提取G-B行（G行作为第一行）的数据
        3. 将列4-8和列9-13分为两组
        4. 每组数据转置（6行×5列 → 5行×6列）
        5. 多文件数据横向合并
        6. 输出格式：
           - 第1行：第1列="二免二"，第3列起隔列填ID
           - 第2-3行：第1列=二免二（1）和（2），第3列起填数据
           - 第4-6行：第3列起连续填剩余数据
           - 第7行：空行
           - 第8-12行：平均值（ID列与其右侧值的平均）
           - 第13行：空行
           - 第14-18行：参数纵向排列（病毒稀释、病毒对照、d值、起始稀释倍数、L值），同时填公式计算值
             - 公式：(病毒对照-平均数)/病毒对照，负数不显示
           - 第19行：空行
           - 第20行：S值（SUM第14-18行，负数不计入）
           - 第21行：空行
           - 第22行：lgTCID50 = L值 + D值*(S值-0.5)
           - 第23行：中和抗体滴度 = 1/(10^lgTCID50)（不保留小数位）
        
        **展示模式：**
        - **隔列展示**：第8-23行计算结果保留在原始id列位置（第3、5、7...列），右侧空列保留
        - **紧凑展示**：第8-23行计算结果去除空列，向左紧凑排列（第3、4、5...列连续），前6行保持不变
        """)
