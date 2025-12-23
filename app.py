import streamlit as st
import pandas as pd
import platform
import io
import warnings
import unicodedata

# 경고 메시지 무시
warnings.simplefilter("ignore")

# -----------------------------------------------------------
# 0. 공통 설정
# -----------------------------------------------------------
st.set_page_config(page_title="메리츠 보고 자동화 V18.35 Final", layout="wide")

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
# 1. 유틸리티 및 데이터 처리 함수
# -----------------------------------------------------------
def clean_currency(x):
    """쉼표 제거 및 숫자 변환 (강화됨: int/float/str 모두 처리)"""
    if pd.isna(x) or x == '':
        return 0.0
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        try:
            return float(x.replace(',', '').replace('"', '').replace("'", "").strip())
        except:
            return 0.0
    return 0.0

def classify_product(campaign_name):
    """상품 구분"""
    if pd.isna(campaign_name):
        return '상품'
    name = str(campaign_name)
    if '보장' in name or '누적' in name:
        return '보장분석'
    else:
        return '상품'

def get_media_from_plab(row):
    """피랩 매체 식별"""
    account = str(row.get('account', '')).upper()
    gubun = str(row.get('구분', '')).upper()
    
    if 'DDN' in account: return '카카오'
    if 'GDN' in account: return '구글'
    
    targets = ['네이버', '카카오', '토스', '구글', 'NAVER', 'KAKAO', 'TOSS', 'GOOGLE']
    media_map = {'NAVER': '네이버', 'KAKAO': '카카오', 'TOSS': '토스', 'GOOGLE': '구글'}
    
    for t in targets:
        if t in account: return media_map.get(t, t)
    for t in targets:
        if t in gubun: return media_map.get(t, t)

    return '기타'

def load_file_by_rule(file):
    """
    [핵심] 파일명 기반 맞춤형 읽기 로직 (인코딩/구분자 자동 해결)
    """
    name = file.name
    file.seek(0)
    
    # 1. 엑셀 파일 처리
    if name.endswith(('.xlsx', '.xls')):
        try:
            return pd.read_excel(file, engine='openpyxl')
        except Exception as e:
            st.error(f"엑셀 파일 읽기 실패 ({name}): {e}")
            return None

    # 2. CSV 파일 처리 (규칙 적용)
    try:
        if '캠페인 보고서' in name: # 구글
            try: return pd.read_csv(file, sep='\t', encoding='utf-16', header=2, on_bad_lines='skip')
            except: return pd.read_csv(file, sep='\t', encoding='utf-8-sig', header=2, on_bad_lines='skip')

        elif '메리츠화재다이렉트' in name: # 카카오
            try: return pd.read_csv(file, sep='\t', encoding='utf-8', on_bad_lines='skip')
            except: return pd.read_csv(file, sep='\t', encoding='cp949', on_bad_lines='skip')

        elif '메리츠 화재' in name: # 토스 (통합 or 시간대별)
            # 헤더가 3행(index 3)에 있음
            try: return pd.read_csv(file, header=3, encoding='utf-8', on_bad_lines='skip')
            except: return pd.read_csv(file, header=3, encoding='cp949', on_bad_lines='skip')
            
    except:
        pass

    # 3. 공통/Fallback 로직 (여러 인코딩 시도)
    encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-16', 'utf-8-sig']
    separators = [',', '\t']
    
    for enc in encodings:
        for sep in separators:
            try:
                file.seek(0)
                df = pd.read_csv(file, encoding=enc, sep=sep, on_bad_lines='skip')
                if len(df.columns) > 1: return df
            except: continue
                
    st.error(f"❌ 파일 형식을 인식할 수 없습니다: {name}")
    return None

