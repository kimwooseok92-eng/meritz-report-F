import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import os
import io
import matplotlib.font_manager as fm
import platform

# -----------------------------------------------------------
# 1. 폰트 설정
# -----------------------------------------------------------
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
    
    if os.path.exists(font_path):
        font_prop = fm.FontProperties(fname=font_path)
        plt.rc('font', family=font_prop.get_name())
    else:
        plt.rc('font', family=font_name)
    plt.rcParams['axes.unicode_minus'] = False

set_korean_font()

# -----------------------------------------------------------
# 2. 유틸리티 함수
# -----------------------------------------------------------
def parse_uploaded_files(files):
    combined_df = pd.DataFrame()
    for file in files:
        try:
            if file.name.endswith('.csv'):
                try: df = pd.read_csv(file, encoding='utf-8-sig')
                except: df = pd.read_csv(file, encoding='cp949')
            else:
                df = pd.read_excel(file)
            
            cols = df.columns.tolist()
            col_cost = next((c for c in cols if any(x in c for x in ['비용', '소진', 'Cost', '금액'])), None)
            col_cnt = next((c for c in cols if any(x in c for x in ['전환', '수량', 'DB', '건수', 'Cnt', '배분'])), None)
            col_camp = next((c for c in cols if any(x in c for x in ['캠페인', '광고명', '매체', '그룹', 'account'])), None)
            col_type = next((c for c in cols if any(x in c for x in ['구분', 'type'])), None)

            if col_cost and col_cnt:
                temp = pd.DataFrame()
                temp['cost'] = df[col_cost].fillna(0)
                temp['count'] = df[col_cnt].fillna(0)
                temp['campaign'] = df[col_camp].fillna('기타') if col_camp else '기타'
                
                if col_type: temp['type'] = df[col_type].fillna('')
                else: temp['type'] = temp['campaign'].apply(lambda x: '보장' if '보장' in str(x) else '상품')
                
                combined_df = pd.concat([combined_df, temp], ignore_index=True)
        except Exception as e:
            st.error(f"파일 읽기 오류 ({file.name}): {e}")
    return combined_df

def analyze_data(df):
    res = {
        'total_cnt': 0, 'total_cost': 0,
        'bojang_cnt': 0, 'prod_cnt': 0,
        'da_cost_only': 0,
        'media_stats': pd.DataFrame(),
        'ratio_ba': 0.12
    }
    
    if df.empty: return res

    res['total_cnt'] = int(df['count'].sum())
    res['total_cost'] = int(df['cost'].sum())

    mask_bojang = df['type'].astype(str).str.contains('보장')
    res['bojang_cnt'] = int(df[mask_bojang]['count'].sum())
    res['prod_cnt'] = int(df[~mask_bojang]['count'].sum())
    
    if res['total_cnt'] > 0:
        res['ratio_ba'] = res['bojang_cnt'] / res['total_cnt']
        
    mask_aff = df['campaign'].astype(str).str.contains('제휴')
    res['da_cost_only'] = int(df[~mask_aff]['cost'].sum())

    def normalize_media(name):
        name = str(name).lower()
        if '네이버' in name or 'naver' in name or 'nasp' in name: return '네이버'
        if '카카오' in name or 'kakao' in name: return '카카오'
        if '토스' in name or 'toss' in name: return '토스'
        if '구글' in name or 'google' in name: return '구글'
        return '기타'
    
    df['media_group'] = df['campaign'].apply(normalize_media)
    
    pivot_cnt = df.pivot_table(index='media_group', columns='type', values='count', aggfunc='sum', fill_value=0)
    pivot_cost = df.pivot_table(index='media_group', columns='type', values='cost', aggfunc='sum', fill_value=0)
    
    pivot_cnt.columns = [f"현재_{c}" for c in pivot_cnt.columns]
    
    media_cost = df.pivot_table(index='media_group', values='cost', aggfunc='sum', fill_value=0)
    media_cost.columns = ['현재_비용']

    stats = pd.concat([pivot_cnt, media_cost], axis=1).fillna(0).astype(int)
    res['media_stats'] = stats
            
    return res

# -----------------------------------------------------------
# 3. 웹사이트 UI & 사이드바
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V6.5", layout="wide")
st.title("📊 메리츠화재 DA 보고 자동화 (V6.5)")

