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
# 1. 유틸리티 함수 (기존 로직 보존)
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
    for enc in ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'utf-8-sig']:
        try:
            file.seek(0)
            return pd.read_csv(file, encoding=enc, on_bad_lines='skip', **kwargs)
        except: continue
    return None

def parse_files_by_rules(files):
    df_cost = pd.DataFrame(); df_db = pd.DataFrame()
    for file in files:
        fname = file.name; temp = pd.DataFrame(); df = None
        try:
            if "메리츠 화재_전략광고3팀_배너광고_캠페인" in fname:
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
            elif "메리츠화재다이렉트_캠페인" in fname:
                df = read_file_safe(file, sep='\t')
                if df is not None:
                    col_cost = '비용' if '비용' in df.columns else None
                    col_camp = '캠페인' if '캠페인' in df.columns else None
                    if col_cost and col_camp:
                        temp['cost'] = df[col_cost].apply(clean_num) * 1.1
                        temp['campaign'] = df[col_camp].fillna('')
                        temp['type'] = temp['campaign'].apply(classify_type_by_name)
                        temp['media'] = '카카오'; df_cost = pd.concat([df_cost, temp], ignore_index=True)
            elif "result" in fname:
                df = read_file_safe(file)
                if df is not None:
                    col_cost = next((c for c in df.columns if '총 비용' in str(c)), None)
                    col_camp = next((c for c in df.columns if '캠페인 이름' in str(c)), None)
                    if col_cost and col_camp:
                        temp['cost'] = df[col_cost].apply(clean_num)
                        temp['campaign'] = df[col_camp].fillna('')
                        temp['type'] = temp['campaign'].apply(classify_type_by_name)
                        temp['media'] = '네이버'; df_cost = pd.concat([df_cost, temp], ignore_index=True)
            elif "캠페인 보고서" in fname:
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
            elif "Performance Lab" in fname:
                df = read_file_safe(file)
                if df is not None:
                    df.columns = df.columns.astype(str).str.strip()
                    s_col = next((c for c in df.columns if 'METIS전송' in c and '율' not in c), None)
                    f_col = next((c for c in df.columns if 'METIS실패' in c), None)
                    r_col = next((c for c in df.columns if 'METIS재인입' in c), None)
                    if s_col:
                        cnts = df[s_col].apply(clean_num)
                        if f_col: cnts -= df[f_col].apply(clean_num)
                        if r_col: cnts -= df[r_col].apply(clean_num)
                        temp['count'] = cnts
                        temp['account'] = df.get('account', '').fillna('')
                        temp['구분'] = df.get('구분', '').fillna('')
                        temp['type'] = temp['구분'].apply(classify_type_by_name)
                        temp['media'] = temp.apply(get_media_from_plab, axis=1)
                        df_db = pd.concat([df_db, temp], ignore_index=True)
        except: continue
    return df_cost, df_db

def get_plab_stats(df):
    if df is None or df.empty: return 0, 0
    b = int(df[df['type'] == '보장']['count'].sum())
    p = int(df[df['type'] == '상품']['count'].sum())
    return b, p

# -----------------------------------------------------------
# 3. 데이터 집계 함수 (기존 aggregate_data_v2 기반)
# -----------------------------------------------------------
def aggregate_data_v2(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt):
    media_list = ['네이버', '카카오', '토스', '구글', '제휴', '기타']
    stats = pd.DataFrame(index=media_list, columns=['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA']).fillna(0)
    if not df_cost.empty:
        cost_grp = df_cost.groupby('media')['cost'].sum()
        for m, val in cost_grp.items():
            if m in stats.index: stats.loc[m, 'Cost'] += val
            else: stats.loc['기타', 'Cost'] += val
    if not df_db.empty:
        cnt_grp = df_db.groupby(['media', 'type'])['count'].sum()
        for (m, t), val in cnt_grp.items():
            target_media = m if m in stats.index else '기타'
            if t == '보장': stats.loc[target_media, 'Bojang_Cnt'] += val
            else: stats.loc[target_media, 'Prod_Cnt'] += val
    if manual_da_cnt > 0 or manual_da_cost > 0:
        stats.loc['기타', 'Prod_Cnt'] += manual_da_cnt
        stats.loc['기타', 'Cost'] += manual_da_cost
    if manual_aff_cnt > 0 or manual_aff_cost > 0:
        stats.loc['제휴', 'Bojang_Cnt'] = manual_aff_cnt
        stats.loc['제휴', 'Cost'] = manual_aff_cost
    stats['Total_Cnt'] = stats['Bojang_Cnt'] + stats['Prod_Cnt']
    stats['CPA'] = stats.apply(lambda x: x['Cost'] / x['Total_Cnt'] if x['Total_Cnt'] > 0 else 0, axis=1)
    res = {
        'da_cost': int(stats.drop('제휴')['Cost'].sum()), 'da_cnt': int(stats.drop('제휴')['Total_Cnt'].sum()),
        'da_bojang': int(stats.drop('제휴')['Bojang_Cnt'].sum()), 'da_prod': int(stats.drop('제휴')['Prod_Cnt'].sum()),
        'aff_cost': int(stats.loc['제휴', 'Cost']), 'aff_cnt': int(stats.loc['제휴', 'Total_Cnt']),
        'bojang_cnt': int(stats['Bojang_Cnt'].sum()), 'prod_cnt': int(stats['Prod_Cnt'].sum()),
        'media_stats': stats
    }
    res['total_cost'] = res['da_cost'] + res['aff_cost']
    res['total_cnt'] = res['da_cnt'] + res['aff_cnt']
    res['ratio_ba'] = res['bojang_cnt'] / res['total_cnt'] if res['total_cnt'] > 0 else 0.898
    return res

