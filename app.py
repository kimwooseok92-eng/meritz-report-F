import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os

# ==========================================
# 1. 폰트 설정 (웹 환경 호환용)
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
st.title("📊 메리츠화재 DA 보고 자동화 (Final)")
st.markdown("SA 수치를 제외한 **순수 DA/제휴 성과**를 기준으로 보고서를 생성합니다.")

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'])
    op_mode = st.selectbox("운영 기조", ['일반', '상품증대', '효율화'])

    st.header("2. 목표 데이터 (광고주 공유)")
    active_member = st.number_input("활동 인원 (명)", value=359)
    # 광고주가 주는 목표는 보통 SA 포함 전체 목표임
    target_total_advertiser = st.number_input("광고주 전체 목표 (SA포함)", value=2539)
    sa_est_17 = st.number_input("SA 예상 (17시)", value=1016)
    sa_est_18 = st.number_input("SA 예상 (18시)", value=1083)
    da_add_target = st.number_input("DA 추가 확보 목표 (버퍼)", value=50)
    start_resource_10 = st.number_input("10시 시작 자원 (누적)", value=1462)

    st.header("3. 실시간 실적 (DA+제휴만 입력)")
    current_total = st.number_input("현재 실적 총합", value=1799)
    current_bojang = st.number_input("현재 보장분석", value=1533)
    current_prod = st.number_input("현재 상품자원", value=266)

    st.header("4. 비용 입력 (원 단위)")
    cost_total = st.number_input("비용 총합", value=62750000)
    cost_da = st.number_input("DA 비용", value=41460000)
    cost_aff = st.number_input("제휴 비용", value=21290000)

    st.header("5. 기타 설정")
    tom_member = st.number_input("명일 활동 인원", value=359)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    fixed_ad = st.checkbox("고정구좌 집행 여부", value=True)
    fixed_content = st.text_input("고정구좌 내용", value="12시 BC카드 LMS, 14시 카카오페이 TMS")

# ==========================================
# 3. 로직 처리 (수정된 부분)
# ==========================================
def generate_report():
    # 운영 기조에 따른 비율
    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.92
    else: ratio_ba = 0.898
    ratio_prod = 1 - ratio_ba
    
    w = {'월': 1.1, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)

    # [핵심 수정] DA 목표 = 전체 목표 - SA 예상 + 추가분
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    da_target_17 = target_total_advertiser - sa_est_17 + da_add_target
    
    # 오전 보고용 전체(Total) 자원 (SA 포함)
    total_resource_18 = da_target_18 + sa_est_18
    total_resource_17 = da_target_17 + sa_est_17

    # 인당 배분 계산
    target_per_18 = round(da_target_18 / active_member, 1) # DA 기준 인당배분 (실무적으로 이렇게 볼 수도 있음)
    # 하지만 통상 보고에는 '전체 인당배분'을 쓰는지 'DA 인당배분'을 쓰는지 확인 필요.
    # 대행사 리포트 예시 "총 2976건 (8.6건)" -> 이건 전체 기준임.
    # 따라서 실시간 보고의 '목표' 텍스트는 DA 기준으로 바꿔야 함.
    
    # DA 목표 기준 인당 배분
    da_target_per_18 = round(da_target_18 / active_member, 1)

    # 예상 마감 시뮬레이션 (DA Only)
    hourly_pace = 195 * w if fixed_ad else 140 * w
    est_increase = round(hourly_pace * 4.0)
    est_18 = current_total + est_increase
    
    # 보정: DA 목표 근처로 수렴 (SA 제외된 목표와 비교)
    if est_18 > da_target_18 + 150: est_18 = da_target_18 + 50
    elif est_18 < da_target_18 - 200: est_18 = da_target_18 - 50
    
    est_24 = round(est_18 * 1.35)

    # 멘트 생성 (DA 목표 달성률 기준)
    achieve_rate = est_18 / da_target_18
    if achieve_rate >= 0.99:
        status_msg = "전체 수량 또한 양사 합산 시 달성가능할 것으로 보입니다."
        action_msg = "조기 배정마감되는 경우, 배너광고 조정하도록 하겠습니다."
    else:
        status_msg = f"DA 목표 대비 약 {da_target_18 - est_18}건 부족할 것으로 예상되나, 집중 운영하겠습니다."
        action_msg = "남은 시간 상품수량 확보 및 보장분석 효율화 자원 확보에 집중하겠습니다."

    fixed_msg = f"금일 제휴 고정구좌 {fixed_content} 예정되어 있습니다." if fixed_ad else "금일 특이사항 없이 운영 중이며,"
    fixed_act = "집행 후 확보 추이에 따라 DA배너 광고 조정하겠습니다." if fixed_ad else ""

    # CPA
    cpa_14 = round(cost_total / current_total / 10000, 1) if current_total else 0
    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0

    return {
        # 오전 보고용 (SA 포함 Total)
        'total_17': total_resource_17, 'total_per_17': round(total_resource_17/active_member, 1),
        'total_18': total_resource_18, 'total_per_18': round(total_resource_18/active_member, 1),
        'da_part_17': da_target_17, 'da_part_18': da_target_18, # DA 파트 할당량
        'ba_18': round(da_target_18 * ratio_ba), 'prod_18': round(da_target_18 * ratio_prod),
        
        # 실시간 보고용 (DA Only)
        'da_target_18': da_target_18, 'da_per_18': da_target_per_18,
        'est_18': est_18, 'est_per_18': round(est_18/active_member, 1),
        'est_ba_18': round(est_18 * ratio_ba), 'est_prod_18': round(est_18 * ratio_prod),
        'est_24': est_24,
        
        'fixed_msg': fixed_msg, 'fixed_act': fixed_act, 'status_msg': status_msg, 'action_msg': action_msg,
        'cpa_14': cpa_14, 'cpa_da': cpa_da, 'cpa_aff': cpa_aff
    }

