import streamlit as st
import pandas as pd
import platform
import io
import warnings
import zipfile
import xml.etree.ElementTree as ET

# 경고 메시지 무시
warnings.simplefilter("ignore")

# -----------------------------------------------------------
# 0. 공통 설정
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V18.35 UI", layout="wide")

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
# 1. 유틸리티 & 스타일 함수
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
    if '보장' in str(campaign_name) or '누적' in str(campaign_name): return '보장분석'
    return '상품'

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

def style_metric_custom(label, current, target, unit="건"):
    """
    커스텀 메트릭 표시 (파란색/빨간색 색상 적용)
    """
    if target > 0:
        rate = (current / target) * 100
        gap = current - target
    else:
        rate = 0
        gap = 0
    
    color = "blue" if gap >= 0 else "red"
    sign = "+" if gap > 0 else ""
    gap_str = f"{sign}{gap:,}"
    
    html = f"""
    <div style="background-color: #f9f9f9; padding: 15px; border-radius: 10px; border: 1px solid #ddd;">
        <p style="margin:0; font-size: 14px; color: #666;">{label}</p>
        <h2 style="margin:0; font-size: 26px; font-weight: bold;">{current:,}{unit} <span style="font-size: 16px; color: #555;">({rate:.1f}%)</span></h2>
        <p style="margin:5px 0 0 0; font-size: 16px; font-weight: bold; color: {color};">
            목표 대비 {gap_str}
        </p>
        <p style="margin:0; font-size: 12px; color: #999;">목표: {target:,}{unit}</p>
    </div>
    """
    return html

# -----------------------------------------------------------
# 2. 파일 로더
# -----------------------------------------------------------
def load_excel_xml_fallback(file):
    try:
        file.seek(0)
        z = zipfile.ZipFile(file)
        strings = []
        if 'xl/sharedStrings.xml' in z.namelist():
            with z.open('xl/sharedStrings.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for si in root.findall('ns:si', ns):
                    t = si.find('ns:t', ns)
                    strings.append(t.text if t is not None else "")
        
        sheet_path = 'xl/worksheets/sheet1.xml'
        if sheet_path not in z.namelist():
             sheets = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]
             if sheets: sheet_path = sheets[0]
             else: return None

        with z.open(sheet_path) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            data = []
            for row in root.findall('ns:sheetData/ns:row', ns):
                row_data = []
                for c in row.findall('ns:c', ns):
                    t = c.get('t')
                    v = c.find('ns:v', ns)
                    val = v.text if v is not None else None
                    if t == 's' and val: val = strings[int(val)]
                    row_data.append(val)
                data.append(row_data)
        
        return pd.DataFrame(data[1:], columns=data[0])
    except: return None

def load_file_auto(file):
    name = file.name
    file.seek(0)
    if name.endswith(('.xlsx', '.xls')):
        if '메리츠 화재' in name:
            try: return pd.read_excel(file, engine='openpyxl', header=3)
            except: pass
        try: return pd.read_excel(file, engine='openpyxl')
        except: return load_excel_xml_fallback(file)
    try:
        if '캠페인 보고서' in name: return pd.read_csv(file, sep='\t', encoding='utf-16', header=2, on_bad_lines='skip')
        if '메리츠화재다이렉트' in name: return pd.read_csv(file, sep='\t', encoding='utf-8', on_bad_lines='skip')
        if '메리츠 화재' in name: return pd.read_csv(file, header=3, encoding='utf-8', on_bad_lines='skip')
    except: pass
    for enc in ['utf-8', 'cp949', 'euc-kr']:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc, on_bad_lines='skip')
        except: continue
    return None

# -----------------------------------------------------------
# 3. 데이터 처리
# -----------------------------------------------------------
def extract_plab_stats(df):
    if df is None: return 0, 0
    df.columns = df.columns.astype(str).str.strip()
    send = next((c for c in df.columns if 'METIS전송' in c and '율' not in c), None)
    fail = next((c for c in df.columns if 'METIS실패' in c), None)
    re_in = next((c for c in df.columns if 'METIS재인입' in c), None)
    
    if not send: return 0, 0
    
    df['cnt'] = df[send].apply(clean_currency)
    if fail: df['cnt'] -= df[fail].apply(clean_currency)
    if re_in: df['cnt'] -= df[re_in].apply(clean_currency)
    
    df['prod_type'] = df['구분'].apply(classify_product)
    bojang = df[df['prod_type'] == '보장분석']['cnt'].sum()
    prod = df[df['prod_type'] == '상품']['cnt'].sum()
    return int(bojang), int(prod)

