import streamlit as st
import pandas as pd
import platform
import io
import warnings
import zipfile
import xml.etree.ElementTree as ET
import re

# 경고 무시
warnings.simplefilter("ignore")

# -----------------------------------------------------------
# 0. 공통 설정 및 폰트
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
# 1. 유틸리티 함수
# -----------------------------------------------------------
def clean_num(x):
    if pd.isna(x) or x == '': return 0.0
    try:
        if isinstance(x, str):
            return float(x.replace(',', '').replace('"', '').strip())
        return float(x)
    except: return 0.0

def classify_type(name):
    name = str(name)
    return '보장' if '보장' in name or '누적' in name else '상품'

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
# 2. 파일 로더 (엑셀 스타일 에러 대응 XML 파서 포함)
# -----------------------------------------------------------
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
                    if t_tag is not None:
                        strings.append(t_tag.text)
                    else:
                        strings.append("".join([t.text for t in si.findall('.//ns:t', ns) if t.text]))
        
        sheet_path = 'xl/worksheets/sheet1.xml'
        with z.open(sheet_path) as f:
            root = ET.parse(f).getroot()
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

def read_file(file):
    name = file.name.lower()
    file.seek(0)
    if name.endswith(('.xlsx', '.xls')):
        df = load_excel_safe(file)
        if df is None:
            try: df = pd.read_excel(file, engine='openpyxl')
            except: return None
        return df
    for enc in ['utf-8', 'cp949', 'utf-16']:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc, on_bad_lines='skip')
        except: continue
    return None

def get_plab_counts(df):
    if df is None: return 0, 0
    df.columns = df.columns.astype(str).str.strip()
    s_col = next((c for c in df.columns if 'METIS전송' in c and '율' not in c), None)
    f_col = next((c for c in df.columns if 'METIS실패' in c), None)
    r_col = next((c for c in df.columns if 'METIS재인입' in c), None)
    if not s_col: return 0, 0
    
    cnts = df[s_col].apply(clean_num)
    if f_col: cnts -= df[f_col].apply(clean_num)
    if r_col: cnts -= df[r_col].apply(clean_num)
    
    df['type'] = df['구분'].apply(classify_type)
    return int(cnts[df['type'] == '보장'].sum()), int(cnts[df['type'] == '상품'].sum())

# -----------------------------------------------------------
# 3. 실시간 매체별 통합 데이터 처리 (네이버/카카오/토스/구글/피랩)
# -----------------------------------------------------------
def process_realtime_data(uploaded_files):
    dfs = []
    toss_files = []
    
    for file in uploaded_files:
        df = read_file(file)
        if df is None: continue
        filename = file.name
        df.columns = df.columns.astype(str).str.strip()
        
        try:
            temp = pd.DataFrame()
            if 'result' in filename: # 네이버
                temp['Cost'] = df['총 비용'].apply(clean_num)
                temp['상품'] = df['캠페인 이름'].apply(classify_type)
                temp['매체'] = '네이버'
                temp['건수'] = 0
            elif '메리츠화재다이렉트' in filename: # 카카오
                temp['Cost'] = df['비용'].apply(clean_num) * 1.1
                temp['상품'] = df['캠페인'].apply(classify_type)
                temp['매체'] = '카카오'
                temp['건수'] = 0
            elif '메리츠 화재' in filename: # 토스
                toss_files.append((filename, df))
                continue
            elif '캠페인 보고서' in filename: # 구글
                if '캠페인' in df.columns: df = df[df['캠페인'].notna()]
                temp['Cost'] = df['비용'].apply(clean_num) * 1.1 * 1.15 if '비용' in df.columns else 0
                temp['상품'] = df['캠페인'].apply(classify_type)
                temp['매체'] = '구글'
                temp['건수'] = 0
            elif 'Performance Lab' in filename: # 피랩
                b, p = get_plab_counts(df)
                # 매체별 상세를 위해 피랩 로직 적용
                df['cnt'] = df.get('cnt', 0) # get_plab_counts 내에서 계산되나 여기서는 별도 그룹화 필요
                # (중복 방지를 위해 상세 매체 데이터 구성)
                plab_temp = pd.DataFrame({
                    '매체': df.apply(get_media_from_plab, axis=1),
                    '상품': df['구분'].apply(classify_type),
                    '건수': 0 # 실제 건수는 get_plab_counts로 받은 전체값 사용 또는 행별 계산
                })
                # 피랩 행별 유효건수 재계산
                s_col = next((c for c in df.columns if 'METIS전송' in c), None)
                f_col = next((c for c in df.columns if 'METIS실패' in c), None)
                r_col = next((c for c in df.columns if 'METIS재인입' in c), None)
                plab_temp['건수'] = df[s_col].apply(clean_num)
                if f_col: plab_temp['건수'] -= df[f_col].apply(clean_num)
                if r_col: plab_temp['건수'] -= df[r_col].apply(clean_num)
                plab_temp['Cost'] = 0
                dfs.append(plab_temp)
                continue

            if not temp.empty:
                dfs.append(temp.groupby(['매체', '상품']).sum(numeric_only=True).reset_index())
        except: continue

    # 토스 후처리
    if toss_files:
        toss_main = next((f for f in toss_files if '통합' in f[0]), None)
        targets = [toss_main] if toss_main else toss_files
        for fname, df in targets:
            try:
                # 헤더 보정
                if '소진 비용' not in df.columns:
                    for i, r in df.head(10).iterrows():
                        if '소진 비용' in [str(v).strip() for v in r.values]:
                            df.columns = [str(v).strip() for v in r.values]; df = df.iloc[i+1:]; break
                if '소진 비용' in df.columns:
                    t_temp = pd.DataFrame()
                    t_temp['Cost'] = df['소진 비용'].apply(clean_num) * 1.1
                    t_temp['상품'] = df['캠페인 명'].apply(classify_type)
                    t_temp['매체'] = '토스'
                    t_temp['건수'] = 0
                    dfs.append(t_temp.groupby(['매체', '상품']).sum(numeric_only=True).reset_index())
            except: pass

    if not dfs: return pd.DataFrame(columns=['매체', '상품', 'Cost', '건수'])
    return pd.concat(dfs).groupby(['매체', '상품']).sum(numeric_only=True).reset_index()