with st.sidebar:
    st.header("1. 기본 설정")
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
    target_mode = st.radio("목표 수립 기조", 
                           ['평시 (8.5~9.0건)', '이슈/보수적 (6.0~7.2건)', '월말/공격적 (9.5건↑)'],
                           index=1 if day_option=='월' else 0)
    
    st.markdown("""<small>💡 <b>운영 전략:</b> 파일 업로드 시 실제 비율 적용</small>""", unsafe_allow_html=True)
    op_mode = st.selectbox("운영 전략", ['일반', '상품증대', '효율화'])

    st.markdown("---")
    st.header("2. 목표 수립")
    active_member = st.number_input("금일 활동 인원", value=359)
    col_t1, col_t2 = st.columns(2)
    with col_t1: target_bojang = st.number_input("🎯 보장 목표", value=500)
    with col_t2: target_product = st.number_input("🎯 상품 목표", value=3100)
    target_total_advertiser = target_bojang + target_product
    
    sa_est_18 = st.number_input("SA 예상 (18시)", value=1000)
    da_add_target = st.number_input("DA 추가 버퍼", value=50, step=10)

    st.markdown("---")
    st.header("3. [자동] 10시 시작 자원")
    with st.expander("📂 파일 업로드"):
        file_yest_24 = st.file_uploader("어제 24시 마감 파일", key="f1")
        file_today_10 = st.file_uploader("오늘 10시 현재 파일", key="f2")
        reported_yest_18 = st.number_input("어제 18시 보고된 총량", value=3000)

    start_resource_10 = 1100
    if file_yest_24 and file_today_10:
        df_y24 = parse_uploaded_files([file_yest_24])
        df_t10 = parse_uploaded_files([file_today_10])
        cnt_y24 = int(df_y24.iloc[:, 1].sum()) if not df_y24.empty else 0
        cnt_t10 = int(df_t10.iloc[:, 1].sum()) if not df_t10.empty else 0
        calc_start = (cnt_y24 - reported_yest_18) + cnt_t10
        if calc_start > 0: start_resource_10 = calc_start
    start_resource_10 = st.number_input("10시 시작 자원 (최종)", value=start_resource_10)

    st.markdown("---")
    st.header("4. [자동] 실시간 분석")
    uploaded_realtime = st.file_uploader("📊 실시간 로우데이터", accept_multiple_files=True)
    
    real_data = analyze_data(parse_uploaded_files(uploaded_realtime) if uploaded_realtime else pd.DataFrame())
    
    if uploaded_realtime and not real_data['media_stats'].empty:
        st.success(f"실적 집계 완료 ({real_data['total_cnt']:,}건)")
        def_total = real_data['total_cnt']
        def_bojang = real_data['bojang_cnt']
        def_prod = real_data['prod_cnt']
        def_cost_da = real_data['da_cost_only']
    else:
        def_total, def_bojang, def_prod = 1963, 1600, 363
        def_cost_da = 23560000

    current_total = st.number_input("현재 총 자원", value=def_total)
    current_bojang = st.number_input("ㄴ 보장분석", value=def_bojang)
    current_prod = st.number_input("ㄴ 상품자원", value=def_prod)
    
    cost_da = st.number_input("DA 소진액 (자동)", value=def_cost_da)
    if uploaded_realtime: st.warning("👇 제휴 소진액을 직접 입력해주세요!")
    cost_aff = st.number_input("제휴 소진액 (수기)", value=11270000)
    cost_total = cost_da + cost_aff

    st.markdown("---")
    st.header("5. 기타 설정")
    tom_member = st.number_input("명일 활동 인원", value=350)
    tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
    tom_dawn_ad = st.checkbox("내일 새벽 고정광고 있음", value=False)
    fixed_ad_type = st.radio("발송 시간", ["없음", "12시 Only", "14시 Only", "12시+14시 Both"], index=2)
    fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")


