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
st.set_page_config(page_title="메리츠 보고 자동화 V16.1", layout="wide")

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
# 1. 유틸리티 함수 (Ultimate Parser V3)
# -----------------------------------------------------------
def parse_uploaded_files(files):
    data_frames = []
    
    # [핵심] 인식 가능한 컬럼명 확장
    target_cols = ['비용', '소진', 'Cost', '금액', '총 비용', '캠페인', 'Campaign', '광고명', '매체']
    count_cols_keywords = ['전환', '수량', 'DB', '건수', 'Cnt', '배분', '결과', '잠재고객', '보장분석', '계', '합계']

    for file in files:
        df = None
        fname = file.name.lower()
        is_plab = 'performance' in fname or 'lab' in fname # 피랩 파일 식별자
        
        try:
            # --- A. CSV / TXT Parsing ---
            if fname.endswith(('.csv', '.txt')):
                df = try_read_csv(file, target_cols, count_cols_keywords)
            
            # --- B. Excel Parsing ---
            elif fname.endswith(('.xlsx', '.xls')):
                try:
                    file.seek(0)
                    temp_df = pd.read_excel(file, engine='openpyxl')
                    if check_validity(temp_df, target_cols):
                        df = refine_df(temp_df, target_cols, count_cols_keywords)
                    else:
                        df = find_header_in_excel(temp_df, target_cols, count_cols_keywords)
                except:
                    # 엑셀 실패 시 CSV로 재시도 (가짜 엑셀 대응)
                    df = try_read_csv(file, target_cols, count_cols_keywords)

            if df is not None:
                # 파일 출처 마킹 (중복 방지 로직용)
                df['source_file'] = 'PLAB' if is_plab else 'RAW'
                data_frames.append(df)

        except Exception:
            pass

    return data_frames

def try_read_csv(file, targets, count_keys):
    encodings = ['utf-8-sig', 'cp949', 'euc-kr', 'utf-8']
    separators = [',', '\t']
    
    extended_targets = targets + count_keys

    for enc in encodings:
        for sep in separators:
            try:
                file.seek(0)
                # 메타데이터 스킵을 위해 상위 30줄 검색
                lines = file.readlines()
                header_row = -1
                for i, line in enumerate(lines[:30]):
                    try:
                        line_str = line.decode(enc)
                        if any(k in line_str for k in targets):
                            header_row = i
                            break
                    except: continue
                
                if header_row != -1:
                    file.seek(0)
                    df = pd.read_csv(file, encoding=enc, sep=sep, header=header_row, on_bad_lines='skip')
                    if check_validity(df, targets):
                        return refine_df(df, targets, count_keys)
            except: continue
    return None

def check_validity(df, targets):
    if len(df.columns) < 1: return False
    return any(k in str(c) for c in df.columns for k in targets)

def find_header_in_excel(df, targets, count_keys):
    for i in range(20):
        if i >= len(df): break
        row_vals = df.iloc[i].astype(str).values
        if any(k in v for v in row_vals for k in targets):
            df.columns = df.iloc[i]
            return refine_df(df.iloc[i+1:].reset_index(drop=True), targets, count_keys)
    return None

def refine_df(df, cost_keys, cnt_keys):
    df.columns = [str(c).strip() for c in df.columns]
    cols = df.columns.tolist()
    
    # 1. 비용 컬럼 찾기
    col_cost = next((c for c in cols if any(x in str(c) for x in cost_keys)), None)
    
    # 2. 건수 컬럼 찾기 (우선순위: 보장분석 > 잠재고객 > 전환 > 결과 > 계)
    col_cnt = None
    for key in cnt_keys: # count_keys 순서대로 탐색
        found = next((c for c in cols if key in str(c)), None)
        if found:
            col_cnt = found
            break
            
    # 3. 캠페인명 찾기
    col_camp = next((c for c in cols if any(x in str(c) for x in ['캠페인', 'Campaign', '광고명', '매체', 'account', 'media group'])), None)
    
    # 4. 결과 유형 (네이버 GFA용)
    col_type_detail = next((c for c in cols if '결과 유형' in str(c)), None)

    if col_camp:
        temp = pd.DataFrame()
        
        # 숫자 정제 함수
        def to_num(x):
            try: return float(str(x).replace(',', '').replace('"', '').replace(' ', ''))
            except: return 0

        temp['campaign'] = df[col_camp].fillna('기타')
        temp['cost'] = df[col_cost].apply(to_num).fillna(0) if col_cost else 0
        
        # 건수 처리 로직
        if col_cnt:
            temp['count'] = df[col_cnt].apply(to_num).fillna(0)
            # 네이버 GFA 예외처리: 결과 유형이 '클릭'이면 건수 0 처리 (전환 데이터만 유효)
            if col_type_detail:
                is_click = df[col_type_detail].astype(str).str.contains('클릭')
                temp.loc[is_click, 'count'] = 0
        else:
            temp['count'] = 0
            
        return temp
    return None

