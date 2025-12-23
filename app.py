import streamlit as st
import pandas as pd
import platform
import io
import warnings

# 경고 메시지 무시
warnings.simplefilter("ignore")

# -----------------------------------------------------------
# 0. 공통 설정
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V18.1", layout="wide")

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
# 1. 유틸리티 함수 (Smart File Reader & Dual Track)
# -----------------------------------------------------------
def read_file_smart(file):
    """
    파일의 형식(CSV/Excel/Tab)과 헤더 위치를 자동으로 찾아 읽어오는 똑똑한 함수
    """
    # 인식해야 할 핵심 키워드들
    header_keywords = ['캠페인', 'Campaign', '광고명', '매체', '구분', 'media group', 'account']
    
    try:
        fname = file.name.lower()
        
        # 1. 엑셀 파일 시도
        if fname.endswith(('.xlsx', '.xls')):
            try:
                # 헤더 찾기
                temp_df = pd.read_excel(file, header=None, nrows=30)
                header_idx = find_header_row(temp_df, header_keywords)
                if header_idx is not None:
                    file.seek(0)
                    return pd.read_excel(file, header=header_idx)
            except: pass

        # 2. CSV / 텍스트 파일 시도 (쉼표 & 탭)
        # 여러 인코딩과 구분자를 순회하며 시도
        encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
        separators = [',', '\t']
        
        for enc in encodings:
            for sep in separators:
                try:
                    file.seek(0)
                    # 일단 앞부분만 읽어서 헤더 위치 파악
                    # sep=None은 파이썬 엔진을 써야해서 느리므로 명시적 sep 사용 권장
                    temp_lines = [file.readline().decode(enc) for _ in range(30)]
                    
                    header_idx = -1
                    for i, line in enumerate(temp_lines):
                        if any(k in line for k in header_keywords):
                            header_idx = i
                            break
                    
                    if header_idx != -1:
                        file.seek(0)
                        df = pd.read_csv(file, encoding=enc, sep=sep, header=header_idx, on_bad_lines='skip')
                        # 읽은 데이터가 유효한지(컬럼이 제대로 파싱됐는지) 확인
                        if len(df.columns) > 1:
                            return df
                except: continue
                
    except Exception as e:
        # st.error(f"파일 읽기 실패: {file.name} / {e}")
        pass
        
    return None

def find_header_row(df, keywords):
    """데이터프레임 상위 행에서 키워드가 있는 행 번호 반환"""
    for i in range(len(df)):
        row_str = str(df.iloc[i].values)
        if any(k in row_str for k in keywords):
            return i
    return None

def parse_files_dual_track(files):
    df_cost_source = pd.DataFrame() 
    df_db_source = pd.DataFrame()   
    
    # 컬럼 매핑 사전
    col_map = {
        'cost': ['비용', '소진', 'Cost', '금액', '총 비용'],
        'count': ['계', '합계', '보장분석', '전환', 'DB', '건수', '잠재고객', '결과'], # '결과'는 네이버용
        'media': ['media', 'account', '매체', '그룹', '캠페인'],
        'type': ['구분', 'type', '캠페인']
    }

    for file in files:
        df = read_file_smart(file)
        if df is None or df.empty: continue
        
        fname = file.name.lower()
        is_plab = 'performance' in fname or 'lab' in fname or '피랩' in fname
        
        # [데이터 클렌징] 컬럼명 공백 제거
        df.columns = [str(c).strip() for c in df.columns]
        
        # [중요] 네이버 GFA '결과' 컬럼 필터링 (클릭수 제외)
        if '결과 유형' in df.columns and '결과' in df.columns:
            # '클릭'이 포함된 행은 제외
            df = df[~df['결과 유형'].astype(str).str.contains('클릭', na=False)]

        if is_plab:
            # [Track B] 피랩 -> DB 건수 추출
            col_cnt = find_col(df, col_map['count'])
            col_media = find_col(df, ['media', 'account', '매체'])
            col_type = find_col(df, ['구분', 'type'])
            
            if col_cnt:
                temp = pd.DataFrame()
                temp['count'] = df[col_cnt].apply(clean_num).fillna(0)
                temp['media_raw'] = df[col_media].fillna('기타') if col_media else '기타'
                temp['type_raw'] = df[col_type].fillna('') if col_type else ''
                temp['source'] = 'PLAB'
                df_db_source = pd.concat([df_db_source, temp], ignore_index=True)
        else:
            # [Track A] Raw -> 비용 추출
            col_cost = find_col(df, col_map['cost'])
            col_camp = find_col(df, ['캠페인', 'Campaign', '광고명'])
            
            if col_cost and col_camp:
                temp = pd.DataFrame()
                temp['cost'] = df[col_cost].apply(clean_num).fillna(0)
                temp['campaign'] = df[col_camp].fillna('기타')
                temp['source'] = 'RAW'
                df_cost_source = pd.concat([df_cost_source, temp], ignore_index=True)

    return df_cost_source, df_db_source

