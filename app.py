import streamlit as st
import pandas as pd
import re
import altair as alt
import io

# ================= 页面基础设置 =================
st.set_page_config(page_title="Facebook 投放自动化报告", layout="wide", initial_sidebar_state="expanded")

# ================= 🚀 专属 PDF 打印与 HTML 表格样式 =================
st.markdown("""
<style>
/* 专为 PDF 和完美排版设计的 HTML 表格样式 */
.pdf-table {
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 25px;
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

/* 打印时的魔法：隐藏边栏、按钮，强行拉宽页面防止错位 */
@media print {
    section[data-testid="stSidebar"] { display: none !important; }
    header { display: none !important; }
    [data-testid="stDownloadButton"] { display: none !important; }
    .block-container {
        max-width: 100% !important;
        width: 100% !important;
        padding: 0 !important;
    }
    .pdf-table th, .pdf-table td {
        font-size: 12px; 
        padding: 5px 8px;
    }
    @page { margin: 10mm; size: landscape; }
}
</style>
""", unsafe_allow_html=True)

st.title("📊 Facebook 广告投放自动化报告")

# ================= 1. 侧边栏：上传数据 =================
st.sidebar.header("📁 上传数据源")
st.sidebar.markdown("请按照对应名称上传 CSV 文件：")
fb_day_file = st.sidebar.file_uploader("1. FB-每个组的分天.csv", type=['csv'])
fb_age_file = st.sidebar.file_uploader("2. FB-每个组的分年龄.csv", type=['csv'])
fb_gender_file = st.sidebar.file_uploader("3. FB-每个组的分性别.csv", type=['csv'])
fb_placement_file = st.sidebar.file_uploader("4. FB-每个组的分版位.csv", type=['csv'])
fb_creative_file = st.sidebar.file_uploader("5. FB-广告组-素材.csv", type=['csv'])
dt_day_file = st.sidebar.file_uploader("6. DT-广告组-日期.csv", type=['csv'])
dt_creative_file = st.sidebar.file_uploader("7. DT-广告组-素材.csv", type=['csv'])


# ================= 通用工具函数 =================
def load_data(file_uploader):
    if file_uploader is None: return pd.DataFrame()
    file_uploader.seek(0)
    try: return pd.read_csv(file_uploader, encoding='utf-8-sig')
    except UnicodeDecodeError:
        file_uploader.seek(0)
        return pd.read_csv(file_uploader, encoding='gbk')

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

# 💡 核心：强力定制化排版引擎
def format_custom_table(df, dimensions, metrics):
    """能够按需定制所有列表的呈现逻辑，不需要的列绝对不显示，缺少的列自动补齐"""
    if df.empty: return df
    df = df.copy()
    
    # 💡 强力格式化：区分整数和小数
    for col in ['展示量', '点击量', '安装量']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int) # 剥离毫无意义的 .0
            
    for col in ['花费']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
            
    # 计算衍生转化指标
    if '点击量' in df.columns and '展示量' in df.columns:
        df['CTR'] = (df['点击量'] / df['展示量']).replace([float('inf'), -float('inf')], 0).fillna(0)
    if '安装量' in df.columns and '点击量' in df.columns:
        df['CVR'] = (df['安装量'] / df['点击量']).replace([float('inf'), -float('inf')], 0).fillna(0)
    if '花费' in df.columns and '安装量' in df.columns:
        df['CPI'] = df.apply(lambda row: row['花费'] / row['安装量'] if row['安装量'] > 0 else 0.0, axis=1)
        
    # 如果指定了“安装量占比”
    if '安装量占比' in metrics and '安装量' in df.columns:
        total = df['安装量'].sum()
        df['安装量占比'] = (df['安装量'] / total).fillna(0) if total > 0 else 0.0
        
    # 补齐未出现的指定列为空值 "-"
    for col in metrics:
        if col not in df.columns:
            df[col] = "-"
            
    # 💡 强力格式化：保留所有浮点数为 2位小数 (在 Excel 中维持为真正的数字类型)
    for col in ['花费', 'CPI']:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: round(float(x), 2) if isinstance(x, (int, float)) else x)
            
    # 格式化百分比
    pct_cols = ['CTR', 'CVR', '安装量占比', '次日留存', 'ROI']
    for col in pct_cols:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: f"{x:.2%}" if pd.notnull(x) and isinstance(x, (int, float)) else x)
            
    # 严格按照“维度 + 指定核心指标”顺序筛选
    final_cols = dimensions + metrics
    return df[[c for c in final_cols if c in df.columns]]

