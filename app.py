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

def analyze_data(df, aff_to_bojang=False):
    """
    aff_to_bojang: True일 경우 제휴 캠페인을 강제로 '보장'으로 분류
    """
    res = {
        'total_cnt': 0, 'total_cost': 0,
        'bojang_cnt': 0, 'prod_cnt': 0,
        'da_cost_only': 0,
        'media_stats': pd.DataFrame(),
        'ratio_ba': 0.12
    }
    
    if df.empty: return res

    # 1. 제휴를 보장으로 강제 변환 (옵션)
    if aff_to_bojang:
        mask_aff = df['campaign'].astype(str).str.contains('제휴')
        df.loc[mask_aff, 'type'] = '보장'

    res['total_cnt'] = int(df['count'].sum())
    res['total_cost'] = int(df['cost'].sum())

    mask_bojang = df['type'].astype(str).str.contains('보장')
    res['bojang_cnt'] = int(df[mask_bojang]['count'].sum())
    res['prod_cnt'] = int(df[~mask_bojang]['count'].sum())
    
    if res['total_cnt'] > 0:
        res['ratio_ba'] = res['bojang_cnt'] / res['total_cnt']
        
    mask_aff_camp = df['campaign'].astype(str).str.contains('제휴')
    res['da_cost_only'] = int(df[~mask_aff_camp]['cost'].sum())

    def normalize_media(name):
        name = str(name).lower()
        if '네이버' in name or 'naver' in name or 'nasp' in name: return '네이버'
        if '카카오' in name or 'kakao' in name: return '카카오'
        if '토스' in name or 'toss' in name: return '토스'
        if '구글' in name or 'google' in name: return '구글'
        return '기타'
    
    df['media_group'] = df['campaign'].apply(normalize_media)
    
    # 피벗 테이블
    pivot_cnt = df.pivot_table(index='media_group', columns='type', values='count', aggfunc='sum', fill_value=0)
    pivot_cnt.columns = [f"현재_{c}" for c in pivot_cnt.columns]
    
    media_cost = df.pivot_table(index='media_group', values='cost', aggfunc='sum', fill_value=0)
    media_cost.columns = ['현재_비용']

    stats = pd.concat([pivot_cnt, media_cost], axis=1).fillna(0).astype(int)
    
    # 합계 컬럼
    stats['현재_합계'] = stats.get('현재_보장', 0) + stats.get('현재_상품', 0)
    
    res['media_stats'] = stats
            
    return res

# -----------------------------------------------------------
# 3. 웹사이트 UI & 사이드바
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V7.1", layout="wide")
st.title("📊 메리츠화재 DA 통합 운영 시스템 (V7.1)")