def find_col(df, keywords):
    for col in df.columns:
        # 정확도 높이기 위해 블랙리스트 적용 (예: '비용' 찾는데 '결과당 비용'은 제외)
        if any(k in str(col) for k in keywords):
            # 예외 처리: '결과당 비용'은 비용 컬럼이 아님 (단가임)
            if '당 비용' in str(col) or 'CPM' in str(col) or 'CPC' in str(col): continue
            return col
    return None

def clean_num(x):
    try: return float(str(x).replace(',', '').replace('"', '').replace(' ', ''))
    except: return 0

def normalize_media(text):
    text = str(text).lower()
    if any(x in text for x in ['네이버', 'naver', 'gfa', 'nasp']): return '네이버'
    if any(x in text for x in ['카카오', 'kakao', 'kakaoment', '비즈보드']): return '카카오'
    if any(x in text for x in ['토스', 'toss']): return '토스'
    if any(x in text for x in ['구글', 'google', 'youtube', 'pmax']): return '구글'
    if any(x in text for x in ['제휴', 'affiliate']): return '제휴'
    return '기타'

def classify_type(text):
    text = str(text).lower()
    if '보장' in text: return '보장'
    return '상품'

def aggregate_dual_source(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt):
    stats = pd.DataFrame(columns=['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA'])
    
    # 1. 비용 집계
    if not df_cost.empty:
        df_cost['media_group'] = df_cost['campaign'].apply(normalize_media)
        cost_grp = df_cost.groupby('media_group')['cost'].sum()
        for media, val in cost_grp.items():
            if media not in stats.index: stats.loc[media] = [0, 0, 0, 0]
            stats.loc[media, 'Cost'] += val

    # 2. DB 집계
    if not df_db.empty:
        df_db['media_group'] = df_db['media_raw'].apply(normalize_media)
        df_db['type_group'] = df_db['type_raw'].apply(classify_type)
        
        # 피랩에서 '계' 컬럼을 가져오면 전체 합이므로, 보장분석만 따로 발라내거나 '계'를 씀.
        # 보통 피랩 '계'는 (보장 + 상품) 합계임.
        # 여기서는 'type_group'으로 나눴으므로 각각 더하면 됨.
        cnt_grp = df_db.groupby(['media_group', 'type_group'])['count'].sum()
        for (media, type_), val in cnt_grp.items():
            if media not in stats.index: stats.loc[media] = [0, 0, 0, 0]
            if type_ == '보장':
                stats.loc[media, 'Bojang_Cnt'] += val
            else:
                stats.loc[media, 'Prod_Cnt'] += val

    # 3. 수기 입력 (DA 추가)
    if manual_da_cnt > 0 or manual_da_cost > 0:
        if '기타(수기)' not in stats.index: stats.loc['기타(수기)'] = [0, 0, 0, 0]
        stats.loc['기타(수기)', 'Prod_Cnt'] += manual_da_cnt
        stats.loc['기타(수기)', 'Cost'] += manual_da_cost

    # 4. 수기 입력 (제휴 Override)
    # 기존에 '제휴'로 잡힌게 있으면 삭제하고 수기값으로 대체
    if manual_aff_cnt > 0 or manual_aff_cost > 0:
        if '제휴' in stats.index: stats.drop('제휴', inplace=True)
        # 제휴는 통상 보장으로 잡히지만, 여기선 보장+상품 합계로 관리되므로 보장에 넣음 (필요시 분배)
        stats.loc['제휴(수기)'] = [manual_aff_cnt, 0, manual_aff_cost, 0]

    stats = stats.fillna(0)
    stats['Total_Cnt'] = stats['Bojang_Cnt'] + stats['Prod_Cnt']
    stats['CPA'] = stats.apply(lambda x: x['Cost'] / x['Total_Cnt'] if x['Total_Cnt'] > 0 else 0, axis=1)
    
    total_res = {
        'da_cost': int(stats.drop(['제휴(수기)', '제휴'], errors='ignore')['Cost'].sum()),
        'da_cnt': int(stats.drop(['제휴(수기)', '제휴'], errors='ignore')['Total_Cnt'].sum()),
        'aff_cost': int(stats.loc[[i for i in stats.index if '제휴' in i], 'Cost'].sum()),
        'aff_cnt': int(stats.loc[[i for i in stats.index if '제휴' in i], 'Total_Cnt'].sum()),
        'bojang_cnt': int(stats['Bojang_Cnt'].sum()),
        'prod_cnt': int(stats['Prod_Cnt'].sum()),
        'media_stats': stats
    }
    
    total_res['total_cost'] = total_res['da_cost'] + total_res['aff_cost']
    total_res['total_cnt'] = total_res['da_cnt'] + total_res['aff_cnt']
    
    if total_res['total_cnt'] > 0:
        total_res['ratio_ba'] = total_res['bojang_cnt'] / total_res['total_cnt']
    else:
        total_res['ratio_ba'] = 0.898

    return total_res


