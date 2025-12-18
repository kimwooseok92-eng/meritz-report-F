import streamlit as st
import datetime

# ==========================================
# 1. 핵심 로직 클래스 (검증 완료된 버전)
# ==========================================
class DailyReportSimulator:
    def __init__(self, date_str, active_agents, is_system_issue, has_dawn_ad_tmrw):
        self.date = date_str
        self.active_agents = active_agents
        self.is_system_issue = is_system_issue
        self.has_dawn_ad_tmrw = has_dawn_ad_tmrw
        
        # 12월 이슈 반영 계수: 정상 8.8 / 오류시 7.4
        self.target_rate = 7.4 if is_system_issue else 8.8
        self.total_target = int(active_agents * self.target_rate)
        
        # 목표 세부 자원 (보장 6 : 상품 4 비중)
        self.guarantee_target = int(self.total_target * 0.60)
        self.product_target = self.total_target - self.guarantee_target
        
        # 전문팀 목표 (활동인원의 약 16%, 효율 2.5배)
        self.special_target = int((self.active_agents * 0.16) * (self.target_rate * 2.5))

    def get_0930_report(self):
        report = []
        report.append("="*30)
        report.append(f"📢 [{self.date}] 오전 09:30 보고 초안")
        report.append("="*30)
        report.append(f"안녕하세요. {self.date} 활동인원 및 캠페인별 목표 공유 드립니다.\n")
        report.append(f"1) 활동인원 : {self.active_agents}명")
        report.append("2) 목표자원")
        report.append(f"- 상품 : {self.product_target}건")
        report.append(f"- 보장분석 : {self.guarantee_target}건")
        report.append(f"- 보장분석 전문 : {self.special_target}건")
        report.append(f"* 광고 이외 (ARS, 마이데이터) : 150건 (예상)")
        
        if self.is_system_issue:
            report.append("\n🚨 [특이사항] 금일 신정원 시스템 불안정이 예상되어 목표를 보수적으로 조정하였습니다.")
            report.append("오전 10~12시 사이 배정 지연 발생 여부 모니터링하겠습니다.")
        return "\n".join(report)

    def get_1400_report(self, current_total):
        # 14시 예측 로직: 14시 실적 * 1.35
        predicted_final = int(current_total * 1.35)
        per_person_current = round(current_total / self.active_agents, 1)
        per_person_final = round(predicted_final / self.active_agents, 1)

        report = []
        report.append("="*30)
        report.append(f"🔥 [{self.date}] 오후 14:00 현황 보고")
        report.append("="*30)
        report.append("DA파트 금일 14시간 현황 전달드립니다.\n")
        report.append(f"금일 목표(18시 기준) : 인당배분 {round(self.total_target/self.active_agents, 1)}건 / 총 {self.total_target}건")
        report.append(f"현황(14시) : 인당배분 {per_person_current}건 / 총 {current_total}건")
        report.append(f"예상 마감(18시 기준) : 인당배분 {per_person_final}건 / 총 {predicted_final}건")
        report.append(f"ㄴ 보장분석 : {int(predicted_final * 0.85)}건, 상품 {int(predicted_final * 0.15)}건\n")
        
        if predicted_final >= self.total_target:
            report.append("* 오전 목표 달성 무난할 것으로 예상되어, DA 배너 소폭 효율화(Save) 운영 중입니다.")
        else:
            diff = self.total_target - predicted_final
            report.append(f"* 목표 대비 약 {diff}건 부족 예상되어, 남은 시간 상품자원/보장분석 Push 운영하겠습니다.")
        return "\n".join(report)

    def get_1600_report(self, current_total):
        # 16시 예측 로직: 현재 + 210건(Last Spurt)
        last_spurt = 210
        expected_final = current_total + last_spurt
        
        report = []
        report.append("="*30)
        report.append(f"⚠️ [{self.date}] 오후 16:00 현황 보고")
        report.append("="*30)
        report.append("DA파트 금일 16시간 현황 전달드립니다.\n")
        report.append(f"금일 목표(18시 기준) : 총 {self.total_target}건")
        report.append(f"16시 현황 : 총 {current_total}건")
        report.append(f"\n16시 ~ 18시 30분 예상 건수")
        report.append(f"ㄴ 보장분석 {int(last_spurt * 0.9)}건")
        report.append(f"ㄴ 상품 {int(last_spurt * 0.1)}건")
        
        if expected_final < self.total_target:
            report.append(f"\n* 마감 전까지 최대한 자원 확보하겠습니다. (예상 부족분: {self.total_target - expected_final}건)")
        return "\n".join(report)

    def get_1800_report(self):
        # 명일 예측 로직: 기본 1100 + 고정광고 300
        base_volume = 1100
        ad_booster = 300 if self.has_dawn_ad_tmrw else 0
        next_day_total = base_volume + ad_booster
        
        next_guar = int(next_day_total * 0.88)
        next_prod = next_day_total - next_guar
        
        report = []
        report.append("="*30)
        report.append(f"🌙 [{self.date}] 오후 18:00 보고 양식")
        report.append("="*30)
        report.append(f"DA+제휴 명일 오전 9시 예상 자원 공유드립니다.\n")
        report.append(f"- 9시 예상 시작 자원 : {next_day_total}건")
        report.append(f"ㄴ 보장분석 : {next_guar}건")
        report.append(f"ㄴ 상품자원 : {next_prod}건\n")
        
        if self.has_dawn_ad_tmrw:
            report.append("* 명일 새벽 고정광고(CPT/풀뷰) 집행 예정으로 자원 추가 확보 예상됩니다.")
        else:
            report.append(f"* 영업가족 {self.active_agents}명 기준 인당 {round(next_day_total/self.active_agents/8, 1)}건 이상 확보할 수 있도록 운영 예정입니다.")
        return "\n".join(report)

