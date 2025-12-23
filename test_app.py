import streamlit as st
import pandas as pd
import platform
import io
import warnings
import zipfile
import xml.etree.ElementTree as ET
import re
from streamlit_gsheets import GSheetsConnection  # 추가

# 경고 메시지 무시
warnings.simplefilter("ignore")

# -----------------------------------------------------------
# 0. 공통 설정 및 데이터베이스 연결
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V18.35 Ultimate", layout="wide")

# 구글 시트 연결 객체 생성
conn = st.connection("gsheets", type=GSheetsConnection)

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
# 1. 유틸리티 및 데이터 처리 함수
# -----------------------------------------------------------

# [기존 유틸리티 함수들: clean_currency, classify_product, get_media_from_plab 등 동일 유지]
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
    if '보장' in name or '누적' in name: return '보장분석'
    else: return '상품'

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

# [XML 파싱 및 파일 로드 함수 동일 유지...]
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
                    if t is not None and t.text: strings.append(t.text)
                    else:
                        text_parts = [rt.text for rt in si.findall('ns:r/ns:t', ns) if rt.text]
                        strings.append("".join(text_parts))
        sheets = [n for n in z.namelist() if n.startswith('xl/worksheets/sheet')]
        if not sheets: return None
        with z.open(sheets[0]) as f:
            tree = ET.parse(f)
            root = tree.getroot()
            ns = {'ns': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
            data = []
            for row in root.findall('ns:sheetData/ns:row', ns):
                row_data = []
                for c in row.findall('ns:c', ns):
                    t, v_tag = c.get('t'), c.find('ns:v', ns)
                    val = v_tag.text if v_tag is not None else None
                    if t == 's' and val is not None: val = strings[int(val)]
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
    encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'utf-8-sig']
    for enc in encodings:
        try:
            file.seek(0)
            df = pd.read_csv(file, encoding=enc, sep=None, engine='python', on_bad_lines='skip')
            if len(df.columns) > 1: return df
        except: continue
    return None

def find_header_and_reload(df, target_col):
    if target_col in df.columns: return df
    for idx, row in df.head(10).iterrows():
        row_values = [str(x).strip() for x in row.values]
        if target_col in row_values:
            new_df = df.iloc[idx+1:].copy()
            new_df.columns = row_values
            return new_df
    return df

# -----------------------------------------------------------
# 2. 통합 데이터 처리 (구글 시트 연동 포함)
# -----------------------------------------------------------
def process_marketing_data(uploaded_files, use_gsheets=False):
    dfs = []
    
    # [A] 구글 시트에서 데이터 가져오기 로직 추가
    if use_gsheets:
        try:
            # 탭 이름 'RAW_실시간 예상 배분'을 읽어옵니다.
            gsheet_df = conn.read(worksheet="RAW_실시간 예상 배분", ttl="5m")
            if not gsheet_df.empty:
                # 구글 시트의 데이터 컬럼명을 기존 로직에 맞게 매핑
                # 예: 시트의 '비용' -> 'Cost', '상품구분' -> '상품'
                gsheet_df['Cost'] = gsheet_df['비용'].apply(clean_currency)
                gsheet_df['상품'] = gsheet_df['상품구분'].apply(classify_product)
                gsheet_df['매체'] = gsheet_df['매체명']
                gsheet_df['보장'] = gsheet_df['실적'].apply(clean_currency)
                
                grouped_gs = gsheet_df.groupby(['매체', '상품'])[['Cost', '보장']].sum().reset_index()
                dfs.append(grouped_gs)
                st.success("✅ 구글 시트 데이터 로드 완료")
        except Exception as e:
            st.error(f"❌ 구글 시트 연동 오류: {e}")

    # [B] 기존 파일 업로드 방식 처리
    if uploaded_files:
        toss_files = []
        for file in uploaded_files:
            filename = file.name
            df = load_file_by_rule(file)
            if df is None: continue
            df.columns = df.columns.astype(str).str.strip()
            
            try:
                if 'result' in filename: # 네이버
                    df['Cost'] = df['총 비용'].apply(clean_currency)
                    df['상품'] = df['캠페인 이름'].apply(classify_product)
                    df['매체'] = '네이버'
                    dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))
                elif '메리츠화재다이렉트' in filename: # 카카오
                    df['Cost'] = df['비용'].apply(clean_currency) * 1.1
                    df['상품'] = df['캠페인'].apply(classify_product)
                    df['매체'] = '카카오'
                    dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))
                elif '메리츠 화재' in filename: # 토스
                    toss_files.append((filename, df))
                elif '캠페인 보고서' in filename: # 구글
                    df = df[df['캠페인'].notna()]
                    df['Cost'] = df['비용'].apply(clean_currency) * 1.1 * 1.15
                    df['상품'] = df['캠페인'].apply(classify_product)
                    df['매체'] = '구글'
                    dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))
                elif 'Performance Lab' in filename: # 피랩
                    send_col = next((c for c in df.columns if 'METIS전송' in c), None)
                    df['보장'] = (df[send_col].apply(clean_currency) - df.get('METIS실패', 0) - df.get('METIS재인입', 0)) if send_col else 0
                    df['매체'] = df.apply(get_media_from_plab, axis=1)
                    df['상품'] = df['구분'].apply(classify_product)
                    dfs.append(df.groupby(['매체', '상품'])['보장'].sum().reset_index().assign(Cost=0))
            except: continue

        # 토스 파일 후처리 (기존 로직 유지)
        for fname, df in toss_files:
            df = find_header_and_reload(df, '소진 비용')
            if '소진 비용' in df.columns:
                df['Cost'] = df['소진 비용'].apply(clean_currency) * 1.1
                df['상품'] = df['캠페인 명'].apply(classify_product)
                df['매체'] = '토스'
                dfs.append(df.groupby(['매체', '상품'])['Cost'].sum().reset_index().assign(보장=0))

    if not dfs: return None
    final_df = pd.concat(dfs, ignore_index=True).groupby(['매체', '상품']).sum().reset_index()
    final_df['CPA'] = final_df.apply(lambda x: x['Cost'] / x['보장'] if x['보장'] > 0 else 0, axis=1)
    return final_df

