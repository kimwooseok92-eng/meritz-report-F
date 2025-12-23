import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
import io

# 1. 폰트 설정 (한글 깨짐 방지)
@st.cache_resource
def get_font():
    try:
        plt.rc('font', family='NanumGothic') 
    except:
        if os.name == 'nt':
            plt.rc('font', family='Malgun Gothic')
        elif os.name == 'posix':
            plt.rc('font', family='AppleGothic')
    plt.rcParams['axes.unicode_minus'] = False

get_font()

# -----------------------------------------------------------
# 2. 유틸리티 함수: 엑셀/CSV 파싱 및 데이터 분류 엔진
# -----------------------------------------------------------
def parse_uploaded_files(files):
    """업로드된 파일들을 읽어 통합 DataFrame으로 반환"""
    combined_df = pd.DataFrame()
    for file in files:
        try:
            if file.name.endswith('.csv'):
                try:
                    df = pd.read_csv(file, encoding='utf-8-sig')
                except:
                    df = pd.read_csv(file, encoding='cp949')
            else:
                df = pd.read_excel(file)
            
            # 컬럼 매핑 (피랩/매체 양식 대응)
            cols = df.columns.tolist()
            # 비용: Cost, 비용, 소진, 집행
            col_cost = next((c for c in cols if any(x in c for x in ['비용', '소진', 'Cost', '금액'])), None)
            # 수량: 전환, 수량, DB, result, cnt
            col_cnt = next((c for c in cols if any(x in c for x in ['전환', '수량', 'DB', '건수', 'Cnt'])), None)
            # 캠페인: 캠페인, 광고, 매체, 그룹
            col_camp = next((c for c in cols if any(x in c for x in ['캠페인', '광고명', '매체', '그룹'])), None)

            if col_cost and col_cnt:
                temp = pd.DataFrame()
                temp['cost'] = df[col_cost].fillna(0)
                temp['count'] = df[col_cnt].fillna(0)
                temp['campaign'] = df[col_camp].fillna('기타') if col_camp else '기타'
                combined_df = pd.concat([combined_df, temp], ignore_index=True)
        except Exception as e:
            st.error(f"파일 읽기 오류 ({file.name}): {e}")
            
    return combined_df

def analyze_data(df):
    """통합 데이터에서 매체별/구분별 실적 추출"""
    res = {
        'total_cnt': 0, 'total_cost': 0,
        'da_cnt': 0, 'da_cost': 0,
        'aff_cnt': 0, 'aff_cost': 0,
        'bojang_cnt': 0, 'prod_cnt': 0,
        'media_breakdown': {} # 매체별 현황
    }
    
    if df.empty: return res

    # 1. 제휴 vs DA 구분 (캠페인명 기준)
    mask_aff = df['campaign'].astype(str).str.contains('제휴')
    
    res['aff_cnt'] = int(df[mask_aff]['count'].sum())
    res['aff_cost'] = int(df[mask_aff]['cost'].sum())
    
    res['da_cnt'] = int(df[~mask_aff]['count'].sum())
    res['da_cost'] = int(df[~mask_aff]['cost'].sum())
    
    res['total_cnt'] = res['aff_cnt'] + res['da_cnt']
    res['total_cost'] = res['aff_cost'] + res['da_cost']

    # 2. 보장 vs 상품 구분
    # '보장'이 포함되면 보장, 나머지는 상품(제휴 포함)
    mask_bojang = df['campaign'].astype(str).str.contains('보장')
    
    res['bojang_cnt'] = int(df[mask_bojang]['count'].sum())
    res['prod_cnt'] = res['total_cnt'] - res['bojang_cnt']

    # 3. 매체별 집계 (네/카/토/구)
    medias = ['네이버', '카카오', '토스', '구글']
    for m in medias:
        mask = df['campaign'].astype(str).str.contains(m)
        cnt = int(df[mask]['count'].sum())
        cost = int(df[mask]['cost'].sum())
        if cnt > 0 or cost > 0:
            res['media_breakdown'][m] = {'count': cnt, 'cost': cost}
            
    return res