with st.sidebar:
    st.header("1. 기본 설정")
    # [NEW] 보고 시점 선택 (대시보드용)
    report_view_option = st.radio("⏱️ 보고 시점 선택 (대시보드)", ["14시 (중간)", "16시 (마감)"], index=0)
    
    day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
    target_mode = st.radio("목표 수립 기조", 
                           ['평시 (8.5~9.0건)', '이슈/보수적 (6.0~7.2건)', '월말/공격적 (9.5건↑)'],
                           index=1 if day_option=='월' else 0)
    
    st.markdown("""<small>💡 <b>운영 전략:</b> 파일 업로드 시 실제 비율 적용</small>""", unsafe_allow_html=True)
    op_mode = st.selectbox("운영 전략", ['일반', '상품증대', '효율화'])

    st.markdown("---")
    st.header("2. 목표 수립 (SA 분리)")
    active_member = st.number_input("금일 활동 인원", value=359)
    
    st.markdown("##### 🎯 전체 목표 (광고주 전달)")
    col_t1, col_t2 = st.columns(2)
    with col_t1: target_bojang = st.number_input("전체 보장 목표", value=500)
    with col_t2: target_product = st.number_input("전체 상품 목표", value=3100)
    target_total_advertiser = target_bojang + target_product
    
    st.markdown("##### 🔎 SA 예상 (차감용)")
    col_s1, col_s2 = st.columns(2)
    with col_s1: sa_est_bojang = st.number_input("SA 보장 예상", value=200)
    with col_s2: sa_est_prod = st.number_input("SA 상품 예상", value=800)
    sa_est_total = sa_est_bojang + sa_est_prod
    
    da_add_target = st.number_input("DA 추가 버퍼 (상품에 반영)", value=50, step=10)

    st.markdown("---")
    st.header("3. [자동] 10시 시작 자원")
    with st.expander("📂 파일 3개 업로드 (완전 자동)"):
        file_yest_24 = st.file_uploader("① 어제 24시 마감 파일", key="f1")
        file_yest_18 = st.file_uploader("② 어제 18시 보고 파일", key="f2")
        file_today_10 = st.file_uploader("③ 오늘 10시 현재 파일", key="f3")

    start_resource_10 = 1100
    if file_yest_24 and file_today_10:
        df_y24 = parse_uploaded_files([file_yest_24])
        df_t10 = parse_uploaded_files([file_today_10])
        cnt_y24 = int(df_y24.iloc[:, 1].sum()) if not df_y24.empty else 0
        cnt_t10 = int(df_t10.iloc[:, 1].sum()) if not df_t10.empty else 0
        
        if file_yest_18:
            df_y18 = parse_uploaded_files([file_yest_18])
            cnt_y18 = int(df_y18.iloc[:, 1].sum()) if not df_y18.empty else 0
            st.success(f"어제 18시 데이터 자동 추출: {cnt_y18}건")
        else:
            cnt_y18 = st.number_input("어제 18시 보고 총량 (수기)", value=3000)
            
        calc_start = (cnt_y24 - cnt_y18) + cnt_t10
        if calc_start > 0: start_resource_10 = calc_start

    start_resource_10 = st.number_input("[자동] 10시 시작 자원 (최종)", value=start_resource_10)

    st.markdown("---")
    st.header("4. [자동] 실시간 분석")
    uploaded_realtime = st.file_uploader("📊 실시간 로우데이터", accept_multiple_files=True)
    
    # [NEW] 제휴 광고 보장분석 예외 처리 옵션
    is_aff_bojang = st.checkbox("☑️ 금일 제휴 광고는 '보장분석' 위주입니다", value=False, help="체크 시 파일 내 제휴 건수를 '보장'으로 분류합니다.")
    
    # 분석 실행 (옵션 전달)
    real_data = analyze_data(parse_uploaded_files(uploaded_realtime) if uploaded_realtime else pd.DataFrame(), aff_to_bojang=is_aff_bojang)
    
    if uploaded_realtime and not real_data['media_stats'].empty:
        st.success(f"집계 완료: {real_data['total_cnt']:,}건")
        def_total = real_data['total_cnt']
        def_bojang = real_data['bojang_cnt']
        def_prod = real_data['prod_cnt']
        def_cost_da = real_data['da_cost_only']
    else:
        def_total, def_bojang, def_prod = 1963, 1600, 363
        def_cost_da = 23560000

    current_total = st.number_input("[자동] 현재 총 자원", value=def_total)
    current_bojang = st.number_input("[자동] ㄴ 보장분석", value=def_bojang)
    current_prod = st.number_input("[자동] ㄴ 상품자원", value=def_prod)
    
    cost_da = st.number_input("[자동] DA 소진액", value=def_cost_da)
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
# 4. 핵심 로직 엔진
# -----------------------------------------------------------
def generate_report():
    # A. Multiplier
    w = {'월': 0.82, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)
    if fixed_ad_type != "없음": 
        if day_option == '월': w = 0.90 
        else: w = max(w, 1.0)

    if "12시" in fixed_ad_type: mul_14 = 1.215 
    else: mul_14 = 1.35 * w 
    mul_16 = 1.099 

    # B. DA 목표 계산
    da_target_bojang = target_bojang - sa_est_bojang
    da_target_prod = target_product - sa_est_prod + da_add_target
    da_target_18 = da_target_bojang + da_target_prod
    da_per_18 = round(da_target_18 / active_member, 1)
    
    gap_percent = 0.040 if fixed_ad_type == "없음" else 0.032
    da_target_17 = da_target_18 - round(da_target_18 * gap_percent)
    da_per_17 = round(da_target_17 / active_member, 1)
    
    # C. 전체 예측
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

    # E. 매체별 대시보드 (14/16시 분리)
    dash_14, dash_16 = pd.DataFrame(), pd.DataFrame()
    if not real_data['media_stats'].empty:
        # 14시용
        d14 = real_data['media_stats'].copy()
        for col in d14.columns:
            if '현재' in col and '비용' not in col: # 건수만 예측
                d14[col.replace('현재', '예상')] = (d14[col] * mul_14).astype(int)
        d14 = d14[sorted(d14.columns.tolist())]
        dash_14 = d14

        # 16시용
        d16 = real_data['media_stats'].copy()
        for col in d16.columns:
            if '현재' in col and '비용' not in col:
                d16[col.replace('현재', '예상')] = (d16[col] * mul_16).astype(int)
        d16 = d16[sorted(d16.columns.tolist())]
        dash_16 = d16

    # F. 16시 및 명일 예측
    est_18_from_16 = int(current_total * mul_16)
    remaining_gap = est_18_from_16 - current_total
    remaining_gap = max(150, min(remaining_gap, 350))
    
    last_spurt_ba = int(remaining_gap * 0.9) 
    last_spurt_prod = remaining_gap - last_spurt_ba

    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total else 0
    est_cost_24 = int(cost_total * 1.8)

    base_multiplier = 3.15
    tom_base_total = int(tom_member * base_multiplier)
    ad_boost = 300 if tom_dawn_ad else 0
    tom_total_target = tom_base_total + ad_boost
    tom_da_req = tom_total_target - tom_sa_9
    tom_per_msg = 5.0 if tom_dawn_ad else 4.4

    # 멘트
    if est_18_from_14 >= da_target_18:
        msg_14 = "금일 고정구좌 이슈없이 집행중이며, 전체 수량 또한 양사 합산 시 소폭 초과 달성할 것으로 보입니다."
    else:
        msg_14 = f"오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 상품자원/보장분석 Push 운영하겠습니다."

    if current_total + remaining_gap >= da_target_18:
        msg_16 = "* 보장분석 자원 넉넉할 것으로 보여 DA배너 일부 축소하여 비용 절감하겠습니다."
    else:
        msg_16 = "* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."

    # [NEW] 대시보드 뷰 결정 (선택된 시점의 데이터 반환)
    dash_view = dash_16 if "16시" in report_view_option else dash_14
    view_label = "16시 마감 기준 (x1.1)" if "16시" in report_view_option else "14시 중간 기준 (x1.35)"

    return {
        'da_target_18': da_target_18, 'da_per_18': da_per_18,
        'da_target_bojang': da_target_bojang, 'da_target_prod': da_target_prod,
        'da_target_17': da_target_17, 'da_per_17': da_per_17,
        'est_18_14': est_18_from_14, 
        'est_per_18_14': round(est_18_from_14/active_member, 1),
        'est_ba_18_14': round(est_18_from_14 * ratio_ba), 
        'est_prod_18_14': round(est_18_from_14 * (1-ratio_ba)),
        'msg_14': msg_14, 'cpa_da': cpa_da, 'cpa_aff': cpa_aff, 'cpa_total': cpa_total,
        'est_18_16': current_total + remaining_gap,
        'remaining_total': remaining_gap, 'remaining_ba': last_spurt_ba, 'remaining_prod': last_spurt_prod, 'msg_16': msg_16,
        'fixed_msg': f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,",
        'tom_total': tom_total_target, 'tom_da': tom_da_req, 'tom_per_msg': tom_per_msg,
        'tom_ba': round(tom_da_req * ratio_ba), 'tom_prod': round(tom_da_req * (1-ratio_ba)),
        'dash_view': dash_view,
        'view_label': view_label
    }

