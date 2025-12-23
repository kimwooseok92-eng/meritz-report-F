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
st.set_page_config(page_title="메리츠 보고 자동화 V15.5", layout="wide")

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
# 1. 유틸리티 함수 (Encoding Master Parser)
# -----------------------------------------------------------
def parse_uploaded_files(files):
    combined_df = pd.DataFrame()
    
    # 이 단어들이 포함된 줄을 '진짜 헤더'로 간주
    target_cols = ['비용', '소진', 'Cost', '금액', '캠페인', 'Campaign', '광고명', '매체']

    for file in files:
        df = None
        # 파일명 소문자 처리
        fname = file.name.lower()
        
        try:
            # -------------------------------------------------------
            # 전략 1: CSV / TXT 파일로 접근 (우선순위)
            # -------------------------------------------------------
            if fname.endswith(('.csv', '.txt')):
                encodings = ['utf-8-sig', 'cp949', 'euc-kr', 'utf-8']
                separators = [',', '\t']
                
                for enc in encodings:
                    if df is not None: break
                    for sep in separators:
                        try:
                            file.seek(0)
                            temp_df = pd.read_csv(file, encoding=enc, sep=sep, on_bad_lines='skip')
                            if check_validity(temp_df, target_cols):
                                df = refine_df(temp_df, target_cols)
                                break
                            else:
                                # 헤더가 아래에 있는 경우 탐색
                                found_df = find_header_in_csv(file, enc, sep, target_cols)
                                if found_df is not None:
                                    df = refine_df(found_df, target_cols)
                                    break
                        except: continue

            # -------------------------------------------------------
            # 전략 2: 엑셀(.xlsx) 파일로 접근
            # -------------------------------------------------------
            elif fname.endswith(('.xlsx', '.xls')):
                # [A] 정석 엑셀 읽기
                try:
                    file.seek(0)
                    temp_df = pd.read_excel(file, engine='openpyxl') # 엔진 명시
                    if check_validity(temp_df, target_cols):
                        df = refine_df(temp_df, target_cols)
                    else:
                        # 헤더 찾기
                        df = find_header_in_excel(temp_df, target_cols)
                except Exception:
                    df = None # 실패 시 다음 단계로

                # [B] 엑셀 읽기 실패 시 -> '가짜 엑셀(CSV)'로 의심하고 CP949로 읽기 (이게 핵심!)
                if df is None:
                    try:
                        file.seek(0)
                        # 한글 윈도우 인코딩(cp949)으로 읽기 시도
                        temp_df = pd.read_csv(file, encoding='cp949', on_bad_lines='skip')
                        if check_validity(temp_df, target_cols):
                            df = refine_df(temp_df, target_cols)
                        else:
                            # 탭 구분자 + cp949 시도
                            file.seek(0)
                            temp_df = pd.read_csv(file, encoding='cp949', sep='\t', on_bad_lines='skip')
                            if check_validity(temp_df, target_cols):
                                df = refine_df(temp_df, target_cols)
                    except Exception:
                        pass # 여기까지 안 되면 진짜 깨진 파일

            # -------------------------------------------------------
            # 3. 데이터 병합
            # -------------------------------------------------------
            if df is not None:
                combined_df = pd.concat([combined_df, df], ignore_index=True)

        except Exception as e:
            # st.error(f"파일 처리 오류 ({file.name}): {e}") # 디버깅용
            pass

    return combined_df

# [보조 함수] 데이터프레임 유효성 검사 (키워드 포함 여부)
def check_validity(df, targets):
    if len(df.columns) < 1: return False
    return any(k in str(c) for c in df.columns for k in targets)

# [보조 함수] CSV 헤더 찾기
def find_header_in_csv(file, enc, sep, targets):
    file.seek(0)
    lines = file.readlines()
    for idx, line in enumerate(lines[:20]):
        try:
            line_str = line.decode(enc)
            if any(k in line_str for k in targets):
                file.seek(0)
                return pd.read_csv(file, encoding=enc, sep=sep, header=idx, on_bad_lines='skip')
        except: continue
    return None