# -----------------------------------------------------------
# MODE 1: Legacy
# -----------------------------------------------------------
def run_v6_6_legacy():
    st.title("📊 메리츠화재 DA 보고 자동화 (Legacy V6.6)")
    st.info("ℹ️ 기존 수기 입력 모드입니다.")
    # (코드 생략)

# -----------------------------------------------------------
# MODE 2: V18.1 Final
# -----------------------------------------------------------
def run_v18_0_dashboard_master():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.1 Parsing Fix)")
    st.markdown("🚀 **이원화 파싱 & 파일 읽기 오류 해결**")

    current_bojang, current_prod = 0, 0
    est_ba_18_14, est_prod_18_14 = 0, 0
    da_target_bojang, da_target_prod = 0, 0
    da_target_18, da_target_17 = 0, 0
    da_per_18, da_per_17 = 0, 0
    
    with st.sidebar:
        st.header("1. 기본 설정")
        current_time_str = st.select_slider(
            "⏱️ 현재 데이터 기준 시각",
            options=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
            value="14:00"
        )
        
        is_boosting = False
        if current_time_str in ["16:00", "17:00"]:
            is_boosting = st.checkbox("🔥 긴급 부스팅 적용", value=False)
        
        day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
        
        st.header("2. 목표 수립")
        active_member = st.number_input("금일 활동 인원", value=359)
        c1, c2 = st.columns(2)
        with c1: target_bojang = st.number_input("전체 보장 목표", value=500)
        with c2: target_product = st.number_input("전체 상품 목표", value=3100)
        c3, c4 = st.columns(2)
        with c3: sa_est_bojang = st.number_input("SA 보장 예상", value=200)
        with c4: sa_est_prod = st.number_input("SA 상품 예상", value=800)
        da_add_target = st.number_input("DA 추가 버퍼", value=50)

        # 목표 계산
        da_target_bojang = target_bojang - sa_est_bojang
        da_target_prod = target_product - sa_est_prod + da_add_target
        da_target_18 = da_target_bojang + da_target_prod
        
        target_ratio_ba = da_target_bojang / da_target_18 if da_target_18 > 0 else 0.898
        
        if active_member > 0:
            da_per_18 = round(da_target_18 / active_member, 1)
            da_target_17 = int(da_target_18 * 0.96)
            da_per_17 = round(da_target_17 / active_member, 1)

        st.header("3. [자동] 10시 시작 자원")
        with st.expander("📂 파일 업로드"):
            file_yest_24 = st.file_uploader("① 어제 24시", key="f1")
            file_today_10 = st.file_uploader("② 오늘 10시", key="f3")
        start_resource_10 = st.number_input("10시 자원 (수기/자동)", value=1100)

        st.header("4. [자동+수기] 실시간 분석")
        uploaded_realtime = st.file_uploader("📊 실시간 로우데이터 (Raw + PLAB)", accept_multiple_files=True)
        is_aff_bojang = st.checkbox("☑️ 금일 제휴는 '보장' 위주", value=False)
        
        st.markdown("**✏️ 수기 입력 (제휴 입력 시 파일값 무시)**")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_da_cnt = st.number_input("DA 추가 건수", value=0)
            manual_da_cost = st.number_input("DA 추가 소진액", value=0)
        with col_m2:
            manual_aff_cost = st.number_input("제휴 수기 소진액", value=11270000) 
            manual_aff_cpa = st.number_input("제휴 수기 단가", value=14000)
            manual_aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0
            st.info(f"ㄴ 제휴 환산: {manual_aff_cnt:,}건")

        df_cost, df_db = parse_files_dual_track(uploaded_realtime) if uploaded_realtime else (pd.DataFrame(), pd.DataFrame())
        res = aggregate_dual_source(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt)
        
        current_total = res['total_cnt']
        cost_total = res['total_cost']
        ratio_ba = res['ratio_ba']
        current_bojang = res['bojang_cnt']
        current_prod = res['prod_cnt']

        st.header("5. 기타 설정")
        tom_member = st.number_input("명일 활동 인원", value=350)
        tom_sa_9 = st.number_input("명일 SA 9시", value=410)
        tom_dawn_ad = st.checkbox("내일 새벽 고정광고", value=False)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 계산 ---
    base_mul_14 = 1.35
    if day_option == '월': base_mul_14 = 1.15
    elif fixed_ad_type != "없음": base_mul_14 = 1.215
    
    mul_14 = base_mul_14
    mul_16 = 1.25 if is_boosting else 1.10

    est_18_from_14 = int(current_total * mul_14)
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150

    est_ba_18_14 = int(est_18_from_14 * ratio_ba)
    est_prod_18_14 = est_18_from_14 - est_ba_18_14

    cpa_da = round(res['da_cost'] / res['da_cnt'] / 10000, 1) if res['da_cnt'] > 0 else 0
    cpa_aff = round(res['aff_cost'] / res['aff_cnt'] / 10000, 1) if res['aff_cnt'] > 0 else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total > 0 else 0

    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"
    msg_14 = "금일 고정구좌 이슈없이 집행중이며..." if est_18_from_14 >= da_target_18 else "오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 집중 관리하겠습니다."
    
    time_multipliers = {
        "09:30": 1.0, "10:00": 1.75, "11:00": 1.65, "12:00": 1.55, "13:00": 1.45,
        "14:00": mul_14, "15:00": (mul_14 + mul_16)/2, "16:00": mul_16, 
        "17:00": 1.05 if not is_boosting else 1.15, "18:00": 1.0
    }
    current_mul = time_multipliers.get(current_time_str, 1.35)
    est_final_live = int(current_total * current_mul)

    # --- 탭 출력 ---
    tab0, tab1, tab2, tab3, tab4 = st.tabs(["📊 대시보드", "🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근"])

    with tab0:
        st.subheader(f"📊 실시간 DA 현황 대시보드 ({current_time_str})")
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("최종 목표", f"{da_target_18:,}건")
        progress = min(1.0, current_total/da_target_18) if da_target_18 > 0 else 0
        c2.metric("현재 실적", f"{current_total:,}건", f"{progress*100:.1f}% 달성")
        c3.metric("마감 예상", f"{est_final_live:,}건", f"Gap: {est_final_live - da_target_18}건")
        c4.metric("현재 CPA", f"{cpa_total:.1f}만원")
        st.progress(progress)
        
        col_d1, col_d2 = st.columns([1, 1])
        with col_d1:
            st.markdown("##### 📌 시간대별 목표 상세")
            hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
            weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
            gap = da_target_18 - start_resource_10
            total_w = sum(weights)
            acc_res = [start_resource_10]
            for w in weights[1:]:
                acc_res.append(acc_res[-1] + round(gap * (w / total_w)))
            acc_res[-1] = da_target_18
            
            df_dash_goal = pd.DataFrame({
                '누적 목표': [f"{x:,}" for x in acc_res],
                '보장 목표': [f"{int(x * target_ratio_ba):,}" for x in acc_res],
                '상품 목표': [f"{int(x * (1-target_ratio_ba)):,}" for x in acc_res]
            }, index=hours)
            st.table(df_dash_goal.T)
            
        with col_d2:
            st.markdown("##### 📌 매체별 실적 상세")
            if not res['media_stats'].empty:
                display_stats = res['media_stats'][['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA']].copy()
                display_stats.columns = ['보장(건)', '상품(건)', '비용(원)', 'CPA(원)']
                st.dataframe(display_stats.style.format("{:,.0f}"), use_container_width=True)
            else:
                st.info("데이터가 없습니다.")

    with tab1:
        st.subheader("📋 오전 목표 수립")
        st.line_chart(pd.DataFrame({'목표 흐름': acc_res}, index=hours))
        
        hourly_get = [0] + [acc_res[i]-acc_res[i-1] for i in range(1, len(acc_res))]
        per_person_target = [round(x/active_member, 1) if active_member else 0 for x in acc_res]
        
        df_plan = pd.DataFrame({
            '누적 목표(건)': [f"{x:,}" for x in acc_res],
            '인당 배분(건)': per_person_target,
            '시간당 확보(건)': [f"{x:,}" for x in hourly_get]
        }, index=hours)
        st.table(df_plan.T)
        
        report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {da_target_17:,}건 ({active_member}명, {da_per_17:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_17*target_ratio_ba):,}건
