import streamlit as st
import pandas as pd
import platform
import io
import warnings
import zipfile
import xml.etree.ElementTree as ET
import re

# 경고 메시지 무시
warnings.simplefilter("ignore")

# -----------------------------------------------------------
# 0. 공통 설정
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V18.35 Ultimate", layout="wide")

@st.cache_resource
def set_korean_font():
    system_name = platform.system()
    if system_name == 'Windows':
        font_path = "C:/Windows/Fonts/malgun.ttf"
        font_name = "Malgun Gothic"
    elif system_name == 'Darwin':
        font_path = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
        font_name = "AppleGothic"
    else:
        font_path = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
        font_name = "NanumGothic"

set_korean_font()

# -----------------------------------------------------------
# 1. 유틸리티 및 데이터 처리 함수 (기존 로직 유지)
# -----------------------------------------------------------
def clean_currency(x):
    if pd.isna(x) or x == '': return 0.0
    if isinstance(x, (int, float)): return float(x)
    if isinstance(x, str):
        try: return float(x.replace(',', '').replace('"', '').replace("'", "").strip())
        except: return 0.0
    return 0.0

def classify_product(campaign_name):
    if pd.isna(campaign_name): return '상품'
    name = str(campaign_name)
    return '보장분석' if '보장' in name or '누적' in name else '상품'

def get_media_from_plab(row):
    account = str(row.get('account', '')).upper()
    gubun = str(row.get('구분', '')).upper()
    if 'DDN' in account: return '카카오'
    if 'GDN' in account: return '구글'
    targets = ['네이버', '카카오', '토스', '구글', 'NAVER', 'KAKAO', 'TOSS', 'GOOGLE']
    media_map = {'NAVER': '네이버', 'KAKAO': '카카오', 'TOSS': '토스', 'GOOGLE': '구글'}
    for t in targets:
        if t in account: return media_map.get(t, t)
    for t in targets:
        if t in gubun: return media_map.get(t, t)
    return '기타'

def load_excel_xml_fallback(file):
    try:
        file.seek(0)
        z = zipfile.ZipFile(file)
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                root = ET.parse(f).getroot()
                ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in root.findall('ns:si', ns):
                    t = si.find('ns:t', ns)
                    if t is not None and t.text: strings.append(t.text)
                    else:
                        text_parts = [rt.text for rt in si.findall('ns:r/ns:t', ns) if rt.text]
                        strings.append("".join(text_parts))
        
        sheet_path = 'xl/worksheets/sheet1.xml'
        if sheet_path not in z.namelist():
            sheets = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]
            if sheets: sheet_path = sheets[0]
            else: return None

        with z.open(sheet_path) as f:
            root = ET.parse(f).getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            data = []
            for row in root.findall('ns:sheetData/ns:row', ns):
                row_data = []
                for c in row.findall('ns:c', ns):
                    t, v_tag = c.get('t'), c.find('ns:v', ns)
                    val = v_tag.text if v_tag is not None else None
                    if t == 's' and val is not None:
                        try: val = strings[int(val)]
                        except: val = ""
                    row_data.append(val)
                data.append(row_data)
        return pd.DataFrame(data[1:], columns=data[0]) if data else None
    except: return None

def load_file_by_rule(file):
    name = file.name
    file.seek(0)
    if name.endswith(('.xlsx', '.xls')):
        if '메리츠 화재' in name:
            try: return pd.read_excel(file, engine='openpyxl', header=3)
            except: pass
        try: return pd.read_excel(file, engine='openpyxl')
        except:
            df_force = load_excel_xml_fallback(file)
            if df_force is not None: return df_force
    
    encodings = ['utf-8', 'cp949', 'utf-16']
    for enc in encodings:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc, sep=None, engine='python', on_bad_lines='skip')
            if len(df.columns) > 1: return df
        except: continue
    return None