# -----------------------------------------------------------
# 4. 앱 메인 실행 함수
# -----------------------------------------------------------
def run_v18_35_master():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.35 Ultimate)")

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
        da_target_18 = da_target_bojang + da_target_prod
        target_ratio_ba = da_target_bojang / da_target_18 if da_target_18 > 0 else 0.898

        st.header("3. 10시 자원 산출")
        mode_10 = st.radio("입력 방식", ["파일 업로드", "수기 입력"], horizontal=True)
        start_b, start_p, t10_b, t10_p = 0, 0, 0, 0
        if mode_10 == "파일 업로드":
            with st.expander("📂 피랩 파일 3개 업로드"):
                f18 = st.file_uploader("어제 18시", key="f18")
                f24 = st.file_uploader("어제 24시", key="f24")
                f10 = st.file_uploader("오늘 10시", key="f10")
            if f18 and f24 and f10:
                _, db18 = parse_files_by_rules([f18]); _, db24 = parse_files_by_rules([f24]); _, db10 = parse_files_by_rules([f10])
                b18, p18 = get_plab_stats(db18); b24, p24 = get_plab_stats(db24); t10_b, t10_p = get_plab_stats(db10)
                start_b = (b24 - b18) + t10_b; start_p = (p24 - p18) + t10_p
                st.success(f"10시 산출: 보장 {start_b:,} / 상품 {start_p:,}")
        else:
            col_b1, col_b2 = st.columns(2)
            start_b = col_b1.number_input("10시 보장", value=300)
            start_p = col_b2.number_input("10시 상품", value=800)
            t10_b, t10_p = int(start_b*0.6), int(start_p*0.6) # 임의 기준값
        start_total = start_b + start_p

        st.header("4. 실시간 분석")
        rt_files = st.file_uploader("실시간 파일 (다중 선택)", accept_multiple_files=True)
        col_m1, col_m2 = st.columns(2)
        with col_m1: manual_da_cnt, manual_da_cost = st.number_input("DA 추가 건", 0), st.number_input("DA 추가 액", 0)
        with col_m2: manual_aff_cost, manual_aff_cpa = st.number_input("제휴 소진액", 11270000), st.number_input("제휴 단가", 14000)
        aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0

        st.header("5. 보고 설정")
        tom_member = st.number_input("명일 인원", value=350)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 계산 로직 ---
    df_cost, df_db = parse_files_by_rules(rt_files) if rt_files else (pd.DataFrame(), pd.DataFrame())
    curr_rt_b, curr_rt_p = get_plab_stats(df_db)
    
    # [로직] 최종 실적 = 10시 시작자원 + (현재 피랩 - 10시 피랩)
    final_bojang = start_b + max(0, curr_rt_b - t10_b) + aff_cnt
    final_prod = start_p + max(0, curr_rt_p - t10_p)
    final_total = final_bojang + final_prod
    
    # 실적 상세 집계 (표용)
    res = aggregate_data_v2(df_cost, df_db, manual_aff_cost, aff_cnt, manual_da_cost, manual_da_cnt)
    res['total_cnt'] = final_total; res['bojang_cnt'] = final_bojang; res['prod_cnt'] = final_prod
    
    # 시간대별 목표 계산
    hours = ["10시","11시","12시","13시","14시","15시","16시","17시","18시"]
    weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
    acc_goals = [start_total]; gap = da_target_18 - start_total
    for w in weights[1:]: acc_goals.append(acc_goals[-1] + int(gap * (w / sum(weights[1:]))))
    acc_goals[-1] = int(da_target_18)
    
    cur_idx = hours.index(current_time_str.replace(":00", "시").replace("09:30", "10시"))
    cur_goal = acc_goals[cur_idx]

    # --- 탭 출력 ---
    tab0, tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 대시보드", "🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근", "🔍 검증"])

    with tab0:
        st.subheader(f"📊 실시간 DA 현황 대시보드 ({current_time_str})")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("최종 목표", f"{da_target_18:,}건"); st.markdown(f":grey[보장 {da_target_bojang:,} / 상품 {da_target_prod:,}]")
        with c2: 
            gap_val = final_total - cur_goal; color = "normal" if gap_val >= 0 else "inverse"
            st.metric("현재 실적", f"{final_total:,}건", f"{(final_total/cur_goal*100):.1f}% (Gap {gap_val:+,})", delta_color=color)
            st.markdown(f":grey[보장 {final_bojang:,} / 상품 {final_prod:,}]")
        with c3:
            time_mul = {"09:30":1.0,"10:00":1.75,"11:00":1.65,"12:00":1.55,"13:00":1.45,"14:00":1.35,"15:00":1.25,"16:00":1.15,"17:00":1.05,"18:00":1.0}
            est_final = int(final_total * time_mul.get(current_time_str, 1.35))
            st.metric("마감 예상", f"{est_final:,}건", f"Gap: {est_final - da_target_18}"); st.markdown(f":grey[보장 {int(est_final*res['ratio_ba']):,} / 상품 {est_final - int(est_final*res['ratio_ba']):,}]")
        with c4: st.metric("현재 CPA", f"{(res['total_cost']/final_total/10000 if final_total>0 else 0):.1f}만원"); st.markdown(f":grey[DA {(res['da_cost']/res['da_cnt']/10000 if res['da_cnt']>0 else 0):.1f} / 제휴 {(res['aff_cost']/res['aff_cnt']/10000 if res['aff_cnt']>0 else 0):.1f}]")
        
        st.progress(min(1.0, final_total/da_target_18) if da_target_18 > 0 else 0)
        
        d1, d2 = st.columns(2)
        with d1:
            st.markdown("##### 📌 시간대별 목표 상세")
            df_dash_goal = pd.DataFrame({'누적 목표': [f"{x:,}" for x in acc_goals], '보장 목표': [f"{int(x*target_ratio_ba):,}" for x in acc_goals], '상품 목표': [f"{int(x*(1-target_ratio_ba)):,}" for x in acc_goals]}, index=hours).T
            st.dataframe(df_dash_goal, use_container_width=True)
        with d2:
            st.markdown("##### 📌 매체별 실적 상세")
            ms = res['media_stats'].copy(); ms.loc['합계'] = ms.sum(numeric_only=True)
            ms.columns = ['보장분석','상품','비용','CPA','토탈']; ms = ms[['토탈','상품','보장분석','비용','CPA']]
            st.dataframe(ms.style.format("{:,.0f}"), use_container_width=True)

    with tab1:
        st.subheader("📋 오전 목표 수립 (09:30)")
        hourly_sec = [start_total]; [hourly_sec.append(acc_goals[i] - acc_goals[i-1]) for i in range(1, 9)]
        df_client = pd.DataFrame({"구분": ["누적자원", "인당배분", "시간당 확보"], **{h: [f"{acc_goals[i]:,}", f"{round(acc_goals[i]/active_member, 1) if active_member>0 else 0}", f"{hourly_sec[i]:,}"] for i, h in enumerate(hours)}})
        st.table(df_client.set_index("구분"))
        st.text_area("복사 텍스트:", f"금일 DA+제휴 예상마감 공유드립니다.\n\n[18시 기준] 총 자원 : {da_target_18:,}건 ({active_member}명)\nㄴ 보장 : {da_target_bojang:,}건 / 상품 : {da_target_prod:,}건\n\n* {fixed_content if fixed_ad_type!='없음' else '특이사항 없음'}", height=200)

    with tab2:
        st.subheader("🔥 14:00 중간 보고")
        st.text_area("복사 (14시):", f"DA 14시 현황: 총 {final_total:,}건 (인당 {round(final_total/active_member, 1) if active_member else 0}건)\n예상 마감: {est_final:,}건\nㄴ 보장: {int(est_final*res['ratio_ba']):,}건, 상품: {est_final - int(est_final*res['ratio_ba']):,}건", height=200)

    with tab3:
        st.subheader("⚠️ 16:00 마감 보고")
        st.text_area("복사 (16시):", f"DA 16시 현황: 총 {final_total:,}건\nㄴ 보장: {final_bojang:,}건, 상품: {final_prod:,}건", height=150)

    with tab4:
        st.subheader("🌙 퇴근 보고")
        tom_total = int(tom_member * 3.15); st.text_area("복사 (퇴근):", f"명일 예상 자원: {tom_total:,}건\nㄴ 보장: {int(tom_total*target_ratio_ba):,}건, 상품: {int(tom_total*(1-target_ratio_ba)):,}건", height=150)

    with tab5:
        st.subheader("🔍 데이터 검증"); st.dataframe(df_db.head(100))

if __name__ == "__main__":
    run_v18_35_master()