res = generate_report()

# ==========================================
# 4. 결과 출력
# ==========================================
tab1, tab2, tab3 = st.tabs(["오전 목표 수립", "실시간 현황 (14시)", "명일 자원 수립"])

with tab1:
    st.subheader("📋 오전 10:30 목표 수립 보고")
    st.info("오전 보고는 SA 수치를 포함한 **전체 예상 마감**을 공유합니다.")
    report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {res['total_17']}건 ({active_member}명, {res['total_per_17']}건 배정 기준)
ㄴ DA+제휴 : {res['da_part_17']}건 / SA : {sa_est_17}건

[18시 기준]
총 자원 : {res['total_18']}건 ({active_member}명, {res['total_per_18']}건 배정 기준)
ㄴ DA+제휴 : {res['da_part_18']}건 / SA : {sa_est_18}건
ㄴ 보장분석(DA) : {res['ba_18']}건
ㄴ 상품(DA) : {res['prod_18']}건

* {res['fixed_msg']} {res['fixed_act']}
* 상품자원 오전부터 push하여 운영 중입니다."""
    st.text_area("복사용 텍스트 (오전):", report_morning, height=300)
    
    # 표 그리기 (DA 목표 기준 배분)
    st.markdown("#### 📉 시간대별 배분 계획표 (DA 목표 기준)")
    hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
    weights = [0, 0.40, 0.40, 0.80, 0.33, 0.80, 0.40, 0.34, 0.23]
    gap = res['da_part_18'] - start_resource_10
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
                   colLabels=hours, rowLabels=['DA누적자원', '인당배분', '시간당 확보'],
                   loc='center', cellLoc='center')
    
    for (i, j), cell in tbl.get_celld().items():
        if i == 0: cell.set_facecolor('black'); cell.set_text_props(color='white', weight='bold')
        elif j == -1: cell.set_facecolor('#f2f2f2'); cell.set_text_props(weight='bold')
    tbl.scale(1, 2)
    st.pyplot(fig)

with tab2:
    st.subheader("📋 실시간 현황 보고 (14시)")
    st.warning("⚠️ 여기는 **SA 수치를 뺀 순수 DA 목표**와 비교합니다.")
    
    report_realtime = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(DA Only) : 인당배분 {res['da_per_18']}건 / 총 {res['da_target_18']}건
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
    tom_per = 4.8 if (res['est_18'] / res['da_target_18']) >= 0.98 else 4.4
    tom_total_target = round(tom_member * tom_per)
    
    if op_mode == '상품증대': r_ba = 0.84
    elif op_mode == '효율화': r_ba = 0.92
    else: r_ba = 0.898
    
    da_tom_req = tom_total_target - tom_sa_9
    
    report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {tom_total_target}건
ㄴ 보장분석 : {round(da_tom_req * r_ba)}건
ㄴ 상품자원 : {round(da_tom_req * (1-r_ba))}건

* 명일 영업가족 {tom_member}명 기준 인당 자원 {tom_per}건 이상 확보할 수 있도록 운영 예정입니다."""
    st.text_area("복사용 텍스트 (퇴근):", report_tomorrow, height=250)