def process_marketing_data(uploaded_files):
    """파일명 기반 통합 로직 (토스 중복 처리 개선)"""
    dfs = []
    toss_files = [] # 토스 파일 별도 관리
    
    for file in uploaded_files:
        filename = file.name
        df = load_file_by_rule(file)
        
        if df is None: continue
            
        try:
            # 1. 네이버
            if 'result' in filename:
                df['Cost'] = df['총 비용'].apply(clean_currency)
                df['상품'] = df['캠페인 이름'].apply(classify_product)
                df['매체'] = '네이버'
                grouped = df.groupby(['매체', '상품'])['Cost'].sum().reset_index()
                grouped['보장'] = 0 
                dfs.append(grouped)

            # 2. 카카오
            elif '메리츠화재다이렉트' in filename:
                df['Cost'] = df['비용'].apply(clean_currency) * 1.1
                df['상품'] = df['캠페인'].apply(classify_product)
                df['매체'] = '카카오'
                grouped = df.groupby(['매체', '상품'])['Cost'].sum().reset_index()
                grouped['보장'] = 0
                dfs.append(grouped)

            # 3. 토스 (일단 리스트에 모음)
            elif '메리츠 화재' in filename:
                toss_files.append((filename, df))

            # 4. 구글
            elif '캠페인 보고서' in filename:
                df.columns = df.columns.str.strip()
                if '캠페인' in df.columns:
                    df = df[~df['캠페인'].astype(str).str.contains('합계|Total|--', case=False, na=False)]
                    df = df[df['캠페인'].notna()]

                cost_val = df['비용'].apply(clean_currency) if '비용' in df.columns else 0
                df['Cost'] = cost_val * 1.1 * 1.15
                df['상품'] = df['캠페인'].apply(classify_product)
                df['매체'] = '구글'
                grouped = df.groupby(['매체', '상품'])['Cost'].sum().reset_index()
                grouped['보장'] = 0
                dfs.append(grouped)

            # 5. 피랩
            elif 'Performance Lab' in filename:
                df.columns = df.columns.str.strip()
                send_col = next((c for c in df.columns if 'METIS전송' in c and '율' not in c), None)
                fail_col = next((c for c in df.columns if 'METIS실패' in c), None)
                re_col = next((c for c in df.columns if 'METIS재인입' in c), None)
                
                if send_col:
                    s = df[send_col].apply(clean_currency)
                    f = df[fail_col].apply(clean_currency) if fail_col else 0
                    r = df[re_col].apply(clean_currency) if re_col else 0
                    df['보장'] = s - f - r
                else:
                    df['보장'] = 0

                df['매체'] = df.apply(get_media_from_plab, axis=1)
                df['상품'] = df['구분'].apply(classify_product)
                
                plab_summary = df.groupby(['매체', '상품'])['보장'].sum().reset_index()
                plab_summary['Cost'] = 0
                dfs.append(plab_summary)

        except Exception as e:
            st.error(f"❌ 데이터 파싱 중 오류 ({filename}): {e}")
            continue

    # [토스 파일 후처리]
    # '통합' 파일이 있으면 그것만 사용, 없으면 모든 토스 파일 합산
    if toss_files:
        toss_total_file = next((item for item in toss_files if '통합' in item[0]), None)
        
        target_toss_files = [toss_total_file] if toss_total_file else toss_files
        
        for fname, df in target_toss_files:
            try:
                # 합계 행 제거
                if '캠페인 명' in df.columns:
                     df = df[~df['캠페인 명'].astype(str).str.contains('합계|Total', case=False, na=False)]
                
                df['Cost'] = df['소진 비용'].apply(clean_currency) * 1.1
                df['상품'] = df['캠페인 명'].apply(classify_product)
                df['매체'] = '토스'
                grouped = df.groupby(['매체', '상품'])['Cost'].sum().reset_index()
                grouped['보장'] = 0
                dfs.append(grouped)
            except Exception as e:
                st.error(f"❌ 토스 파일 처리 오류 ({fname}): {e}")

    if not dfs:
        return None

    # 통합
    all_data = pd.concat(dfs, ignore_index=True)
    final_df = all_data.groupby(['매체', '상품']).sum().reset_index()
    
    if '보장' not in final_df.columns: final_df['보장'] = 0.0
    if 'Cost' not in final_df.columns: final_df['Cost'] = 0.0
    
    final_df['CPA'] = final_df.apply(lambda x: x['Cost'] / x['보장'] if x['보장'] > 0 else 0, axis=1)
    
    return final_df