# 💡 核心：HTML 表格呈现器 (完美抹除索引，小数自动补全 .00)
def show_table(df):
    if df.empty: return
    display_df = df.copy()
    
    # 为了 HTML 网页展示完美对齐，强制把类似 "5.0" 转化为 "5.00" 字符串形式展示
    for col in ['花费', 'CPI']:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(lambda x: f"{x:.2f}" if isinstance(x, (int, float)) else x)
            
    html = display_df.to_html(index=False, classes='pdf-table', border=0, justify='left')
    st.markdown(html, unsafe_allow_html=True)

# 🎨 饼图直显百分比
def draw_pie_chart_with_labels(df, category_col, value_col="安装量"):
    if df.empty or value_col not in df.columns or category_col not in df.columns: return None
    pie_data = df.groupby(category_col, as_index=False)[value_col].sum()
    pie_data = pie_data[pie_data[value_col] > 0]
    if pie_data.empty: return None
    
    total = pie_data[value_col].sum()
    pie_data['percent'] = pie_data[value_col] / total
    # 占比 > 3% 的才显示文本防重叠
    pie_data['percent_label'] = pie_data['percent'].apply(lambda x: f"{x:.1%}" if x > 0.03 else "")

    base = alt.Chart(pie_data).encode(
        theta=alt.Theta(f"{value_col}:Q", stack=True)
    )
    
    pie = base.mark_arc(outerRadius=120, innerRadius=50).encode(
        color=alt.Color(f"{category_col}:N", legend=alt.Legend(title=category_col, orient='right')),
        tooltip=[category_col, value_col, alt.Tooltip('percent:Q', format='.1%', title='占比')]
    )
    
    text = base.mark_text(radius=85, size=14, color='white', fontStyle='bold', align='center', baseline='middle').encode(
        text='percent_label:N'
    )
    return (pie + text).properties(height=300)

# 📈 花费与 ROI 双轴合并图
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


# ================= 定义各层级需要的标准指标 =================
FULL_METRICS = ['安装量', 'CPI', '花费', '展示量', '点击量', 'CTR', 'CVR', '次日留存', 'ROI']
AGE_GENDER_METRICS = ['安装量', '花费', 'CPI', '安装量占比']
PLACEMENT_METRICS = ['安装量', 'CPI', '花费', '展示量', '点击量', 'CTR', 'CVR']

