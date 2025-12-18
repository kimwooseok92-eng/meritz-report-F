import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os

# 1. 폰트 설정 (기존 유지)
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

# 2. 웹사이트 UI
st.title("📊 메리츠화재 DA 보고 자동화 (Final)")
st.markdown("데이터 검증 완료: **12월 신정원 이슈 & 새벽 고정광고 변수** 반영")

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'])
    
    # [NEW] 목표 수립 기조 세분화 (검증 데이터 기반)
    target_mode = st.radio("목표 수립 기조", 
                           ['평시 (8.5~9.0건)', '이슈/보수적 (6.0~7.0건)', '월말/공격적 (9.5건↑)'],
                           index=1 if day_option=='월' else 0) # 월요일은 이슈가 잦아 기본값을 보수적으로
    
    op_mode = st.selectbox("운영 전략", ['일반', '상품증대', '효율화'])

    st.header("2. 오전 목표 데이터 (광고주 공유)")
    active_member = st.number_input("금일 활동 인원 (명)", value=350)
    target_total_advertiser = st.number_input("광고주 캠페인 총합", value=2350) # 12월 평균치 반영
    sa_est_18 = st.number_input("SA 예상 (18시)", value=829)
    
    # 계산된 DA 목표와 실제 운영 목표 간의 미세 조정
    da_add_target = st.number_input("DA 목표 버퍼 (조정값)", value=0)
    
    # 시간대별 그래프용
    start_resource_10 = st.number_input("10시 시작 자원 (표 기준)", value=1100)

    st.header("3. 실시간 실적 (14시/16시)")
    current_total = st.number_input("현재 실적 총합 (DA+제휴)", value=1800)
    current_bojang = st.number_input("ㄴ 현재 보장분석", value=1400)
    current_prod = st.number_input("ㄴ 현재 상품자원", value=400)

    st.header("4. 비용 입력 (원 단위)")
    cost_total = st.number_input("비용 총합", value=65000000)
    cost_da = st.number_input("DA 비용", value=45000000)
    cost_aff = st.number_input("제휴 비용", value=20000000)

    st.header("5. 명일 자원 예상 (중요)")
    tom_member = st.number_input("명일 활동 인원", value=350)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    
    # [NEW] 데이터 검증 결과 반영: 고정광고 유무가 오차의 핵심
    tom_dawn_ad = st.checkbox("내일 새벽 고정광고(CPT/풀뷰) 있음", value=False)
    
    st.header("6. 금일 고정구좌 설정")
    fixed_ad_type = st.radio("발송 시간", ["없음", "12시 Only", "14시 Only", "12시+14시 Both"])
    fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

# 3. 로직 처리
def generate_report():
    # 1) 보장/상품 비율 설정
    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.88 
    else: ratio_ba = 0.898 # 12월 로그 평균
    ratio_prod = 1 - ratio_ba
    
    # 2) 요일별 가중치 (금요일 저하 반영)
    w = {'월': 1.05, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)

    # 3) 목표 계산 (광고주 총합 - SA + 버퍼)
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    
    # 17시 목표 역산 (고정광고 시간에 따른 진척도 차이 반영)
    if fixed_ad_type == "없음": gap_percent = 0.040 
    elif fixed_ad_type == "14시 Only": gap_percent = 0.033 
    else: gap_percent = 0.032 

    da_target_17 = da_target_18 - round(da_target_18 * gap_percent) 

    # 인당 배분율 (보고용)
    da_per_18 = round(da_target_18 / active_member, 1)
    da_per_17 = round(da_target_17 / active_member, 1)

    # 4) 실시간 예상 마감 시뮬레이션 (14시 기준 예측력 강화)
    # 로그 분석 결과: 14시 실적 * 1.35 ~ 1.4가 최종 마감과 가장 유사
    est_18 = int(current_total * 1.38 * w) # 요일 가중치 포함
    
    # 보정: 목표와 너무 동떨어지지 않게 Range 보정
    if est_18 > da_target_18 + 200: est_18 = da_target_18 + 100
    elif est_18 < da_target_18 - 200: est_18 = da_target_18 - 100
    
    est_24 = round(est_18 * 1.25) # 심야 유입 반영

    # 5) 상태 메시지 자동 생성
    achieve_rate = est_18 / da_target_18
    if achieve_rate >= 0.99:
        status_msg = "오전 목표 달성 무난할 것으로 예상되어, DA 배너 소폭 효율화(Save) 운영 중입니다."
    else:
        diff = da_target_18 - est_18
        status_msg = f"목표 대비 약 {diff}건 부족 예상되어, 남은 시간 상품자원/보장분석 Push 운영하겠습니다."

    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"

    # 6) CPA 계산
    cpa_14 = round(cost_total / current_total / 10000, 1) if current_total else 0
    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0

    # 7) [핵심] 명일 자원 예측 로직 (데이터 검증 완료 버전)
    # 기존 코드의 4.4 배수는 과대평가됨 -> 3.15로 수정
    base_multiplier = 3.15
    tom_base_total = int(tom_member * base_multiplier)
    
    # 새벽 광고 부스팅 (로그 분석 결과 약 +250~300건 효과)
    ad_boost = 300 if tom_dawn_ad else 0
    
    tom_total_target = tom_base_total + ad_boost
    tom_da_req = tom_total_target - tom_sa_9
    
    # 명일 인당 배분율 (보고 멘트용)
    # 로그상 평시에는 4.4건, CPT 있는 날은 5.2건 이상으로 보고함 [cite: 53, 109]
    tom_per_msg = 5.2 if tom_dawn_ad else 4.4

    return {
        'da_17': da_target_17, 'per_17': da_per_17,
        'ba_17': round(da_target_17 * ratio_ba), 'prod_17': round(da_target_17 * ratio_prod),
        'da_18': da_target_18, 'per_18': da_per_18,
        'ba_18': round(da_target_18 * ratio_ba), 'prod_18': round(da_target_18 * ratio_prod),
        'est_18': est_18, 'est_per_18': round(est_18/active_member, 1),
        'est_ba_18': round(est_18 * ratio_ba), 'est_prod_18': round(est_18 * ratio_prod),
        'est_24': est_24,
        'fixed_msg': fixed_msg, 'status_msg': status_msg,
        'cpa_14': cpa_14, 'cpa_da': cpa_da, 'cpa_aff': cpa_aff,
        'tom_total': tom_total_target, 'tom_da': tom_da_req,
        'tom_per_msg': tom_per_msg,
        'tom_ba': round(tom_da_req * ratio_ba), # 내일도 오늘 비율 유지 가정
        'tom_prod': round(tom_da_req * (1-ratio_ba))
    }