def process_marketing_data(uploaded_files):
    dfs = []
    toss_files = []
    for file in uploaded_files:
        df = load_file_auto(file)
        if df is None: continue
        filename = file.name
        df.columns = df.columns.astype(str).str.strip()
        try:
            temp = pd.DataFrame()
            if 'result' in filename:
                temp['Cost'] = df['총 비용'].apply(clean_currency)
                temp['상품'] = df['캠페인 이름'].apply(classify_product)
                temp['매체'] = '네이버'
                temp['보장'] = 0
            elif '메리츠화재다이렉트' in filename:
                temp['Cost'] = df['비용'].apply(clean_currency) * 1.1
                temp['상품'] = df['캠페인'].apply(classify_product)
                temp['매체'] = '카카오'
                temp['보장'] = 0
            elif '메리츠 화재' in filename:
                toss_files.append((filename, df))
                continue
            elif '캠페인 보고서' in filename:
                if '캠페인' in df.columns: df = df[df['캠페인'].notna()]
                temp['Cost'] = df['비용'].apply(clean_currency) * 1.1 * 1.15 if '비용' in df.columns else 0
                temp['상품'] = df['캠페인'].apply(classify_product)
                temp['매체'] = '구글'
                temp['보장'] = 0
            elif 'Performance Lab' in filename:
                send = next((c for c in df.columns if 'METIS전송' in c and '율' not in c), None)
                fail = next((c for c in df.columns if 'METIS실패' in c), None)
                re_in = next((c for c in df.columns if 'METIS재인입' in c), None)
                if send:
                    df['cnt'] = df[send].apply(clean_currency)
                    if fail: df['cnt'] -= df[fail].apply(clean_currency)
                    if re_in: df['cnt'] -= df[re_in].apply(clean_currency)
                else: df['cnt'] = 0
                temp['보장'] = df['cnt']
                temp['Cost'] = 0
                temp['매체'] = df.apply(get_media_from_plab, axis=1)
                temp['상품'] = df['구분'].apply(classify_product)
            if not temp.empty: dfs.append(temp.groupby(['매체', '상품']).sum().reset_index())
        except: continue

    if toss_files:
        toss_main = next((f for f in toss_files if '통합' in f[0]), None)
        targets = [toss_main] if toss_main else toss_files
        for fname, df in targets:
            try:
                if '소진 비용' not in df.columns:
                    for i, r in df.head(10).iterrows():
                        if '소진 비용' in r.values: df.columns = r.values; df = df.iloc[i+1:]; break
                if '소진 비용' in df.columns:
                    temp = pd.DataFrame()
                    temp['Cost'] = df['소진 비용'].apply(clean_currency) * 1.1
                    temp['상품'] = df['캠페인 명'].apply(classify_product)
                    temp['매체'] = '토스'
                    temp['보장'] = 0
                    dfs.append(temp.groupby(['매체', '상품']).sum().reset_index())
            except: pass

    if not dfs: return pd.DataFrame(columns=['매체', '상품', 'Cost', '보장'])
    final = pd.concat(dfs).groupby(['매체', '상품']).sum().reset_index()
    final['CPA'] = final.apply(lambda x: x['Cost']/x['보장'] if x['보장']>0 else 0, axis=1)
    return final

