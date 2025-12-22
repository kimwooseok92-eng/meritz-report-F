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
st.title("📊 메리츠화재 DA 보고 자동화 (V4.1)")
st.markdown("✅ **12시 발송 완료 시 예측 정확도 보정 (과대평가 방지)**")

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
    target_mode = st.radio("목표 수립 기조", 
                           ['평시 (8.5~9.0건)', '이슈/보수적 (6.0~7.2건)', '월말/공격적 (9.5건↑)'],
                           index=1 if day_option=='월' else 0)
    op_mode = st.selectbox("운영 전략", ['일반', '상품증대', '효율화'])

    st.header("2. 오전 목표 (매뉴얼 반영)")
    active_member = st.number_input("금일 활동 인원", value=359)
    target_total_advertiser = st.number_input("광고주 전달 목표 (전체)", value=3666)
    sa_est_18 = st.number_input("SA 예상 (18시)", value=1399)
    da_add_target = st.number_input("DA 추가 버퍼 (+20~100건)", value=50, step=10)
    start_resource_10 = st.number_input("10시 시작 자원 (그래프용)", value=1100)

    st.header("3. 실시간 실적 입력")
    # 14시 또는 16시 시점의 데이터를 입력하세요
    current_total = st.number_input("현재 총 자원 (DA+제휴)", value=1963)
    current_bojang = st.number_input("ㄴ 보장분석", value=1600)
    current_prod = st.number_input("ㄴ 상품자원", value=363)

    st.header("4. 비용 입력 (14시 보고용)")
    cost_da = st.number_input("DA 소진액", value=23560000)
    cost_aff = st.number_input("제휴 소진액", value=11270000)
    cost_total = cost_da + cost_aff

    st.header("5. 명일 예상 설정")
    tom_member = st.number_input("명일 활동 인원", value=350)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    tom_dawn_ad = st.checkbox("내일 새벽 고정광고 있음", value=False)
    
    st.header("6. 금일 고정구좌 (중요)")
    fixed_ad_type = st.radio("발송 시간", ["없음", "12시 Only", "14시 Only", "12시+14시 Both"], index=1)
    fixed_content = st.text_input("내용", value="12시 KBPAY 발송 완료되었습니다")

# 3. 로직 처리
def generate_report():
    # 1) 보장/상품 비율
    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.88 
    else: ratio_ba = 0.898
    ratio_prod = 1 - ratio_ba
    
    # 2) 요일 가중치
    w = {'월': 0.82, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)
    if fixed_ad_type != "없음": 
        if day_option == '월': w = 0.90 
        else: w = max(w, 1.0)

    # 3) 목표 계산
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    da_per_18 = round(da_target_18 / active_member, 1)
    
    # 17시 목표 역산
    if fixed_ad_type == "없음": gap_percent = 0.040 
    elif fixed_ad_type == "14시 Only": gap_percent = 0.033 
    else: gap_percent = 0.032 
    da_target_17 = da_target_18 - round(da_target_18 * gap_percent) 
    da_per_17 = round(da_target_17 / active_member, 1)

    # 4) [14시 로직] 재무 및 예측 (V4.1 핵심 수정)
    if "12시" in fixed_ad_type:
        forecast_multiplier = 1.215 # 오늘 데이터(1.21) 반영
    else:
        forecast_multiplier = 1.35 * w 
        
    est_18_from_14 = int(current_total * forecast_multiplier)
    
    # Range 보정
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150
    
    # 24시 예측
    est_cost_24 = int(cost_total * 1.8)

    # 5) [16시 로직] 운영 및 Last Spurt
    est_18_from_16 = int(current_total / 0.91)
    remaining_gap = est_18_from_16 - current_total
    
    if remaining_gap < 150: remaining_gap = 150
    elif remaining_gap > 350: remaining_gap = 350
    
    last_spurt_ba = int(remaining_gap * 0.9) 
    last_spurt_prod = remaining_gap - last_spurt_ba

    # 6) 멘트 생성
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

    # 7) CPA 계산
    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total else 0

    # 8) 명일 예측
    base_multiplier = 3.15
    tom_base_total = int(tom_member * base_multiplier)
    ad_boost = 300 if tom_dawn_ad else 0
    tom_total_target = tom_base_total + ad_boost
    tom_da_req = tom_total_target - tom_sa_9
    
    if tom_dawn_ad: tom_per_msg = 5.0 
    else: tom_per_msg = 4.4

    return {
        'da_17': da_target_17, 'per_17': da_per_17,
        'ba_17': round(da_target_17 * ratio_ba), 'prod_17': round(da_target_17 * ratio_prod),
        'da_18': da_target_18, 'per_18': da_per_18,
        'ba_18': round(da_target_18 * ratio_ba), 'prod_18': round(da_target_18 * ratio_prod),
        
        # 14시 데이터
        'est_18_14': est_18_from_14, 
        'est_per_18_14': round(est_18_from_14/active_member, 1),
        'est_ba_18_14': round(est_18_from_14 * 0.90), 
        'est_prod_18_14': round(est_18_from_14 * 0.10),
        'msg_14': msg_14,
        'cpa_da': cpa_da, 'cpa_aff': cpa_aff, 'cpa_total': cpa_total,

        # 16시 데이터
        'est_18_16': current_total + remaining_gap,
        'remaining_total': remaining_gap,
        'remaining_ba': last_spurt_ba,
        'remaining_prod': last_spurt_prod,
        'msg_16': msg_16,

        'fixed_msg': fixed_msg,
        'tom_total': tom_total_target, 'tom_da': tom_da_req, 'tom_per_msg': tom_per_msg,
        'tom_ba': round(tom_da_req * ratio_ba), 'tom_prod': round(tom_da_req * (1-ratio_ba))
    }

res = generate_report()

# 4. 탭 구성
tab1, tab2, tab3, tab4 = st.tabs(["09:30 목표", "14:00 중간(재무)", "16:00 마감(운영)", "18:00 퇴근"])

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
    st.text_area("복사용 텍스트 (오전):", report_morning, height=300)
    
    # 시간대별 그래프 코드 복원
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
    st.subheader("🔥 14:00 중간 보고 (재무/예측)")
    
    est_cost_24 = int(cost_total * 1.8)
    
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
- 총합(DA/제휴): {est_cost_24//10000}만원 / 가망CPA {max(2.9, res['cpa_total']-0.4)}만원"""
    
    st.text_area("복사용 텍스트 (14시):", report_1400, height=450)

with tab3:
    st.subheader("⚠️ 16:00 마감 임박 보고 (운영)")
    st.warning("※ 16시에는 사이드바의 '실시간 실적' 숫자를 16시 기준으로 수정해주세요.")
    
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
