import streamlit as st
import pandas as pd
import numpy as np
import io

st.set_page_config(page_title="斑点面积分析", layout="wide")
st.title("🦠 斑点面积分析")

# --- 1. 文件上传与数据提取 ---
uploaded_file = st.file_uploader("上传包含 'Well areas covered by spots' 表格的 Excel 文件", type=["xlsx", "xls"])

if uploaded_file:
    try:
        xls = pd.ExcelFile(uploaded_file)
        target_df = None
        
        for sheet_name in xls.sheet_names:
            df_raw = pd.read_excel(xls, sheet_name=sheet_name, header=None)
            mask = df_raw.apply(lambda row: row.astype(str).str.contains("Well areas covered by spots", case=False, na=False).any(), axis=1)
            matched_rows = np.where(mask)[0]
            
            if len(matched_rows) > 0:
                start_row_idx = int(matched_rows[0])
                row_data = df_raw.iloc[start_row_idx].astype(str)
                matched_cols = np.where(row_data.str.contains("Well areas covered by spots", case=False, na=False))[0]
                start_col_idx = int(matched_cols[0])
                
                data_start_row = start_row_idx + 6
                data_start_col = start_col_idx + 1
                
                raw_data = df_raw.iloc[data_start_row:data_start_row+6, data_start_col:data_start_col+10].copy()
                raw_data.reset_index(drop=True, inplace=True)
                raw_data.columns = range(10)
                raw_data = raw_data.apply(pd.to_numeric, errors='coerce')
                
                target_df = raw_data
                break
        
        if target_df is None:
            st.error("未在文件中找到 'Well areas covered by spots (% of counted area)' 表格。")
            st.stop()

        # --- 2. 参数设置 ---
        st.subheader("参数设置")
        col1, col2 = st.columns(2)
        with col1:
            virus_control = st.number_input("病毒对照 (B1)", value=15.62, format="%.2f")
        with col2:
            dilution_input = st.text_input("样品稀释倍数 (B2:B4)", value="30, 40, 60")
            dilutions = [x.strip() for x in dilution_input.split(",") if x.strip()]

        # --- 3. 数据计算 ---
        num_rows = len(target_df)
        row_labels = [str(i) for i in range(1, num_rows + 1)]
        target_df.index = row_labels
        target_df.columns = [str(i) for i in range(2, 12)] 
        
        avg_df = pd.DataFrame(index=row_labels, columns=[2, 4, 6, 8, 10])
        result_df = pd.DataFrame(index=row_labels, columns=[2, 4, 6, 8, 10])
        
        for i in range(0, 10, 2):
            col_pair_1 = str(i + 2) 
            col_pair_2 = str(i + 3) 
            avg_col = (target_df[col_pair_1] + target_df[col_pair_2]) / 2
            avg_df[int(col_pair_1)] = avg_col.values
            result_col = (virus_control - avg_col) / virus_control * 100
            result_df[int(col_pair_1)] = result_col.values
        
        # --- 4. 结果显示 ---
        st.subheader("结果")
        compact_mode = st.checkbox("紧凑模式 (平均值和结果连续排列)", value=False)
        
        st.markdown("**原始数据**")
        st.dataframe(target_df, width="stretch")
        
        # 平均值显示
        if compact_mode:
            display_avg = pd.DataFrame(index=row_labels)
            display_result = pd.DataFrame(index=row_labels)
            for i, (orig, new) in enumerate(zip([2,4,6,8,10], [2,3,4,5,6])):
                display_avg[new] = avg_df[orig]
                display_result[new] = result_df[orig]
        else:
            display_avg = pd.DataFrame(index=row_labels)
            display_result = pd.DataFrame(index=row_labels)
            for c in range(2, 12):
                if c % 2 == 0:
                    display_avg[c] = avg_df[c]
                    display_result[c] = result_df[c]
                else:
                    display_avg[c] = np.nan
                    display_result[c] = np.nan
        
        st.markdown("**平均值**")
        st.dataframe(display_avg, width="stretch")
        st.markdown("**结果 (%)**")
        st.dataframe(display_result, width="stretch")
        
        # --- 5. 下载功能 ---
        st.subheader("下载")
        
        if dilutions:
            dilution_list = [dilutions[i % len(dilutions)] for i in range(num_rows)]
        else:
            dilution_list = [""] * num_rows
        
        rows = []
        rows.append(["病毒对照", virus_control] + [""] * 9)
        rows.append(["样品稀释倍数", "SM5"] + [""] * 9)
        
        for i in range(num_rows):
            rows.append([dilution_list[i]] + target_df.iloc[i].tolist())
        
        rows.append([""] * 11)
        
        # 平均值行
        if compact_mode:
            for i in range(num_rows):
                row = ["平均值"] + [""] * 10
                for j, orig_col in enumerate([2,4,6,8,10]):
                    val = avg_df.iloc[i][orig_col]
                    if pd.notna(val):
                        row[1 + j] = val
                rows.append(row)
        else:
            for i in range(num_rows):
                row = ["平均值"] + [""] * 10
                for orig_col in [2,4,6,8,10]:
                    val = avg_df.iloc[i][orig_col]
                    if pd.notna(val):
                        row[orig_col - 1] = val
                rows.append(row)
        
        rows.append([""] * 11)
        
        # 结果行
        if compact_mode:
            for i in range(num_rows):
                row = ["结果"] + [""] * 10
                for j, orig_col in enumerate([2,4,6,8,10]):
                    val = result_df.iloc[i][orig_col]
                    if pd.notna(val):
                        row[1 + j] = val
                rows.append(row)
        else:
            for i in range(num_rows):
                row = ["结果"] + [""] * 10
                for orig_col in [2,4,6,8,10]:
                    val = result_df.iloc[i][orig_col]
                    if pd.notna(val):
                        row[orig_col - 1] = val
                rows.append(row)
        
        download_df = pd.DataFrame(rows)
        
        csv_buffer = io.StringIO()
        download_df.to_csv(csv_buffer, index=False, header=False)
        st.download_button(
            label="下载为 CSV",
            data=csv_buffer.getvalue(),
            file_name="spot_area_analysis.csv",
            mime="text/csv"
        )
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            download_df.to_excel(writer, index=False, header=False, sheet_name='分析结果')
        st.download_button(
            label="下载为 XLSX",
            data=excel_buffer.getvalue(),
            file_name="spot_area_analysis.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    except Exception as e:
        st.error(f"处理文件时出错: {e}")
else:
    st.info("请上传 Excel 文件以开始分析。")
