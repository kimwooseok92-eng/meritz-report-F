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
st.set_page_config(page_title="메리츠 보고 자동화 V18.0", layout="wide")

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
# 1. 유틸리티 함수 (Dual Track Parser & Aggregator)
# -----------------------------------------------------------
def normalize_media(text):
    """매체명 표준화 함수"""
    text = str(text).lower()
    if any(x in text for x in ['네이버', 'naver', 'gfa', 'nasp']): return '네이버'
    if any(x in text for x in ['카카오', 'kakao', 'kakaoment', '비즈보드']): return '카카오'
    if any(x in text for x in ['토스', 'toss']): return '토스'
    if any(x in text for x in ['구글', 'google', 'youtube', 'pmax']): return '구글'
    if any(x in text for x in ['제휴', 'affiliate']): return '제휴'
    return '기타'

def classify_type(text):
    """보장/상품 구분 함수"""
    text = str(text).lower()
    if '보장' in text: return '보장'
    return '상품'

def clean_num(x):
    try: return float(str(x).replace(',', '').replace('"', '').replace(' ', ''))
    except: return 0

def parse_files_dual_track(files):
    """
    파일을 '비용 소스(Raw)'와 'DB 소스(PLAB)'로 분리하여 처리
    """
    df_cost_source = pd.DataFrame() 
    df_db_source = pd.DataFrame()   
    
    cost_keywords = ['비용', '소진', 'Cost', '금액', '총 비용']
    db_keywords = ['계', '합계', '보장분석', '전환', 'DB', '건수', '잠재고객']

    for file in files:
        fname = file.name.lower()
        is_plab = 'performance' in fname or 'lab' in fname or '피랩' in fname
        
        try:
            df = read_file_generic(file)
            if df is None or df.empty: continue
            
            if is_plab:
                # [Track B] 피랩 데이터 -> DB 건수 추출 전용
                temp = pd.DataFrame()
                col_cnt = find_col(df, db_keywords)
                col_media = find_col(df, ['media', 'account', '매체', '그룹'])
                col_type = find_col(df, ['구분', 'type', '캠페인'])
                
                if col_cnt:
                    temp['count'] = df[col_cnt].apply(clean_num).fillna(0)
                    temp['media_raw'] = df[col_media].fillna('기타') if col_media else '기타'
                    temp['type_raw'] = df[col_type].fillna('') if col_type else ''
                    temp['source'] = 'PLAB'
                    df_db_source = pd.concat([df_db_source, temp], ignore_index=True)
            else:
                # [Track A] 매체 로우 데이터 -> 비용 추출 전용
                temp = pd.DataFrame()
                col_cost = find_col(df, cost_keywords)
                col_camp = find_col(df, ['캠페인', 'Campaign', '광고명'])
                
                if col_cost and col_camp:
                    temp['cost'] = df[col_cost].apply(clean_num).fillna(0)
                    temp['campaign'] = df[col_camp].fillna('기타')
                    temp['source'] = 'RAW'
                    df_cost_source = pd.concat([df_cost_source, temp], ignore_index=True)

        except Exception:
            pass

    return df_cost_source, df_db_source

def read_file_generic(file):
    try:
        file.seek(0)
        if file.name.lower().endswith(('.csv', '.txt')):
            for enc in ['utf-8-sig', 'cp949', 'euc-kr']:
                for sep in [',', '\t']:
                    try:
                        file.seek(0)
                        return pd.read_csv(file, encoding=enc, sep=sep, on_bad_lines='skip')
                    except: continue
        else:
            try: return pd.read_excel(file, engine='openpyxl')
            except: return pd.read_csv(file)
    except: return None
    return None

def find_col(df, keywords):
    for col in df.columns:
        if any(k in str(col) for k in keywords):
            return col
    return None