# [보조 함수] 엑셀 헤더 찾기 및 정제
def find_header_in_excel(df, targets):
    for i in range(20):
        if i >= len(df): break
        row_vals = df.iloc[i].astype(str).values
        if any(k in v for v in row_vals for k in targets):
            df.columns = df.iloc[i]
            return refine_df(df.iloc[i+1:].reset_index(drop=True), targets)
    return None

# [보조 함수] 최종 데이터 정제 (컬럼 매핑 및 숫자 변환)
def refine_df(df, targets):
    df.columns = [str(c).strip() for c in df.columns]
    cols = df.columns.tolist()
    
    col_cost = next((c for c in cols if any(x in str(c) for x in ['비용', '소진', 'Cost', '금액'])), None)
    col_cnt = next((c for c in cols if any(x in str(c) for x in ['전환', '수량', 'DB', '건수', 'Cnt', '배분'])), None)
    col_camp = next((c for c in cols if any(x in str(c) for x in ['캠페인', '광고명', '매체', '그룹', 'account'])), None)
    col_type = next((c for c in cols if any(x in str(c) for x in ['구분', 'type'])), None)

    if col_cost and col_cnt:
        temp = pd.DataFrame()
        def clean_num(x):
            try: return float(str(x).replace(',', '').replace('"', '').replace(' ', ''))
            except: return 0
        
        temp['cost'] = df[col_cost].apply(clean_num).fillna(0)
        temp['count'] = df[col_cnt].apply(clean_num).fillna(0)
        temp['campaign'] = df[col_camp].fillna('기타') if col_camp else '기타'
        
        if col_type: temp['type'] = df[col_type].fillna('')
        else: temp['type'] = temp['campaign'].apply(lambda x: '보장' if '보장' in str(x) else '상품')
        return temp
    return None

def analyze_data(df, aff_to_bojang=False):
    res = {
        'total_cnt': 0, 'total_cost': 0,
        'bojang_cnt': 0, 'prod_cnt': 0,
        'da_cnt': 0, 'da_cost': 0,
        'aff_cnt': 0,
        'media_stats': pd.DataFrame(),
        'ratio_ba': 0.84
    }
    
    if df.empty: return res

    if aff_to_bojang:
        mask_aff = df['campaign'].astype(str).str.contains('제휴')
        df.loc[mask_aff, 'type'] = '보장'

    mask_aff_camp = df['campaign'].astype(str).str.contains('제휴')
    res['da_cnt'] = int(df[~mask_aff_camp]['count'].sum())
    res['da_cost'] = int(df[~mask_aff_camp]['cost'].sum())
    res['aff_cnt'] = int(df[mask_aff_camp]['count'].sum())

    res['total_cnt'] = int(df['count'].sum())
    res['total_cost'] = int(df['cost'].sum())

    mask_bojang = df['type'].astype(str).str.contains('보장')
    res['bojang_cnt'] = int(df[mask_bojang]['count'].sum())
    res['prod_cnt'] = int(df[~mask_bojang]['count'].sum())
    
    if res['total_cnt'] > 0:
        res['ratio_ba'] = res['bojang_cnt'] / res['total_cnt']

    def normalize_media(name):
        name = str(name).lower()
        if '네이버' in name or 'naver' in name or 'nasp' in name: return '네이버'
        if '카카오' in name or 'kakao' in name: return '카카오'
        if '토스' in name or 'toss' in name: return '토스'
        if '구글' in name or 'google' in name: return '구글'
        return '기타'
    
    df['media_group'] = df['campaign'].apply(normalize_media)
    
    pivot_cnt = df.pivot_table(index='media_group', columns='type', values='count', aggfunc='sum', fill_value=0)
    pivot_cnt.columns = [f"현재_{c}" for c in pivot_cnt.columns]
    
    media_cost = df.pivot_table(index='media_group', values='cost', aggfunc='sum', fill_value=0)
    media_cost.columns = ['현재_비용']

    stats = pd.concat([pivot_cnt, media_cost], axis=1).fillna(0).astype(int)
    stats['현재_합계'] = stats.get('현재_보장', 0) + stats.get('현재_상품', 0)
    
    res['media_stats'] = stats
            
    return res