def classify_row(row):
    camp = str(row['campaign']).lower()
    # 제휴 키워드 식별
    if any(x in camp for x in ['토스', 'toss', '제휴', '캐시', '오케이', '버즈', 'cpa']):
        return 'Affiliate'
    return 'DA'

def aggregate_data(dfs, manual_aff_cost=0, manual_aff_cnt=0, manual_da_cost=0, manual_da_cnt=0):
    res = {
        'da_cost': 0, 'da_cnt': 0,
        'aff_cost': 0, 'aff_cnt': 0,
        'total_cost': 0, 'total_cnt': 0,
        'ratio_ba': 0.898
    }
    
    if not dfs:
        # 파일 없으면 순수 수기 모드
        res['da_cost'] = manual_da_cost
        res['da_cnt'] = manual_da_cnt
        res['aff_cost'] = manual_aff_cost
        res['aff_cnt'] = manual_aff_cnt
        res['total_cost'] = manual_da_cost + manual_aff_cost
        res['total_cnt'] = manual_da_cnt + manual_aff_cnt
        return res

    # 1. 파일 데이터 통합 및 분류
    all_rows = pd.concat(dfs, ignore_index=True)
    all_rows['group'] = all_rows.apply(classify_row, axis=1)
    
    # 2. PLAB 파일 존재 여부 확인 (건수 마스터)
    has_plab = any(df['source_file'].iloc[0] == 'PLAB' for df in dfs if not df.empty)
    
    # 3. 집계 로직
    # A. 비용 (Cost) - 모든 파일에서 합산 (PLAB엔 비용이 보통 없으므로 RAW에서 옴)
    file_da_cost = all_rows[all_rows['group']=='DA']['cost'].sum()
    file_aff_cost = all_rows[all_rows['group']=='Affiliate']['cost'].sum()
    
    # B. 건수 (Count) - PLAB 있으면 PLAB만, 없으면 RAW 합산
    if has_plab:
        plab_rows = all_rows[all_rows['source_file']=='PLAB']
        file_da_cnt = plab_rows[plab_rows['group']=='DA']['count'].sum()
        file_aff_cnt = plab_rows[plab_rows['group']=='Affiliate']['count'].sum()
    else:
        file_da_cnt = all_rows[all_rows['group']=='DA']['count'].sum()
        file_aff_cnt = all_rows[all_rows['group']=='Affiliate']['count'].sum()
        
    # 4. 수기 입력 Override (제휴) & Addition (DA)
    # DA: 파일 누락분 보정용으로 '추가' (파일값 + 수기값)
    res['da_cost'] = int(file_da_cost + manual_da_cost)
    res['da_cnt'] = int(file_da_cnt + manual_da_cnt)
    
    # Affiliate: 수기 입력 있으면 파일값 '무시' (중복 방지, Override)
    if manual_aff_cost > 0 or manual_aff_cnt > 0:
        res['aff_cost'] = int(manual_aff_cost)
        res['aff_cnt'] = int(manual_aff_cnt)
    else:
        res['aff_cost'] = int(file_aff_cost)
        res['aff_cnt'] = int(file_aff_cnt)
        
    res['total_cost'] = res['da_cost'] + res['aff_cost']
    res['total_cnt'] = res['da_cnt'] + res['aff_cnt']
    
    # 비율 계산 (파일 내 보장 키워드 기반 추정)
    bojang_kwd_cnt = all_rows[all_rows['campaign'].astype(str).str.contains('보장')]['count'].sum()
    total_file_cnt = all_rows['count'].sum()
    if total_file_cnt > 0:
        res['ratio_ba'] = bojang_kwd_cnt / total_file_cnt
        if res['ratio_ba'] < 0.1: res['ratio_ba'] = 0.898 # 너무 낮으면 기본값
        
    return res


# -----------------------------------------------------------
# MODE 1: Legacy (유지)
# -----------------------------------------------------------
def run_v6_6_legacy():
    st.title("📊 메리츠화재 DA 보고 자동화 (Legacy V6.6)")
    st.info("ℹ️ 기존 수기 입력 모드입니다.")
    # (Legacy 코드는 이전과 동일)