res = generate_report()

# -----------------------------------------------------------
# 5. 메인 탭 출력
# -----------------------------------------------------------
tab0, tab1, tab2, tab3, tab4 = st.tabs(["📊 통합 대시보드", "🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근"])

with tab0:
    st.subheader(f"📊 DA 운영 현황 대시보드 ({res['view_label']})")
    
    # 1. 달성률 게이지
    progress = min(1.0, current_total / res['da_target_18'])
    st.metric(label="현재 달성률 (목표 대비)", value=f"{int(progress*100)}%", delta=f"{current_total - res['da_target_18']}건")
    st.progress(progress)
    
    col_d1, col_d2, col_d3 = st.columns(3)
    col_d1.metric("DA 전체 목표", f"{res['da_target_18']:,}건")
    col_d2.metric("보장분석 목표", f"{res['da_target_bojang']:,}건")
    col_d3.metric("상품자원 목표", f"{res['da_target_prod']:,}건")
    
    st.markdown("---")
    
    # 2. 매체별 현황 (선택된 시점 기준)
    if not res['dash_view'].empty:
        st.markdown(f"##### 💳 매체별 상세 현황 ({res['view_label']} 예측)")
        # 예상 컬럼 하이라이트
        hl_cols = [c for c in res['dash_view'].columns if '예상' in c]
        st.dataframe(res['dash_view'].style.format("{:,}").background_gradient(cmap='Blues', subset=hl_cols), use_container_width=True)
    elif uploaded_realtime:
        st.error("데이터 로드 실패")
    else:
        st.info("실시간 파일을 업로드하면 매체별 현황이 표시됩니다.")

    st.markdown("---")
    
    # 3. 누적 자원 흐름
    st.markdown("##### 📈 누적 자원 예상 흐름 (보장 vs 상품)")
    hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
    ba_start = int(start_resource_10 * 0.12)
    prod_start = start_resource_10 - ba_start
    ba_end = res['est_ba_18_14']
    prod_end = res['est_prod_18_14']
    
    ba_flow = [int(ba_start + (ba_end - ba_start) * (i/8)) for i in range(9)]
    prod_flow = [int(prod_start + (prod_end - prod_start) * (i/8)) for i in range(9)]
    
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(hours, ba_flow, marker='o', label='보장분석', color='#d62728', linewidth=2)
    ax.plot(hours, prod_flow, marker='s', label='상품자원', color='#1f77b4', linewidth=2)
    for i in [0, 4, 8]:
        ax.annotate(f"{ba_flow[i]}", (hours[i], ba_flow[i]), xytext=(0,5), textcoords='offset points', color='red', ha='center', fontsize=9)
        ax.annotate(f"{prod_flow[i]}", (hours[i], prod_flow[i]), xytext=(0,-15), textcoords='offset points', color='blue', ha='center', fontsize=9)
    ax.legend()
    ax.grid(True, alpha=0.3)
    st.pyplot(fig)