# -----------------------------------------------------------
# 4. 메인 앱
# -----------------------------------------------------------
def run_v18_35_final():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.35 UI)")
    
    with st.sidebar:
        st.header("1. 기본 설정")
        current_time_str = st.select_slider("⏱️ 현재 시간", options=["09:30","10:00","11:00","12:00","13:00","14:00","15:00","16:00","17:00","18:00"], value="14:00")
        
        st.header("2. 목표 수립")
        active_member = st.number_input("활동 인원", value=359)
        c1, c2 = st.columns(2)
        target_bojang = c1.number_input("보장 목표", value=500)
        target_prod = c2.number_input("상품 목표", value=3100)
        sa_bojang = c1.number_input("SA 보장", value=200)
        sa_prod = c2.number_input("SA 상품", value=800)
        
        da_target_bojang = target_bojang - sa_bojang
        da_target_prod = target_prod - sa_prod + 50
        da_target_total = da_target_bojang + da_target_prod
        
        st.header("3. 10시 자원 설정")
        upload_mode = st.radio("입력 방식", ["수기 입력", "파일 업로드"], horizontal=True)
        start_bojang, start_prod = 0, 0
        if upload_mode == "파일 업로드":
            with st.expander("📂 파일 업로드"):
                f_yest_18 = st.file_uploader("전일 18시", key="y18")
                f_yest_24 = st.file_uploader("전일 24시", key="y24")
                f_today_10 = st.file_uploader("금일 10시", key="t10")
            if f_yest_18 and f_yest_24 and f_today_10:
                df_y18 = load_file_auto(f_yest_18)
                df_y24 = load_file_auto(f_yest_24)
                df_t10 = load_file_auto(f_today_10)
                b18, p18 = extract_plab_stats(df_y18)
                b24, p24 = extract_plab_stats(df_y24)
                b10, p10 = extract_plab_stats(df_t10)
                start_bojang = max(0, b24 - b18) + b10
                start_prod = max(0, p24 - p18) + p10
                st.success(f"10시: 보장 {start_bojang} / 상품 {start_prod}")
                plab_10_bojang, plab_10_prod = b10, p10
            else: plab_10_bojang, plab_10_prod = 0, 0
        else:
            c1, c2 = st.columns(2)
            start_bojang = c1.number_input("10시 보장", value=300)
            start_prod = c2.number_input("10시 상품", value=800)
            plab_10_bojang = int(start_bojang * 0.6)
            plab_10_prod = int(start_prod * 0.6)
        start_total = start_bojang + start_prod

        st.header("4. 실시간 분석")
        files = st.file_uploader("실시간 파일", accept_multiple_files=True)
        aff_cost = st.number_input("제휴 소진액", value=11270000)
        aff_cpa = st.number_input("제휴 단가", value=14000)
        aff_cnt = int(aff_cost / aff_cpa) if aff_cpa > 0 else 0

    # --- 계산 ---
    df_res = process_marketing_data(files) if files else pd.DataFrame()
    curr_plab_bojang, curr_plab_prod = 0, 0
    da_cost = 0
    if not df_res.empty:
        curr_plab_bojang = int(df_res[df_res['상품']=='보장분석']['보장'].sum())
        curr_plab_prod = int(df_res[df_res['상품']=='상품']['보장'].sum())
        da_cost = int(df_res['Cost'].sum())
    
    if start_total > 0 and files:
        final_bojang = start_bojang + max(0, curr_plab_bojang - plab_10_bojang)
        final_prod = start_prod + max(0, curr_plab_prod - plab_10_prod)
    else:
        final_bojang = curr_plab_bojang
        final_prod = curr_plab_prod
    
    total_bojang = final_bojang + aff_cnt
    total_prod = final_prod
    total_all = total_bojang + total_prod
    total_cost = da_cost + aff_cost
    
    # 시간대별 목표 계산
    hours = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"]
    hour_labels = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
    weights = [0.0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09] # 10시(0)부터 시작
    
    # 누적 목표 계산
    acc_targets = []
    acc_bojang_targets = []
    acc_prod_targets = []
    
    gap = da_target_total - start_total
    current_acc = start_total
    
    # 비율
    ratio_b = da_target_bojang / da_target_total if da_target_total else 0
    ratio_p = 1 - ratio_b

    for w in weights:
        # 10시는 start_total 그대로, 그 이후는 가중치 더함
        if w > 0:
            added = int(gap * (w / sum(weights[1:]))) # weights[0]은 0이므로 제외하고 합계
            current_acc += added
        
        # 마지막 18시는 목표값으로 강제 보정
        if len(acc_targets) == 8: # 18시
             current_acc = da_target_total

        acc_targets.append(current_acc)
        acc_bojang_targets.append(int(current_acc * ratio_b))
        acc_prod_targets.append(int(current_acc * ratio_p))

    # 현재 시간의 목표값 찾기
    try:
        cur_idx = hours.index(current_time_str)
        cur_target_total = acc_targets[cur_idx]
    except:
        cur_target_total = da_target_total

    # 마감 예상 (단순 배수 적용)
    # 현재 시간이 10시~18시 사이라면 진행률 기반 추정 가능하나, 
    # 기존 로직(14시 기준 등)을 유지
    time_multipliers = {
        "09:30": 1.0, "10:00": 1.75, "11:00": 1.65, "12:00": 1.55, "13:00": 1.45,
        "14:00": 1.35, "15:00": 1.25, "16:00": 1.15, "17:00": 1.05, "18:00": 1.0
    }
    est_final = int(total_all * time_multipliers.get(current_time_str, 1.35))

    # --- 탭 ---
    tab1, tab2, tab3 = st.tabs(["📊 대시보드", "🌅 09:30 목표", "📋 상세 리포트"])
    
    with tab1:
        st.subheader(f"📊 실시간 현황 ({current_time_str})")
        
        # 1. 커스텀 메트릭 표시
        m1, m2, m3, m4 = st.columns(4)
        with m1:
            st.markdown(style_metric_custom("현재 실적 (시간대 목표 대비)", total_all, cur_target_total), unsafe_allow_html=True)
        with m2:
            st.markdown(style_metric_custom("마감 예상 (최종 목표 대비)", est_final, da_target_total), unsafe_allow_html=True)
        with m3:
            cpa_val = total_cost / total_all if total_all > 0 else 0
            st.metric("현재 CPA", f"{int(cpa_val):,}원")
        with m4:
             st.metric("총 비용", f"{int(total_cost/10000):,}만원")

        st.divider()
        st.markdown("##### 📉 시간대별 목표 대비 상세")
        
        # 2. 시간대별 상세 표 생성
        # 데이터프레임 구조: 열=시간대, 행=목표/실적/차이
        
        # 실적 데이터 매핑 (10시와 현재 시간만)
        real_total = [''] * 9
        real_bojang = [''] * 9
        real_prod = [''] * 9
        
        # 10시 데이터 채우기
        real_total[0] = f"{start_total:,}"
        real_bojang[0] = f"{start_bojang:,}"
        real_prod[0] = f"{start_prod:,}"
        
        # 현재 시간 데이터 채우기
        if current_time_str in hours:
            idx = hours.index(current_time_str)
            # 10시와 다를 때만 채움 (겹치면 이미 채워짐)
            if idx > 0:
                real_total[idx] = f"{total_all:,}"
                real_bojang[idx] = f"{total_bojang:,}"
                real_prod[idx] = f"{total_prod:,}"

        # 차이(Gap) 계산 및 색상 태그 함수
        def format_gap(target, actual_str):
            if not actual_str: return "-"
            try:
                act = int(actual_str.replace(',', ''))
                gap = act - target
                color = "blue" if gap >= 0 else "red"
                sign = "+" if gap > 0 else ""
                return f'<span style="color:{color}; font-weight:bold;">{sign}{gap:,}</span>'
            except: return "-"

        gap_total = [format_gap(t, a) for t, a in zip(acc_targets, real_total)]
        gap_bojang = [format_gap(t, a) for t, a in zip(acc_bojang_targets, real_bojang)]
        gap_prod = [format_gap(t, a) for t, a in zip(acc_prod_targets, real_prod)]
        
        # 테이블 데이터 생성
        table_data = {
            "구분": [
                "누적 목표", "누적 실적", "차이 (Gap)", 
                "보장 목표", "보장 실적", "차이 (Gap)",
                "상품 목표", "상품 실적", "차이 (Gap)"
            ],
            **{
                h: [
                    f"{acc_targets[i]:,}", real_total[i], gap_total[i],
                    f"{acc_bojang_targets[i]:,}", real_bojang[i], gap_bojang[i],
                    f"{acc_prod_targets[i]:,}", real_prod[i], gap_prod[i]
                ] for i, h in enumerate(hour_labels)
            }
        }
        
        df_table = pd.DataFrame(table_data)
        
        # HTML로 테이블 렌더링 (색상 적용을 위해)
        st.write(df_table.to_html(escape=False, index=False), unsafe_allow_html=True)

    with tab2:
        st.subheader("📋 광고주 보고용 목표 테이블")
        
        # 시간당 확보량 계산 (단순 차이)
        hourly_secure = []
        prev = 0
        for t in acc_targets:
            hourly_secure.append(t - prev)
            prev = t
        hourly_secure[0] = start_total # 10시는 시작 자원
            
        per_person = [round(x / active_member, 1) if active_member > 0 else 0 for x in acc_targets]
        
        df_goal_table = pd.DataFrame({
            "구분": ["누적자원", "인당배분", "시간당 확보"],
            **{h: [f"{a:,}", f"{p}", f"{s:,}"] for h, a, p, s in zip(hour_labels, acc_targets, per_person, hourly_secure)}
        })
        st.table(df_goal_table.set_index("구분"))
        
        st.text_area("복사용 텍스트", f"""[09:30 광고주 보고]
금일 예상 시작 자원 공유드립니다.

- 총 자원 : {start_total:,}건
  ㄴ 보장 : {start_bojang:,}건
  ㄴ 상품 : {start_prod:,}건

* 전일 야간 및 금일 오전 효율 기반으로 산출되었습니다.""")

    with tab3:
        st.subheader("🔍 매체별 상세")
        if not df_res.empty:
            st.dataframe(df_res.style.format({'Cost': '{:,.0f}', '보장': '{:,.0f}', 'CPA': '{:,.0f}'}))

if __name__ == "__main__":
    run_v18_35_final()