def aggregate_dual_source(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt):
    """
    이원화된 데이터를 매체별로 집계하고, 수기 입력을 반영하여 최종 통계를 산출
    """
    # 1. 초기화
    stats = pd.DataFrame(columns=['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA'])
    
    # 2. 매체별 그룹핑 (비용)
    if not df_cost.empty:
        df_cost['media_group'] = df_cost['campaign'].apply(normalize_media)
        cost_grp = df_cost.groupby('media_group')['cost'].sum()
        for media, val in cost_grp.items():
            if media not in stats.index: stats.loc[media] = [0, 0, 0, 0]
            stats.loc[media, 'Cost'] += val

    # 3. 매체별 그룹핑 (건수)
    if not df_db.empty:
        df_db['media_group'] = df_db['media_raw'].apply(normalize_media)
        df_db['type_group'] = df_db['type_raw'].apply(classify_type)
        
        cnt_grp = df_db.groupby(['media_group', 'type_group'])['count'].sum()
        for (media, type_), val in cnt_grp.items():
            if media not in stats.index: stats.loc[media] = [0, 0, 0, 0]
            if type_ == '보장':
                stats.loc[media, 'Bojang_Cnt'] += val
            else:
                stats.loc[media, 'Prod_Cnt'] += val

    # 4. 수기 입력 반영
    # 4-1. DA 수기 (기존 값에 더하기 - 누락분 보정)
    if manual_da_cnt > 0 or manual_da_cost > 0:
        if '기타(수기)' not in stats.index: stats.loc['기타(수기)'] = [0, 0, 0, 0]
        # 일단 비율대로 나누거나 상품으로 몰기 (여기선 단순 상품으로 가정)
        stats.loc['기타(수기)', 'Prod_Cnt'] += manual_da_cnt
        stats.loc['기타(수기)', 'Cost'] += manual_da_cost

    # 4-2. 제휴 수기 (Override - 기존 파일의 제휴 데이터 덮어쓰기)
    if manual_aff_cnt > 0 or manual_aff_cost > 0:
        # 기존에 '제휴'나 '토스' 등에 섞여있던 제휴 데이터를 어떻게 처리할지가 관건
        # 리더님 요청: "수기 입력 시 파일 데이터 무시" -> '제휴' 행을 아예 수기로 교체
        if '제휴' in stats.index:
            stats.drop('제휴', inplace=True) # 기존 제휴 삭제
        
        # 새 제휴 행 추가 (제휴는 보통 보장 위주라고 가정하거나 설정 따름)
        stats.loc['제휴(수기)'] = [manual_aff_cnt, 0, manual_aff_cost, 0] 
        # *제휴는 보통 보장으로 분류되지만, 필요 시 분기 처리 가능

    # 5. 최종 CPA 계산 및 합계
    stats = stats.fillna(0)
    stats['Total_Cnt'] = stats['Bojang_Cnt'] + stats['Prod_Cnt']
    stats['CPA'] = stats.apply(lambda x: x['Cost'] / x['Total_Cnt'] if x['Total_Cnt'] > 0 else 0, axis=1)
    
    # 6. 전체 합계 딕셔너리 생성
    total_res = {
        'da_cost': int(stats.drop(['제휴(수기)', '제휴'], errors='ignore')['Cost'].sum()),
        'da_cnt': int(stats.drop(['제휴(수기)', '제휴'], errors='ignore')['Total_Cnt'].sum()),
        'aff_cost': int(stats.loc[[i for i in stats.index if '제휴' in i], 'Cost'].sum()),
        'aff_cnt': int(stats.loc[[i for i in stats.index if '제휴' in i], 'Total_Cnt'].sum()),
        'bojang_cnt': int(stats['Bojang_Cnt'].sum()),
        'prod_cnt': int(stats['Prod_Cnt'].sum()),
        'media_stats': stats # 대시보드용 데이터프레임
    }
    
    total_res['total_cost'] = total_res['da_cost'] + total_res['aff_cost']
    total_res['total_cnt'] = total_res['da_cnt'] + total_res['aff_cnt']
    
    if total_res['total_cnt'] > 0:
        total_res['ratio_ba'] = total_res['bojang_cnt'] / total_res['total_cnt']
    else:
        total_res['ratio_ba'] = 0.898

    return total_res


# -----------------------------------------------------------
# MODE 1: Legacy (유지)
# -----------------------------------------------------------
def run_v6_6_legacy():
    st.title("📊 메리츠화재 DA 보고 자동화 (Legacy V6.6)")
    st.info("ℹ️ 기존 수기 입력 모드입니다.")
    # (Legacy 코드 생략)

