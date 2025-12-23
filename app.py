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
st.set_page_config(page_title="메리츠 보고 자동화 V18.2", layout="wide")

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
# 1. 유틸리티 함수 (Updated Logic)
# -----------------------------------------------------------
def clean_num(x):
    """문자열 숫자를 실수형으로 변환 (쉼표 제거 강화)"""
    if pd.isna(x) or x == '':
        return 0.0
    try:
        if isinstance(x, str):
            return float(x.replace(',', '').replace('"', '').replace("'", "").strip())
        return float(x)
    except:
        return 0.0

def classify_type_by_name(text):
    """캠페인명을 기준으로 보장/상품 분류"""
    text = str(text).lower()
    if '보장' in text or '누적' in text:
        return '보장'
    return '상품'

def get_media_from_plab(row):
    """
    [V18.2 Update] 피랩(PLAB) 매체 정밀 매핑 함수
    - DDN -> 카카오, GDN -> 구글 자동 매핑 적용
    """
    account = str(row.get('account', '')).upper()
    gubun = str(row.get('구분', '')).upper()
    
    # 1. 명시적 약어 매핑 (DDN, GDN 처리)
    if 'DDN' in account: return '카카오'
    if 'GDN' in account: return '구글'
    
    # 2. 키워드 검색 (우선순위: Account -> 구분)
    targets = ['네이버', '카카오', '토스', '구글', 'NAVER', 'KAKAO', 'TOSS', 'GOOGLE']
    media_map = {'NAVER': '네이버', 'KAKAO': '카카오', 'TOSS': '토스', 'GOOGLE': '구글'}
    
    for t in targets:
        if t in account: return media_map.get(t, '기타')
    for t in targets:
        if t in gubun: return media_map.get(t, '기타')

    return '기타'

