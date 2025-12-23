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
st.set_page_config(page_title="메리츠 보고 자동화 V18.35 Logic", layout="wide")

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
# 1. 유틸리티 함수
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

# -----------------------------------------------------------
# 2. 파일 로더 (XML 파싱 포함)
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
# 3. 데이터 처리 로직
# -----------------------------------------------------------
def extract_plab_stats(df):
    """피랩 파일에서 보장/상품 건수 추출"""
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
    """실시간 파일 통합 처리"""
    dfs = []
    toss_files = []
    
    for file in uploaded_files:
        df = load_file_auto(file)
        if df is None: continue
        filename = file.name
        df.columns = df.columns.astype(str).str.strip()
        
        try:
            temp = pd.DataFrame()
            if 'result' in filename: # 네이버
                temp['Cost'] = df['총 비용'].apply(clean_currency)
                temp['상품'] = df['캠페인 이름'].apply(classify_product)
                temp['매체'] = '네이버'
                temp['보장'] = 0
            elif '메리츠화재다이렉트' in filename: # 카카오
                temp['Cost'] = df['비용'].apply(clean_currency) * 1.1
                temp['상품'] = df['캠페인'].apply(classify_product)
                temp['매체'] = '카카오'
                temp['보장'] = 0
            elif '메리츠 화재' in filename: # 토스
                toss_files.append((filename, df))
                continue
            elif '캠페인 보고서' in filename: # 구글
                if '캠페인' in df.columns: df = df[df['캠페인'].notna()]
                temp['Cost'] = df['비용'].apply(clean_currency) * 1.1 * 1.15 if '비용' in df.columns else 0
                temp['상품'] = df['캠페인'].apply(classify_product)
                temp['매체'] = '구글'
                temp['보장'] = 0
            elif 'Performance Lab' in filename: # 피랩
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
            
            if not temp.empty:
                dfs.append(temp.groupby(['매체', '상품']).sum().reset_index())

        except: continue

    # 토스 처리
    if toss_files:
        toss_main = next((f for f in toss_files if '통합' in f[0]), None)
        targets = [toss_main] if toss_main else toss_files
        for fname, df in targets:
            try:
                if '소진 비용' not in df.columns: # 헤더 찾기
                    for i, r in df.head(10).iterrows():
                        if '소진 비용' in r.values:
                            df.columns = r.values; df = df.iloc[i+1:]; break
                
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
# 4. 메인 로직
# -----------------------------------------------------------
def run_logic():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.35 Logic)")
    
    with st.sidebar:
        st.header("1. 기본 설정")
        current_time = st.select_slider("⏱️ 현재 시간", options=["09:30","10:00","11:00","12:00","13:00","14:00","15:00","16:00","17:00","18:00"], value="14:00")
        
        st.header("2. 목표 수립")
        active_member = st.number_input("활동 인원", value=359)
        c1, c2 = st.columns(2)
        target_bojang = c1.number_input("보장 목표", value=500)
        target_prod = c2.number_input("상품 목표", value=3100)
        sa_bojang = c1.number_input("SA 보장", value=200)
        sa_prod = c2.number_input("SA 상품", value=800)
        
        da_target_bojang = target_bojang - sa_bojang
        da_target_prod = target_prod - sa_prod + 50 # 버퍼 포함
        da_target_total = da_target_bojang + da_target_prod
        
        st.header("3. 10시 자원 설정")
        upload_mode = st.radio("입력 방식", ["수기 입력", "파일 업로드"], horizontal=True)
        
        start_bojang, start_prod = 0, 0
        
        if upload_mode == "파일 업로드":
            with st.expander("📂 파일 업로드 (피랩 파일)"):
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
                
                # 로직: (전일24 - 전일18) + 금일10
                night_bojang = max(0, b24 - b18)
                night_prod = max(0, p24 - p18)
                
                start_bojang = night_bojang + b10
                start_prod = night_prod + p10
                
                st.info(f"계산된 10시 자원: 보장 {start_bojang} / 상품 {start_prod} (합 {start_bojang+start_prod})")
                
                # 10시 시점의 실적 저장 (실시간 계산용)
                plab_10_bojang = b10
                plab_10_prod = p10
            else:
                plab_10_bojang, plab_10_prod = 0, 0
                
        else: # 수기 입력
            c1, c2 = st.columns(2)
            start_bojang = c1.number_input("10시 보장", value=300)
            start_prod = c2.number_input("10시 상품", value=800)
            # 수기 입력 시 10시 기준 피랩 데이터는 알 수 없으므로 0으로 가정하거나 입력 필요
            # 여기서는 편의상 입력값의 60%를 10시 당일 실적으로 가정 (보정 가능)
            plab_10_bojang = int(start_bojang * 0.6)
            plab_10_prod = int(start_prod * 0.6)
            
        start_total = start_bojang + start_prod

        st.header("4. 실시간 분석")
        files = st.file_uploader("실시간 파일", accept_multiple_files=True)
        
        # 제휴 수기
        aff_cost = st.number_input("제휴 소진액", value=11270000)
        aff_cpa = st.number_input("제휴 단가", value=14000)
        aff_cnt = int(aff_cost / aff_cpa) if aff_cpa > 0 else 0
        
    # --- 데이터 집계 ---
    df_res = process_marketing_data(files) if files else pd.DataFrame()
    
    # 실시간 피랩 수치 추출 (DA only)
    curr_plab_bojang, curr_plab_prod = 0, 0
    if not df_res.empty:
        curr_plab_bojang = int(df_res['보장'].sum()) # 상품구분 로직 적용 필요
        # process_marketing_data 함수 내에서 이미 구분되어 있음
        # 다시 계산
        curr_plab_bojang = int(df_res[df_res['상품']=='보장분석']['보장'].sum())
        curr_plab_prod = int(df_res[df_res['상품']=='상품']['보장'].sum())
    
    # 실시간 실적 로직: 10시 자원 + (현재 피랩 - 10시 피랩)
    # 단, 파일 업로드가 안된 초기 상태면 그냥 현재 피랩 사용
    if start_total > 0 and files:
        final_bojang = start_bojang + max(0, curr_plab_bojang - plab_10_bojang)
        final_prod = start_prod + max(0, curr_plab_prod - plab_10_prod)
    else:
        final_bojang = curr_plab_bojang
        final_prod = curr_plab_prod
        
    final_da_total = final_bojang + final_prod
    
    # 제휴 합산
    total_bojang = final_bojang + aff_cnt # 제휴는 보장으로 간주
    total_prod = final_prod
    total_all = total_bojang + total_prod
    
    # 비용
    da_cost = int(df_res['Cost'].sum()) if not df_res.empty else 0
    total_cost = da_cost + aff_cost
    
    # --- 탭 구성 ---
    tab1, tab2, tab3 = st.tabs(["📊 대시보드", "🌅 09:30 목표", "📋 상세 리포트"])
    
    with tab1:
        st.subheader(f"📊 실시간 현황 ({current_time})")
        c1, c2, c3 = st.columns(3)
        c1.metric("총 실적 (DA+제휴)", f"{total_all:,}건", f"목표 {da_target_total:,}")
        c2.metric("보장 분석", f"{total_bojang:,}건", f"목표 {da_target_bojang:,}")
        c3.metric("상품", f"{total_prod:,}건", f"목표 {da_target_prod:,}")
        
        st.progress(min(1.0, total_all/da_target_total) if da_target_total else 0)
        
        st.markdown("---")
        st.markdown("#### 📌 10시 자원 산출 내역")
        st.write(f"- 10시 확정 자원 : **{start_total:,}건** (보장 {start_bojang} / 상품 {start_prod})")
        st.write(f"- 실시간 추가분 : **{max(0, curr_plab_bojang + curr_plab_prod - plab_10_bojang - plab_10_prod):,}건**")
        st.caption("※ 실시간 추가분 = (현재 피랩 조회값 - 10시 기준 피랩 조회값)")

    with tab2:
        st.subheader("📋 광고주 보고용 목표 테이블")
        
        # 목표 배분 로직
        # 10시 자원 + 예상 추가분으로 18시 목표 맞춤
        
        # 표 데이터 생성
        data = {
            '구분': ['보장분석', '상품', '합계'],
            '배정 목표': [da_target_bojang, da_target_prod, da_target_total],
            '09시 예상': [start_bojang, start_prod, start_total],
            '달성률': [
                f"{start_bojang/da_target_bojang*100:.1f}%" if da_target_bojang else "0%",
                f"{start_prod/da_target_prod*100:.1f}%" if da_target_prod else "0%",
                f"{start_total/da_target_total*100:.1f}%" if da_target_total else "0%"
            ]
        }
        df_goal = pd.DataFrame(data)
        st.table(df_goal.set_index('구분'))
        
        st.text_area("복사용 텍스트", f"""[09:30 광고주 보고]
금일 예상 시작 자원 공유드립니다.

- 총 자원 : {start_total:,}건
  ㄴ 보장 : {start_bojang:,}건 ({start_bojang/da_target_bojang*100:.1f}%)
  ㄴ 상품 : {start_prod:,}건 ({start_prod/da_target_prod*100:.1f}%)

* 전일 야간 및 금일 오전 효율 기반으로 산출되었습니다.""")

    with tab3:
        st.subheader("🔍 매체별 상세")
        if not df_res.empty:
            st.dataframe(df_res.style.format({'Cost': '{:,.0f}', '보장': '{:,.0f}', 'CPA': '{:,.0f}'}))

if __name__ == "__main__":
    run_logic()