def process_marketing_data(uploaded_files):
    dfs = []
    toss_files = []
    for file in uploaded_files:
        df = load_file_by_rule(file)
        if df is None: continue
        df.columns = df.columns.astype(str).str.strip()
        fname = file.name
        try:
            if 'result' in fname: # 네이버
                df['Cost'] = df['총 비용'].apply(clean_currency)
                df['상품'] = df['캠페인 이름'].apply(classify_product)
                df['매체'] = '네이버'
                dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))
            elif '메리츠화재다이렉트' in fname: # 카카오
                df['Cost'] = df['비용'].apply(clean_currency) * 1.1
                df['상품'] = df['캠페인'].apply(classify_product)
                df['매체'] = '카카오'
                dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))
            elif '메리츠 화재' in fname: toss_files.append((fname, df))
            elif '캠페인 보고서' in fname: # 구글
                df = df[df['캠페인'].notna()]
                df['Cost'] = df['비용'].apply(clean_currency) * 1.1 * 1.15
                df['상품'] = df['캠페인'].apply(classify_product)
                df['매체'] = '구글'
                dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))
            elif 'Performance Lab' in fname: # 피랩
                send_col = next((c for c in df.columns if 'METIS전송' in c and '율' not in c), None)
                fail_col = next((c for c in df.columns if 'METIS실패' in c), None)
                re_col = next((c for c in df.columns if 'METIS재인입' in c), None)
                if send_col:
                    s = df[send_col].apply(clean_currency)
                    f = df[fail_col].apply(clean_currency) if fail_col else 0
                    r = df[re_col].apply(clean_currency) if re_col else 0
                    df['보장'] = s - f - r
                else: df['보장'] = 0
                df['매체'] = df.apply(get_media_from_plab, axis=1)
                df['상품'] = df['구분'].apply(classify_product)
                dfs.append(df.groupby(['매체', '상품'])['보장'].sum().reset_index().assign(Cost=0))
        except: continue

    if toss_files:
        for fn, df in toss_files:
            if '소진 비용' in df.columns or '캠페인 명' in df.columns:
                df['Cost'] = df['소진 비용'].apply(clean_currency) * 1.1
                df['상품'] = df['캠페인 명'].apply(classify_product)
                df['매체'] = '토스'
                dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))

    if not dfs: return None
    final = pd.concat(dfs, ignore_index=True).groupby(['매체', '상품']).sum().reset_index()
    final['CPA'] = final.apply(lambda x: x['Cost'] / x['보장'] if x['보장'] > 0 else 0, axis=1)
    return final