# -----------------------------------------------------------
# 3. 웹사이트 UI & 사이드바 (Input)
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V6.0", layout="wide")
st.title("📊 메리츠화재 DA 보고 자동화 (V6.0)")
st.markdown("""
<style>
    .metric-box { border: 1px solid #e0e0e0; padding: 10px; border-radius: 5px; background-color: #f9f9f9; text-align: center; }
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
    
    # 요일별/이슈별 목표 기조 설정
    target_mode = st.radio("목표 수립 기조", 
                           ['평시 (8.5~9.0건)', '이슈/보수적 (6.0~7.2건)', '월말/공격적 (9.5건↑)'],
                           index=1 if day_option=='월' else 0)
    op_mode = st.selectbox("운영 전략", ['일반', '상품증대', '효율화'])

    st.markdown("---")
    st.header("2. 목표 수립 (분리 입력)")
    active_member = st.number_input("금일 활동 인원", value=359)
    
    col_t1, col_t2 = st.columns(2)
    with col_t1:
        target_bojang = st.number_input("🎯 보장 목표", value=500)
    with col_t2:
        target_product = st.number_input("🎯 상품 목표", value=3100)
    
    # 전체 목표 자동 합산
    target_total_advertiser = target_bojang + target_product
    st.info(f"📋 전체 목표: **{target_total_advertiser:,}건**")

    sa_est_18 = st.number_input("SA 예상 (18시)", value=1000)
    da_add_target = st.number_input("DA 추가 버퍼", value=50, step=10, help="인수인계 가이드: +20~100건")

    st.markdown("---")
    st.header("3. [자동] 10시 시작 자원")
    with st.expander("📂 파일 업로드 (어제마감+오늘10시)"):
        file_yest_24 = st.file_uploader("어제 24시 마감 파일", key="f1")
        file_today_10 = st.file_uploader("오늘 10시 현재 파일", key="f2")
        reported_yest_18 = st.number_input("어제 18시 보고된 총량", value=3000, help="어제 퇴근 전 보고한 수치")

    # 10시 자원 자동 계산 로직
    start_resource_10 = 1100 # 기본값
    if file_yest_24 and file_today_10:
        df_y24 = parse_uploaded_files([file_yest_24])
        df_t10 = parse_uploaded_files([file_today_10])
        
        cnt_y24 = int(df_y24.iloc[:, 1].sum()) if not df_y24.empty else 0 # 2번째 컬럼을 수량으로 가정
        cnt_t10 = int(df_t10.iloc[:, 1].sum()) if not df_t10.empty else 0
        
        # 공식: (전일24시 - 전일18시) + 금일10시
        calc_start = (cnt_y24 - reported_yest_18) + cnt_t10
        if calc_start > 0:
            start_resource_10 = calc_start
            st.success(f"🧮 자동 계산됨: {start_resource_10}건")
    
    # 수동 보정 가능하도록 입력창 제공
    start_resource_10 = st.number_input("10시 시작 자원 (최종)", value=start_resource_10)

    st.markdown("---")
    st.header("4. [자동] 실시간 실적 분석")
    uploaded_realtime = st.file_uploader("📊 실시간 로우데이터 (드래그앤드롭)", accept_multiple_files=True)
    
    # 자동 분석 실행
    real_data = analyze_data(parse_uploaded_files(uploaded_realtime) if uploaded_realtime else pd.DataFrame())
    
    if uploaded_realtime:
        st.success(f"파일 분석 완료: 총 {real_data['total_cnt']:,}건")
        # 자동값 적용
        def_total = real_data['total_cnt']
        def_bojang = real_data['bojang_cnt']
        def_prod = real_data['prod_cnt']
        def_cost_da = real_data['da_cost']
        def_cost_aff = real_data['aff_cost']
    else:
        # 수기 기본값
        def_total, def_bojang, def_prod = 1963, 1600, 363
        def_cost_da, def_cost_aff = 23560000, 11270000

    # 하이브리드 입력창 (자동값 채워지되 수정 가능)
    current_total = st.number_input("현재 총 자원", value=def_total)
    current_bojang = st.number_input("ㄴ 보장분석", value=def_bojang)
    current_prod = st.number_input("ㄴ 상품자원", value=def_prod)
    
    cost_da = st.number_input("DA 소진액", value=def_cost_da)
    cost_aff = st.number_input("제휴 소진액", value=def_cost_aff)
    cost_total = cost_da + cost_aff

    st.markdown("---")
    st.header("5. 명일 예상 & 고정구좌")
    tom_member = st.number_input("명일 활동 인원", value=350)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    tom_dawn_ad = st.checkbox("내일 새벽 고정광고 있음", value=False)
    
    fixed_ad_type = st.radio("발송 시간", ["없음", "12시 Only", "14시 Only", "12시+14시 Both"], index=2)
    fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")


# -----------------------------------------------------------
# 4. 핵심 로직 엔진 (V6.0)
# -----------------------------------------------------------
def generate_report():
    # A. 운영 비율 및 요일 가중치
    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.88 
    else: ratio_ba = 0.898
    ratio_prod = 1 - ratio_ba
    
    w = {'월': 0.82, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)
    if fixed_ad_type != "없음": 
        if day_option == '월': w = 0.90 
        else: w = max(w, 1.0)

    # B. 목표 계산 (분리된 목표 합산 처리)
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    da_per_18 = round(da_target_18 / active_member, 1)
    
    # 17시 목표 역산
    gap_percent = 0.040 if fixed_ad_type == "없음" else 0.032
    da_target_17 = da_target_18 - round(da_target_18 * gap_percent)
    da_per_17 = round(da_target_17 / active_member, 1)

    # C. 14시 예측 (12시 발송 여부 반영)
    if "12시" in fixed_ad_type:
        forecast_multiplier = 1.215 
    else:
        forecast_multiplier = 1.35 * w 
        
    est_18_from_14 = int(current_total * forecast_multiplier)
    
    # Range 보정
    limit = 250
    if est_18_from_14 > da_target_18 + limit: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - limit: est_18_from_14 = da_target_18 - 150
    
    est_cost_24 = int(cost_total * 1.8)

    # D. 16시 예측 (Last Spurt)
    est_18_from_16 = int(current_total / 0.91)
    remaining_gap = est_18_from_16 - current_total
    
    if remaining_gap < 150: remaining_gap = 150
    elif remaining_gap > 350: remaining_gap = 350
    
    last_spurt_ba = int(remaining_gap * 0.9) 
    last_spurt_prod = remaining_gap - last_spurt_ba

    # E. 멘트 및 CPA
    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"
    
    # 14시 멘트
    if est_18_from_14 >= da_target_18:
        msg_14 = "금일 고정구좌 이슈없이 집행중이며, 전체 수량 또한 양사 합산 시 소폭 초과 달성할 것으로 보입니다."
    else:
        msg_14 = f"오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 상품자원/보장분석 Push 운영하겠습니다."

    # 16시 멘트
    if current_total + remaining_gap >= da_target_18:
        msg_16 = "* 보장분석 자원 넉넉할 것으로 보여 DA배너 일부 축소하여 비용 절감하겠습니다."
    else:
        msg_16 = "* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."

    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total else 0

    # F. 명일 예측 (인수인계 가이드 4.2~5.0 준수)
    base_multiplier = 3.15
    tom_base_total = int(tom_member * base_multiplier)
    ad_boost = 300 if tom_dawn_ad else 0
    tom_total_target = tom_base_total + ad_boost
    tom_da_req = tom_total_target - tom_sa_9
    
    tom_per_msg = 5.0 if tom_dawn_ad else 4.4

    return {
        'da_17': da_target_17, 'per_17': da_per_17,
        'ba_17': round(da_target_17 * ratio_ba), 'prod_17': round(da_target_17 * ratio_prod),
        'da_18': da_target_18, 'per_18': da_per_18,
        'ba_18': round(da_target_18 * ratio_ba), 'prod_18': round(da_target_18 * ratio_prod),
        'est_18_14': est_18_from_14, 
        'est_per_18_14': round(est_18_from_14/active_member, 1),
        'est_ba_18_14': round(est_18_from_14 * 0.90), 
        'est_prod_18_14': round(est_18_from_14 * 0.10),
        'msg_14': msg_14,
        'cpa_da': cpa_da, 'cpa_aff': cpa_aff, 'cpa_total': cpa_total,
        'est_18_16': current_total + remaining_gap,
        'remaining_total': remaining_gap,
        'remaining_ba': last_spurt_ba,
        'remaining_prod': last_spurt_prod,
        'msg_16': msg_16,
        'fixed_msg': fixed_msg,
        'tom_total': tom_total_target, 'tom_da': tom_da_req, 'tom_per_msg': tom_per_msg,
        'tom_ba': round(tom_da_req * ratio_ba), 'tom_prod': round(tom_da_req * (1-ratio_ba)),
        'media_data': real_data['media_breakdown'] if uploaded_realtime else {}
    }

res = generate_report()

# -----------------------------------------------------------
# 5. 메인 탭 출력 (Output)
# -----------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["🌅 09:30 목표", "🔥 14:00 중간(재무)", "⚠️ 16:00 마감(운영)", "🌙 18:00 퇴근"])

with tab1:
    st.subheader("📋 오전 10:30 목표 수립 보고")
    issue_text = "\n* 금일 이슈 상황을 고려하여 목표를 보수적으로 설정하였습니다." if "이슈" in target_mode else ""
    
    report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {res['da_17']}건 ({active_member}명, {res['per_17']}건 배정 기준)
ㄴ 보장분석 : {res['ba_17']}건
ㄴ 상품 : {res['prod_17']}건

[18시 기준]
총 자원 : {res['da_18']}건 ({active_member}명, {res['per_18']}건 배정 기준)
ㄴ 보장분석 : {res['ba_18']}건
ㄴ 상품 : {res['prod_18']}건

* {res['fixed_msg']}{issue_text}"""
    
    col_m1, col_m2 = st.columns([1, 1])
    with col_m1:
        st.text_area("복사용 텍스트 (오전):", report_morning, height=300)
    with col_m2:
        # 시간대별 그래프
        st.markdown("#### 📉 시간대별 배분 계획표")
        hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
        if fixed_ad_type == "14시 Only": weights = [0, 0.11, 0.11, 0.11, 0.11, 0.28, 0.10, 0.10, 0.08]
        elif fixed_ad_type == "12시 Only": weights = [0, 0.10, 0.10, 0.28, 0.12, 0.12, 0.10, 0.10, 0.08]
        elif fixed_ad_type == "12시+14시 Both": weights = [0, 0.10, 0.10, 0.20, 0.10, 0.25, 0.10, 0.08, 0.07]
        else: weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]

        gap = res['da_18'] - start_resource_10
        total_w = sum(weights)
        acc_res = [start_resource_10]
        hourly_get = [0]
        for w in weights[1:]:
            get = round(gap * (w / total_w))
            hourly_get.append(get)
            acc_res.append(acc_res[-1] + get)
        acc_res[-1] = res['da_18']
        per_person = [round(x/active_member, 1) for x in acc_res]

        fig, ax = plt.subplots(figsize=(8, 3))
        ax.plot(hours, acc_res, marker='o', linestyle='-', color='#eb4034')
        for i, txt in enumerate(acc_res):
            ax.annotate(f"{txt}", (hours[i], acc_res[i]), textcoords="offset points", xytext=(0,10), ha='center')
        ax.set_title("누적 자원 예상 흐름")
        ax.grid(True, linestyle='--', alpha=0.5)
        st.pyplot(fig)

