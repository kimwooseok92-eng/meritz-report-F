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
st.set_page_config(page_title="메리츠 보고 자동화 V17.0", layout="wide")

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
# 1. 유틸리티 함수 (Dual Track Parser)
# -----------------------------------------------------------
def parse_files_dual_track(files):
    """
    파일을 '비용 소스(Raw)'와 'DB 소스(PLAB)'로 분리하여 처리
    """
    df_cost_source = pd.DataFrame() # 비용 계산용 (네/카/구/토)
    df_db_source = pd.DataFrame()   # DB 계산용 (피랩)
    
    # [설정] 비용 파일에서 찾을 컬럼
    cost_keywords = ['비용', '소진', 'Cost', '금액', '총 비용']
    # [설정] DB 파일(피랩)에서 찾을 컬럼 (우선순위: 계 > 보장분석 > 합계)
    db_keywords = ['계', '합계', '보장분석', '전환', 'DB', '건수', '잠재고객']

    for file in files:
        fname = file.name.lower()
        is_plab = 'performance' in fname or 'lab' in fname or '피랩' in fname
        
        try:
            # 파일 읽기 (공통)
            df = read_file_generic(file)
            if df is None or df.empty: continue
            
            # --- 트랙 분기 ---
            if is_plab:
                # [Track B] 피랩 데이터 -> DB 건수 추출 전용
                # 필요한 컬럼: 매체 구분(account, media), 유형(구분), 건수(계/보장분석)
                temp = pd.DataFrame()
                
                # 1. 건수 컬럼 찾기
                col_cnt = find_col(df, db_keywords)
                
                # 2. 매체/유형 컬럼 찾기
                col_media = find_col(df, ['media', 'account', '매체', '그룹'])
                col_type = find_col(df, ['구분', 'type', '캠페인'])
                
                if col_cnt:
                    temp['count'] = df[col_cnt].apply(clean_num).fillna(0)
                    temp['media_raw'] = df[col_media].fillna('기타') if col_media else '기타'
                    temp['type_raw'] = df[col_type].fillna('') if col_type else ''
                    temp['source'] = 'PLAB'
                    df_db_source = pd.concat([df_db_source, temp], ignore_index=True)
                    
            else:
                # [Track A] 매체 로우 데이터 -> 비용 추출 전용
                # 필요한 컬럼: 캠페인명(보장/상품 구분용), 비용
                temp = pd.DataFrame()
                
                col_cost = find_col(df, cost_keywords)
                col_camp = find_col(df, ['캠페인', 'Campaign', '광고명'])
                
                if col_cost and col_camp:
                    temp['cost'] = df[col_cost].apply(clean_num).fillna(0)
                    temp['campaign'] = df[col_camp].fillna('기타')
                    temp['source'] = 'RAW'
                    df_cost_source = pd.concat([df_cost_source, temp], ignore_index=True)

        except Exception as e:
            pass

    return df_cost_source, df_db_source

def read_file_generic(file):
    """CSV/Excel 상관없이 읽어서 DataFrame 반환"""
    try:
        file.seek(0)
        if file.name.lower().endswith(('.csv', '.txt')):
            for enc in ['utf-8-sig', 'cp949', 'euc-kr']:
                for sep in [',', '\t']:
                    try:
                        file.seek(0)
                        return pd.read_csv(file, encoding=enc, sep=sep, on_bad_lines='skip')
                    except: continue
        else:
            try: return pd.read_excel(file, engine='openpyxl')
            except: return pd.read_csv(file) # 가짜 엑셀 대응
    except: return None
    return None

def find_col(df, keywords):
    """키워드가 포함된 컬럼명 찾기"""
    for col in df.columns:
        if any(k in str(col) for k in keywords):
            return col
    return None

def clean_num(x):
    try: return float(str(x).replace(',', '').replace('"', '').replace(' ', ''))
    except: return 0