# -----------------------------------------------------------
# MODE 1: V6.6 Legacy
# -----------------------------------------------------------
def run_v6_6_legacy():
    st.title("📊 메리츠화재 DA 보고 자동화 (Legacy V6.6)")
    st.info("ℹ️ 기존 로직 기반의 수기 입력 모드입니다.")

    with st.sidebar:
        st.header("1. 기본 설정")
        day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
        target_mode = st.radio("목표 수립 기조", 
                               ['평시 (8.5~9.0건)', '이슈/보수적 (6.0~7.2건)', '월말/공격적 (9.5건↑)'],
                               index=1 if day_option=='월' else 0)
        op_mode = st.selectbox("운영 전략", ['일반', '상품증대', '효율화'])

        st.header("2. 오전 목표")
        active_member = st.number_input("금일 활동 인원", value=359)
        da_target_18 = st.number_input("DA 전체 목표", value=3600)
        start_resource_10 = st.number_input("10시 시작 자원 (그래프용)", value=1100)

        st.header("3. 실시간 실적 입력")
        current_total = st.number_input("현재 총 자원", value=2000)
        current_bojang = st.number_input("ㄴ 보장분석", value=1600)
        current_prod = st.number_input("ㄴ 상품자원", value=400)
        
        cost_da = st.number_input("DA 소진액", value=23000000)
        cost_aff = st.number_input("제휴 소진액", value=11270000)
        cost_total = cost_da + cost_aff

        st.header("4. 명일 예상 설정")
        tom_member = st.number_input("명일 활동 인원", value=350)
        tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
        tom_dawn_ad = st.checkbox("내일 새벽 고정광고 있음", value=False)
        
        st.header("5. 금일 고정구좌 (중요)")
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시 Only", "14시 Only", "12시+14시 Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 KBPAY 발송 완료되었습니다")

    # --- V6.6 로직 ---
    w = {'월': 0.82, '화': 1.0, '수': 1.0, '목': 0.95, '금': 0.85}.get(day_option, 1.0)
    if fixed_ad_type != "없음" and day_option == '월': w = 0.90
    mul_14 = 1.215 if "12시" in fixed_ad_type else 1.35 * w
    mul_16 = 1.099

    if op_mode == '상품증대': ratio_ba = 0.84
    elif op_mode == '효율화': ratio_ba = 0.88 
    else: ratio_ba = 0.898
    ratio_prod = 1 - ratio_ba

    da_target_bojang = int(da_target_18 * ratio_ba)
    da_target_prod = da_target_18 - da_target_bojang
    da_per_18 = round(da_target_18 / active_member, 1)
    
    da_target_17 = da_target_18 - round(da_target_18 * (0.040 if fixed_ad_type == "없음" else 0.032))
    da_per_17 = round(da_target_17 / active_member, 1)
    
    est_18_from_14 = int(current_total * mul_14)
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150

    est_ba_18_14 = int(est_18_from_14 * ratio_ba)
    est_prod_18_14 = est_18_from_14 - est_ba_18_14

    cpa_da = round(cost_da / current_bojang / 10000, 1) if current_bojang else 0
    cpa_aff = round(cost_aff / current_prod / 10000, 1) if current_prod else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total else 0
    est_cost_24 = int(cost_total * 1.8)

    est_18_from_16 = int(current_total * mul_16)
    remaining_gap = max(150, min(est_18_from_16 - current_total, 350))
    last_spurt_ba = int(remaining_gap * 0.9) 
    last_spurt_prod = remaining_gap - last_spurt_ba

    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"
    msg_14 = "금일 고정구좌 이슈없이 집행중이며, 전체 수량 또한 양사 합산 시 소폭 초과 달성할 것으로 보입니다." if est_18_from_14 >= da_target_18 else "오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 상품자원/보장분석 Push 운영하겠습니다."
    msg_16 = "* 보장분석 자원 넉넉할 것으로 보여 DA배너 일부 축소하여 비용 절감하겠습니다." if current_total + remaining_gap >= da_target_18 else "* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."
    
    base_multiplier = 3.15
    tom_base_total = int(tom_member * base_multiplier)
    ad_boost = 300 if tom_dawn_ad else 0
    tom_total_target = tom_base_total + ad_boost 
    tom_da_req = tom_total_target - tom_sa_9
    tom_per_msg = 5.0 if tom_dawn_ad else 4.4
    ad_msg = "\n* 명일 새벽 고정광고(CPT/풀뷰) 집행 예정으로 자원 추가 확보 예상됩니다." if tom_dawn_ad else ""

    # --- 탭 출력 ---
    tab1, tab2, tab3, tab4 = st.tabs(["🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근"])

    with tab1:
        st.subheader("📋 오전 10:30 목표 수립")
        report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {da_target_17:,}건 ({active_member}명, {da_per_17:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_17*ratio_ba):,}건