with tab2:
    st.subheader("🔥 14:00 중간 보고 (재무/예측)")
    
    # 매체별 현황 (파일 업로드 시에만 표시)
    if res['media_data']:
        st.markdown("#### 📊 매체별 현황 (Auto Analysis)")
        m_cols = st.columns(len(res['media_data']))
        for idx, (m_name, m_val) in enumerate(res['media_data'].items()):
            with m_cols[idx]:
                st.metric(label=m_name, value=f"{m_val['count']}건", delta=f"{int(m_val['cost']/10000)}만원")
    
    report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {res['per_18']}건 / 총 {res['da_18']}건
현황(14시) : 인당배분 {round(current_total/active_member, 1)}건 / 총 {current_total}건
예상 마감(18시 기준) : 인당배분 {res['est_per_18_14']}건 / 총 {res['est_18_14']}건
ㄴ 보장분석 : {res['est_ba_18_14']}건, 상품 {res['est_prod_18_14']}건

* {res['fixed_msg']} {res['msg_14']}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {int(cost_total)//10000}만원 / 가망CPA {res['cpa_total']}만원
- DA: {int(cost_da)//10000}만원 / 가망CPA {res['cpa_da']}만원
- 제휴: {int(cost_aff)//10000}만원 / 가망CPA {res['cpa_aff']}만원

[예상 마감 - 18시 기준]
- 총합(DA/제휴): {int(cost_total * 1.35)//10000}만원 / 가망CPA {max(3.1, res['cpa_total']-0.2)}만원
- DA: {int(cost_da * 1.4)//10000}만원 / 가망CPA {max(4.4, res['cpa_da'])}만원
- 제휴: {int(cost_aff * 1.25)//10000}만원 / 가망CPA {max(2.4, res['cpa_aff']-0.2)}만원

[예상 마감 - 24시 기준]
- 총합(DA/제휴): {int(cost_total * 1.8)//10000}만원 / 가망CPA {max(2.9, res['cpa_total']-0.4)}만원"""
    
    st.text_area("복사용 텍스트 (14시):", report_1400, height=450)

with tab3:
    st.subheader("⚠️ 16:00 마감 임박 보고 (운영)")
    
    report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {res['da_18']}건
ㄴ 보장분석 : {res['ba_18']}건, 상품 {res['prod_18']}건

16시 현황 : 총 {current_total}건
ㄴ 보장분석 : {current_bojang}건, 상품 {current_prod}건

16시 ~ 18시 30분 예상 건수
ㄴ 보장분석 {res['remaining_ba']}건
ㄴ 상품 {res['remaining_prod']}건

{res['msg_16']}"""
    st.text_area("복사용 텍스트 (16시):", report_1600, height=300)

with tab4:
    st.subheader("🌙 명일 자원 수립 (퇴근 전)")
    ad_msg = "\n* 명일 새벽 고정광고(CPT/풀뷰) 집행 예정으로 자원 추가 확보 예상됩니다." if tom_dawn_ad else ""
    report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {res['tom_total']}건
ㄴ 보장분석 : {res['tom_ba']}건
ㄴ 상품자원 : {res['tom_prod']}건

* 영업가족 {tom_member}명 기준 인당 {res['tom_per_msg']}건 이상 확보할 수 있도록 운영 예정입니다.{ad_msg}"""
    st.text_area("복사용 텍스트 (퇴근):", report_tomorrow, height=250)