def normalize_media(row, source_type):
    """매체명 표준화"""
    text = str(row.get('campaign', '') if source_type == 'RAW' else row.get('media_raw', '')).lower()
    if any(x in text for x in ['네이버', 'naver', 'gfa', 'nasp']): return '네이버'
    if any(x in text for x in ['카카오', 'kakao', 'kakaoment']): return '카카오'
    if any(x in text for x in ['토스', 'toss']): return '토스'
    if any(x in text for x in ['구글', 'google', 'youtube']): return '구글'
    return '기타'

def classify_type(row, source_type):
    """보장/상품 구분"""
    text = str(row.get('campaign', '') if source_type == 'RAW' else row.get('type_raw', '')).lower()
    if '보장' in text: return '보장'
    return '상품' # 기본값

def aggregate_dual_source(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt):
    res = {
        'da_cost': 0, 'da_cnt': 0,
        'aff_cost': 0, 'aff_cnt': 0,
        'total_cost': 0, 'total_cnt': 0,
        'bojang_cnt': 0, 'prod_cnt': 0,
        'ratio_ba': 0.898
    }

    # 1. 비용 집계 (Raw File 기준)
    if not df_cost.empty:
        df_cost['media'] = df_cost.apply(lambda x: normalize_media(x, 'RAW'), axis=1)
        df_cost['type'] = df_cost.apply(lambda x: classify_type(x, 'RAW'), axis=1)
        
        # 제휴 비용 분리 (토스, 카카오 등 제휴 매체로 식별된 것 중 캠페인명에 '제휴'가 있거나 특정 조건)
        # 리더님 요청: "네/카/구/토는 보장/상품 구분과 비용 데이터만 사용" -> DA 비용으로 산정하되 제휴는 별도
        # 여기서는 단순하게 매체별 합산 후 제휴 수기 입력과 병합
        
        # 전체 비용 합산
        res['da_cost'] = int(df_cost['cost'].sum())

    # 2. DB 집계 (PLAB File 기준)
    if not df_db.empty:
        df_db['media'] = df_db.apply(lambda x: normalize_media(x, 'PLAB'), axis=1)
        df_db['type'] = df_db.apply(lambda x: classify_type(x, 'PLAB'), axis=1)
        
        # 전체 DB 합산
        res['da_cnt'] = int(df_db['count'].sum())
        
        # 보장/상품 건수 상세 집계
        res['bojang_cnt'] = int(df_db[df_db['type']=='보장']['count'].sum())
        res['prod_cnt'] = int(df_db[df_db['type']=='상품']['count'].sum())

    # 3. 수기 입력 적용 (Override & Add)
    # DA: 파일값 + 수기값 (누락분 추가)
    res['da_cost'] += manual_da_cost
    res['da_cnt'] += manual_da_cnt
    
    # 제휴: 수기값 우선 (파일에 제휴가 섞여있어도 피랩이 건수 마스터이므로, 피랩에 제휴가 포함되어 있다면 중복 위험)
    # 피랩 데이터에 제휴가 포함되어 있다면? -> 피랩에서 제휴를 발라내야 함.
    # 피랩의 'media_raw'나 'type_raw'에 '제휴'가 있는지 확인
    if not df_db.empty:
        # 피랩 데이터 중 '제휴'로 추정되는 건수 제외 (수기로 넣을거니까)
        mask_aff_plab = df_db['media_raw'].astype(str).str.contains('제휴') | df_db['type_raw'].astype(str).str.contains('제휴')
        aff_in_plab = df_db[mask_aff_plab]['count'].sum()
        
        # 피랩 총 건수에서 제휴 추정치 제외 (순수 DA만 남김)
        res['da_cnt'] -= int(aff_in_plab)
        if res['bojang_cnt'] > aff_in_plab: res['bojang_cnt'] -= int(aff_in_plab) # 대략적 차감

    # 제휴 최종값 설정
    res['aff_cost'] = manual_aff_cost
    res['aff_cnt'] = manual_aff_cnt
    
    # 최종 합산
    res['total_cost'] = res['da_cost'] + res['aff_cost']
    res['total_cnt'] = res['da_cnt'] + res['aff_cnt']
    
    # 보장 건수 보정 (수기 제휴가 보장이라면)
    # (여기선 단순하게 비율 계산을 위해 놔둠)
    
    if res['total_cnt'] > 0:
        # 보장 비율 재계산 (PLAB 기준 보장 건수 + 수기 제휴가 보장이라면 추가 필요)
        # 편의상 현재 PLAB의 비율을 전체에 적용하거나, 수기 입력 시 보장 여부를 묻는게 정확함.
        # 일단 PLAB 데이터 기반 비율 유지
        if not df_db.empty:
            total_plab = df_db['count'].sum()
            bojang_plab = df_db[df_db['type']=='보장']['count'].sum()
            if total_plab > 0:
                res['ratio_ba'] = bojang_plab / total_plab
    
    return res


