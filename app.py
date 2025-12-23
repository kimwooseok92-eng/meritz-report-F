import streamlit as st
import pandas as pd
import platform
import io
import warnings
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

# 경고 무시
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
# 1. 유틸리티 함수 (기존 로직 유지)
# -----------------------------------------------------------
def clean_num(x):
    if pd.isna(x) or x == '': return 0.0
    try:
        if isinstance(x, str):
            return float(x.replace(',', '').replace('"', '').replace("'", "").strip())
        return float(x)
    except: return 0.0

def normalize_str(text):
    if pd.isna(text): return ''
    return unicodedata.normalize('NFC', str(text)).strip()

def classify_type_by_name(text):
    text = normalize_str(text).lower()
    if '보장' in text or '누적' in text: return '보장'
    return '상품'

def get_media_from_plab(row):
    account = normalize_str(row.get('account', '')).upper()
    gubun = normalize_str(row.get('구분', '')).upper()
    if 'DDN' in account: return '카카오'
    if 'GDN' in account: return '구글'
    targets = ['네이버', '카카오', '토스', '구글', 'NAVER', 'KAKAO', 'TOSS', 'GOOGLE']
    media_map = {'NAVER': '네이버', 'KAKAO': '카카오', 'TOSS': '토스', 'GOOGLE': '구글'}
    for t in targets:
        if t in account: return media_map.get(t, '기타')
    for t in targets:
        if t in gubun: return media_map.get(t, '기타')
    return '기타'

# 엑셀 스타일 에러 방지용 안전 로더
def load_excel_safe(file):
    try:
        file.seek(0)
        z = zipfile.ZipFile(file)
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                root = ET.parse(f).getroot()
                ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in root.findall('ns:si', ns):
                    t_tag = si.find('ns:t', ns)
                    if t_tag is not None: strings.append(t_tag.text)
                    else: strings.append("".join([t.text for t in si.findall('.//ns:t', ns) if t.text]))
        sheet_path = [n for n in z.namelist() if 'xl/worksheets/sheet1.xml' in n or 'sheet' in n][0]
        with z.open(sheet_path) as f:
            root = ET.parse(f).getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            data = []
            for row in root.findall('ns:sheetData/ns:row', ns):
                row_data = []
                for c in row.findall('ns:c', ns):
                    t, v = c.get('t'), c.find('ns:v', ns)
                    val = v.text if v is not None else None
                    if t == 's' and val: val = strings[int(val)]
                    row_data.append(val)
                data.append(row_data)
        return pd.DataFrame(data[1:], columns=data[0])
    except: return None

def read_file_safe(file, **kwargs):
    file.seek(0)
    fname = file.name.lower()
    if fname.endswith(('.xlsx', '.xls')):
        df = load_excel_safe(file)
        if df is None:
            try: return pd.read_excel(file, engine='openpyxl', **kwargs)
            except: return None
        return df
    # CSV 처리
    for enc in ['utf-8', 'cp949', 'euc-kr', 'utf-16']:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc, on_bad_lines='skip', **kwargs)
        except: continue
    return None