# -----------------------------------------------------------
# MODE 2: V18.0 Dashboard Master
# -----------------------------------------------------------
def run_v18_0_dashboard_master():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.0 Dashboard Master)")
    st.markdown("🚀 **비용(Raw)/건수(PLAB) 이원화 & 대시보드/부스팅 복구**")

    # 변수 초기화 (NameError 방지)
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
        
        # [복구] 부스팅 기능
        is_boosting = False
        if current_time_str in ["16:00", "17:00"]:
            is_boosting = st.checkbox("🔥 긴급 부스팅 적용 (막판 스퍼트)", value=False)
        
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

        # [분석 수행]
        df_cost, df_db = parse_files_dual_track(uploaded_realtime) if uploaded_realtime else (pd.DataFrame(), pd.DataFrame())
        res = aggregate_dual_source(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt)
        
        current_total = res['total_cnt']
        cost_total = res['total_cost']
        ratio_ba = res['ratio_ba']
        current_bojang = res['bojang_cnt']
        current_prod = res['prod_cnt']
        
        # 제휴 보장 옵션에 따라 보장/상품 건수 미세 조정 (수기 제휴가 들어간 경우)
        if is_aff_bojang and manual_aff_cnt > 0:
             # 집계 함수에서 이미 제휴를 보장으로 쳤는지 확인 어렵지만,
             # 여기서는 단순화를 위해 전체 비율로 재계산하거나 유지
             pass 

        st.header("5. 기타 설정")
        tom_member = st.number_input("명일 활동 인원", value=350)
        tom_sa_9 = st.number_input("명일 SA 9시", value=410)
        tom_dawn_ad = st.checkbox("내일 새벽 고정광고", value=False)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 예측 계산 ---
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
        
        # 1. 상단 지표
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("최종 목표", f"{da_target_18:,}건")
        progress = min(1.0, current_total/da_target_18) if da_target_18 > 0 else 0
        c2.metric("현재 실적", f"{current_total:,}건", f"{progress*100:.1f}% 달성")
        c3.metric("마감 예상", f"{est_final_live:,}건", f"Gap: {est_final_live - da_target_18}건")
        c4.metric("현재 CPA", f"{cpa_total:.1f}만원")
        
        st.progress(progress)
        
        # 2. [요청하신 기능] 매체별 상세 표
        st.markdown("##### 📌 매체별 상세 현황")
        if not res['media_stats'].empty:
            # 포맷팅을 위한 복사본
            display_stats = res['media_stats'].copy()
            display_stats = display_stats[['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA']]
            display_stats.columns = ['보장(건)', '상품(건)', '비용(원)', 'CPA(원)']
            st.dataframe(display_stats.style.format("{:,.0f}").background_gradient(cmap='Blues', subset=['보장(건)', '상품(건)']), use_container_width=True)
        else:
            st.info("데이터가 없습니다. 파일을 업로드해주세요.")

    with tab1:
        st.subheader("📋 오전 목표 수립 (복구됨)")
        
        # [복구] 목표 그래프 및 표 로직
        hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
        weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
        gap = da_target_18 - start_resource_10
        total_w = sum(weights)
        acc_res = [start_resource_10]
        for w in weights[1:]:
            acc_res.append(acc_res[-1] + round(gap * (w / total_w)))
        acc_res[-1] = da_target_18
        
        # 시간당 확보량 계산
        hourly_get = [0] + [acc_res[i]-acc_res[i-1] for i in range(1, len(acc_res))]
        
        # 차트
        chart_data = pd.DataFrame({'누적 목표': acc_res}, index=hours)
        st.line_chart(chart_data)
        
        # 표
        df_plan = pd.DataFrame({
            '누적 목표(건)': [f"{x:,}" for x in acc_res],
            '시간당 확보(건)': [f"{x:,}" for x in hourly_get]
        }, index=hours)
        st.table(df_plan.T)
        
        report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {da_target_17:,}건 ({active_member}명, {da_per_17:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_17*ratio_ba):,}건
ㄴ 상품 : {int(da_target_17*(1-ratio_ba)):,}건

[18시 기준]
총 자원 : {da_target_18:,}건 ({active_member}명, {da_per_18:.1f}건 배정 기준)
ㄴ 보장분석 : {da_target_bojang:,}건
ㄴ 상품 : {da_target_prod:,}건

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
ㄴ 보장분석 : {int(tom_base_total * ratio_ba):,}건
ㄴ 상품자원 : {int(tom_base_total * (1-ratio_ba)):,}건

* 영업가족 {tom_member}명 기준 인당 {4.4 if not tom_dawn_ad else 5.0}건 이상 확보할 수 있도록 운영 예정입니다."""
        st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)

def main():
    st.sidebar.title("⚙️ 시스템 버전 선택")
    version = st.sidebar.selectbox("버전 선택", ["V18.0 (Dashboard Master)", "V6.6 (Legacy)"])
    if version == "V18.0 (Dashboard Master)": run_v18_0_dashboard_master()
    else: run_v6_6_legacy()

if __name__ == "__main__":
    main()