# -----------------------------------------------------------
# MODE 2: V17.0 Advanced
# -----------------------------------------------------------
def run_v16_0_advanced():
    st.title("📊 메리츠화재 DA 통합 시스템 (V17.0 Dual Master)")
    st.markdown("🚀 **비용(Raw) / 건수(PLAB) 이원화 처리**")

    # [중요] 변수 사전 초기화 (NameError 방지)
    current_bojang, current_prod = 0, 0
    est_ba_18_14, est_prod_18_14 = 0, 0
    da_target_bojang, da_target_prod = 0, 0
    da_per_18, da_per_17 = 0, 0
    da_target_18, da_target_17 = 0, 0
    
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

        # 목표 계산 (에러 방지를 위해 최상단 수행)
        da_target_bojang = target_bojang - sa_est_bojang
        da_target_prod = target_product - sa_est_prod + da_add_target
        da_target_18 = da_target_bojang + da_target_prod
        
        if active_member > 0:
            da_per_18 = round(da_target_18 / active_member, 1)
            da_target_17 = int(da_target_18 * 0.96) # 단순화
            da_per_17 = round(da_target_17 / active_member, 1)

        st.header("3. [자동] 10시 시작 자원")
        with st.expander("📂 파일 업로드"):
            file_yest_24 = st.file_uploader("① 어제 24시", key="f1")
            file_today_10 = st.file_uploader("② 오늘 10시", key="f3")
        start_resource_10 = st.number_input("10시 자원 (수기/자동)", value=1100)

        st.header("4. [자동+수기] 실시간 분석")
        uploaded_realtime = st.file_uploader("📊 실시간 로우데이터 (모두 선택)", accept_multiple_files=True)
        is_aff_bojang = st.checkbox("☑️ 금일 제휴는 '보장' 위주", value=False)
        
        st.markdown("**✏️ 수기 입력 (제휴)**")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_da_cnt = st.number_input("DA 추가 건수", value=0)
            manual_da_cost = st.number_input("DA 추가 소진액", value=0)
        with col_m2:
            manual_aff_cost = st.number_input("제휴 수기 소진액", value=11270000) 
            manual_aff_cpa = st.number_input("제휴 수기 단가", value=14000)
            manual_aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0
            st.info(f"ㄴ 제휴 환산: {manual_aff_cnt:,}건")

        # [핵심 로직] 이원화 파싱 및 집계
        df_cost, df_db = parse_files_dual_track(uploaded_realtime) if uploaded_realtime else (pd.DataFrame(), pd.DataFrame())
        res = aggregate_dual_source(df_cost, df_db, manual_aff_cost, manual_aff_cnt, manual_da_cost, manual_da_cnt)
        
        current_total = res['total_cnt']
        cost_total = res['total_cost']
        ratio_ba = res['ratio_ba']
        
        # 보장/상품 배분
        if is_aff_bojang:
            current_bojang = int(res['da_cnt'] * ratio_ba) + res['aff_cnt']
        else:
            current_bojang = int(current_total * ratio_ba)
        current_prod = current_total - current_bojang

        st.header("5. 기타 설정")
        tom_member = st.number_input("명일 활동 인원", value=350)
        tom_sa_9 = st.number_input("명일 SA 9시", value=410)
        tom_dawn_ad = st.checkbox("내일 새벽 고정광고", value=False)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 예측 계산 ---
    base_mul_14 = 1.35
    if day_option == '월': base_mul_14 = 1.15
    elif fixed_ad_type != "없음": base_mul_14 = 1.215
    
    mul_14 = base_mul_14
    mul_16 = 1.25 if is_boosting else 1.10

    est_18_from_14 = int(current_total * mul_14)
    # Range limit
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150

    if is_aff_bojang:
        est_ba_18_14 = int((est_18_from_14 - res['aff_cnt']) * ratio_ba) + res['aff_cnt']
    else:
        est_ba_18_14 = int(est_18_from_14 * ratio_ba)
    est_prod_18_14 = est_18_from_14 - est_ba_18_14

    cpa_da = round(res['da_cost'] / res['da_cnt'] / 10000, 1) if res['da_cnt'] > 0 else 0
    cpa_aff = round(res['aff_cost'] / res['aff_cnt'] / 10000, 1) if res['aff_cnt'] > 0 else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total > 0 else 0

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
        if da_target_18 > 0:
            st.progress(min(1.0, current_total/da_target_18))
            
        # 목표 그래프 (V14 복구)
        hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
        weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
        gap = da_target_18 - start_resource_10
        total_w = sum(weights)
        acc_res = [start_resource_10]
        for w in weights[1:]:
            acc_res.append(acc_res[-1] + round(gap * (w / total_w)))
        acc_res[-1] = da_target_18
        
        st.line_chart(pd.DataFrame({'목표 흐름': acc_res}, index=hours))

    with tab1:
        st.subheader("📋 오전 목표")
        report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {da_target_17:,}건 ({active_member}명, {da_per_17:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_17*ratio_ba):,}건