def convert_to_stats(final_df, manual_aff_cnt, manual_aff_cost, manual_da_cnt, manual_da_cost):
    """통계 변환"""
    media_list = ['네이버', '카카오', '토스', '구글', '제휴', '기타']
    stats = pd.DataFrame(index=media_list, columns=['Bojang_Cnt', 'Prod_Cnt', 'Cost', 'CPA']).fillna(0)
    
    if final_df is not None:
        for _, row in final_df.iterrows():
            m = row['매체']
            if m not in stats.index: m = '기타'
            
            stats.loc[m, 'Cost'] += row['Cost']
            if row['상품'] == '보장분석':
                stats.loc[m, 'Bojang_Cnt'] += row['보장']
            else:
                stats.loc[m, 'Prod_Cnt'] += row['보장']
    
    # 수기 보정
    if manual_da_cnt > 0 or manual_da_cost > 0:
        stats.loc['기타', 'Prod_Cnt'] += manual_da_cnt
        stats.loc['기타', 'Cost'] += manual_da_cost

    if manual_aff_cnt > 0 or manual_aff_cost > 0:
        stats.loc['제휴', :] = 0
        stats.loc['제휴', 'Bojang_Cnt'] = manual_aff_cnt
        stats.loc['제휴', 'Cost'] = manual_aff_cost

    stats['Total_Cnt'] = stats['Bojang_Cnt'] + stats['Prod_Cnt']
    stats['CPA'] = stats.apply(lambda x: x['Cost'] / x['Total_Cnt'] if x['Total_Cnt'] > 0 else 0, axis=1)
    
    res = {
        'da_cost': int(stats.drop('제휴')['Cost'].sum()),
        'da_cnt': int(stats.drop('제휴')['Total_Cnt'].sum()),
        'da_bojang': int(stats.drop('제휴')['Bojang_Cnt'].sum()),
        'da_prod': int(stats.drop('제휴')['Prod_Cnt'].sum()),
        'aff_cost': int(stats.loc['제휴', 'Cost']),
        'aff_cnt': int(stats.loc['제휴', 'Total_Cnt']),
        'bojang_cnt': int(stats['Bojang_Cnt'].sum()),
        'prod_cnt': int(stats['Prod_Cnt'].sum()),
        'media_stats': stats
    }
    
    res['total_cost'] = res['da_cost'] + res['aff_cost']
    res['total_cnt'] = res['da_cnt'] + res['aff_cnt']
    res['ratio_ba'] = res['bojang_cnt'] / res['total_cnt'] if res['total_cnt'] > 0 else 0.898
    
    return res

