import streamlit as st

# ========== 多页面导航入口 ==========

st.set_page_config(page_title="生物信息学工具箱", layout="wide")

# 页面导航配置 - 使用列表形式兼容旧版本 Streamlit
page_table = st.Page("pages/1_表格处理.py", title="📊 表格处理")
page_table2 = st.Page("pages/7_斑点面积分析.py",title="📊 斑点面积分析")
page_codon = st.Page("pages/2_密码子优化.py", title="🔬 密码子优化")
page_ab1 = st.Page("pages/3_AB1测序分析.py", title="🔬 AB1测序分析")
page_properties = st.Page("pages/4_蛋白性质计算.py", title="🔬 蛋白性质计算")
page_gel = st.Page("pages/5_胶图标注_手动.py", title="🧬 胶图手动标注") 
page_gel_auto = st.Page("pages/5_胶图标注_自动.py", title="🧬 胶图自动标注")


pg = st.navigation([
    page_table,
    page_table2,
    page_codon, 
    page_ab1, 
    page_properties,
    page_gel,
    page_gel_auto
])
pg.run()