def parse_files_by_rules(files):
    """
    [V18.2 Update] 매체별 전용 파서 적용 (탭 구분, 헤더 위치 보정)
    """
    df_cost = pd.DataFrame() # 비용 데이터
    df_db = pd.DataFrame()   # DB 데이터
    
    for file in files:
        fname = file.name
        temp = pd.DataFrame()
        
        try:
            # -----------------------------------------------------------
            # [Rule 1] 토스 (헤더 4번째 줄)
            # -----------------------------------------------------------
            if "메리츠 화재_전략광고3팀_배너광고_캠페인" in fname:
                df = pd.read_csv(file, header=3) # Header correction
                
                # 컬럼 매핑 (소진 비용, 캠페인 명)
                col_cost = next((c for c in df.columns if '소진 비용' in str(c)), None)
                col_camp = next((c for c in df.columns if '캠페인 명' in str(c)), None)
                
                if col_cost and col_camp:
                    temp['cost'] = df[col_cost].apply(clean_num) * 1.1 # 부가세 1.1
                    temp['campaign'] = df[col_camp].fillna('')
                    temp['type'] = temp['campaign'].apply(classify_type_by_name)
                    temp['media'] = '토스'
                    df_cost = pd.concat([df_cost, temp], ignore_index=True)

            # -----------------------------------------------------------
            # [Rule 2] 카카오 (탭 구분)
            # -----------------------------------------------------------
            elif "메리츠화재다이렉트_캠페인" in fname:
                df = pd.read_csv(file, sep='\t') # Tab separator
                
                col_cost = '비용' if '비용' in df.columns else None
                col_camp = '캠페인' if '캠페인' in df.columns else None
                
                if col_cost and col_camp:
                    temp['cost'] = df[col_cost].apply(clean_num) * 1.1 # 부가세 1.1
                    temp['campaign'] = df[col_camp].fillna('')
                    temp['type'] = temp['campaign'].apply(classify_type_by_name)
                    temp['media'] = '카카오'
                    df_cost = pd.concat([df_cost, temp], ignore_index=True)

            # -----------------------------------------------------------
            # [Rule 3] 네이버 (일반 CSV)
            # -----------------------------------------------------------
            elif "result" in fname:
                df = pd.read_csv(file)
                
                col_cost = next((c for c in df.columns if '총 비용' in str(c)), None)
                col_camp = next((c for c in df.columns if '캠페인 이름' in str(c)), None)
                
                if col_cost and col_camp:
                    temp['cost'] = df[col_cost].apply(clean_num) # 값 그대로
                    temp['campaign'] = df[col_camp].fillna('')
                    temp['type'] = temp['campaign'].apply(classify_type_by_name)
                    temp['media'] = '네이버'
                    df_cost = pd.concat([df_cost, temp], ignore_index=True)

            # -----------------------------------------------------------
            # [Rule 4] 구글 (탭 구분, 헤더 3번째 줄)
            # -----------------------------------------------------------
            elif "캠페인 보고서" in fname:
                df = pd.read_csv(file, sep='\t', header=2)
                df.columns = df.columns.str.strip() # 공백 제거
                
                col_cost = '비용' if '비용' in df.columns else None
                col_camp = '캠페인' if '캠페인' in df.columns else None
                
                if col_cost and col_camp:
                    temp['cost'] = df[col_cost].apply(clean_num) * 1.1 * 1.15 # 부가세 * 수수료
                    temp['campaign'] = df[col_camp].fillna('')
                    temp['type'] = temp['campaign'].apply(classify_type_by_name)
                    temp['media'] = '구글'
                    df_cost = pd.concat([df_cost, temp], ignore_index=True)

            # -----------------------------------------------------------
            # [Rule 5] 피랩 (DB 마스터)
            # -----------------------------------------------------------
            elif "Performance Lab" in fname:
                df = pd.read_csv(file)
                
                col_send = next((c for c in df.columns if 'METIS전송' in str(c) and '율' not in str(c)), None)
                col_fail = next((c for c in df.columns if 'METIS실패건수' in str(c)), None)
                col_re = next((c for c in df.columns if 'METIS재인입건수' in str(c)), None)
                
                if col_send:
                    s = df[col_send].apply(clean_num).fillna(0)
                    f = df[col_fail].apply(clean_num).fillna(0) if col_fail else 0
                    r = df[col_re].apply(clean_num).fillna(0) if col_re else 0
                    
                    temp['count'] = s - f - r
                    temp['campaign'] = df['구분'].fillna('')
                    temp['account'] = df['account'].fillna('') # 매체 매핑용
                    temp['구분'] = df['구분'].fillna('')       # 매체 매핑용 fallback
                    temp['type'] = temp['campaign'].apply(classify_type_by_name)
                    
                    # [Updated] 매체 정밀 매핑 (DDN, GDN 등)
                    temp['media'] = temp.apply(get_media_from_plab, axis=1)
                    
                    df_db = pd.concat([df_db, temp], ignore_index=True)
                    
        except Exception as e:
            st.error(f"❌ 파일 처리 중 오류 발생: {fname} / {e}")
            continue

    return df_cost, df_db