ㄴ 상품 : {int(da_target_17*ratio_prod):,}건

[18시 기준]
총 자원 : {da_target_18:,}건 ({active_member}명, {da_per_18:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_18*ratio_ba):,}건
ㄴ 상품 : {int(da_target_18*ratio_prod):,}건

* {fixed_msg}"""
        st.text_area("복사 텍스트:", report_morning, height=300)

        hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
        weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
        if fixed_ad_type == "14시 Only": weights = [0, 0.11, 0.11, 0.11, 0.11, 0.28, 0.10, 0.10, 0.08]
        gap = da_target_18 - start_resource_10
        total_w = sum(weights)
        acc_res = [start_resource_10]
        hourly_get = [0]
        for w in weights[1:]:
            get = round(gap * (w / total_w))
            hourly_get.append(get)
            acc_res.append(acc_res[-1] + get)
        acc_res[-1] = da_target_18
        
        per_person = [f"{x/active_member:.1f}" for x in acc_res]
        acc_res_str = [f"{x:,}" for x in acc_res]
        hourly_get_str = [f"{x:,}" for x in hourly_get]
        df_plan = pd.DataFrame([acc_res_str, per_person, hourly_get_str], columns=hours, index=['누적자원', '인당배분', '시간당확보'])
        st.table(df_plan)
        
        st.line_chart(pd.DataFrame({'누적 예상': acc_res}, index=hours))

    with tab2:
        st.subheader("🔥 14:00 중간 보고")
        report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {da_per_18:.1f}건 / 총 {da_target_18:,}건
현황(14시) : 인당배분 {current_total/active_member:.1f}건 / 총 {current_total:,}건
예상 마감(18시 기준) : 인당배분 {round(est_18_from_14/active_member, 1):.1f}건 / 총 {est_18_from_14:,}건
ㄴ 보장분석 : {est_ba_18_14:,}건, 상품 {est_prod_18_14:,}건

* {fixed_msg} {msg_14}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {int(cost_total)//10000:,}만원 / 가망CPA {cpa_total:.1f}만원
- DA: {int(cost_da)//10000:,}만원 / 가망CPA {cpa_da:.1f}만원
- 제휴: {int(cost_aff)//10000:,}만원 / 가망CPA {cpa_aff:.1f}만원

[예상 마감 - 18시 기준]
- 총합(DA/제휴): {int(cost_total * 1.35)//10000:,}만원 / 가망CPA {max(3.1, cpa_total-0.2):.1f}만원
- DA: {int(cost_da * 1.4)//10000:,}만원 / 가망CPA {max(4.4, cpa_da):.1f}만원
- 제휴: {int(cost_aff * 1.25)//10000:,}만원 / 가망CPA {max(2.4, cpa_aff-0.2):.1f}만원"""
        st.text_area("복사 텍스트 (14시):", report_1400, height=450)

    with tab3:
        st.subheader("⚠️ 16:00 마감 임박 보고")
        report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {da_target_18:,}건
ㄴ 보장분석 : {da_target_bojang:,}건, 상품 {da_target_prod:,}건

16시 현황 : 총 {current_total:,}건
ㄴ 보장분석 : {current_bojang:,}건, 상품 {current_prod:,}건

16시 ~ 18시 30분 예상 건수
ㄴ 보장분석 {last_spurt_ba:,}건
ㄴ 상품 {last_spurt_prod:,}건

{msg_16}"""
        st.text_area("복사 텍스트 (16시):", report_1600, height=300)

    with tab4:
        st.subheader("🌙 명일 자원 수립")
        report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {tom_total_target:,}건
ㄴ 보장분석 : {round(tom_da_req * ratio_ba):,}건
ㄴ 상품자원 : {round(tom_da_req * ratio_prod):,}건

* 영업가족 {tom_member}명 기준 인당 {tom_per_msg}건 이상 확보할 수 있도록 운영 예정입니다.{ad_msg}"""
        st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)