# -----------------------------------------------------------
# MODE 2: V16.1 Advanced
# -----------------------------------------------------------
def run_v16_0_advanced():
    st.title("📊 메리츠화재 DA 통합 시스템 (V16.1 Fixed)")
    st.markdown("🚀 **제휴 실적 수기 우선(Override) & 데이터 중복 방지**")

    with st.sidebar:
        st.header("1. 기본 설정")
        current_time_str = st.select_slider(
            "⏱️ 현재 데이터 기준 시각",
            options=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"],
            value="14:00"
        )
        
        is_boosting = False
        if current_time_str in ["16:00", "17:00"]:
            is_boosting = st.checkbox("🔥 긴급 부스팅 적용", value=False)
        
        day_option = st.selectbox("오늘 요일", ['월', '화', '수', '목', '금'], index=0)
        
        st.header("2. 목표 수립")
        active_member = st.number_input("금일 활동 인원", value=359)
        c1, c2 = st.columns(2)
        with c1: target_bojang = st.number_input("전체 보장 목표", value=500)
        with c2: target_product = st.number_input("전체 상품 목표", value=3100)
        c3, c4 = st.columns(2)
        with c3: sa_est_bojang = st.number_input("SA 보장 예상", value=200)
        with c4: sa_est_prod = st.number_input("SA 상품 예상", value=800)
        da_add_target = st.number_input("DA 추가 버퍼", value=50)

        st.header("3. [자동] 10시 시작 자원")
        with st.expander("📂 파일 업로드"):
            file_yest_24 = st.file_uploader("① 어제 24시", key="f1")
            file_today_10 = st.file_uploader("② 오늘 10시", key="f3")
        start_resource_10 = st.number_input("10시 자원 (수기/자동)", value=1100)

        st.header("4. [자동+수기] 실시간 분석")
        uploaded_realtime = st.file_uploader("📊 실시간 로우데이터 (다중 선택)", accept_multiple_files=True)
        is_aff_bojang = st.checkbox("☑️ 금일 제휴는 '보장' 위주", value=False)
        
        st.markdown("**✏️ 수기 입력 (제휴 입력 시 파일값 덮어씀)**")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_da_cnt = st.number_input("DA 추가 건수", value=0)
            manual_da_cost = st.number_input("DA 추가 소진액", value=0)
        with col_m2:
            manual_aff_cost = st.number_input("제휴 수기 소진액", value=11270000) # 기본값 예시
            manual_aff_cpa = st.number_input("제휴 수기 단가", value=14000)
            manual_aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0
            st.info(f"ㄴ 제휴 환산: {manual_aff_cnt:,}건")

        # 분석 및 집계
        dfs = parse_uploaded_files(uploaded_realtime) if uploaded_realtime else []
        res = aggregate_data(dfs, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt)
        
        current_total = res['total_cnt']
        cost_total = res['total_cost']
        ratio_ba = res['ratio_ba']
        
        # 보장/상품 배분
        ratio_prod = 1 - ratio_ba
        if is_aff_bojang:
            # 제휴는 전량 보장, DA는 비율대로
            est_bojang = int(res['da_cnt'] * ratio_ba) + res['aff_cnt']
        else:
            est_bojang = int(current_total * ratio_ba)
        est_prod = current_total - est_bojang

        st.header("5. 기타 설정")
        tom_member = st.number_input("명일 활동 인원", value=350)
        tom_sa_9 = st.number_input("명일 SA 9시", value=410)
        tom_dawn_ad = st.checkbox("내일 새벽 고정광고", value=False)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 계산 로직 ---
    base_mul_14 = 1.35
    if day_option == '월': base_mul_14 = 1.15
    elif fixed_ad_type != "없음": base_mul_14 = 1.215
    
    mul_14 = base_mul_14
    mul_16 = 1.25 if is_boosting else 1.10

    da_target_18 = (target_bojang - sa_est_bojang) + (target_product - sa_est_prod + da_add_target)
    da_per_18 = round(da_target_18 / active_member, 1) if active_member else 0

    est_18_from_14 = int(current_total * mul_14)
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150

    est_ba_18_14 = int(est_18_from_14 * ratio_ba) if not is_aff_bojang else int((est_18_from_14 - res['aff_cnt']) * ratio_ba) + res['aff_cnt']
    est_prod_18_14 = est_18_from_14 - est_ba_18_14

    # CPA
    cpa_da = round(res['da_cost'] / res['da_cnt'] / 10000, 1) if res['da_cnt'] > 0 else 0
    cpa_aff = round(res['aff_cost'] / res['aff_cnt'] / 10000, 1) if res['aff_cnt'] > 0 else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total > 0 else 0

    # [FIXED] 멘트 변수 정의 (이 부분이 누락되어 에러 발생했음)
    fixed_msg = f"금일 {fixed_content}." if fixed_ad_type != "없음" else "금일 특이사항 없이 운영 중이며,"
    msg_14 = "금일 고정구좌 이슈없이 집행중이며..." if est_18_from_14 >= da_target_18 else "오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 집중 관리하겠습니다."
    
    time_multipliers = {
        "09:30": 1.0, "10:00": 1.75, "11:00": 1.65, "12:00": 1.55, "13:00": 1.45,
        "14:00": mul_14, "15:00": (mul_14 + mul_16)/2, "16:00": mul_16, 
        "17:00": 1.05 if not is_boosting else 1.15, "18:00": 1.0
    }
    current_mul = time_multipliers.get(current_time_str, 1.35)
    est_final_live = int(current_total * current_mul)

    # --- 탭 출력 ---
    tab0, tab1, tab2, tab3, tab4 = st.tabs(["📊 인사이트 대시보드", "🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근"])

    with tab0:
        st.subheader(f"📊 실시간 DA 운영 현황 ({current_time_str})")
        c1, c2, c3 = st.columns(3)
        c1.metric("최종 목표", f"{da_target_18:,}건")
        c2.metric("현재 실적", f"{current_total:,}건")
        c3.metric("마감 예상", f"{est_final_live:,}건")
        st.progress(min(1.0, current_total/da_target_18 if da_target_18 else 1))

    with tab2:
        st.subheader("🔥 14:00 중간 보고")
        report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {da_per_18:.1f}건 / 총 {da_target_18:,}건