def aggregate_data_v2(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt):
    """
    이원화된 데이터 집계 및 수기 보정
    """
    # 기본 통계표 생성
    media_list = ['네이버', '카카오', '토스', '구글', '제휴', '기타']
    stats = pd.DataFrame(index=media_list, columns=['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA']).fillna(0)
    
    # 1. 비용 집계 (Raw Data)
    if not df_cost.empty:
        cost_grp = df_cost.groupby('media')['cost'].sum()
        for m, val in cost_grp.items():
            if m in stats.index: stats.loc[m, 'Cost'] += val
            else: 
                if '기타' not in stats.index: stats.loc['기타'] = [0,0,0,0]
                stats.loc['기타', 'Cost'] += val

    # 2. DB 집계 (PLAB Data)
    if not df_db.empty:
        cnt_grp = df_db.groupby(['media', 'type'])['count'].sum()
        for (m, t), val in cnt_grp.items():
            target_media = m if m in stats.index else '기타'
            if t == '보장':
                stats.loc[target_media, 'Bojang_Cnt'] += val
            else:
                stats.loc[target_media, 'Prod_Cnt'] += val

    # 3. 수기 입력 보정
    if manual_da_cnt > 0 or manual_da_cost > 0:
        stats.loc['기타', 'Prod_Cnt'] += manual_da_cnt
        stats.loc['기타', 'Cost'] += manual_da_cost

    # 제휴 Override
    if manual_aff_cnt > 0 or manual_aff_cost > 0:
        stats.loc['제휴', :] = 0
        stats.loc['제휴', 'Bojang_Cnt'] = manual_aff_cnt
        stats.loc['제휴', 'Cost'] = manual_aff_cost

    # 4. 최종 계산
    stats['Total_Cnt'] = stats['Bojang_Cnt'] + stats['Prod_Cnt']
    stats['CPA'] = stats.apply(lambda x: x['Cost'] / x['Total_Cnt'] if x['Total_Cnt'] > 0 else 0, axis=1)
    
    # 결과 딕셔너리
    res = {
        'da_cost': int(stats.drop('제휴')['Cost'].sum()),
        'da_cnt': int(stats.drop('제휴')['Total_Cnt'].sum()),
        'aff_cost': int(stats.loc['제휴', 'Cost']),
        'aff_cnt': int(stats.loc['제휴', 'Total_Cnt']),
        'bojang_cnt': int(stats['Bojang_Cnt'].sum()),
        'prod_cnt': int(stats['Prod_Cnt'].sum()),
        'media_stats': stats
    }
    
    res['total_cost'] = res['da_cost'] + res['aff_cost']
    res['total_cnt'] = res['da_cnt'] + res['aff_cnt']
    res['ratio_ba'] = res['bojang_cnt'] / res['total_cnt'] if res['total_cnt'] > 0 else 0.898
    
    return res


# -----------------------------------------------------------
# MODE 2: V18.2 Rule-Based Master
# -----------------------------------------------------------
def run_v18_2_master():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.2 Rule-Based)")
    st.markdown("🚀 **매체별 맞춤 파싱 & 비용/DB 이원화**")

    # 변수 초기화
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
        uploaded_realtime = st.file_uploader("📊 실시간 로우데이터 (파일명 규칙 준수)", accept_multiple_files=True)
        is_aff_bojang = st.checkbox("☑️ 금일 제휴는 '보장' 위주", value=False)
        
        st.markdown("**✏️ 수기 입력 (제휴)**")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_da_cnt = st.number_input("DA 추가 건수", value=0)
            manual_da_cost = st.number_input("DA 추가 소진액", value=0)
        with col_m2:
            manual_aff_cost = st.number_input("제휴 수기 소진액", value=11270000) 
            manual_aff_cpa = st.number_input("제휴 수기 단가", value=14000)
            manual_aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0
            st.info(f"ㄴ 제휴 환산: {manual_aff_cnt:,}건")

        # [핵심] 룰 기반 파싱 (Updated Logic Call)
        df_cost, df_db = parse_files_by_rules(uploaded_realtime) if uploaded_realtime else (pd.DataFrame(), pd.DataFrame())
        res = aggregate_data_v2(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt)
        
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
    # Range limit
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
            acc_res = [start_resource_10]
            gap = da_target_18 - start_resource_10
            total_w = sum(weights)
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
                # 합계 행 추가
                display_stats = res['media_stats'].copy()
                display_stats.loc['합계'] = display_stats.sum(numeric_only=True)
                # CPA 재계산
                display_stats.loc['합계', 'CPA'] = display_stats.loc['합계', 'Cost'] / display_stats.loc['합계', 'Total_Cnt'] if display_stats.loc['합계', 'Total_Cnt'] > 0 else 0
                
                # 포맷팅
                st.dataframe(display_stats[['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA']].style.format("{:,.0f}"), use_container_width=True)
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

# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
def main():
    st.sidebar.title("⚙️ 시스템 버전 선택")
    version = st.sidebar.selectbox("버전 선택", ["V18.2 (Rule-Based)", "V6.6 (Legacy)"])
    if version == "V18.2 (Rule-Based)": run_v18_2_master()
    else: st.warning("레거시 모드는 이 코드에 포함되지 않았습니다.")

if __name__ == "__main__":
    main()