# -----------------------------------------------------------
# 4. 핵심 로직
# -----------------------------------------------------------
def generate_report():
    # A. Multiplier 계산
    w = {'월': 0.82, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)
    if fixed_ad_type != "없음": 
        if day_option == '월': w = 0.90 
        else: w = max(w, 1.0)

    # 14시 예측용 계수
    if "12시" in fixed_ad_type: mul_14 = 1.215 
    else: mul_14 = 1.35 * w 

    # 16시 예측용 계수 (1/0.91 = 약 1.098)
    mul_16 = 1.099 

    # B. 전체 목표
    da_target_18 = target_total_advertiser - sa_est_18 + da_add_target
    da_per_18 = round(da_target_18 / active_member, 1)
    
    gap_percent = 0.040 if fixed_ad_type == "없음" else 0.032
    da_target_17 = da_target_18 - round(da_target_18 * gap_percent)
    da_per_17 = round(da_target_17 / active_member, 1)
    
    # C. 전체 예측 (14시 기준)
    est_18_from_14 = int(current_total * mul_14)
    # Range 보정
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150

    # D. 비율 결정
    if uploaded_realtime and real_data['total_cnt'] > 0:
        ratio_ba = real_data['ratio_ba']
    else:
        if op_mode == '상품증대': ratio_ba = 0.16 
        elif op_mode == '효율화': ratio_ba = 0.12
        else: ratio_ba = 0.102

    # E. 매체별 대시보드 생성 (14시용 / 16시용 분리)
    dash_14, dash_16 = pd.DataFrame(), pd.DataFrame()
    
    if not real_data['media_stats'].empty:
        # 14시 대시보드
        d14 = real_data['media_stats'].copy()
        for col in d14.columns:
            if '건수' in col:
                d14[col.replace('현재', '예상')] = (d14[col] * mul_14).astype(int)
        cols14 = sorted(d14.columns.tolist())
        dash_14 = d14[cols14]

        # 16시 대시보드
        d16 = real_data['media_stats'].copy()
        for col in d16.columns:
            if '건수' in col:
                d16[col.replace('현재', '예상')] = (d16[col] * mul_16).astype(int)
        cols16 = sorted(d16.columns.tolist())
        dash_16 = d16[cols16]

    # F. 16시 예측 (전체)
    est_18_from_16 = int(current_total * mul_16)
    remaining_gap = est_18_from_16 - current_total
    if remaining_gap < 150: remaining_gap = 150
    elif remaining_gap > 350: remaining_gap = 350
    
    last_spurt_ba = int(remaining_gap * 0.9) 
    last_spurt_prod = remaining_gap - last_spurt_ba

    # G. 멘트 및 CPA
    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"
    
    if est_18_from_14 >= da_target_18:
        msg_14 = "금일 고정구좌 이슈없이 집행중이며, 전체 수량 또한 양사 합산 시 소폭 초과 달성할 것으로 보입니다."
    else:
        msg_14 = f"오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 상품자원/보장분석 Push 운영하겠습니다."

    if current_total + remaining_gap >= da_target_18:
        msg_16 = "* 보장분석 자원 넉넉할 것으로 보여 DA배너 일부 축소하여 비용 절감하겠습니다."
    else:
        msg_16 = "* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."

    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total else 0

    est_cost_24 = int(cost_total * 1.8)

    # H. 명일 예측
    base_multiplier = 3.15
    tom_base_total = int(tom_member * base_multiplier)
    ad_boost = 300 if tom_dawn_ad else 0
    tom_total_target = tom_base_total + ad_boost
    tom_da_req = tom_total_target - tom_sa_9
    tom_per_msg = 5.0 if tom_dawn_ad else 4.4

    return {
        'da_17': da_target_17, 'per_17': da_per_17,
        'ba_17': round(da_target_17 * ratio_ba), 'prod_17': round(da_target_17 * (1-ratio_ba)),
        'da_18': da_target_18, 'per_18': da_per_18,
        'ba_18': round(da_target_18 * ratio_ba), 'prod_18': round(da_target_18 * (1-ratio_ba)),
        'est_18_14': est_18_from_14, 
        'est_per_18_14': round(est_18_from_14/active_member, 1),
        'est_ba_18_14': round(est_18_from_14 * ratio_ba), 
        'est_prod_18_14': round(est_18_from_14 * (1-ratio_ba)),
        'msg_14': msg_14, 'cpa_da': cpa_da, 'cpa_aff': cpa_aff, 'cpa_total': cpa_total,
        'est_18_16': current_total + remaining_gap,
        'remaining_total': remaining_gap, 'remaining_ba': last_spurt_ba, 'remaining_prod': last_spurt_prod, 'msg_16': msg_16,
        'fixed_msg': fixed_msg,
        'tom_total': tom_total_target, 'tom_da': tom_da_req, 'tom_per_msg': tom_per_msg,
        'tom_ba': round(tom_da_req * ratio_ba), 'tom_prod': round(tom_da_req * (1-ratio_ba)),
        'dash_14': dash_14, 'dash_16': dash_16
    }