# ==========================================
# 2. Streamlit UI 구성
# ==========================================
st.set_page_config(page_title="메리츠화재 보고 자동화", page_icon="📊")

st.title("📊 메리츠화재 통합 일일 보고 시뮬레이터")
st.markdown("---")

# 사이드바: 기본 설정
with st.sidebar:
    st.header("⚙️ 기본 설정 (Daily Setting)")
    
    # 날짜 선택 (기본값: 오늘)
    report_date = st.date_input("보고 날짜", datetime.date.today())
    date_str = report_date.strftime("%m월 %d일")
    
    # 활동 인원 입력
    active_agents = st.number_input("금일 활동 인원 (명)", min_value=100, max_value=500, value=350)
    
    st.markdown("---")
    st.subheader("🚨 이슈 및 변수 체크")
    # 신정원 오류 여부 체크
    is_system_issue = st.checkbox("신정원 시스템 오류 발생 (오전)", value=True, help="체크 시 목표 수량을 보수적으로(인당 7.4건) 계산합니다.")
    # 명일 새벽 광고 유무 체크
    has_dawn_ad = st.checkbox("내일 새벽 고정광고(CPT) 있음", value=False, help="체크 시 명일 예상 자원에 +300건을 가산합니다.")

# 메인 화면: 탭 구성
tab1, tab2, tab3, tab4 = st.tabs(["🌅 09:30 목표수립", "🔥 14:00 중간점검", "⚠️ 16:00 마감임박", "🌙 18:00 익일예상"])

# 시뮬레이터 인스턴스 생성
simulator = DailyReportSimulator(date_str, active_agents, is_system_issue, has_dawn_ad)

# 탭 1: 오전 보고
with tab1:
    st.subheader("🌅 오전 09:30 목표 공유")
    if st.button("보고 문구 생성", key="btn_0930"):
        result = simulator.get_0930_report()
        st.code(result, language="text")
        st.success(f"설정된 목표: 총 {simulator.total_target}건 (인당 {round(simulator.total_target/active_agents, 1)}건)")

# 탭 2: 14시 보고
with tab2:
    st.subheader("🔥 오후 14:00 실시간 현황")
    st.info("담당자에게 전달받은 '14시 기준 총 자원 수'를 입력하세요.")
    current_14 = st.number_input("14시 기준 총 확보량", min_value=0, value=1600, step=10)
    
    if st.button("보고 문구 생성", key="btn_1400"):
        result = simulator.get_1400_report(current_14)
        st.code(result, language="text")

# 탭 3: 16시 보고
with tab3:
    st.subheader("⚠️ 오후 16:00 마감 임박 현황")
    st.info("담당자에게 전달받은 '16시 기준 총 자원 수'를 입력하세요.")
    current_16 = st.number_input("16시 기준 총 확보량", min_value=0, value=2100, step=10)
    
    if st.button("보고 문구 생성", key="btn_1600"):
        result = simulator.get_1600_report(current_16)
        st.code(result, language="text")

# 탭 4: 18시 보고
with tab4:
    st.subheader("🌙 오후 18:00 익일 자원 공유")
    if st.button("보고 문구 생성", key="btn_1800"):
        result = simulator.get_1800_report()
        st.code(result, language="text")