# -----------------------------------------------------------
# MODE: V18.35 Master
# -----------------------------------------------------------
def run_v18_35_master():
    st.title("📊 메리츠화재 DA 통합 시스템 (V18.35 Final)")
    st.markdown("🚀 **토스 비용 & 파일 인식 완벽 대응 패치**")

    # 변수 초기화
    current_bojang, current_prod = 0, 0
    
    with st.sidebar:
        st.header("1. 기본 설정")
        current_time_str = st.select_slider("⏱️ 현재 기준", options=["09:30", "10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00", "18:00"], value="14:00")
        is_boosting = False
        if current_time_str in ["16:00", "17:00"]:
            is_boosting = st.checkbox("🔥 긴급 부스팅", value=False)
        day_option = st.selectbox("요일", ['월', '화', '수', '목', '금'], index=0)
        
        st.header("2. 목표 수립")
        active_member = st.number_input("활동 인원", value=359)
        c1, c2 = st.columns(2)
        with c1: target_bojang = st.number_input("보장 목표", value=500)
        with c2: target_product = st.number_input("상품 목표", value=3100)
        c3, c4 = st.columns(2)
        with c3: sa_est_bojang = st.number_input("SA 보장", value=200)
        with c4: sa_est_prod = st.number_input("SA 상품", value=800)
        da_add_target = st.number_input("DA 버퍼", value=50)

        da_target_bojang = target_bojang - sa_est_bojang
        da_target_prod = target_product - sa_est_prod + da_add_target
        da_target_18 = da_target_bojang + da_target_prod
        target_ratio_ba = da_target_bojang / da_target_18 if da_target_18 > 0 else 0.898
        
        if active_member > 0:
            da_per_18 = round(da_target_18 / active_member, 1)
            da_target_17 = int(da_target_18 * 0.96)
            da_per_17 = round(da_target_17 / active_member, 1)

        st.header("3. [자동] 10시 자원")
        with st.expander("📂 업로드"):
            st.file_uploader("어제 24시", key="f1")
            st.file_uploader("오늘 10시", key="f3")
        start_resource_10 = st.number_input("10시 자원", value=1100)

        st.header("4. [실시간] 분석")
        uploaded_realtime = st.file_uploader("실시간 파일 (파일명 자동 인식)", accept_multiple_files=True)
        
        st.markdown("**✏️ 수기 입력 (제휴)**")
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            manual_da_cnt = st.number_input("DA 추가 건", value=0)
            manual_da_cost = st.number_input("DA 추가 액", value=0)
        with col_m2:
            manual_aff_cost = st.number_input("제휴 소진액", value=11270000) 
            manual_aff_cpa = st.number_input("제휴 단가", value=14000)
            manual_aff_cnt = int(manual_aff_cost / manual_aff_cpa) if manual_aff_cpa > 0 else 0
            st.caption(f"제휴 환산: {manual_aff_cnt:,}건")

        # --- 데이터 처리 ---
        final_df = process_marketing_data(uploaded_realtime) if uploaded_realtime else None
        res = convert_to_stats(final_df, manual_aff_cnt, manual_aff_cost, manual_da_cnt, manual_da_cost)
        
        current_total = res['total_cnt']
        cost_total = res['total_cost']
        ratio_ba = res['ratio_ba']
        current_bojang = res['bojang_cnt']
        current_prod = res['prod_cnt']

        st.header("5. 보고 설정")
        tom_member = st.number_input("명일 인원", value=350)
        tom_dawn_ad = st.checkbox("새벽 광고", value=False)
        fixed_ad_type = st.radio("발송 시간", ["없음", "12시", "14시", "Both"], index=2)
        fixed_content = st.text_input("내용", value="14시 카카오페이 TMS 발송 예정입니다")

    # --- 계산 ---
    base_mul_14 = 1.35
    if day_option == '월': base_mul_14 = 1.15
    elif fixed_ad_type != "없음": base_mul_14 = 1.215
    
    mul_14 = base_mul_14
    mul_16 = 1.25 if is_boosting else 1.10

    est_18_from_14 = int(current_total * mul_14)
    if est_18_from_14 > da_target_18 + 250: est_18_from_14 = da_target_18 + 150
    elif est_18_from_14 < da_target_18 - 250: est_18_from_14 = da_target_18 - 150

    est_ba_18_14 = int(est_18_from_14 * ratio_ba)
    est_prod_18_14 = est_18_from_14 - est_ba_18_14

    cpa_da = round(res['da_cost'] / res['da_cnt'] / 10000, 1) if res['da_cnt'] > 0 else 0
    cpa_aff = round(res['aff_cost'] / res['aff_cnt'] / 10000, 1) if res['aff_cnt'] > 0 else 0
    cpa_total = round(cost_total / current_total / 10000, 1) if current_total > 0 else 0

    if fixed_ad_type != "없음":
        fixed_msg = f"금일 {fixed_content}." if fixed_content.strip() else "금일 특이사항 없이 운영 중이며,"
    else:
        fixed_msg = "금일 특이사항 없이 운영 중이며,"

    msg_14 = "금일 고정구좌 이슈없이 집행중이며..." if est_18_from_14 >= da_target_18 else "오전 목표 대비 소폭 부족할 것으로 예상되나, 남은 시간 집중 관리하겠습니다."
    
    time_multipliers = {
        "09:30": 1.0, "10:00": 1.75, "11:00": 1.65, "12:00": 1.55, "13:00": 1.45,
        "14:00": mul_14, "15:00": (mul_14 + mul_16)/2, "16:00": mul_16, 
        "17:00": 1.05 if not is_boosting else 1.15, "18:00": 1.0
    }
    current_mul = time_multipliers.get(current_time_str, 1.35)
    est_final_live = int(current_total * current_mul)

    # --- 탭 ---
    tab0, tab1, tab2, tab3, tab4 = st.tabs(["📊 대시보드", "🌅 09:30 목표", "🔥 14:00 중간", "⚠️ 16:00 마감", "🌙 18:00 퇴근"])

    with tab0:
        st.subheader(f"📊 실시간 DA 현황 대시보드 ({current_time_str})")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("최종 목표", f"{da_target_18:,}건")
            st.markdown(f":grey[보장 {da_target_bojang:,} / 상품 {da_target_prod:,}]")
        with c2:
            progress = min(1.0, current_total/da_target_18) if da_target_18 > 0 else 0
            st.metric("현재 실적", f"{current_total:,}건", f"{progress*100:.1f}%")
            st.markdown(f":grey[보장 {current_bojang:,} / 상품 {current_prod:,}]")
        with c3:
            st.metric("마감 예상", f"{est_final_live:,}건", f"Gap: {est_final_live - da_target_18}")
            est_ba_live = int(est_final_live * ratio_ba)
            est_prod_live = est_final_live - est_ba_live
            st.markdown(f":grey[보장 {est_ba_live:,} / 상품 {est_prod_live:,}]")
        with c4:
            st.metric("현재 CPA", f"{cpa_total:.1f}만원")
            st.markdown(f":grey[DA {cpa_da:.1f} / 제휴 {cpa_aff:.1f}]")

        st.progress(progress)
        
        col_d1, col_d2 = st.columns([1, 1])
        with col_d1:
            st.markdown("##### 📌 시간대별 목표 상세")
            hours = ["10시", "11시", "12시", "13시", "14시", "15시", "16시", "17시", "18시"]
            weights = [0, 0.11, 0.18, 0.15, 0.11, 0.16, 0.10, 0.10, 0.09]
            acc_res = [start_resource_10]
            gap = da_target_18 - start_resource_10
            total_w = sum(weights)
            for w in weights[1:]:
                acc_res.append(acc_res[-1] + round(gap * (w / total_w)))
            acc_res[-1] = da_target_18
            
            df_dash_goal = pd.DataFrame({
                '누적 목표': [f"{x:,}" for x in acc_res],
                '보장 목표': [f"{int(x * target_ratio_ba):,}" for x in acc_res],
                '상품 목표': [f"{int(x * (1-target_ratio_ba)):,}" for x in acc_res]
            }, index=hours).T
            
            target_col = current_time_str.replace(":00", "시").replace("09:30", "10시")
            def highlight_col(s):
                return ['background-color: #ffffcc' if s.name == target_col else '' for _ in s]
            
            if target_col in df_dash_goal.columns:
                st.dataframe(df_dash_goal.style.apply(highlight_col, axis=0), use_container_width=True)
            else:
                st.dataframe(df_dash_goal, use_container_width=True)
            
        with col_d2:
            st.markdown("##### 📌 매체별 실적 상세")
            if not res['media_stats'].empty:
                display_stats = res['media_stats'].copy()
                display_stats.loc['합계'] = display_stats.sum(numeric_only=True)
                total_cpa = display_stats.loc['합계', 'Cost'] / display_stats.loc['합계', 'Total_Cnt'] if display_stats.loc['합계', 'Total_Cnt'] > 0 else 0
                display_stats.loc['합계', 'CPA'] = total_cpa
                
                display_stats = display_stats[['Total_Cnt', 'Prod_Cnt', 'Bojang_Cnt', 'Cost', 'CPA']]
                display_stats.columns = ['토탈', '상품', '보장분석', '비용', 'CPA']
                display_stats.index.name = '매체'
                
                stats_body = display_stats.drop('합계').sort_values('토탈', ascending=False)
                stats_total = display_stats.loc[['합계']]
                final_table = pd.concat([stats_body, stats_total])
                
                st.dataframe(final_table.style.format("{:,.0f}"), use_container_width=True)
            else:
                st.info("데이터가 없습니다.")

    with tab1:
        st.subheader("📋 오전 목표 수립")
        st.line_chart(pd.DataFrame({'목표 흐름': acc_res}, index=hours))
        report_morning = f"""금일 DA+제휴파트 예상마감 공유드립니다.

[17시 기준]
총 자원 : {da_target_17:,}건 ({active_member}명, {da_per_17:.1f}건 배정 기준)
ㄴ 보장분석 : {int(da_target_17*target_ratio_ba):,}건
ㄴ 상품 : {int(da_target_17*(1-target_ratio_ba)):,}건

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
ㄴ 보장분석 : {int(tom_base_total * target_ratio_ba):,}건
ㄴ 상품자원 : {int(tom_base_total * (1-target_ratio_ba)):,}건

* 영업가족 {tom_member}명 기준 인당 {4.4 if not tom_dawn_ad else 5.0}건 이상 확보할 수 있도록 운영 예정입니다."""
        st.text_area("복사 텍스트 (퇴근):", report_tomorrow, height=250)

# -----------------------------------------------------------
# MAIN
# -----------------------------------------------------------
def main():
    st.sidebar.title("⚙️ 시스템 버전")
    version = st.sidebar.selectbox("선택", ["V18.35 (UI 업데이트)", "V6.6 (Legacy)"])
    if version == "V18.35 (UI 업데이트)": run_v18_35_master()
    else: st.warning("레거시 모드는 제외되었습니다.")

if __name__ == "__main__":
    main()