# -----------------------------------------------------------
# 4. 앱 실행 함수
# -----------------------------------------------------------
def main():
    st.title("📊 메리츠화재 통합 리포트 시스템 V18.35")
    
    with st.sidebar:
        st.header("1. 기본 설정")
        current_hour_str = st.select_slider("⏱️ 현재 기준 시간", options=["10시","11시","12시","13시","14시","15시","16시","17시","18시"], value="14시")
        active_member = st.number_input("활동 인원", value=359)
        
        st.header("2. 목표 수립 (DA)")
        c1, c2 = st.columns(2)
        da_target_bojang = c1.number_input("보장 목표", value=300) # (보장 500 - SA 200)
        da_target_prod = c2.number_input("상품 목표", value=2350) # (상품 3100 - SA 800 + 버퍼 50)
        da_target_total = da_target_bojang + da_target_prod

        st.header("3. 10시 시작자원 설정")
        mode = st.radio("입력 방식", ["파일 업로드", "수기 입력"])
        start_b, start_p = 0, 0
        if mode == "파일 업로드":
            with st.expander("📂 피랩 파일 3개 업로드"):
                f18 = st.file_uploader("전일 18시", key="f18")
                f24 = st.file_uploader("전일 24시", key="f24")
                f10 = st.file_uploader("오늘 10시", key="f10")
            if f18 and f24 and f10:
                b18, p18 = get_plab_counts(read_file(f18))
                b24, p24 = get_plab_counts(read_file(f24))
                b10, p10 = get_plab_counts(read_file(f10))
                start_b = (b24 - b18) + b10
                start_p = (p24 - p18) + p10
                st.success(f"산출: 보장 {start_b:,} / 상품 {start_p:,}")
        else:
            c3, c4 = st.columns(2)
            start_b = c3.number_input("10시 보장", value=300)
            start_p = c4.number_input("10시 상품", value=800)
        start_total = start_b + start_p

        st.header("4. 실시간/제휴 설정")
        rt_files = st.file_uploader("실시간 매체 파일들", accept_multiple_files=True)
        aff_cost = st.number_input("제휴 소진액", value=11270000)
        aff_cpa = st.number_input("제휴 단가", value=14000)
        aff_cnt = int(aff_cost / aff_cpa) if aff_cpa > 0 else 0

    # --- 데이터 계산 ---
    df_res = process_realtime_data(rt_files) if rt_files else pd.DataFrame()
    
    # 현재 피랩 실적 (실시간 파일에서 추출)
    curr_b = int(df_res[df_res['상품']=='보장']['건수'].sum()) if not df_res.empty else 0
    curr_p = int(df_res[df_res['상품']=='상품']['건수'].sum()) if not df_res.empty else 0
    
    # [로직 3] 최종 실적 = 10시 자원 + 현재 실적
    final_bojang = start_b + curr_b + aff_cnt # 제휴는 보장에 합산
    final_prod = start_p + curr_p
    final_total = final_bojang + final_prod
    
    # 시간대별 가중치 목표
    hours = ["10시","11시","12시","13시","14시","15시","16시","17시","18시"]
    weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
    acc_goals = [start_total]
    gap = da_target_total - start_total
    for w in weights[1:]:
        acc_goals.append(acc_goals[-1] + int(gap * (w / sum(weights[1:]))))
    acc_goals[-1] = da_target_total
    
    cur_idx = hours.index(current_hour_str)
    cur_target = acc_goals[cur_idx]

    # --- 탭 출력 ---
    t1, t2, t3 = st.tabs(["📊 대시보드", "🌅 09:30 목표 수립", "🔍 매체별 상세"])

    with t1:
        st.subheader(f"💡 실시간 달성 현황 ({current_hour_str})")
        m1, m2, m3 = st.columns(3)
        
        # 색상 스타일 함수
        def color_val(v):
            color = "blue" if v >= 0 else "red"
            return f"<span style='color:{color}; font-weight:bold;'>{v:+,}</span>"

        with m1:
            st.metric("총 실적 (DA+제휴)", f"{final_total:,}건")
            st.write(f"목표 대비: {color_val(final_total - cur_target)}", unsafe_allow_html=True)
            st.write(f"달성률: **{final_total/cur_target*100:.1f}%**")
        with m2: st.metric("보장 분석 (제휴포함)", f"{final_bojang:,}건")
        with m3: st.metric("상품 자원", f"{final_prod:,}건")
        
        st.divider()
        st.markdown("#### 📉 시간대별 목표 상세")
        
        real_row = [""] * 9
        real_row[0], real_row[cur_idx] = f"{start_total:,}", f"{final_total:,}"
        gap_row = [""] * 9
        gap_row[0] = color_val(start_total - acc_goals[0])
        gap_row[cur_idx] = color_val(final_total - acc_goals[cur_idx])

        df_dash = pd.DataFrame({
            "구분": ["누적 목표", "누적 실적", "차이(Gap)"],
            **{h: [f"{acc_goals[i]:,}", real_row[i], gap_row[i]] for i, h in enumerate(hours)}
        })
        st.write(df_dash.to_html(escape=False, index=False), unsafe_allow_html=True)

    with t2:
        st.subheader("📋 광고주 보고용 목표 (09:30)")
        
        # [로직 1] 누적자원 / 인당배분 / 시간당 확보
        hourly_sec = [start_total]
        for i in range(1, 9): hourly_sec.append(acc_goals[i] - acc_goals[i-1])
        per_member = [round(x / active_member, 1) if active_member > 0 else 0 for x in acc_goals]
        
        df_client = pd.DataFrame({
            "구분": ["누적자원", "인당배분", "시간당 확보"],
            **{h: [f"{acc_goals[i]:,}", f"{per_member[i]}", f"{hourly_sec[i]:,}"] for i, h in enumerate(hours)}
        })
        st.table(df_client.set_index("구분"))
        
        st.text_area("카톡 보고용 텍스트", f"""금일 DA+제휴 예상 시작 자원 공유드립니다.

- 총 시작 자원 : {start_total:,}건
  ㄴ 보장 : {start_b:,}건
  ㄴ 상품 : {start_p:,}건

* 전일 야간 및 금일 오전 효율 기반으로 산출되었습니다.""", height=150)

    with t3:
        st.subheader("매체별 비용 및 건수 집계")
        if not df_res.empty:
            # 매체별 합계 표
            summary = df_res.groupby('매체').sum(numeric_only=True).reset_index()
            # 제휴 추가
            summary = pd.concat([summary, pd.DataFrame([{'매체':'제휴', 'Cost':aff_cost, '건수':aff_cnt}])], ignore_index=True)
            summary['CPA'] = summary.apply(lambda x: x['Cost']/x['건수'] if x['건수']>0 else 0, axis=1)
            st.dataframe(summary.style.format({'Cost': '{:,.0f}', '건수': '{:,.0f}', 'CPA': '{:,.0f}'}))

if __name__ == "__main__":
    main()
