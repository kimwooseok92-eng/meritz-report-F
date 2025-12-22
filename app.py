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
st.title("📊 메리츠화재 DA 보고 자동화 (V3.1)")
st.markdown("**Final Update:** 14시/16시 양식 분리 + 월요일 예측 로직 보정 완료")

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
    target_mode = st.radio("목표 수립 기조", 
                           ['평시 (8.5~9.0건)', '이슈/보수적 (6.0~7.2건)', '월말/공격적 (9.5건↑)'],
                           index=1 if day_option=='월' else 0)
    op_mode = st.selectbox("운영 전략", ['일반', '상품증대', '효율화'])

    st.header("2. 오전 목표 (광고주 공유값)")
    active_member = st.number_input("금일 활동 인원", value=359)
    target_total_advertiser = st.number_input("광고주 캠페인 총합", value=3600)
    sa_est_18 = st.number_input("SA 예상 (18시)", value=1000)
    da_add_target = st.number_input("DA 목표 버퍼", value=0)
    start_resource_10 = st.number_input("10시 시작 자원 (그래프용)", value=1100)

    st.header("3. 실시간 실적 입력")
    # 14시 또는 16시 시점의 데이터를 입력
    current_total = st.number_input("현재 총 자원 (DA+제휴)", value=1800)
    current_bojang = st.number_input("ㄴ 보장분석", value=1500)
    current_prod = st.number_input("ㄴ 상품자원", value=300)

    st.header("4. 비용 입력 (14시 보고용)")
    cost_da = st.number_input("DA 소진액", value=45000000)
    cost_aff = st.number_input("제휴 소진액", value=20000000)
    cost_total = cost_da + cost_aff

    st.header("5. 명일 예상 설정")
    tom_member = st.number_input("명일 활동 인원", value=350)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    tom_dawn_ad = st.checkbox("내일 새벽 고정광고 있음", value=False)
    
    st.header("6. 금일 고정구좌")
    fixed_ad_type = st.radio("발송 시간", ["없음", "12시 Only", "14시 Only", "12시+14시 Both"], index=2)
    fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

# 3. 로직 처리
def generate_report():
    # 1) 보장/상품 비율
    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.88 
    else: ratio_ba = 0.898
    ratio_prod = 1 - ratio_ba
    
    # 2) 요일 가중치 (월요일 과대평가 방지 로직 적용)
    # 월요일은 14시 실적이 높아도 18시 마감율이 낮으므로 가중치 0.82 적용
    w = {'월': 0.82, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)
    
    # 고정광고가 있으면 가중치 회복 (단, 월요일은 보수적 유지)
    if fixed_ad_type != "없음": 
        if day_option == '월': w = 0.90 # 월요일이라도 광고 있으면 조금 회복
        else: w = max(w, 1.0)

    # 3) 목표 계산
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    
    # 17시 목표 역산
    if fixed_ad_type == "없음": gap_percent = 0.040 
    elif fixed_ad_type == "14시 Only": gap_percent = 0.033 
    else: gap_percent = 0.032 
    da_target_17 = da_target_18 - round(da_target_18 * gap_percent) 

    da_per_18 = round(da_target_18 / active_member, 1)
    da_per_17 = round(da_target_17 / active_member, 1)

    # 4) [14시 로직] Financial Forecast (월요일 보정 적용)
    # 기본 Multiplier 1.35 * 요일가중치
    est_18_from_14 = int(current_total * 1.35 * w)
    
    # Range 보정 (목표와 너무 동떨어지지 않게)
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150
    
    # 24시 예측 (18시 대비 약 1.4배)
    est_24 = int(est_18_from_14 * 1.40)

    # 5) [16시 로직] Last Spurt (적중률 높음)
    # 16시 실적 / 0.91 (약 9% 추가 성장)
    est_18_from_16 = int(current_total / 0.91)
    
    remaining_gap = est_18_from_16 - current_total
    
    # 최소/최대 안전장치
    if remaining_gap < 150: remaining_gap = 150
    elif remaining_gap > 350: remaining_gap = 350
    
    last_spurt_ba = int(remaining_gap * 0.9) 
    last_spurt_prod = remaining_gap - last_spurt_ba

    # 6) 멘트 생성
    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"
    
    # 14시용 멘트
    if est_18_from_14 >= da_target_18:
        msg_14 = "금일 고정구좌 이슈없이 집행중이며, 전체 수량 또한 양사 합산 시 달성가능할 것으로 보입니다."
    else:
        msg_14 = f"오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 상품자원/보장분석 Push 운영하겠습니다."

    # 16시용 멘트 (운영 중심)
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
    tom_per_msg = 5.2 if tom_dawn_ad else 4.4

    return {
        'da_17': da_target_17, 'per_17': da_per_17,
        'ba_17': round(da_target_17 * ratio_ba), 'prod_17': round(da_target_17 * ratio_prod),
        'da_18': da_target_18, 'per_18': da_per_18,
        'ba_18': round(da_target_18 * ratio_ba), 'prod_18': round(da_target_18 * ratio_prod),
        
        # 14시 데이터
        'est_18_14': est_18_from_14, 
        'est_per_18_14': round(est_18_from_14/active_member, 1),
        'est_ba_18_14': round