with tab1:
    st.subheader("📋 오전 10:30 목표 수립")
    issue_text = "\n* 금일 이슈 상황을 고려하여 목표를 보수적으로 설정하였습니다." if "이슈" in target_mode else ""
    report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {res['da_target_17']:,}건 ({active_member}명, {res['da_per_17']:.1f}건 배정 기준)
ㄴ 보장분석 : {int(res['da_target_17']*0.12):,}건
ㄴ 상품 : {int(res['da_target_17']*0.88):,}건

[18시 기준]
총 자원 : {res['da_target_18']:,}건 ({active_member}명, {res['da_per_18']:.1f}건 배정 기준)
ㄴ 보장분석 : {res['da_target_bojang']:,}건
ㄴ 상품 : {res['da_target_prod']:,}건

* {res['fixed_msg']}{issue_text}"""
    st.text_area("복사 텍스트:", report_morning, height=300)
    
    hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
    weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09] 
    if fixed_ad_type == "14시 Only": weights = [0, 0.11, 0.11, 0.11, 0.11, 0.28, 0.10, 0.10, 0.08]
    elif fixed_ad_type == "12시 Only": weights = [0, 0.10, 0.10, 0.28, 0.12, 0.12, 0.10, 0.10, 0.08]
    elif fixed_ad_type == "12시+14시 Both": weights = [0, 0.10, 0.10, 0.20, 0.10, 0.25, 0.10, 0.08, 0.07]

    gap = res['da_target_18'] - start_resource_10
    total_w = sum(weights)
    acc_res = [start_resource_10]
    hourly_get = [0]
    for w in weights[1:]:
        get = round(gap * (w / total_w))
        hourly_get.append(get)
        acc_res.append(acc_res[-1] + get)
    acc_res[-1] = res['da_target_18']
    
    per_person = [f"{x/active_member:.1f}" for x in acc_res]
    acc_res_str = [f"{x:,}" for x in acc_res]
    hourly_get_str = [f"{x:,}" for x in hourly_get]
    
    df_plan = pd.DataFrame([acc_res_str, per_person, hourly_get_str], columns=hours, index=['누적자원', '인당배분', '시간당확보'])
    st.table(df_plan)

with tab2:
    st.subheader("🔥 14:00 중간 보고")
    report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {res['da_per_18']:.1f}건 / 총 {res['da_target_18']:,}건
현황(14시) : 인당배분 {current_total/active_member:.1f}건 / 총 {current_total:,}건
예상 마감(18시 기준) : 인당배분 {res['est_per_18_14']:.1f}건 / 총 {res['est_18_14']:,}건
ㄴ 보장분석 : {res['est_ba_18_14']:,}건, 상품 {res['est_prod_18_14']:,}건

* {res['fixed_msg']} {res['msg_14']}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {int(cost_total)//10000:,}만원 / 가망CPA {res['cpa_total']}만원
- DA: {int(cost_da)//10000:,}만원 / 가망CPA {res['cpa_da']}만원
- 제휴: {int(cost_aff)//10000:,}만원 / 가망CPA {res['cpa_aff']}만원

[예상 마감 - 18시 기준]
- 총합(DA/제휴): {int(cost_total * 1.35)//10000:,}만원 / 가망CPA {max(3.1, res['cpa_total']-0.2)}만원
- DA: {int(cost_da * 1.4)//10000:,}만원 / 가망CPA {max(4.4, res['cpa_da'])}만원
- 제휴: {int(cost_aff * 1.25)//10000:,}만원 / 가망CPA {max(2.4, res['cpa_aff']-0.2)}만원

[예상 마감 - 24시 기준]
- 총합(DA/제휴): {est_cost_24//10000:,}만원 / 가망CPA {max(2.9, res['cpa_total']-0.4)}만원"""
    st.text_area("복사 텍스트 (14시):", report_1400, height=450)

with tab3:
    st.subheader("⚠️ 16:00 마감 임박 보고")
    report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {res['da_target_18']:,}건
ㄴ 보장분석 : {res['da_target_bojang']:,}건, 상품 {res['da_target_prod']:,}건

16시 현황 : 총 {current_total:,}건
ㄴ 보장분석 : {current_bojang:,}건, 상품 {current_prod:,}건

16시 ~ 18시 30분 예상 건수
ㄴ 보장분석 {res['remaining_ba']:,}건
ㄴ 상품 {res['remaining_prod']:,}건

{res['msg_16']}"""
    st.text_area("복사 텍스트 (16시):", report_1600, height=300)

with tab4:
    st.subheader("🌙 명일 자원 수립")
    ad_msg = "\n* 명일 새벽 고정광고(CPT/풀뷰) 집행 예정으로 자원 추가 확보 예상됩니다." if tom_dawn_ad else ""
    report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {res['tom_total']:,}건
ㄴ 보장분석 : {res['tom_ba']:,}건
ㄴ 상품자원 : {res['tom_prod']:,}건

* 영업가족 {tom_member}명 기준 인당 {res['tom_per_msg']}건 이상 확보할 수 있도록 운영 예정입니다.{ad_msg}"""
    st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)