# -----------------------------------------------------------
# MODE 2: V15.5 (Advanced - Encoding Master)
# -----------------------------------------------------------
def run_v15_0_advanced():
    st.title("📊 메리츠화재 DA 통합 시스템 (V15.5 Master)")
    st.markdown("🚀 **엑셀 오류 자동 회피 & CSV 집중 분석**")

    with st.sidebar:
        st.header("1. 기본 설정")
        current_time_str = st.select_slider(
            "⏱️ 현재 데이터 기준 시각",
            options=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
            value="14:00"
        )
        
        is_boosting = False
        if current_time_str in ["16:00", "17:00"]:
            is_boosting = st.checkbox("🔥 긴급 부스팅 적용 (막판 스퍼트)", value=False)
        
        day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
        target_mode = st.radio("목표 기조", ['평시', '이슈/보수적', '월말/공격적'], index=1 if day_option=='월' else 0)
        op_mode_select = st.selectbox("운영 전략 (수기용)", ['일반', '상품증대', '효율화'])
        
        st.header("2. 목표 수립 (SA 분리)")
        active_member = st.number_input("금일 활동 인원", value=359)
        c1, c2 = st.columns(2)
        with c1: target_bojang = st.number_input("전체 보장 목표", value=500)
        with c2: target_product = st.number_input("전체 상품 목표", value=3100)
        c3, c4 = st.columns(2)
        with c3: sa_est_bojang = st.number_input("SA 보장 예상", value=200)
        with c4: sa_est_prod = st.number_input("SA 상품 예상", value=800)
        da_add_target = st.number_input("DA 추가 버퍼", value=50)

        st.header("3. [자동] 10시 시작 자원")
        with st.expander("📂 파일 3개 업로드"):
            file_yest_24 = st.file_uploader("① 어제 24시", key="f1")
            file_yest_18 = st.file_uploader("② 어제 18시", key="f2")
            file_today_10 = st.file_uploader("③ 오늘 10시", key="f3")

        start_resource_10 = 1100
        if file_yest_24 and file_today_10:
            df_y24 = parse_uploaded_files([file_yest_24])
            df_t10 = parse_uploaded_files([file_today_10])
            cnt_y24 = int(df_y24.iloc[:, 1].sum()) if not df_y24.empty else 0
            cnt_t10 = int(df_t10.iloc[:, 1].sum()) if not df_t10.empty else 0
            if file_yest_18:
                df_y18 = parse_uploaded_files([file_yest_18])
                cnt_y18 = int(df_y18.iloc[:, 1].sum()) if not df_y18.empty else 0
                st.success(f"18시 데이터 자동: {cnt_y18}건")
            else:
                cnt_y18 = st.number_input("어제 18시 보고 (수기)", value=3000)
            calc_start = (cnt_y24 - cnt_y18) + cnt_t10
            if calc_start > 0: start_resource_10 = calc_start
        start_resource_10 = st.number_input("[자동] 10시 시작 자원", value=start_resource_10)

        st.header("4. [자동+수기] 실시간 분석")
        uploaded_realtime = st.file_uploader("📊 실시간 로우데이터 (탭 구분 파일 자동 인식)", accept_multiple_files=True)
        is_aff_bojang = st.checkbox("☑️ 금일 제휴는 '보장' 위주", value=False)
        
        real_data = analyze_data(parse_uploaded_files(uploaded_realtime) if uploaded_realtime else pd.DataFrame(), aff_to_bojang=is_aff_bojang)
        
        if uploaded_realtime:
            st.info(f"💡 파일 기반 비율 적용 중 (보장 {int(real_data['ratio_ba']*100)}%)")
            ratio_ba = real_data['ratio_ba']
            current_da_cnt = real_data['da_cnt']
            cost_da = real_data['da_cost']
            current_aff_cnt = real_data['aff_cnt']
            cost_aff = int(real_data['total_cost'] - cost_da) 
            cpa_aff_input = 0
        else:
            st.caption("📂 파일 없음: 수기 입력 모드")
            if op_mode_select == '상품증대': ratio_ba = 0.84
            elif op_mode_select == '효율화': ratio_ba = 0.88
            else: ratio_ba = 0.898
            
            st.markdown("##### 🅰️ DA (배너광고)")
            current_da_cnt = st.number_input("DA 실적 (건수)", value=1500)
            cost_da = st.number_input("DA 소진액 (원)", value=23000000)
            
            st.markdown("##### 🅱️ 제휴 (카카오/토스)")
            cost_aff = st.number_input("제휴 소진액 (원)", value=11270000)
            cpa_aff_input = st.number_input("제휴 단가 (CPA)", value=14000, step=100)
            current_aff_cnt = int(cost_aff / cpa_aff_input) if cpa_aff_input > 0 else 0
            st.info(f"🧮 제휴 실적 자동 계산: **{current_aff_cnt:,}건**")

        ratio_prod = 1 - ratio_ba
        
        current_total = current_da_cnt + current_aff_cnt
        cost_total = cost_da + cost_aff
        
        if is_aff_bojang:
            current_bojang = int(current_total * ratio_ba)
        else:
            current_bojang = int(current_total * ratio_ba)
            
        current_prod = current_total - current_bojang

        st.header("5. 기타 설정")
        tom_member = st.number_input("명일 활동 인원", value=350)
        tom_sa_9 = st.number_input("명일 SA 9시 예상", value=410)
        tom_dawn_ad = st.checkbox("내일 새벽 고정광고", value=False)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 로직 ---
    base_mul_14 = 1.35
    if day_option == '월': 
        base_mul_14 = 1.15
    elif fixed_ad_type != "없음": 
        base_mul_14 = 1.215 
        
    mul_14 = base_mul_14
    mul_16 = 1.25 if is_boosting else 1.10

    da_target_bojang = target_bojang - sa_est_bojang
    da_target_prod = target_product - sa_est_prod + da_add_target
    da_target_18 = da_target_bojang + da_target_prod
    da_per_18 = round(da_target_18 / active_member, 1)
    
    da_target_17 = da_target_18 - round(da_target_18 * (0.040 if fixed_ad_type == "없음" else 0.032))
    da_per_17 = round(da_target_17 / active_member, 1)

    est_18_from_14 = int(current_total * mul_14)
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150

    est_ba_18_14 = round(est_18_from_14 * ratio_ba) 
    est_prod_18_14 = round(est_18_from_14 * (1-ratio_ba))

    cpa_da = round(cost_da / current_da_cnt / 10000, 1) if current_da_cnt > 0 else 0
    cpa_aff = round(cost_aff / current_aff_cnt / 10000, 1) if current_aff_cnt > 0 else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total > 0 else 0
    est_cost_24 = int(cost_total * 1.8)

    est_18_from_16 = int(current_total * mul_16)
    remaining_gap = max(150, min(est_18_from_16 - current_total, 350))
    last_spurt_ba = int(remaining_gap * 0.9) 
    last_spurt_prod = remaining_gap - last_spurt_ba

    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"
    msg_14 = "금일 고정구좌 이슈없이 집행중이며..." if est_18_from_14 >= da_target_18 else "오전 목표 대비 소폭 부족할 것으로..."
    
    if current_total + remaining_gap >= da_target_18:
        msg_16 = "* 보장분석 자원 넉넉할 것으로 보여 DA배너 일부 축소하여 비용 절감하겠습니다."
    else:
        msg_16 = "* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."
    
    time_multipliers = {
        "09:30": 1.0, 
        "10:00": 1.75, "11:00": 1.65, "12:00": 1.55, "13:00": 1.45,
        "14:00": mul_14,
        "15:00": (mul_14 + mul_16) / 2, 
        "16:00": mul_16, 
        "17:00": 1.05 if not is_boosting else 1.15, 
        "18:00": 1.0
    }
    
    current_mul = time_multipliers.get(current_time_str, 1.35)
    
    dash_live = pd.DataFrame()
    if uploaded_realtime and not real_data['media_stats'].empty:
        d_raw = real_data['media_stats'].copy()
        for col in d_raw.columns:
            if '현재' in col and '비용' not in col:
                d_raw[col.replace('현재', '예상')] = (d_raw[col] * current_mul).astype(int)
        dash_live = d_raw[sorted(d_raw.columns.tolist())]
    
    view_label = f"기준 시각: {current_time_str} (x{current_mul:.2f})"
    if is_boosting: view_label += " 🔥부스팅 ON"
    
    base_multiplier = 3.15
    tom_base_total = int(tom_member * base_multiplier)
    ad_boost = 300 if tom_dawn_ad else 0
    tom_total_target = tom_base_total + ad_boost
    tom_da_req = tom_total_target - tom_sa_9
    tom_per_msg = 5.0 if tom_dawn_ad else 4.4
    ad_msg = "\n* 명일 새벽 고정광고(CPT/풀뷰) 집행 예정으로 자원 추가 확보 예상됩니다." if tom_dawn_ad else ""

    # --- 탭 출력 ---
    tab0, tab1, tab2, tab3, tab4 = st.tabs(["📊 인사이트 대시보드", "🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근"])

    with tab0:
        st.subheader(f"📊 실시간 DA 운영 현황")
        st.caption(f"ℹ️ {view_label}이 적용된 예상치입니다.")
        
        if current_time_str == "09:30":
             st.info("📌 오전 09:30: 실시간 예측 대신 '목표 배분 계획'을 확인하세요.")
             hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
             weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
             if fixed_ad_type == "14시 Only": weights = [0, 0.11, 0.11, 0.11, 0.11, 0.28, 0.10, 0.10, 0.08]
             gap = da_target_18 - start_resource_10
             total_w = sum(weights)
             acc_res = [start_resource_10]
             for w in weights[1:]:
                 acc_res.append(acc_res[-1] + round(gap * (w / total_w)))
             acc_res[-1] = da_target_18
             
             acc_ba = [int(x * ratio_ba) for x in acc_res]
             acc_prod = [x - b for x, b in zip(acc_res, acc_ba)]
             
             df_detail = pd.DataFrame({
                 '누적 목표': [f"{x:,}" for x in acc_res],
                 '보장 목표': [f"{x:,}" for x in acc_ba],
                 '상품 목표': [f"{x:,}" for x in acc_prod]
             }, index=hours)
             
             st.table(df_detail)
             st.line_chart(pd.DataFrame({'목표 흐름': acc_res}, index=hours))
        
        else:
            progress = min(1.0, current_total / da_target_18)
            est_final_live = int(current_total * current_mul)
            
            c1, c2, c3 = st.columns(3)
            c1.metric("최종 목표", f"{da_target_18:,}건")
            c2.metric(f"현재 실적 ({current_time_str})", f"{current_total:,}건", f"{int(progress*100)}% 달성")
            c3.metric(f"마감 예상 ({current_time_str} 기준)", f"{est_final_live:,}건", f"Gap: {est_final_live - da_target_18}건")
            
            st.progress(progress)
            
            if not dash_live.empty:
                st.dataframe(dash_live.style.format("{:,}").background_gradient(cmap='Blues'), use_container_width=True)
            
            hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
            ba_start = int(start_resource_10 * ratio_ba)
            prod_start = start_resource_10 - ba_start
            
            est_ba_live = int(est_final_live * ratio_ba)
            est_prod_live = est_final_live - est_ba_live
            
            ba_flow = [int(ba_start + (est_ba_live - ba_start) * (i/8)) for i in range(9)]
            prod_flow = [int(prod_start + (est_prod_live - prod_start) * (i/8)) for i in range(9)]
            total_flow = [b+p for b,p in zip(ba_flow, prod_flow)]
            
            st.markdown("##### 📉 시간대별 예상 진도 (상세)")
            df_detail_live = pd.DataFrame({
                 '예상 총합': [f"{x:,}" for x in total_flow],
                 '예상 보장': [f"{x:,}" for x in ba_flow],
                 '예상 상품': [f"{x:,}" for x in prod_flow]
             }, index=hours)
            st.table(df_detail_live)
            
            st.line_chart(pd.DataFrame({'보장분석': ba_flow, '상품자원': prod_flow}, index=hours))

    with tab1:
        st.subheader("📋 오전 목표")
        report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {da_target_17:,}건 ({active_member}명, {da_per_17:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_17*0.12):,}건