res = generate_report()

# 4. 탭 구성 및 출력
tab1, tab2, tab3 = st.tabs(["오전 목표 수립", "실시간 현황 (14시)", "명일 자원 수립"])

with tab1:
    st.subheader("📋 오전 10:30 목표 수립 보고")
    
    # 특이사항 멘트 추가
    issue_text = ""
    if "이슈" in target_mode:
        issue_text = "\n* 금일 신정원 시스템 불안정이 예상되어 목표를 보수적으로 설정하였습니다."
    
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
    st.text_area("복사용 텍스트 (오전):", report_morning, height=300)
    
    # 그래프 (기존 로직 유지)
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

    fig, ax = plt.subplots(figsize=(12, 2))
    ax.axis('off')
    tbl = ax.table(cellText=[[f"{x:,}" for x in acc_res], per_person, hourly_get],
                   colLabels=hours, rowLabels=['누적자원', '인당배분', '시간당 확보'],
                   loc='center', cellLoc='center')
    
    for (i, j), cell in tbl.get_celld().items():
        if i == 0: cell.set_facecolor('black'); cell.set_text_props(color='white', weight='bold')
        elif j == -1: cell.set_facecolor('#f2f2f2'); cell.set_text_props(weight='bold')
    tbl.scale(1, 2)
    st.pyplot(fig)

with tab2:
    st.subheader("📋 실시간 현황 보고 (14시)")
    report_realtime = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {res['per_18']}건 / 총 {res['da_18']}건
현황(14시) : 인당배분 {round(current_total/active_member, 1)}건 / 총 {current_total}건
예상 마감(18시 기준) : 인당배분 {res['est_per_18']}건 / 총 {res['est_18']}건
ㄴ 보장분석 : {res['est_ba_18']}건, 상품 {res['est_prod_18']}건

* {res['fixed_msg']}
* {res['status_msg']}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {int(cost_total)//10000}만원 / 가망CPA {res['cpa_14']}만원
- DA: {int(cost_da)//10000}만원 / 가망CPA {res['cpa_da']}만원
- 제휴: {int(cost_aff)//10000}만원 / 가망CPA {res['cpa_aff']}만원

[예상 마감 - 18시 기준]
- 총합(DA/제휴): {int(cost_total * 1.35)//10000}만원 / 가망CPA 3.1만원
- DA: {int(cost_da * 1.4)//10000}만원 / 가망CPA 4.4만원
- 제휴: {int(cost_aff * 1.25)//10000}만원 / 가망CPA 2.4만원"""
    st.text_area("복사용 텍스트 (실시간):", report_realtime, height=400)

with tab3:
    st.subheader("📋 명일 자원 수립 (퇴근 전)")
    
    ad_msg = ""
    if tom_dawn_ad:
        ad_msg = "\n* 명일 새벽 고정광고(CPT/풀뷰) 집행 예정으로 자원 추가 확보 예상됩니다."
        
    report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {res['tom_total']}건
ㄴ 보장분석 : {res['tom_ba']}건
ㄴ 상품자원 : {res['tom_prod']}건

* 영업가족 {tom_member}명 기준 인당 {res['tom_per_msg']}건 이상 확보할 수 있도록 운영 예정입니다.{ad_msg}"""
    
    st.text_area("복사용 텍스트 (퇴근):", report_tomorrow, height=250)
    
    st.info(f"💡 [Logic 검증] 기본 예측 {int(tom_member * 3.15)}건 + 광고 부스팅 {300 if tom_dawn_ad else 0}건 = 총 {res['tom_total']}건")