# ================= 核心数据全局处理 =================
if fb_day_file and dt_day_file:
    
    # --- 1. 读取基础数据 ---
    fb_day = standardize_fb_df(load_data(fb_day_file))
    dt_day = load_data(dt_day_file)
    fb_age = standardize_fb_df(load_data(fb_age_file))
    fb_gender = standardize_fb_df(load_data(fb_gender_file))
    fb_placement = standardize_fb_df(load_data(fb_placement_file))
    fb_creative = standardize_fb_df(load_data(fb_creative_file))
    dt_creative = load_data(dt_creative_file)
    
    # DT 日期清洗
    dt_day = dt_day.rename(columns={'次日留存率(%)': '次日留存', '实际ROI(%)': 'ROI'})
    if '广告组' in dt_day.columns:
        dt_day = dt_day[['日期', '广告组', '次日留存', 'ROI']]
        dt_day['日期'] = dt_day['日期'].apply(clean_date)
        dt_day['次日留存'] = dt_day['次日留存'].apply(clean_percentage)
        dt_day['ROI'] = dt_day['ROI'].apply(clean_percentage)

    # ================= 数据加工厂 =================
    # 1. 汇总数据
    agg_cols = [c for c in ['花费', '展示量', '点击量', '安装量'] if c in fb_day.columns]
    fb_summary = fb_day.groupby('广告组', as_index=False)[agg_cols].sum()
    dt_summary = dt_day.groupby('广告组', as_index=False)[['次日留存', 'ROI']].mean() if '广告组' in dt_day.columns else pd.DataFrame()
    final_summary = pd.merge(fb_summary, dt_summary, on='广告组', how='left') if not dt_summary.empty else fb_summary
    
    total_data = {'广告组': '🔥 合计 (Total)'}
    for col in agg_cols: total_data[col] = final_summary[col].sum()
    if '次日留存' in final_summary.columns: total_data['次日留存'] = final_summary['次日留存'].mean()
    if 'ROI' in final_summary.columns: total_data['ROI'] = final_summary['ROI'].mean()
    final_summary = pd.concat([final_summary, pd.DataFrame([total_data])], ignore_index=True)
    
    # 2. 分天数据
    daily_merged = pd.merge(fb_day, dt_day, on=['日期', '广告组'], how='left')

    # 3. 分素材数据打通
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


    # ================= 顶部：一键生成 Excel =================
    st.success("✅ 数据处理完毕！完美对齐版报表生成。导出 PDF 请按 `Ctrl + P` 并选择『横向』布局。")
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        format_custom_table(final_summary, ['广告组'], FULL_METRICS).to_excel(writer, sheet_name='1.各组汇总', index=False)
        if not daily_merged.empty: format_custom_table(daily_merged, ['日期', '广告组'], FULL_METRICS).to_excel(writer, sheet_name='2.分天明细', index=False)
        if not fb_age.empty: format_custom_table(fb_age, ['年龄', '广告组'], AGE_GENDER_METRICS).to_excel(writer, sheet_name='3.分年龄', index=False)
        if not fb_gender.empty: format_custom_table(fb_gender, ['性别', '广告组'], AGE_GENDER_METRICS).to_excel(writer, sheet_name='4.分性别', index=False)
        if not fb_placement.empty: format_custom_table(fb_placement, ['平台', '版位', '广告组'], PLACEMENT_METRICS).to_excel(writer, sheet_name='5.分版位', index=False)
        if not creative_merged.empty: format_custom_table(creative_merged, ['广告组', '素材名'], FULL_METRICS).to_excel(writer, sheet_name='6.分素材', index=False)
    
    st.download_button(
        label="📥 一键下载完整数据报表 (多Sheet Excel)", data=buffer.getvalue(),
        file_name="Facebook_全维度自动化报表.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True
    )
    st.markdown("---")


    # ================= 瀑布流页面展示 =================
    
    # 模块一：全局汇总
    st.header("🏆 一、各广告组全局汇总")
    show_table(format_custom_table(final_summary, ['广告组'], FULL_METRICS))
    st.markdown("<br><br>", unsafe_allow_html=True)
    
    # 模块二：循环展示各组明细
    st.header("📂 二、各广告组明细数据剖析")
    all_adsets = [a for a in sorted(fb_day['广告组'].dropna().unique().tolist()) if a != '🔥 合计 (Total)']
    
    for adset in all_adsets:
        st.markdown(f"""
        <div style="background-color:#f0f2f6; padding:10px; border-radius:10px; margin-top:20px; margin-bottom:10px;">
        <h3 style="color:#1f77b4; margin:0;">🔹 广告组：【{adset}】 专属报告</h3>
        </div>
        """, unsafe_allow_html=True)
        
        # 1. 分天数据
        if not daily_merged.empty:
            st.markdown("#### 📅 1. 分天数据与趋势")
            adset_daily = daily_merged[daily_merged['广告组'] == adset]
            if not adset_daily.empty:
                chart_data = adset_daily.copy()
                dual_chart = draw_dual_axis_chart(chart_data)
                if dual_chart: st.altair_chart(dual_chart, use_container_width=True)
                show_table(format_custom_table(adset_daily.sort_values('日期', ascending=False), ['日期'], FULL_METRICS))

        # 2. 受众画像
        st.markdown("#### 👥 2. 受众画像 (分年龄 & 分性别)")
        col_age, col_gender = st.columns(2)
        
        with col_age:
            if not fb_age.empty:
                adset_age = fb_age[fb_age['广告组'] == adset]
                if not adset_age.empty:
                    st.caption("🟢 分年龄占比分布")
                    pie_age = draw_pie_chart_with_labels(adset_age, '年龄', '安装量')
                    if pie_age: st.altair_chart(pie_age, use_container_width=True)
                    show_table(format_custom_table(adset_age, ['年龄'], AGE_GENDER_METRICS))

        with col_gender:
            if not fb_gender.empty:
                adset_gender = fb_gender[fb_gender['广告组'] == adset]
                if not adset_gender.empty:
                    st.caption("🟣 分性别占比分布")
                    pie_gender = draw_pie_chart_with_labels(adset_gender, '性别', '安装量')
                    if pie_gender: st.altair_chart(pie_gender, use_container_width=True)
                    show_table(format_custom_table(adset_gender, ['性别'], AGE_GENDER_METRICS))

        # 3. 版位
        if not fb_placement.empty:
            st.markdown("#### 📱 3. 分版位表现")
            adset_placement = fb_placement[fb_placement['广告组'] == adset]
            if not adset_placement.empty:
                show_table(format_custom_table(adset_placement, ['平台', '版位'], PLACEMENT_METRICS))

        # 4. 素材
        if not creative_merged.empty:
            st.markdown("#### 🖼️ 4. 分素材核心数据打通")
            adset_creative = creative_merged[creative_merged['广告组'] == adset]
            if not adset_creative.empty:
                adset_creative = adset_creative.sort_values(by='花费', ascending=False)
                show_table(format_custom_table(adset_creative, ['素材名'], FULL_METRICS))

        st.markdown("<br><hr><br>", unsafe_allow_html=True) # 巨大分割线

else:
    st.info("👋 欢迎使用！请在左侧边栏上传数据源，见证奇迹！")