ㄴ 상품 : {int(da_target_17*(1-ratio_ba)):,}건

[18시 기준]
총 자원 : {da_target_18:,}건 ({active_member}명, {da_per_18:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_bojang):,}건
ㄴ 상품 : {int(da_target_prod):,}건

* {fixed_msg}"""
        st.text_area("복사 텍스트:", report_morning, height=300)

    with tab2:
        st.subheader("🔥 14:00 중간 보고")
        report_1400 = f"""DA파트 금일 14시간 현황 전달드립니다.

금일 목표(18시 기준) : 인당배분 {da_per_18:.1f}건 / 총 {da_target_18:,}건
현황(14시) : 인당배분 {round(current_total/active_member, 1) if active_member else 0:.1f}건 / 총 {current_total:,}건
예상 마감(18시 기준) : 인당배분 {round(est_18_from_14/active_member, 1) if active_member else 0:.1f}건 / 총 {est_18_from_14:,}건
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

    with tab3:
        st.subheader("⚠️ 16:00 마감 임박 보고")
        report_1600 = f"""DA파트 금일 16시간 현황 전달드립니다.

금일 목표(18시 기준) : 총 {da_target_18:,}건
ㄴ 보장분석 : {da_target_bojang:,}건, 상품 {da_target_prod:,}건

16시 현황 : 총 {current_total:,}건
ㄴ 보장분석 : {int(current_bojang):,}건, 상품 {int(current_prod):,}건

* 마감 전까지 배너광고 및 제휴 매체 최대한 활용하여 자원 확보하겠습니다."""
        st.text_area("복사 텍스트 (16시):", report_1600, height=300)

    with tab4:
        st.subheader("🌙 명일 자원 수립")
        tom_base_total = int(tom_member * 3.15) + (300 if tom_dawn_ad else 0)
        report_tomorrow = f"""DA+제휴 명일 오전 9시 예상 자원 공유드립니다.

- 9시 예상 시작 자원 : {tom_base_total:,}건
ㄴ 보장분석 : {int(tom_base_total * ratio_ba):,}건
ㄴ 상품자원 : {int(tom_base_total * (1-ratio_ba)):,}건

* 영업가족 {tom_member}명 기준 인당 {4.4 if not tom_dawn_ad else 5.0}건 이상 확보할 수 있도록 운영 예정입니다."""
        st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)

def main():
    st.sidebar.title("⚙️ 시스템 버전 선택")
    version = st.sidebar.selectbox("버전 선택", ["V17.0 (Dual Master)", "V6.6 (Legacy)"])
    if version == "V17.0 (Dual Master)": run_v16_0_advanced()
    else: run_v6_6_legacy()

if __name__ == "__main__":
    main()