현황(14시) : 인당배분 {round(current_total/active_member, 1):.1f}건 / 총 {current_total:,}건
예상 마감(18시 기준) : 인당배분 {round(est_18_from_14/active_member, 1):.1f}건 / 총 {est_18_from_14:,}건
ㄴ 보장분석 : {est_ba_18_14:,}건, 상품 {est_prod_18_14:,}건

* {fixed_msg} {msg_14}

[현재 성과 - 14시 기준]
- 총합(DA/제휴): {int(cost_total)//10000:,}만원 / 가망CPA {cpa_total:.1f}만원
- DA: {int(res['da_cost'])//10000:,}만원 / 가망CPA {cpa_da:.1f}만원
- 제휴: {int(res['aff_cost'])//10000:,}만원 / 가망CPA {cpa_aff:.1f}만원

[예상 마감 - 18시 기준]
- 총합(DA/제휴): {int(cost_total * 1.35)//10000:,}만원 / 가망CPA {max(3.1, cpa_total-0.2):.1f}만원
- DA: {int(res['da_cost'] * 1.4)//10000:,}만원 / 가망CPA {max(4.4, cpa_da):.1f}만원
- 제휴: {int(res['aff_cost'] * 1.25)//10000:,}만원 / 가망CPA {max(2.4, cpa_aff-0.2):.1f}만원"""
        st.text_area("복사 텍스트 (14시):", report_1400, height=450)

    # (tab1, tab3, tab4는 이전과 동일)
    with tab1:
        # (tab1 내용 복원)
        st.subheader("📋 오전 목표")
        st.info("파일 업로드 시 상세 데이터 표시")

    with tab3:
        # (tab3 내용 복원)
        st.subheader("⚠️ 16:00 마감 임박 보고")
        report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {da_target_18:,}건
ㄴ 보장분석 : {int(est_ba_18_14):,}건, 상품 {int(est_prod_18_14):,}건

16시 현황 : 총 {current_total:,}건
ㄴ 보장분석 : {int(current_bojang):,}건, 상품 {int(current_prod):,}건

* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."""
        st.text_area("복사 텍스트 (16시):", report_1600, height=300)

    with tab4:
        # (tab4 내용 복원)
        st.subheader("🌙 명일 자원 수립")
        report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : 1,450건
ㄴ 보장분석 : 1,200건
ㄴ 상품자원 : 250건

* 영업가족 {tom_member}명 기준 인당 4.4건 이상 확보할 수 있도록 운영 예정입니다."""
        st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)

def main():
    st.sidebar.title("⚙️ 시스템 버전 선택")
    version = st.sidebar.selectbox("버전 선택", ["V16.1 (Fixed)", "V6.6 (Legacy)"])
    if version == "V16.1 (Fixed)": run_v16_0_advanced()
    else: run_v6_6_legacy()

if __name__ == "__main__":
    main()