res = generate_report()

# -----------------------------------------------------------
# 5. 메인 탭
# -----------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근"])

with tab1:
    st.subheader("📋 오전 10:30 목표 수립")
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
    st.text_area("복사 텍스트:", report_morning, height=300)
    
    hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
    weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09] 
    if fixed_ad_type == "14시 Only": weights = [0, 0.11, 0.11, 0.11, 0.11, 0.28, 0.10, 0.10, 0.08]
    elif fixed_ad_type == "12시 Only": weights = [0, 0.10, 0.10, 0.28, 0.12, 0.12, 0.10, 0.10, 0.08]
    elif fixed_ad_type == "12시+14시 Both": weights = [0, 0.10, 0.10, 0.20, 0.10, 0.25, 0.10, 0.08, 0.07]

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
    df_plan = pd.DataFrame([acc_res, per_person, hourly_get], columns=hours, index=['누적자원', '인당배분', '시간당확보'])
    st.table(df_plan)
    
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(hours, acc_res, marker='o', linestyle='-', color='#eb4034')
    for i, txt in enumerate(acc_res):
        ax.annotate(f"{txt}", (hours[i], acc_res[i]), textcoords="offset points", xytext=(0,10), ha='center')
    ax.set_title("누적 자원 예상 흐름")
    ax.grid(True, linestyle='--', alpha=0.5)
    st.pyplot(fig)


with tab2:
    st.subheader("🔥 14:00 중간 보고 & 대시보드")
    
    if not res['dash_14'].empty:
        st.markdown("#### 📊 매체별 예상 성과 (Live Dashboard)")
        highlight_cols = [c for c in res['dash_14'].columns if '예상' in c]
        st.dataframe(res['dash_14'].style.background_gradient(cmap='Blues', subset=highlight_cols).format("{:,}"), use_container_width=True)
    elif uploaded_realtime:
        st.error("⚠️ 데이터를 읽지 못했습니다.")
    else:
        st.info("📂 로우데이터 업로드 시 매체별 상세 예측이 표시됩니다.")

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
    st.text_area("복사 텍스트 (14시):", report_1400, height=450)

with tab3:
    st.subheader("⚠️ 16:00 마감 임박 보고")
    
    # [FIX] 16시 전용 대시보드 (dash_16) 표시
    if not res['dash_16'].empty:
        st.markdown("#### 📊 매체별 운영 현황 (16시 기준 예상)")
        highlight_cols = [c for c in res['dash_16'].columns if '예상' in c]
        st.dataframe(res['dash_16'].style.background_gradient(cmap='Greens', subset=highlight_cols).format("{:,}"), use_container_width=True)

    report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {res['da_18']}건
ㄴ 보장분석 : {res['ba_18']}건, 상품 {res['prod_18']}건

16시 현황 : 총 {current_total}건
ㄴ 보장분석 : {current_bojang}건, 상품 {current_prod}건

16시 ~ 18시 30분 예상 건수
ㄴ 보장분석 {res['remaining_ba']}건
ㄴ 상품 {res['remaining_prod']}건

{res['msg_16']}"""
    st.text_area("복사 텍스트 (16시):", report_1600, height=300)

with tab4:
    st.subheader("🌙 명일 자원 수립")
    ad_msg = "\n* 명일 새벽 고정광고(CPT/풀뷰) 집행 예정으로 자원 추가 확보 예상됩니다." if tom_dawn_ad else ""
    report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {res['tom_total']}건
ㄴ 보장분석 : {res['tom_ba']}건
ㄴ 상품자원 : {res['tom_prod']}건

* 영업가족 {tom_member}명 기준 인당 {res['tom_per_msg']}건 이상 확보할 수 있도록 운영 예정입니다.{ad_msg}"""
    st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)
