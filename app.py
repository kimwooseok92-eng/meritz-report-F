import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os

# 1. 폰트 설정
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
st.title("📊 메리츠화재 DA 보고 자동화 (Time-Slot 패치)")
st.markdown("**발송 시간대별(12시/14시) 정밀 가중치** 적용 완료")

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'])
    op_mode = st.selectbox("운영 기조", ['일반', '상품증대', '효율화'])

    st.header("2. 목표 데이터 (광고주/SA 공유)")
    active_member = st.number_input("활동 인원 (명)", value=361)
    target_total_advertiser = st.number_input("광고주 캠페인 총합", value=3627)
    sa_est_17 = st.number_input("SA 예상 (17시)", value=939)
    sa_est_18 = st.number_input("SA 예상 (18시)", value=995)
    
    # [중요] 계산된 목표(2632)와 실제 목표(2532) 차이인 -100 입력
    da_add_target = st.number_input("DA 목표 조정 (버퍼)", value=-100)
    
    # [중요] 표 이미지 상의 10시 누적 자원 입력
    start_resource_10 = st.number_input("10시 시작 자원 (표 기준)", value=1408)

    st.header("3. 실시간 실적 (DA+제휴만)")
    current_total = st.number_input("현재 실적 총합", value=1852)
    # 14시 기준 실적 입력 (없으면 추정치)
    current_bojang = st.number_input("현재 보장분석", value=1286)
    current_prod = st.number_input("현재 상품자원", value=566)

    st.header("4. 비용 입력 (원 단위)")
    cost_total = st.number_input("비용 총합", value=62750000)
    cost_da = st.number_input("DA 비용", value=41460000)
    cost_aff = st.number_input("제휴 비용", value=21290000)

    st.header("5. 기타 설정")
    tom_member = st.number_input("명일 활동 인원", value=361)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    
    # [NEW] 고정구좌 발송 시간 선택 기능
    fixed_ad_type = st.radio("고정구좌 발송 시간", ["없음", "12시 Only", "14시 Only", "12시+14시 Both"])
    fixed_content = st.text_input("고정구좌 내용", value="14시 카카오페이 TMS 발송 예정입니다")

# 3. 로직 처리
def generate_report():
    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.88 # 오늘 기준 보장비중 88%
    else: ratio_ba = 0.898
    ratio_prod = 1 - ratio_ba
    
    w = {'월': 1.1, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)

    # 목표 계산
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    
    # [핵심] 발송 타입별 17시 목표 역산 비율 (자연 증가분)
    if fixed_ad_type == "없음":
        gap_percent = 0.040 # 평시
    elif fixed_ad_type == "14시 Only":
        gap_percent = 0.033 # 15시에 몰리고 17-18시는 둔화
    else:
        gap_percent = 0.032 # 12시, Both 포함

    hourly_gap = round(da_target_18 * gap_percent) 
    da_target_17 = da_target_18 - hourly_gap 

    da_per_18 = round(da_target_18 / active_member, 1)
    da_per_17 = round(da_target_17 / active_member, 1)

    # 실시간 예상 마감 시뮬레이션
    # 오늘 같은 날은 14시 이후 폭증하므로 pace를 높게 잡음
    if fixed_ad_type == "14시 Only":
        base_pace = 210
    elif fixed_ad_type == "없음":
        base_pace = 140
    else:
        base_pace = 195
        
    hourly_pace = base_pace * w
    est_increase = round(hourly_pace * 4.0)
    est_18 = current_total + est_increase
    
    # 보정 로직
    if est_18 > da_target_18 + 150: est_18 = da_target_18 + 50
    elif est_18 < da_target_18 - 200: est_18 = da_target_18 - 50
    est_24 = round(est_18 * 1.35)

    # 멘트 생성
    achieve_rate = est_18 / da_target_18
    if achieve_rate >= 0.99:
        status_msg = "전체 수량 또한 양사 합산 시 달성가능할 것으로 보입니다."
        action_msg = "조기 배정마감되는 경우, 배너광고 조정하도록 하겠습니다."
    else:
        status_msg = f"목표 대비 약 {da_target_18 - est_18}건 부족할 것으로 예상되나, 집중 운영하겠습니다."
        action_msg = "남은 시간 상품수량 확보 및 보장분석 효율화 자원 확보에 집중하겠습니다."

    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"

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
        'fixed_msg': fixed_msg, 'status_msg': status_msg, 'action_msg': action_msg,
        'cpa_14': cpa_14, 'cpa_da': cpa_da, 'cpa_aff': cpa_aff
    }

res = generate_report()

# 4. 결과 출력
tab1, tab2, tab3 = st.tabs(["오전 목표 수립", "실시간 현황 (14시)", "명일 자원 수립"])

with tab1:
    st.subheader("📋 오전 10:30 목표 수립 보고")
    report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {res['da_17']}건 ({active_member}명, {res['per_17']}건 배정 기준)
ㄴ 보장분석 : {res['ba_17']}건
ㄴ 상품 : {res['prod_17']}건

[18시 기준]
총 자원 : {res['da_18']}건 ({active_member}명, {res['per_18']}건 배정 기준)
ㄴ 보장분석 : {res['ba_18']}건
ㄴ 상품 : {res['prod_18']}건

* {res['fixed_msg']}"""
    st.text_area("복사용 텍스트 (오전):", report_morning, height=300)
    
    st.markdown("#### 📉 시간대별 배분 계획표")
    
    # [핵심] 선택한 발송 타입에 따른 동적 가중치 할당
    hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
    
    if fixed_ad_type == "14시 Only":
        # 오늘(12/18) 패턴: 14시까지 일정하다가 15시에 폭발 (image_b0ad45 반영)
        # 비율: 0.11(평) -> 0.28(피크) -> 0.08(감소)
        weights = [0, 0.11, 0.11, 0.11, 0.11, 0.28, 0.10, 0.10, 0.08]
        
    elif fixed_ad_type == "12시 Only":
        # 13시에 피크
        weights = [0, 0.10, 0.10, 0.28, 0.12, 0.12, 0.10, 0.10, 0.08]
        
    elif fixed_ad_type == "12시+14시 Both":
        # 13시, 15시 더블 피크
        weights = [0, 0.10, 0.10, 0.20, 0.10, 0.25, 0.10, 0.08, 0.07]
        
    else: # 없음
        weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]

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
    
    da_tom_req = tom_total_target - tom_sa_9
    
    report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {tom_total_target}건
ㄴ 보장분석 : {round(da_tom_req * ratio_ba)}건
ㄴ 상품자원 : {round(da_tom_req * (1-ratio_ba))}건

* 명일 영업가족 {tom_member}명 기준 인당 자원 {tom_per}건 이상 확보할 수 있도록 운영 예정입니다."""
    st.text_area("복사용 텍스트 (퇴근):", report_tomorrow, height=250)