# -----------------------------------------------------------
# 2. 매체별 파싱 및 집계 로직 (기존 Rule 유지)
# -----------------------------------------------------------
def parse_files_by_rules(files):
    df_cost = pd.DataFrame(); df_db = pd.DataFrame()
    for file in files:
        fname = file.name; temp = pd.DataFrame(); df = None
        try:
            if "메리츠 화재_전략광고3팀_배너광고_캠페인" in fname: # 토스
                df = read_file_safe(file, header=3)
                if df is not None:
                    df = df[~df['캠페인 명'].astype(str).str.contains('합계|Total', case=False, na=False)]
                    col_cost = next((c for c in df.columns if '소진 비용' in str(c)), None)
                    col_camp = next((c for c in df.columns if '캠페인 명' in str(c)), None)
                    if col_cost and col_camp:
                        temp['cost'] = df[col_cost].apply(clean_num) * 1.1
                        temp['campaign'] = df[col_camp].fillna('')
                        temp['type'] = temp['campaign'].apply(classify_type_by_name)
                        temp['media'] = '토스'; df_cost = pd.concat([df_cost, temp], ignore_index=True)
            elif "메리츠화재다이렉트_캠페인" in fname: # 카카오
                df = read_file_safe(file, sep='\t')
                if df is not None:
                    col_cost = '비용' if '비용' in df.columns else None
                    col_camp = '캠페인' if '캠페인' in df.columns else None
                    if col_cost and col_camp:
                        temp['cost'] = df[col_cost].apply(clean_num) * 1.1
                        temp['campaign'] = df[col_camp].fillna('')
                        temp['type'] = temp['campaign'].apply(classify_type_by_name)
                        temp['media'] = '카카오'; df_cost = pd.concat([df_cost, temp], ignore_index=True)
            elif "result" in fname: # 네이버
                df = read_file_safe(file)
                if df is not None:
                    col_cost = next((c for c in df.columns if '총 비용' in str(c)), None)
                    col_camp = next((c for c in df.columns if '캠페인 이름' in str(c)), None)
                    if col_cost and col_camp:
                        temp['cost'] = df[col_cost].apply(clean_num)
                        temp['campaign'] = df[col_camp].fillna('')
                        temp['type'] = temp['campaign'].apply(classify_type_by_name)
                        temp['media'] = '네이버'; df_cost = pd.concat([df_cost, temp], ignore_index=True)
            elif "캠페인 보고서" in fname: # 구글
                df = read_file_safe(file, sep='\t', header=2)
                if df is not None:
                    df.columns = df.columns.str.strip()
                    df = df[~df['캠페인'].astype(str).str.contains('합계|Total|--', case=False, na=False)]
                    col_cost = '비용' if '비용' in df.columns else None
                    col_camp = '캠페인' if '캠페인' in df.columns else None
                    if col_cost and col_camp:
                        temp['cost'] = df[col_cost].apply(clean_num) * 1.1 * 1.15
                        temp['campaign'] = df[col_camp].fillna('')
                        temp['type'] = temp['campaign'].apply(classify_type_by_name)
                        temp['media'] = '구글'; df_cost = pd.concat([df_cost, temp], ignore_index=True)
            elif "Performance Lab" in fname: # 피랩
                df = read_file_safe(file)
                if df is not None:
                    df.columns = df.columns.str.strip()
                    s_col = next((c for c in df.columns if 'METIS전송' in c and '율' not in c), None)
                    f_col = next((c for c in df.columns if 'METIS실패' in c), None)
                    r_col = next((c for c in df.columns if 'METIS재인입' in c), None)
                    if s_col:
                        cnts = df[s_col].apply(clean_num)
                        if f_col: cnts -= df[f_col].apply(clean_num)
                        if r_col: cnts -= df[r_col].apply(clean_num)
                        temp['count'] = cnts
                        temp['account'] = df['account'].fillna(''); temp['구분'] = df['구분'].fillna('')
                        temp['type'] = temp['구분'].apply(classify_type_by_name)
                        temp['media'] = temp.apply(get_media_from_plab, axis=1)
                        df_db = pd.concat([df_db, temp], ignore_index=True)
        except: continue
    return df_cost, df_db

def get_plab_summary(df):
    if df is None or df.empty: return 0, 0
    b = int(df[df['type'] == '보장']['count'].sum())
    p = int(df[df['type'] == '상품']['count'].sum())
    return b, p