# [기존 convert_to_stats 함수 동일 유지]
def convert_to_stats(final_df, manual_aff_cnt, manual_aff_cost, manual_da_cnt, manual_da_cost):
    media_list = ['네이버', '카카오', '토스', '구글', '제휴', '기타']
    stats = pd.DataFrame(index=media_list, columns=['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA']).fillna(0)
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
    
    res = {'da_cost': int(stats.drop('제휴')['Cost'].sum()), 'da_cnt': int(stats.drop('제휴')['Total_Cnt'].sum()),
           'da_bojang': int(stats.drop('제휴')['Bojang_Cnt'].sum()), 'da_prod': int(stats.drop('제휴')['Prod_Cnt'].sum()),
           'aff_cost': int(stats.loc['제휴', 'Cost']), 'aff_cnt': int(stats.loc['제휴', 'Total_Cnt']),
           'bojang_cnt': int(stats['Bojang_Cnt'].sum()), 'prod_cnt': int(stats['Prod_Cnt'].sum()), 'media_stats': stats}
    res['total_cost'], res['total_cnt'] = res['da_cost'] + res['aff_cost'], res['da_cnt'] + res['aff_cnt']
    res['ratio_ba'] = res['bojang_cnt'] / res['total_cnt'] if res['total_cnt'] > 0 else 0.898
    return res

# -----------------------------------------------------------
# MODE: V18.35 Master
# -----------------------------------------------------------
def run_v18_35_master():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.35 Ultimate)")
    
    with st.sidebar:
        st.header("1. 데이터 소스 선택")
        use_gsheets = st.toggle("🌐 구글 시트 RAW 연결", value=True)
        
        st.header("2. 기본 설정")
        current_time_str = st.select_slider("⏱️ 현재 기준", options=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"], value="14:00")
        day_option = st.selectbox("요일", ['월', '화', '수', '목', '금'], index=0)
        
        st.header("3. 목표 수립")
        active_member = st.number_input("활동 인원", value=359)
        target_bojang = st.number_input("보장 목표", value=500)
        target_product = st.number_input("상품 목표", value=3100)
        sa_est_bojang = st.number_input("SA 보장", value=200)
        sa_est_prod = st.number_input("SA 상품", value=800)
        
        da_target_bojang = target_bojang - sa_est_bojang
        da_target_prod = target_product - sa_est_prod
        da_target_18 = da_target_bojang + da_target_prod
        target_ratio_ba = da_target_bojang / da_target_18 if da_target_18 > 0 else 0.898

        st.header("4. 실시간 파일 업로드")
        uploaded_realtime = st.file_uploader("파일 추가 (구글 시트 미연동 매체용)", accept_multiple_files=True)
        
        manual_da_cnt = st.number_input("DA 추가 건", value=0)
        manual_da_cost = st.number_input("DA 추가 액", value=0)
        manual_aff_cost = st.number_input("제휴 소진액", value=11270000) 
        manual_aff_cpa = st.number_input("제휴 단가", value=14000)
        manual_aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0

        # --- 데이터 처리 실행 ---
        final_df = process_marketing_data(uploaded_realtime, use_gsheets=use_gsheets)
        res = convert_to_stats(final_df, manual_aff_cnt, manual_aff_cost, manual_da_cnt, manual_da_cost)

    # [이후 시각화 및 탭 구성 로직은 기존 코드와 동일하게 흐름...]
    # (코드 중복 방지를 위해 생략하지만, 실제 파일에는 기존의 Tab0~Tab4 내용을 그대로 유지하시면 됩니다.)
    
    # --- 대시보드 출력 부분 (기존 코드 참조) ---
    st.subheader(f"📊 실시간 DA 현황 대시보드 ({current_time_str})")
    # ... (기존 Tab 로직 코드들)
    # [리더님 코드의 Tab0 ~ Tab4 내용을 여기에 그대로 붙여넣으세요]
    
    # 예시: 
    progress = min(1.0, res['total_cnt']/da_target_18) if da_target_18 > 0 else 0
    st.metric("현재 실적", f"{res['total_cnt']:,}건", f"{progress*100:.1f}%")
    st.progress(progress)

def main():
    st.sidebar.title("⚙️ 시스템 버전")
    version = st.sidebar.selectbox("선택", ["V18.35 (UI 업데이트)", "V6.6 (Legacy)"])
    if version == "V18.35 (UI 업데이트)": run_v18_35_master()
    else: st.warning("레거시 모드는 제외되었습니다.")

if __name__ == "__main__":
    main()