ㄴ 상품 : {int(da_target_17*(1-target_ratio_ba)):,}건

[18시 기준]
총 자원 : {da_target_18:,}건 ({active_member}명, {da_per_18:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_bojang):,}건
ㄴ 상품 : {int(da_target_prod):,}건

* {fixed_msg}"""
        st.text_area("복사 텍스트:", report_morning, height=300)

    with tab2:
        st.subheader("🔥 14:00 중간 보고")
        report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {da_per_18:.1f}건 / 총 {da_target_18:,}건
현황(14시) : 인당배분 {round(current_total/active_member, 1) if active_member else 0:.1f}건 / 총 {current_total:,}건
예상 마감(18시 기준) : 인당배분 {round(est_18_from_14/active_member, 1) if active_member else 0:.1f}건 / 총 {est_18_from_14:,}건
ㄴ 보장분석 : {est_ba_18_14:,}건, 상품 {est_prod_18_14:,}건

* {fixed_msg} {msg_14}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {int(cost_total)//10000:,}만원 / 가망CPA {cpa_total:.1f}만원
- DA: {int(res['da_cost'])//10000:,}만원 / 가망CPA {cpa_da:.1f}만원
- 제휴: {int(res['aff_cost'])//10000:,}만원 / 가망CPA {cpa_aff:.1f}만원

[예상 마감 - 18시 기준]
- 총합(DA/제휴): {int(cost_total * 1.35)//10000:,}만원 / 가망CPA {max(3.1, cpa_total-0.2):.1f}만원
- DA: {int(res['da_cost'] * 1.4)//10000:,}만원 / 가망CPA {max(4.4, cpa_da):.1f}만원
- 제휴: {int(res['aff_cost'] * 1.25)//10000:,}만원 / 가망CPA {max(2.4, cpa_aff-0.2):.1f}만원"""
        st.text_area("복사 텍스트 (14시):", report_1400, height=450)

    with tab3:
        st.subheader("⚠️ 16:00 마감 임박 보고")
        report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {da_target_18:,}건
ㄴ 보장분석 : {da_target_bojang:,}건, 상품 {da_target_prod:,}건

16시 현황 : 총 {current_total:,}건
ㄴ 보장분석 : {int(current_bojang):,}건, 상품 {int(current_prod):,}건

* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."""
        st.text_area("복사 텍스트 (16시):", report_1600, height=300)

    with tab4:
        st.subheader("🌙 명일 자원 수립")
        tom_base_total = int(tom_member * 3.15) + (300 if tom_dawn_ad else 0)
        report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {tom_base_total:,}건
ㄴ 보장분석 : {int(tom_base_total * target_ratio_ba):,}건
ㄴ 상품자원 : {int(tom_base_total * (1-target_ratio_ba)):,}건

* 영업가족 {tom_member}명 기준 인당 {4.4 if not tom_dawn_ad else 5.0}건 이상 확보할 수 있도록 운영 예정입니다."""
        st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)

def main():
    st.sidebar.title("⚙️ 시스템 버전 선택")
    version = st.sidebar.selectbox("버전 선택", ["V18.1 (Final)", "V6.6 (Legacy)"])
    if version == "V18.1 (Final)": run_v18_0_dashboard_master()
    else: run_v6_6_legacy()

if __name__ == "__main__":
    main()