# -----------------------------------------------------------
# 3. 메인 앱 실행
# -----------------------------------------------------------
def run_v18_35_master():
    st.title("📊 메리츠화재 DA 통합 리포트 (V18.35 Ultimate)")

    with st.sidebar:
        st.header("1. 기본 설정")
        current_time_str = st.select_slider("⏱️ 현재 기준", options=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"], value="14:00")
        day_option = st.selectbox("요일", ['월', '화', '수', '목', '금'], index=0)
        
        st.header("2. 목표 수립")
        active_member = st.number_input("활동 인원", value=359)
        c1, c2 = st.columns(2)
        target_bojang = c1.number_input("보장 목표", value=500)
        target_product = c2.number_input("상품 목표", value=3100)
        c3, c4 = st.columns(2)
        sa_est_bojang = c3.number_input("SA 보장", value=200)
        sa_est_prod = c4.number_input("SA 상품", value=800)
        da_add_target = st.number_input("DA 버퍼", value=50)

        da_target_bojang = target_bojang - sa_est_bojang
        da_target_prod = target_product - sa_est_prod + da_add_target
        da_target_total = da_target_bojang + da_target_prod
        
        st.header("3. 10시 자원 산출")
        mode_10 = st.radio("입력 방식", ["수기 입력", "파일 업로드"], horizontal=True)
        start_b, start_p, t10_b, t10_p = 0, 0, 0, 0
        if mode_10 == "파일 업로드":
            with st.expander("📂 피랩 파일 3개 업로드"):
                f18 = st.file_uploader("어제 18시", key="f18")
                f24 = st.file_uploader("어제 24시", key="f24")
                f10 = st.file_uploader("오늘 10시", key="f10")
            if f18 and f24 and f10:
                _, db18 = parse_files_by_rules([f18])
                _, db24 = parse_files_by_rules([f24])
                _, db10 = parse_files_by_rules([f10])
                b18, p18 = get_plab_summary(db18); b24, p24 = get_plab_summary(db24); t10_b, t10_p = get_plab_summary(db10)
                start_b = (b24 - b18) + t10_b; start_p = (p24 - p18) + t10_p
                st.success(f"10시 자원: 보장 {start_b:,} / 상품 {start_p:,}")
        else:
            col_b1, col_b2 = st.columns(2)
            start_b = col_b1.number_input("10시 보장", value=300)
            start_p = col_b2.number_input("10시 상품", value=800)
            t10_b, t10_p = int(start_b*0.6), int(start_p*0.6) # 임의 기준값

        st.header("4. 실시간 분석")
        rt_files = st.file_uploader("실시간 파일 (다중 선택)", accept_multiple_files=True)
        manual_aff_cost = st.number_input("제휴 소진액", value=11270000)
        manual_aff_cpa = st.number_input("제휴 단가", value=14000)
        aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0

    # --- 계산 로직 ---
    df_cost, df_db = parse_files_by_rules(rt_files) if rt_files else (pd.DataFrame(), pd.DataFrame())
    
    # 실시간 피랩 기준 확보량
    curr_rt_b, curr_rt_p = get_plab_summary(df_db)
    
    # [로직] 최종 실적 = 10시 시작자원 + (현재 피랩 - 10시 피랩)
    final_bojang = start_b + max(0, curr_rt_b - t10_b) + aff_cnt
    final_prod = start_p + max(0, curr_rt_p - t10_p)
    final_total = final_bojang + final_prod
    
    cost_da = int(df_cost['cost'].sum()) if not df_cost.empty else 0
    total_cost = cost_da + manual_aff_cost
    
    # 시간대별 목표 계산
    hours = ["10시","11시","12시","13시","14시","15시","16시","17시","18시"]
    weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
    acc_goals = [start_b + start_p]
    gap = da_target_total - (start_b + start_p)
    for w in weights[1:]: acc_goals.append(acc_goals[-1] + int(gap * (w / sum(weights[1:]))))
    acc_goals[-1] = int(da_target_total)
    
    cur_idx = hours.index(current_time_str.replace(":00", "시").replace("09:30", "10시"))
    cur_goal = acc_goals[cur_idx]

    # --- 탭 출력 ---
    tab0, tab1, tab2 = st.tabs(["📊 대시보드", "🌅 09:30 목표", "🔥 상세 보고"])

    with tab0:
        st.subheader(f"📊 실시간 현황 ({current_time_str})")
        c1, c2, c3 = st.columns(3)
        
        def display_metric(label, curr, target):
            gap = curr - target; color = "blue" if gap >= 0 else "red"; sign = "+" if gap >= 0 else ""
            st.metric(label, f"{curr:,}건", f"{(curr/target*100):.1f}% (목표대비 {sign}{gap:,})", delta_color="normal" if gap >= 0 else "inverse")

        with c1: display_metric("총 실적 (DA+제휴)", final_total, cur_goal)
        with c2: st.metric("보장 분석", f"{final_bojang:,}건", f"목표 {da_target_bojang:,}")
        with c3: st.metric("상품 자원", f"{final_prod:,}건", f"목표 {da_target_prod:,}")
        
        st.divider()
        st.markdown("##### 📉 시간대별 상세 현황")
        real_line = [""] * 9; real_line[0] = f"{start_b + start_p:,}"; real_line[cur_idx] = f"{final_total:,}"
        df_dash = pd.DataFrame({"구분": ["누적 목표", "누적 실적"], **{h: [f"{acc_goals[i]:,}", real_line[i]] for i, h in enumerate(hours)}})
        st.table(df_dash.set_index("구분"))

    with tab1:
        st.subheader("📋 광고주 보고용 목표 (09:30)")
        # 광고주 표 양식: 누적자원 / 인당배분 / 시간당 확보
        hourly_sec = [start_b + start_p]
        for i in range(1, 9): hourly_sec.append(acc_goals[i] - acc_goals[i-1])
        per_person = [round(x / active_member, 1) if active_member > 0 else 0 for x in acc_goals]
        
        df_client = pd.DataFrame({
            "구분": ["누적자원", "인당배분", "시간당 확보"],
            **{h: [f"{acc_goals[i]:,}", f"{per_person[i]}", f"{hourly_sec[i]:,}"] for i, h in enumerate(hours)}
        })
        st.table(df_client.set_index("구분"))
        
        st.text_area("카톡 복사용", f"""[09:30 광고주 보고]
금일 예상 시작 자원 공유드립니다.

- 총 자원 : {start_b+start_p:,}건
  ㄴ 보장 : {start_b:,}건
  ㄴ 상품 : {start_p:,}건

* 전일 야간 및 금일 오전 유입량 기반으로 산출되었습니다.""", height=150)

    with tab2:
        st.subheader("🔍 매체별 실적 상세")
        # 매체별 테이블 (기존 UI 유지)
        if not df_cost.empty or not df_db.empty:
            media_stats = pd.DataFrame(index=['네이버', '카카오', '토스', '구글', '제휴', '기타'], columns=['토탈', '보장', '상품', '비용', 'CPA']).fillna(0)
            # DB 집계
            for _, r in df_db.iterrows():
                m = r['media'] if r['media'] in media_stats.index else '기타'
                media_stats.loc[m, '토탈'] += r['count']
                if r['type'] == '보장': media_stats.loc[m, '보장'] += r['count']
                else: media_stats.loc[m, '상품'] += r['count']
            # 비용 집계
            for _, r in df_cost.iterrows():
                m = r['media'] if r['media'] in media_stats.index else '기타'
                media_stats.loc[m, '비용'] += r['cost']
            # 제휴 추가
            media_stats.loc['제휴', '토탈'] = aff_cnt; media_stats.loc['제휴', '보장'] = aff_cnt; media_stats.loc['제휴', '비용'] = manual_aff_cost
            media_stats['CPA'] = media_stats.apply(lambda x: x['비용'] / x['토탈'] if x['토탈'] > 0 else 0, axis=1)
            st.dataframe(media_stats.style.format("{:,.0f}"), use_container_width=True)

if __name__ == "__main__":
    run_v18_35_master()
