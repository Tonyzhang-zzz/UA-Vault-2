import streamlit as st
import pandas as pd
import re
import altair as alt
import io
from openai import OpenAI

# ================= 页面基础设置 =================
st.set_page_config(page_title="Facebook 投放自动化报告", layout="wide", initial_sidebar_state="expanded")

# ================= 🚀 终极无空白页 PDF 打印样式 =================
st.markdown("""
<style>
/* 基础 HTML 表格样式 */
.pdf-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 20px;
    font-family: sans-serif;
    font-size: 14px;
    text-align: left;
}
.pdf-table th {
    background-color: #f0f2f6;
    color: #31333F;
    font-weight: 600;
    padding: 10px 12px;
    border-bottom: 1px solid #e6e6e9;
    white-space: nowrap;
}
.pdf-table td {
    padding: 8px 12px;
    border-bottom: 1px solid #e6e6e9;
    color: #31333F;
}
.pdf-table tr:hover { background-color: #f8f9fa; }

/* 打印环境下的“完美精准切割”魔法 */
@media print {
    section[data-testid="stSidebar"] { display: none !important; }
    header { display: none !important; }
    [data-testid="stDownloadButton"] { display: none !important; }
    .stButton { display: none !important; } 
    
    .block-container {
        max-width: 100% !important;
        width: 100% !important;
        padding: 0 !important;
    }
    
    .pdf-table th, .pdf-table td {
        font-size: 12px; 
        padding: 5px 8px;
    }
    
    /* 💡 终极杀手锏：仅在每个新板块"之前"插入分页符，彻底消灭末尾空白页！ */
    .page-break-separator {
        page-break-before: always !important;
        break-before: page !important;
        display: block;
        width: 100%;
        height: 1px;
        visibility: hidden;
    }
    
    /* 防劈开：保证一个表格或图表不被从中间腰斩 */
    .pdf-table, [data-testid="stVegaLiteChart"] {
        page-break-inside: avoid !important;
    }

    .stTextArea textarea {
        border: none !important;
        background-color: transparent !important;
        color: #000 !important;
        padding: 0 !important;
        font-size: 14px !important;
        resize: none !important;
        overflow: hidden !important;
        page-break-inside: avoid !important;
    }
    
    hr { display: none !important; }
    
    @page { margin: 10mm; size: landscape; }
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Facebook 广告投放自动化报告")

# ================= 1. 侧边栏：上传数据 =================
st.sidebar.header("📁 上传数据源 (支持 CSV/Excel)")
st.sidebar.markdown("请按照对应名称上传数据文件：")

file_types = ['csv', 'xlsx', 'xls']
fb_day_file = st.sidebar.file_uploader("1. FB-每个组的分天", type=file_types)
fb_age_file = st.sidebar.file_uploader("2. FB-每个组的分年龄", type=file_types)
fb_gender_file = st.sidebar.file_uploader("3. FB-每个组的分性别", type=file_types)
fb_placement_file = st.sidebar.file_uploader("4. FB-每个组的分版位", type=file_types)
fb_creative_file = st.sidebar.file_uploader("5. FB-广告组-素材", type=file_types)
dt_day_file = st.sidebar.file_uploader("6. DT-广告组-日期", type=file_types)
dt_creative_file = st.sidebar.file_uploader("7. DT-广告组-素材", type=file_types)

# ================= 💡 侧边栏：AI 智脑配置 =================
st.sidebar.markdown("---")
st.sidebar.header("🤖 AI 自动分析配置")
api_key = st.sidebar.text_input("🔑 API Key", type="password", help="在此输入 DeepSeek API Key")
api_base = st.sidebar.text_input("🌐 Base URL", value="https://api.deepseek.com/v1", help="DeepSeek 官方接口地址")
model_name = st.sidebar.text_input("🧠 模型名称", value="deepseek-chat", help="DeepSeek 模型名称")


# ================= 通用工具函数 =================

@st.cache_data(show_spinner=False)
def load_data(file_uploader):
    if file_uploader is None: return pd.DataFrame()
    
    file_extension = file_uploader.name.split('.')[-1].lower()
    bytes_data = file_uploader.getvalue()
    
    # 1. 优先处理 Excel 格式 (FB 导出的神器)
    if file_extension in ['xls', 'xlsx']:
        try:
            return pd.read_excel(io.BytesIO(bytes_data))
        except Exception as e:
            st.error(f"⚠️ 无法读取 Excel 文件【{file_uploader.name}】。报错: {e}")
            return pd.DataFrame()
            
    # 2. 处理 CSV 格式 (完美兼容 DT 系统导出的数据)
    elif file_extension == 'csv':
        encodings = ['utf-8-sig', 'utf-8', 'gbk', 'gb18030', 'utf-16', 'utf-16le', 'latin1']
        for enc in encodings:
            try:
                df = pd.read_csv(io.BytesIO(bytes_data), encoding=enc)
                if df.shape[1] == 1:
                    df_tab = pd.read_csv(io.BytesIO(bytes_data), encoding=enc, sep='\t')
                    if df_tab.shape[1] > 1: return df_tab
                return df
            except Exception:
                continue
        st.error(f"⚠️ 无法解析文件【{file_uploader.name}】的编码。")
        return pd.DataFrame()
        
    else:
        st.error(f"⚠️ 不支持的文件格式：{file_extension}。")
        return pd.DataFrame()

def standardize_fb_df(df):
    if df.empty: return df
    mapping = {
        'Reporting starts': '日期', '报告开始日期': '日期',
        'Ad set name': '广告组', '广告组名称': '广告组',
        'Ad name': '素材名', '广告名称': '素材名',
        'Amount spent (USD)': '花费', '已花费金额 (USD)': '花费',
        'Impressions': '展示量', '展示次数': '展示量',
        'Clicks (all)': '点击量', '全部点击量': '点击量', '链接点击量': '点击量', '点击量': '点击量', '点击量（全部）': '点击量',
        'Age': '年龄', 'Gender': '性别', 
        'Platform': '平台', 'Placement': '版位'
    }
    df = df.rename(columns=mapping)
    if 'App installs' in df.columns: df = df.rename(columns={'App installs': '安装量'})
    elif '移动应用安装' in df.columns: df = df.rename(columns={'移动应用安装': '安装量'})
    elif '成效' in df.columns: df = df.rename(columns={'成效': '安装量'})
    elif 'Results' in df.columns: df = df.rename(columns={'Results': '安装量'})
    df = df.loc[:, ~df.columns.duplicated()]
    return df

def clean_percentage(val):
    if isinstance(val, str) and '%' in val:
        try: return float(val.replace('%', '')) / 100
        except ValueError: return 0.0
    return val

def clean_date(val):
    if isinstance(val, str):
        match = re.search(r'\d{4}-\d{2}-\d{2}', val)
        if match: return match.group(0)
    return val

def format_custom_table(df, dimensions, metrics):
    if df.empty: return df
    df = df.copy()
    for col in ['展示量', '点击量', '安装量']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    for col in ['花费']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    if '点击量' in df.columns and '展示量' in df.columns:
        df['CTR'] = (df['点击量'] / df['展示量']).replace([float('inf'), -float('inf')], 0).fillna(0)
    if '安装量' in df.columns and '点击量' in df.columns:
        df['CVR'] = (df['安装量'] / df['点击量']).replace([float('inf'), -float('inf')], 0).fillna(0)
    if '花费' in df.columns and '安装量' in df.columns:
        df['CPI'] = df.apply(lambda row: row['花费'] / row['安装量'] if row['安装量'] > 0 else 0.0, axis=1)
        
    # 计算 CPM (花费 / 展示量 * 1000)
    if '花费' in df.columns and '展示量' in df.columns:
        df['CPM'] = df.apply(lambda row: (row['花费'] / row['展示量'] * 1000) if row['展示量'] > 0 else 0.0, axis=1)
        
    if '安装量占比' in metrics and '安装量' in df.columns:
        total = df['安装量'].sum()
        df['安装量占比'] = (df['安装量'] / total).fillna(0) if total > 0 else 0.0
        
    for col in metrics:
        if col not in df.columns: df[col] = "-"
            
    for col in ['花费', 'CPI', 'CPM']:
        if col in df.columns: df[col] = df[col].apply(lambda x: round(float(x), 2) if isinstance(x, (int, float)) else x)
            
    pct_cols = ['CTR', 'CVR', '安装量占比', '次日留存', 'ROI']
    for col in pct_cols:
        if col in df.columns: df[col] = df[col].apply(lambda x: f"{x:.2%}" if pd.notnull(x) and isinstance(x, (int, float)) else x)
            
    final_cols = dimensions + metrics
    return df[[c for c in final_cols if c in df.columns]]

def show_table(df):
    if df.empty: return
    display_df = df.copy()
    for col in ['花费', 'CPI', 'CPM']:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x)
    html = display_df.to_html(index=False, classes='pdf-table', border=0, justify='left')
    st.markdown(html, unsafe_allow_html=True)

# 💡 终极修复：强制排序(Order)和锁定归属(Detail)，彻底解决文字和色块移花接木的错位问题
def draw_pie_chart_with_labels(df, category_col, value_col="安装量"):
    if df.empty or value_col not in df.columns or category_col not in df.columns: return None
    pie_data = df.groupby(category_col, as_index=False)[value_col].sum()
    pie_data = pie_data[pie_data[value_col] > 0]
    if pie_data.empty: return None
    
    total = pie_data[value_col].sum()
    pie_data['percent'] = pie_data[value_col] / total
    pie_data['percent_label'] = pie_data['percent'].apply(lambda x: f"{x:.1%}" if x > 0.03 else "")

    base = alt.Chart(pie_data).encode(
        theta=alt.Theta(f"{value_col}:Q", stack=True),
        order=alt.Order(f"{category_col}:N", sort='ascending')
    )
    
    pie = base.mark_arc(outerRadius=150, innerRadius=60).encode(
        color=alt.Color(f"{category_col}:N", legend=alt.Legend(title=category_col, orient='right')),
        tooltip=[category_col, value_col, alt.Tooltip('percent:Q', format='.1%', title='占比')]
    )
    
    text = base.mark_text(radius=100, size=16, fontStyle='bold', align='center', baseline='middle').encode(
        text='percent_label:N',
        color=alt.value('white'), 
        detail=alt.Detail(f"{category_col}:N")
    )
    
    return (pie + text).properties(height=350)

def draw_dual_axis_chart(chart_data):
    if chart_data.empty: return None
    base = alt.Chart(chart_data).encode(x=alt.X('日期:O', title='', axis=alt.Axis(labelAngle=-45)))
    bar = base.mark_bar(color='#5B9BD5', opacity=0.8, size=25).encode(
        y=alt.Y('花费:Q', title='花费 (USD)', axis=alt.Axis(titleColor='#5B9BD5'))
    )
    if 'ROI' in chart_data.columns and chart_data['ROI'].sum() > 0:
        line = base.mark_line(color='#ED7D31', strokeWidth=3).encode(
            y=alt.Y('ROI:Q', title='ROI', axis=alt.Axis(titleColor='#ED7D31', format='%'))
        )
        points = base.mark_circle(color='#ED7D31', size=70).encode(
            y=alt.Y('ROI:Q'),
            tooltip=[alt.Tooltip('日期:O'), alt.Tooltip('花费:Q'), alt.Tooltip('ROI:Q', format='.2%')]
        )
        return alt.layer(bar, line + points).resolve_scale(y='independent').properties(height=350)
    else:
        return bar.properties(height=350)

def get_ai_insight(df, context):
    try:
        client = OpenAI(api_key=api_key, base_url=api_base, timeout=25.0)
        
        # AI 优化：只取前20条核心数据并转为 Markdown，节约 Token 且防报错
        lean_df = df.head(20) 
        data_str = lean_df.to_markdown(index=False)
        
        prompt = f"""
        你是一位极其专业的 Facebook 广告投放资深优化师。请根据以下【{context}】的数据报表，进行深度分析。
        
        要求严格按照以下 3 段式结构输出（总字数控制在 100-150 字以内，切勿使用客套话，直接输出干货）：
        1. 核心结论：(一句话总结花钱最多、转化最好或最差的核心问题)
        2. 数据分析：(提炼支撑结论的核心数据，如成本CPI、CPM、次日留存、ROI表现等)
        3. 优化洞察：(明确给出具有实操性的下一步动作，如调整某受众预算、关停某素材、扩量等)
        
        待分析数据如下：
        {data_str}
        """
        response = client.chat.completions.create(
            model=model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content
    except Exception as e:
        error_msg = str(e)
        if "insufficient" in error_msg.lower() or "balance" in error_msg.lower() or "402" in error_msg:
            return "⚠️ DeepSeek 提示余额不足，请联系管理员充值。"
        elif "401" in error_msg or "auth" in error_msg.lower():
            return "⚠️ API Key 错误，请检查左侧边栏输入的 Key 是否正确。"
        else:
            return f"⚠️ AI 生成出错: {error_msg}"

# ================= 定义各层级需要的标准指标 =================
FULL_METRICS = ['安装量', 'CPI', '花费', '展示量', '点击量', 'CPM', 'CTR', 'CVR', '次日留存', 'ROI']
AGE_GENDER_METRICS = ['安装量', '花费', 'CPI', '安装量占比']
PLACEMENT_METRICS = ['安装量', 'CPI', '花费', '展示量', '点击量', 'CPM', 'CTR', 'CVR']

# ================= 核心数据全局处理 =================
if fb_day_file and dt_day_file:
    
    fb_day = standardize_fb_df(load_data(fb_day_file))
    dt_day = load_data(dt_day_file)
    fb_age = standardize_fb_df(load_data(fb_age_file))
    fb_gender = standardize_fb_df(load_data(fb_gender_file))
    fb_placement = standardize_fb_df(load_data(fb_placement_file))
    fb_creative = standardize_fb_df(load_data(fb_creative_file))
    dt_creative = load_data(dt_creative_file)
    
    dt_day = dt_day.rename(columns={'次日留存率(%)': '次日留存', '实际ROI(%)': 'ROI'})
    if '广告组' in dt_day.columns:
        dt_day = dt_day[['日期', '广告组', '次日留存', 'ROI']]
        dt_day['日期'] = dt_day['日期'].apply(clean_date)
        dt_day['次日留存'] = dt_day['次日留存'].apply(clean_percentage)
        dt_day['ROI'] = dt_day['ROI'].apply(clean_percentage)

    agg_cols = [c for c in ['花费', '展示量', '点击量', '安装量'] if c in fb_day.columns]
    fb_summary = fb_day.groupby('广告组', as_index=False)[agg_cols].sum()
    dt_summary = dt_day.groupby('广告组', as_index=False)[['次日留存', 'ROI']].mean() if '广告组' in dt_day.columns else pd.DataFrame()
    final_summary = pd.merge(fb_summary, dt_summary, on='广告组', how='left') if not dt_summary.empty else fb_summary
    
    total_data = {'广告组': '🔥 合计 (Total)'}
    for col in agg_cols: total_data[col] = final_summary[col].sum()
    if '次日留存' in final_summary.columns: total_data['次日留存'] = final_summary['次日留存'].mean()
    if 'ROI' in final_summary.columns: total_data['ROI'] = final_summary['ROI'].mean()
    final_summary = pd.concat([final_summary, pd.DataFrame([total_data])], ignore_index=True)
    
    daily_merged = pd.merge(fb_day, dt_day, on=['日期', '广告组'], how='left')

    creative_merged = pd.DataFrame()
    if not fb_creative.empty and not dt_creative.empty:
        agg_c_cols = [c for c in ['花费', '展示量', '点击量', '安装量'] if c in fb_creative.columns]
        fb_c_agg = fb_creative.groupby(['广告组', '素材名'], as_index=False)[agg_c_cols].sum()
        dt_creative = dt_creative.rename(columns={'广告': '素材名', '次日留存率(%)': '次日留存', '实际ROI(%)': 'ROI'})
        dt_c_cols = ['素材名', '次日留存', 'ROI']
        if '广告组' in dt_creative.columns: dt_c_cols.insert(0, '广告组')
        dt_c_cols = [c for c in dt_c_cols if c in dt_creative.columns]
        dt_creative = dt_creative[dt_c_cols]
        if '次日留存' in dt_creative.columns: dt_creative['次日留存'] = dt_creative['次日留存'].apply(clean_percentage)
        if 'ROI' in dt_creative.columns: dt_creative['ROI'] = dt_creative['ROI'].apply(clean_percentage)
        merge_keys = ['广告组', '素材名'] if '广告组' in dt_creative.columns else ['素材名']
        creative_merged = pd.merge(fb_c_agg, dt_creative, on=merge_keys, how='left')

    st.success("✅ 数据已读取！请确认左侧边栏已填写 API Key，然后点击下方按钮获取深度分析。")
    generate_all = st.button("🧠 一键获取 AI 深度分析报告", type="primary", use_container_width=True)
    if generate_all:
        if not api_key:
            st.error("⚠️ 请先在左侧边栏填入 API Key！")
            st.stop()
        else:
            st.session_state["trigger_ai"] = True

    is_trigger_ai = st.session_state.get("trigger_ai", False)

    # 封装一个专门负责“新起一页并打印带背景标题”的魔法函数
    def render_module_header(title):
        st.markdown('<div class="page-break-separator"></div>', unsafe_allow_html=True)
        st.markdown(f"""
        <div style="background-color:#f0f2f6; padding:12px; border-radius:8px; margin-bottom:15px;">
        <h3 style="color:#1f77b4; margin:0;">{title}</h3>
        </div>
        """, unsafe_allow_html=True)

    # ================= 模块一：全局汇总 (第一页，不需要分页符) =================
    st.header("🏆 一、各广告组全局汇总")
    df_summary_show = format_custom_table(final_summary, ['广告组'], FULL_METRICS)
    show_table(df_summary_show)
    
    if "input_summary" not in st.session_state: st.session_state["input_summary"] = ""
    if is_trigger_ai:
        with st.spinner("🤖 AI 正在诊断大盘表现..."):
            st.session_state["input_summary"] = get_ai_insight(df_summary_show, "各广告组大盘汇总对比")
    st.text_area("✍️ 大盘表现与优化建议（支持人工修改）：", key="input_summary", height=130)
    
    # ================= 模块二：循环展示各组明细 =================
    all_adsets = [a for a in sorted(fb_day['广告组'].dropna().unique().tolist()) if a != '🔥 合计 (Total)']
    
    for adset in all_adsets:
        # 1. 分天数据 (新起一页)
        if not daily_merged.empty:
            adset_daily = daily_merged[daily_merged['广告组'] == adset]
            if not adset_daily.empty:
                render_module_header(f"🔹 广告组：【{adset}】 - 📅 分天数据与趋势")
                
                chart_data = adset_daily.copy()
                dual_chart = draw_dual_axis_chart(chart_data)
                if dual_chart: st.altair_chart(dual_chart, use_container_width=True)
                
                df_daily_show = format_custom_table(adset_daily.sort_values('日期', ascending=False), ['日期'], FULL_METRICS)
                show_table(df_daily_show)
                
                key_daily = f"input_daily_{adset}"
                if key_daily not in st.session_state: st.session_state[key_daily] = ""
                if is_trigger_ai:
                    with st.spinner(f"🤖 AI 正在分析【{adset}】表现趋势..."):
                        st.session_state[key_daily] = get_ai_insight(df_daily_show.head(7), f"{adset}的最近7天分天表现趋势")
                st.text_area(f"✍️ 【{adset}】分天趋势洞察：", key=key_daily, height=130)

        # 2. 受众画像 (新起一页，上下排布不再重叠)
        adset_age = fb_age[fb_age['广告组'] == adset] if not fb_age.empty else pd.DataFrame()
        adset_gender = fb_gender[fb_gender['广告组'] == adset] if not fb_gender.empty else pd.DataFrame()
        
        if not adset_age.empty or not adset_gender.empty:
            render_module_header(f"🔹 广告组：【{adset}】 - 👥 受众画像分析")
            df_audience_feed = pd.DataFrame()
            
            if not adset_age.empty:
                st.markdown("##### 🟢 分年龄占比分布")
                pie_age = draw_pie_chart_with_labels(adset_age, '年龄', '安装量')
                if pie_age: st.altair_chart(pie_age, use_container_width=True)
                df_age_show = format_custom_table(adset_age, ['年龄'], AGE_GENDER_METRICS)
                show_table(df_age_show)
                df_audience_feed = pd.concat([df_audience_feed, df_age_show])

            if not adset_gender.empty:
                st.markdown("##### 🟣 分性别占比分布")
                pie_gender = draw_pie_chart_with_labels(adset_gender, '性别', '安装量')
                if pie_gender: st.altair_chart(pie_gender, use_container_width=True)
                df_gender_show = format_custom_table(adset_gender, ['性别'], AGE_GENDER_METRICS)
                show_table(df_gender_show)
                df_audience_feed = pd.concat([df_audience_feed, df_gender_show])
        
            key_aud = f"input_aud_{adset}"
            if key_aud not in st.session_state: st.session_state[key_aud] = ""
            if is_trigger_ai:
                with st.spinner(f"🤖 AI 正在提炼【{adset}】受众结构..."):
                    st.session_state[key_aud] = get_ai_insight(df_audience_feed, f"{adset}的受众画像(年龄和性别)")
            st.text_area(f"✍️ 【{adset}】受众画像洞察：", key=key_aud, height=130)

        # 3. 版位表现 (新起一页)
        if not fb_placement.empty:
            adset_placement = fb_placement[fb_placement['广告组'] == adset]
            if not adset_placement.empty:
                render_module_header(f"🔹 广告组：【{adset}】 - 📱 各版位效率表现")
                df_placement_show = format_custom_table(adset_placement, ['平台', '版位'], PLACEMENT_METRICS)
                show_table(df_placement_show)
                
                key_pla = f"input_pla_{adset}"
                if key_pla not in st.session_state: st.session_state[key_pla] = ""
                if is_trigger_ai:
                    with st.spinner(f"🤖 AI 正在诊断【{adset}】版位效率..."):
                        st.session_state[key_pla] = get_ai_insight(df_placement_show.sort_values(by='花费', ascending=False).head(5), f"{adset}的花费Top5版位表现")
                st.text_area(f"✍️ 【{adset}】版位表现洞察：", key=key_pla, height=130)

        # 4. 素材数据 (新起一页)
        if not creative_merged.empty:
            adset_creative = creative_merged[creative_merged['广告组'] == adset]
            if not adset_creative.empty:
                render_module_header(f"🔹 广告组：【{adset}】 - 🖼️ 素材核心打通数据")
                adset_creative = adset_creative.sort_values(by='花费', ascending=False)
                df_creative_show = format_custom_table(adset_creative, ['素材名'], FULL_METRICS)
                show_table(df_creative_show)
                
                key_cre = f"input_cre_{adset}"
                if key_cre not in st.session_state: st.session_state[key_cre] = ""
                if is_trigger_ai:
                    with st.spinner(f"🤖 AI 正在总结【{adset}】头部素材特性..."):
                        st.session_state[key_cre] = get_ai_insight(df_creative_show.head(5), f"{adset}的花费Top5头部素材优劣势(结合ROI和留存)")
                st.text_area(f"✍️ 【{adset}】素材跑量与回本洞察：", key=key_cre, height=130)

    if is_trigger_ai:
        st.session_state["trigger_ai"] = False

else:
    st.info("👋 欢迎使用！将需要分析的数据表格(支持CSV或Excel)拖拽至左侧，系统将生成图文报告。")