def convert_to_stats(final_df, manual_aff_cnt, manual_aff_cost, manual_da_cnt, manual_da_cost):
    media_list = ['네이버', '카카오', '토스', '구글', '제휴', '기타']
    stats = pd.DataFrame(index=media_list, columns=['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'Total_Cnt', 'CPA']).fillna(0)
    if final_df is not None:
        for _, row in final_df.iterrows():
            m = row['매체'] if row['매체'] in stats.index else '기타'
            stats.loc[m, 'Cost'] += row['Cost']
            if row['상품'] == '보장분석': stats.loc[m, 'Bojang_Cnt'] += row['보장']
            else: stats.loc[m, 'Prod_Cnt'] += row['보장']
    
    stats.loc['기타', 'Prod_Cnt'] += manual_da_cnt
    stats.loc['기타', 'Cost'] += manual_da_cost
    stats.loc['제휴', 'Bojang_Cnt'] = manual_aff_cnt
    stats.loc['제휴', 'Cost'] = manual_aff_cost
    stats['Total_Cnt'] = stats['Bojang_Cnt'] + stats['Prod_Cnt']
    stats['CPA'] = stats.apply(lambda x: x['Cost'] / x['Total_Cnt'] if x['Total_Cnt'] > 0 else 0, axis=1)
    
    return {
        'da_cost': int(stats.drop('제휴')['Cost'].sum()),
        'da_cnt': int(stats.drop('제휴')['Total_Cnt'].sum()),
        'aff_cost': int(stats.loc['제휴', 'Cost']),
        'aff_cnt': int(stats.loc['제휴', 'Total_Cnt']),
        'bojang_cnt': int(stats['Bojang_Cnt'].sum()),
        'prod_cnt': int(stats['Prod_Cnt'].sum()),
        'total_cnt': int(stats['Total_Cnt'].sum()),
        'total_cost': int(stats['Cost'].sum()),
        'media_stats': stats
    }

# -----------------------------------------------------------
# MODE: V18.35 Master
# -----------------------------------------------------------
def run_v18_35_master():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.35 Ultimate)")
    st.markdown("🚀 **10시 시작 자원 포함 실시간 실적 집계 모드**")

    with st.sidebar:
        st.header("1. 기본 설정")
        current_time_str = st.select_slider("⏱️ 현재 기준", options=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"], value="14:00")
        day_option = st.selectbox("요일", ['월', '화', '수', '목', '금'], index=0)
        is_boosting = st.checkbox("🔥 긴급 부스팅", value=False) if current_time_str in ["16:00", "17:00"] else False
        
        st.header("2. 목표 수립")
        active_member = st.number_input("활동 인원", value=359)
        c1, c2 = st.columns(2)
        with c1: target_bojang = st.number_input("보장 목표", value=500)
        with c2: target_product = st.number_input("상품 목표", value=3100)
        c3, c4 = st.columns(2)
        with c3: sa_est_bojang = st.number_input("SA 보장", value=200)
        with c4: sa_est_prod = st.number_input("SA 상품", value=800)
        da_add_target = st.number_input("DA 버퍼", value=50)

        da_target_bojang = target_bojang - sa_est_bojang
        da_target_prod = target_product - sa_est_prod + da_add_target
        da_target_18 = da_target_bojang + da_target_prod
        target_ratio_ba = da_target_bojang / da_target_18 if da_target_18 > 0 else 0.898
        
        st.header("3. 자원 설정")
        start_resource_10 = st.number_input("☀️ 10시 시작 자원 (고정)", value=1100)
        uploaded_realtime = st.file_uploader("📂 실시간 피랩/매체 데이터", accept_multiple_files=True)
        
        st.header("4. 수기 및 제휴")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_da_cnt = st.number_input("DA 추가 건", value=0)
            manual_da_cost = st.number_input("DA 추가 액", value=0)
        with col_m2:
            manual_aff_cost = st.number_input("제휴 소진액", value=11270000)
            manual_aff_cpa = st.number_input("제휴 단가", value=14000)
            manual_aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0

        st.header("5. 보고 설정")
        tom_member = st.number_input("명일 인원", value=350)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 데이터 계산 엔진 ---
    final_df = process_marketing_data(uploaded_realtime) if uploaded_realtime else None
    res = convert_to_stats(final_df, manual_aff_cnt, manual_aff_cost, manual_da_cnt, manual_da_cost)
    
    # [핵심 로직 변경] 현재 실적 = 10시 시작 자원 + 실시간 데이터(피랩/수기)
    current_total = start_resource_10 + res['total_cnt']
    # 보장/상품 비중은 타겟 비율에 맞춰 10시 자원을 안분함
    current_bojang = int(start_resource_10 * target_ratio_ba) + res['bojang_cnt']
    current_prod = current_total - current_bojang
    
    # 예측 멀티플라이어 계산
    base_mul_14 = 1.15 if day_option == '월' else (1.215 if fixed_ad_type != "없음" else 1.35)
    time_multipliers = {
        "09:30": 1.0, "10:00": 1.75, "11:00": 1.65, "12:00": 1.55, "13:00": 1.45,
        "14:00": base_mul_14, "15:00": (base_mul_14 + 1.10)/2, "16:00": 1.10 if not is_boosting else 1.25,
        "17:00": 1.05, "18:00": 1.0
    }
    current_mul = time_multipliers.get(current_time_str, 1.2)
    est_final_live = int(current_total * current_mul)
    
    # CPA 계산
    cpa_da = (res['da_cost'] / (current_total - manual_aff_cnt) / 10000) if (current_total - manual_aff_cnt) > 0 else 0
    cpa_total = (res['total_cost'] / current_total / 10000) if current_total > 0 else 0

    # --- 탭 구성 ---
    tab0, tab1, tab2, tab3 = st.tabs(["📊 실시간 대시보드", "🔥 중간 보고", "⚠️ 마감/퇴근", "📋 상세 데이터"])

    with tab0:
        st.subheader(f"📊 {current_time_str} 자원 현황 (10시 자원 포함)")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("최종 목표", f"{da_target_18:,}건", f"보장 {da_target_bojang:,}")
        with c2: st.metric("현재 실적", f"{current_total:,}건", f"달성률 {min(100.0, current_total/da_target_18*100):.1f}%")
        with c3: st.metric("마감 예상", f"{est_final_live:,}건", f"Gap {est_final_live - da_target_18:,}")
        with c4: st.metric("가망 CPA", f"{cpa_total:.1f}만원", f"DA {cpa_da:.1f}")

        st.progress(min(1.0, current_total/da_target_18))
        
        # 차트 및 테이블
        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.markdown("##### 📌 실시간 구성")
            st.write(f"- 10시 고정 자원: **{start_resource_10:,}** 건")
            st.write(f"- 실시간 유입(피랩/제휴): **{res['total_cnt']:,}** 건")
            st.write(f"- 현재 보장분석: **{current_bojang:,}** 건")
            st.write(f"- 현재 상품자원: **{current_prod:,}** 건")
        with col_d2:
            st.markdown("##### 📌 매체 요약")
            st.dataframe(res['media_stats'][['Total_Cnt', 'CPA']].style.format("{:,.1f}"), use_container_width=True)

    with tab1:
        st.subheader("🔥 14:00 중간 보고 양식")
        report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {round(da_target_18/active_member, 1)}건 / 총 {da_target_18:,}건
현황(14시) : 인당배분 {round(current_total/active_member, 1)}건 / 총 {current_total:,}건 (10시 자원 포함)
예상 마감(18시 기준) : 총 {est_final_live:,}건
ㄴ 보장분석 : {int(est_final_live * target_ratio_ba):,}건, 상품 {est_final_live - int(est_final_live * target_ratio_ba):,}건

* {'금일 ' + fixed_content if fixed_ad_type != '없음' else '특이사항 없이 운영 중이며'}, {'오전 목표 달성 가시권입니다.' if est_final_live >= da_target_18 else '남은 시간 유입 극대화하겠습니다.'}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {res['total_cost']//10000:,}만원 / 가망CPA {cpa_total:.1f}만원"""
        st.text_area("복사용 텍스트", report_1400, height=350)

    with tab2:
        st.subheader("🌙 마감 및 명일 자원")
        tom_base = int(tom_member * 3.15)
        report_tom = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.
- 9시 예상 시작 자원 : {tom_base:,}건
ㄴ 보장분석 : {int(tom_base * target_ratio_ba):,}건
ㄴ 상품자원 : {tom_base - int(tom_base * target_ratio_ba):,}건
* 영업가족 {tom_member}명 기준 인당 4.4건 이상 확보 예정입니다."""
        st.text_area("명일 보고 양식", report_tom, height=200)

def main():
    st.sidebar.title("⚙️ 시스템 버전")
    version = st.sidebar.selectbox("선택", ["V18.35 (UI 업데이트)", "V6.6 (Legacy)"])
    if version == "V18.35 (UI 업데이트)": run_v18_35_master()
    else: st.warning("레거시 모드는 제외되었습니다.")

if __name__ == "__main__":
    main()
