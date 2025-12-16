import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os

# ==========================================
# 1. 폰트 설정
# ==========================================
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

# ==========================================
# 2. 웹사이트 UI 구성
# ==========================================
st.title("📊 메리츠화재 DA 보고 자동화 (Final Ver.)")
st.markdown("오전/오후 모두 **SA를 제외한 순수 DA+제휴 데이터**로 보고서를 생성합니다.")

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'])
    op_mode = st.selectbox("운영 기조", ['일반', '상품증대', '효율화'])

    st.header("2. 목표 데이터 (광고주/SA 공유)")
    active_member = st.number_input("활동 인원 (명)", value=364)
    target_total_advertiser = st.number_input("광고주 전체 목표 (SA포함)", value=3530)
    sa_est_17 = st.number_input("SA 예상 (17시)", value=1392)
    sa_est_18 = st.number_input("SA 예상 (18시)", value=1443)
    da_add_target = st.number_input("DA 추가 확보 목표 (버퍼)", value=30)
    start_resource_10 = st.number_input("10시 시작 자원 (누적)", value=1263)

    st.header("3. 실시간 실적 (DA+제휴만)")
    current_total = st.number_input("현재 실적 총합", value=1799)
    current_bojang = st.number_input("현재 보장분석", value=1533)
    current_prod = st.number_input("현재 상품자원", value=266)

    st.header("4. 비용 입력 (원 단위)")
    cost_total = st.number_input("비용 총합", value=62750000)
    cost_da = st.number_input("DA 비용", value=41460000)
    cost_aff = st.number_input("제휴 비용", value=21290000)

    st.header("5. 기타 설정")
    tom_member = st.number_input("명일 활동 인원", value=364)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    fixed_ad = st.checkbox("고정구좌 집행 여부", value=True)
    fixed_content = st.text_input("고정구좌 내용", value="제휴 12시 신세계포인트 LMS 발송 예정입니다")

# ==========================================
# 3. 로직 처리 (정합성 완료)
# ==========================================
def generate_report():
    # 1. 운영 기조에 따른 비율 설정
    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.915 # 요청하신 데이터 기준 보정
    else: ratio_ba = 0.898
    ratio_prod = 1 - ratio_ba
    
    w = {'월': 1.1, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)

    # 2. 목표 계산 (DA Only)
    # 18시 DA 목표 = 전체목표 - SA18시 + 버퍼
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    
    # 17시 DA 목표 = 18시 목표에서 1시간치 자연증가분(약 4%) 차감 역산
    # (단순히 전체-SA17시로 하면 DA목표가 과하게 잡히는 오류 수정)
    hourly_gap = round(da_target_18 * 0.04) 
    da_target_17 = da_target_18 - hourly_gap

    # 인당 배분 (DA 목표 기준)
    da_per_18 = round(da_target_18 / active_member, 1)
    da_per_17 = round(da_target_17 / active_member, 1)

    # 3. 실시간 예상 마감 시뮬레이션
    hourly_pace = 195 * w if fixed_ad else 140 * w
    est_increase = round(hourly_pace * 4.0)
    est_18 = current_total + est_increase
    
    # 목표 수렴 보정
    if est_18 > da_target_18 + 150: est_18 = da_target_18 + 50
    elif est_18 < da_target_18 - 200: est_18 = da_target_18 - 50
    est_24 = round(est_18 * 1.35)

    # 4. 멘트 생성
    achieve_rate = est_18 / da_target_18
    if achieve_rate >= 0.99:
        status_msg = "전체 수량 또한 양사 합산 시 달성가능할 것으로 보입니다."
        action_msg = "조기 배정마감되는 경우, 배너광고 조정하도록 하겠습니다."
    else:
        status_msg = f"목표 대비 약 {da_target_18 - est_18}건 부족할 것으로 예상되나, 집중 운영하겠습니다."
        action_msg = "남은 시간 상품수량 확보 및 보장분석 효율화 자원 확보에 집중하겠습니다."

    fixed_msg = f"{fixed_content}" if fixed_ad else "금일 특이사항 없이 운영 중이며,"
    fixed_act = "" # 고정구좌 멘트가 있으면 보통 액션 멘트는 생략하거나 통합됨

    # CPA
    cpa_14 = round(cost_total / current_total / 10000, 1) if current_total else 0
    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0

    return {
        'da_17': da_target_17, 'per_17': da_per_17,
        'ba_17': round(da_target_17 * ratio_ba), 'prod_17': round(da_target_17 * ratio_prod),
        
        'da_18': da_target_18, 'per_18': da_per_18,
        'ba_18': round(da_target_18 * ratio_ba), 'prod_18': round(da_target_18 * ratio_prod),
        
        'est_18': est_18, 'est_per_18': round(est_18/active_member, 1),
        'est_ba_18': round(est_18 * ratio_ba), 'est_prod_18': round(est_18 * ratio_prod),
        'est_24': est_24,
        
        'fixed_msg': fixed_msg, 'fixed_act': fixed_act, 'status_msg': status_msg, 'action_msg': action_msg,
        'cpa_14': cpa_14, 'cpa_da': cpa_da, 'cpa_aff': cpa_aff
    }

res = generate_report()

# ==========================================
# 4. 결과 출력 (수정됨)
# ==========================================
tab1, tab2, tab3 = st.tabs(["오전 목표 수립", "실시간 현황 (14시)", "명일 자원 수립"])

with tab1:
    st.subheader("📋 오전 10:30 목표 수립 보고")
    st.success("✅ SA를 제외한 **DA+제휴 파트** 목표만 출력됩니다.")
    
    report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {res['da_17']}건 ({active_member}명, {res['per_17']}건 배정 기준)
ㄴ 보장분석 : {res['ba_17']}건
ㄴ 상품 : {res['prod_17']}건

[18시 기준]
총 자원 : {res['da_18']}건 ({active_member}명, {res['per_18']}건 배정 기준)
ㄴ 보장분석 : {res['ba_18']}건
ㄴ 상품 : {res['prod_18']}건

* {res['fixed_msg']} {res['fixed_act']}"""
    st.text_area("복사용 텍스트 (오전):", report_morning, height=300)
    
    # 표 그리기 (DA 목표 기준 배분)
    st.markdown("#### 📉 시간대별 배분 계획표")
    hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
    weights = [0, 0.40, 0.40, 0.80, 0.33, 0.80, 0.40, 0.34, 0.23]
    gap = res['da_18'] - start_resource_10
    total_w = sum(weights)
    
    acc_res = [start_resource_10]
    hourly_get = [0]
    for w in weights[1:]:
        get = round(gap * (w / total_w))
        hourly_get.append(get)
        acc_res.append(acc_res[-1] + get)
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

* {res['fixed_msg']} {res['status_msg']}
* {res['action_msg']}

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
    tom_per = 4.8 if (res['est_18'] / res['da_18']) >= 0.98 else 4.4
    tom_total_target = round(tom_member * tom_per)
    
    if op_mode == '상품증대': r_ba = 0.84
    elif op_mode == '효율화': r_ba = 0.915
    else: r_ba = 0.898
    
    da_tom_req = tom_total_target - tom_sa_9
    
    report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {tom_total_target}건
ㄴ 보장분석 : {round(da_tom_req * r_ba)}건
ㄴ 상품자원 : {round(da_tom_req * (1-r_ba))}건

* 명일 영업가족 {tom_member}명 기준 인당 자원 {tom_per}건 이상 확보할 수 있도록 운영 예정입니다."""
    st.text_area("복사용 텍스트 (퇴근):", report_tomorrow, height=250)