ㄴ 상품 : {int(da_target_17*0.88):,}건

[18시 기준]
총 자원 : {da_target_18:,}건 ({active_member}명, {da_per_18:.1f}건 배정 기준)
ㄴ 보장분석 : {da_target_bojang:,}건
ㄴ 상품 : {da_target_prod:,}건

* {fixed_msg}"""
        st.text_area("복사 텍스트:", report_morning, height=300)

        hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
        weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
        if fixed_ad_type == "14시 Only": weights = [0, 0.11, 0.11, 0.11, 0.11, 0.28, 0.10, 0.10, 0.08]
        gap = da_target_18 - start_resource_10
        total_w = sum(weights)
        acc_res = [start_resource_10]
        hourly_get = [0]
        for w in weights[1:]:
            get = round(gap * (w / total_w))
            hourly_get.append(get)
            acc_res.append(acc_res[-1] + get)
        acc_res[-1] = da_target_18
        
        per_person = [f"{x/active_member:.1f}" for x in acc_res]
        acc_res_str = [f"{x:,}" for x in acc_res]
        hourly_get_str = [f"{x:,}" for x in hourly_get]
        df_plan = pd.DataFrame([acc_res_str, per_person, hourly_get_str], columns=hours, index=['누적자원', '인당배분', '시간당확보'])
        st.table(df_plan)

    with tab2:
        st.subheader("🔥 14:00 중간 보고")
        report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {da_per_18:.1f}건 / 총 {da_target_18:,}건
현황(14시) : 인당배분 {current_total/active_member:.1f}건 / 총 {current_total:,}건
예상 마감(18시 기준) : 인당배분 {round(est_18_from_14/active_member, 1):.1f}건 / 총 {est_18_from_14:,}건
ㄴ 보장분석 : {est_ba_18_14:,}건, 상품 {est_prod_18_14:,}건

* {fixed_msg} {msg_14}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {int(cost_total)//10000:,}만원 / 가망CPA {cpa_total:.1f}만원
- DA: {int(cost_da)//10000:,}만원 / 가망CPA {cpa_da:.1f}만원
- 제휴: {int(cost_aff)//10000:,}만원 / 가망CPA {cpa_aff:.1f}만원

[예상 마감 - 18시 기준]
- 총합(DA/제휴): {int(cost_total * 1.35)//10000:,}만원 / 가망CPA {max(3.1, cpa_total-0.2):.1f}만원
- DA: {int(cost_da * 1.4)//10000:,}만원 / 가망CPA {max(4.4, cpa_da):.1f}만원
- 제휴: {int(cost_aff * 1.25)//10000:,}만원 / 가망CPA {max(2.4, cpa_aff-0.2):.1f}만원"""
        st.text_area("복사 텍스트 (14시):", report_1400, height=450)

    with tab3:
        st.subheader("⚠️ 16:00 마감 임박 보고")
        report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {da_target_18:,}건
ㄴ 보장분석 : {da_target_bojang:,}건, 상품 {da_target_prod:,}건

16시 현황 : 총 {current_total:,}건
ㄴ 보장분석 : {current_bojang:,}건, 상품 {current_prod:,}건

16시 ~ 18시 30분 예상 건수
ㄴ 보장분석 {last_spurt_ba:,}건
ㄴ 상품 {last_spurt_prod:,}건

{msg_16}"""
        st.text_area("복사 텍스트 (16시):", report_1600, height=300)

    with tab4:
        st.subheader("🌙 명일 자원 수립")
        report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {tom_total_target:,}건
ㄴ 보장분석 : {round(tom_da_req * ratio_ba):,}건
ㄴ 상품자원 : {round(tom_da_req * ratio_prod):,}건

* 영업가족 {tom_member}명 기준 인당 {tom_per_msg}건 이상 확보할 수 있도록 운영 예정입니다.{ad_msg}"""
        st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)


# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
def main():
    st.sidebar.title("⚙️ 시스템 버전 선택")
    version = st.sidebar.selectbox(
        "사용할 버전을 선택하세요:",
        ["V15.5 (Master)", "V6.6 (Legacy)"]
    )
    
    if version == "V15.5 (Master)":
        run_v15_0_advanced()
    else:
        run_v6_6_legacy()

if __name__ == "__main__":
    main()
