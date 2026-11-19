import streamlit as st
import time
import hmac
import os
from datetime import datetime, timezone
from uuid import uuid4

import psycopg
from streamlit.errors import StreamlitSecretNotFoundError

from product_quiz import CATALOG_URL, PRODUCTS, QUESTION_BANK_VERSION, QUESTION_SETS as PRODUCT_QUESTION_SETS
from result_store import DatabaseSettings, QuizSubmission, TEST_CONSENT_VERSION, save_submission


def load_database_settings() -> DatabaseSettings:
    """Load DB settings from Streamlit secrets or Hugging Face Space env vars."""
    try:
        postgres = st.secrets["postgres"]
        return {
            "host": str(postgres["host"]),
            "port": int(postgres["port"]),
            "dbname": str(postgres["dbname"]),
            "user": str(postgres["user"]),
            "password": str(postgres["password"]),
            "sslmode": str(postgres.get("sslmode", "require")),
        }
    except (KeyError, StreamlitSecretNotFoundError, TypeError, ValueError):
        pass

    required = {
        "host": os.environ.get("POSTGRES_HOST"),
        "dbname": os.environ.get("POSTGRES_DB", "postgres"),
        "user": os.environ.get("POSTGRES_USER"),
        "password": os.environ.get("POSTGRES_PASSWORD"),
        "sslmode": os.environ.get("POSTGRES_SSLMODE", "require"),
    }
    missing = [key for key, value in required.items() if key != "sslmode" and not value]
    if missing:
        raise StreamlitSecretNotFoundError(
            f"Missing database settings: {', '.join(missing)}"
        )
    return {
        "host": required["host"],
        "port": int(os.environ.get("POSTGRES_PORT", "5432")),
        "dbname": required["dbname"],
        "user": required["user"],
        "password": required["password"],
        "sslmode": required["sslmode"],
    }


# ==========================================
# 1. 페이지 기본 설정
# ==========================================
st.set_page_config(
    page_title="바이엘 제품 학습 미션",
    page_icon="🎮",
    layout="centered"
)

preview_password = os.environ.get("QUIZ_PREVIEW_PASSWORD")
if preview_password is not None:
    if not preview_password:
        st.error("시연 접속 비밀번호가 설정되지 않았습니다. 관리자에게 문의해 주세요.")
        st.stop()
    if not st.session_state.get("preview_authenticated", False):
        st.title("제품 퀴즈 시연")
        st.caption("전달받은 시연 비밀번호를 입력해 주세요. 가상 이름과 소속으로만 테스트해 주세요.")
        with st.form("preview_login", clear_on_submit=True):
            entered_password = st.text_input("시연 비밀번호", type="password")
            enter_preview = st.form_submit_button("입장하기", key="enter_preview")
        if enter_preview:
            if hmac.compare_digest(entered_password.encode("utf-8"), preview_password.encode("utf-8")):
                st.session_state["preview_authenticated"] = True
                st.rerun()
            st.error("시연 비밀번호가 일치하지 않습니다.")
        st.stop()

# ==========================================
# 2. 상수 및 데이터 구조 정의
# ==========================================
QUESTIONS = [
    {
        "question_id": "SIVANTO_001",
        "topic": "Mode of Action",
        "difficulty": "Basic",
        "mission_text": (
            "Sivanto가 표적 해충의 신경계에 접근했습니다. "
            "여러 수용체 신호 중 Sivanto가 작용하는 올바른 신호를 포착해 주세요."
        ),
        "question_text": "Sivanto는 표적 해충의 어떤 수용체에 작용할까요?",
        "options": {
            "A": "Nicotinic Acetylcholine Receptor (nAChR)",
            "B": "GABAA and GABAC Receptors",
            "C": "Serotonin Type 3 (5-HT3 Receptors)",
            "D": "Glycine Receptors"
        },
        "correct_option": "A",
        "hint_html": """
            💡 <b>힌트 신호 주파수</b><br>
            이 수용체는 신경전달물질인 <b>아세틸콜린(Acetylcholine)</b>에 의해 활성화되는 이온통로형 수용체입니다. 
            화학 작용군 분류(IRAC) 중 <b>Group 4D (Butenolides)</b>에 속합니다.
        """,
        "correct_feedback_html": """
            <b>📖 학습 포인트 (Mode of Action)</b><br>
            Sivanto의 유효성분 flupyradifurone은 해충의 <b>nicotinic acetylcholine receptor (nAChR)</b>에 작용하며, 
            IRAC Group 4D, Butenolides로 분류됩니다. 이 작용 기작은 유익한 곤충에 해를 최소화하면서 표적 흡즙해충을 효과적으로 방제하는 데 최적화되어 있습니다.
        """,
        "wrong_feedback_text": (
            "Sivanto의 타겟 수용체는 다른 작용 메커니즘을 가집니다. "
            "기회는 총 2회 제공됩니다. 다시 한 번 집중해서 신호를 맞춰보세요!"
        )
    },
    {
        "question_id": "SIVANTO_002",
        "topic": "Target Pest Selectivity",
        "difficulty": "Basic",
        "mission_text": (
            "Sivanto Prime의 신호가 여러 곤충 개체들 사이에서 교차 수신되고 있습니다. "
            "실제로 방제 효과가 나타나는 표적 신호만 정확히 포착해 주세요."
        ),
        "question_text": "Sivanto Prime은 다음 중 어떤 대상에 높은 방제 효과를 보일까요?",
        "options": {
            "A": "Apis mellifera (서양꿀벌)",
            "B": "Chrysoperla carnea (풀잠자리)",
            "C": "Coccinellidae septempunctata (칠성무당벌레)",
            "D": "Empoasca devastans (목화잎매미충)"
        },
        "correct_option": "D",
        "hint_html": """
            💡 <b>힌트 신호 주파수</b><br>
            Sivanto Prime은 <b>흡즙성 해충(sap-feeding pest)</b>에 선택적으로 작용하도록 설계되었습니다. 
            꿀벌, 풀잠자리, 무당벌레는 모두 유익 곤충(Beneficial insect)으로 분류됩니다.
        """,
        "correct_feedback_html": """
            <b>📖 학습 포인트 (Target Pest Selectivity)</b><br>
            <b>Empoasca devastans(목화잎매미충)</b>는 작물의 즙액을 빨아먹는 대표적인 흡즙해충으로, Sivanto Prime의 핵심 방제 대상입니다. 
            반면 Apis mellifera, Chrysoperla carnea, Coccinellidae septempunctata는 모두 유익 곤충으로, Sivanto는 이들에게 미치는 영향을 최소화하도록 설계되었습니다.
        """,
        "wrong_feedback_text": (
            "선택하신 종은 Sivanto Prime의 방제 대상이 아닌 유익 곤충일 수 있습니다. "
            "기회는 총 2회 제공됩니다. 흡즙해충(sap-feeding pest)에 집중해서 다시 신호를 맞춰보세요!"
        )
    },
    {
        "question_id": "SIVANTO_003",
        "topic": "Pest Stress & Yield Loss",
        "difficulty": "Basic",
        "mission_text": (
            "해충 경보 신호가 지연되고 있습니다. 단 하루의 방제 지연이 작물에 어떤 영향을 미치는지 "
            "신호를 분석해 정확한 수치를 포착해 주세요."
        ),
        "question_text": (
            "흡즙해충 및 환경 스트레스와 같은 어떤 유형이든 하루의 스트레스는 수확량 손실을 "
            "얼마나 유발할까요?"
        ),
        "options": {
            "A": "5 KG per acre",
            "B": "10 KG per acre",
            "C": "12 KG per acre",
            "D": "8 KG per acre"
        },
        "correct_option": "B",
        "hint_html": """
            💡 <b>힌트 신호 주파수</b><br>
            흡즙해충으로 인한 스트레스는 누적될수록 손실이 커지며, 방제 결정을 하루만 늦춰도 
            작물의 회복 불가능한 손실로 이어질 수 있습니다. 두 자릿수 초반대의 수치를 떠올려 보세요.
        """,
        "correct_feedback_html": """
            <b>📖 학습 포인트 (Pest Stress & Yield Loss)</b><br>
            흡즙해충이나 환경적 스트레스 등 어떤 형태든 <b>단 하루의 스트레스</b>는 
            <b>에이커당 10 KG</b>의 수확량 손실로 이어질 수 있습니다. 
            따라서 초기 방제 타이밍을 놓치지 않는 것이 Sivanto 방제 전략의 핵심입니다.
        """,
        "wrong_feedback_text": (
            "정확한 손실 수치가 아닙니다. 하루의 지연이 생각보다 큰 영향을 미친다는 점을 떠올리며 "
            "기회는 총 2회 제공됩니다. 다시 한 번 집중해서 신호를 맞춰보세요!"
        )
    },
    {
        "question_id": "SIVANTO_004",
        "topic": "Discovery Origin",
        "difficulty": "Basic",
        "mission_text": (
            "Sivanto의 기원 신호를 추적합니다. flupyradifurone을 탄생시킨 자연계의 원형 물질을 "
            "정확히 포착해 주세요."
        ),
        "question_text": "Flupyradifurone의 발견으로 이어진 천연물(natural product)은 무엇일까요?",
        "options": {
            "A": "Didehydrostemofoline",
            "B": "Stemofoline",
            "C": "Dehydrostemofoline",
            "D": "Ocystemofoline"
        },
        "correct_option": "B",
        "hint_html": """
            💡 <b>힌트 신호 주파수</b><br>
            <i>Stemona japonica</i> 식물에서 발견된 이 천연 살충 성분은 빠른 효과와 우수한 
            섭식 저해(antifeedant) 작용을 보였지만, 곤충의 nAChR에는 효율적으로 결합하지 못했습니다. 
            이 구조를 모티프로 flupyradifurone이 설계되었습니다.
        """,
        "correct_feedback_html": """
            <b>📖 학습 포인트 (Discovery Origin)</b><br>
            Flupyradifurone은 <i>Stemona japonica</i>에서 유래한 천연 살충 성분 
            <b>Stemofoline</b>과 구조적으로 연관되어 있습니다. Stemofoline은 속효성과 
            섭식 저해 효과는 뛰어났지만 곤충 nAChR 결합력이 낮았고, 이를 개선하여 
            flupyradifurone(Sivanto)이 개발되었습니다.
        """,
        "wrong_feedback_text": (
            "정확한 천연물 명칭이 아닙니다. Stemona 속 식물에서 유래한 성분이라는 점을 떠올리며 "
            "기회는 총 2회 제공됩니다. 다시 한 번 집중해서 신호를 맞춰보세요!"
        )
    },
    {
        "question_id": "SIVANTO_005",
        "topic": "Mode of Action",
        "difficulty": "Basic",
        "mission_text": (
            "Sivanto가 해충 체내 깊숙이 침투했습니다. 치명적인 최종 신호가 어느 시스템을 "
            "마비시키는지 추적해 주세요."
        ),
        "question_text": "Sivanto는 어떤 시스템에 작용하여 해충을 치사시킬까요?",
        "options": {
            "A": "Insect Excretory System",
            "B": "Insect Circulatory System",
            "C": "Endocrine System",
            "D": "Insect Nervous System"
        },
        "correct_option": "D",
        "hint_html": """
            💡 <b>힌트 신호 주파수</b><br>
            Sivanto의 유효성분은 nicotinic acetylcholine receptor(nAChR)에 작용하는 agonist입니다. 
            이 수용체는 신경 신호를 전달하는 시냅스에 존재합니다.
        """,
        "correct_feedback_html": """
            <b>📖 학습 포인트 (Mode of Action)</b><br>
            Sivanto는 <b>곤충의 신경계(Insect Nervous System)</b>에 작용합니다. 
            nAChR에 결합해 신경 세포막을 지속적으로 탈분극시켜 신경 전달을 마비시키고, 
            결국 해충을 치사에 이르게 합니다.
        """,
        "wrong_feedback_text": (
            "정확한 작용 시스템이 아닙니다. Sivanto의 작용점이 nAChR이라는 점을 떠올리며 "
            "기회는 총 2회 제공됩니다. 다시 한 번 집중해서 신호를 맞춰보세요!"
        )
    }
]

LEGACY_QUESTIONS = QUESTIONS
QUESTION_SETS = {**PRODUCT_QUESTION_SETS, "시반토 기존 미션": LEGACY_QUESTIONS}
st.session_state.setdefault("active_product", next(iter(QUESTION_SETS)))
QUESTIONS = QUESTION_SETS[st.session_state.active_product]
TOTAL_QUESTIONS = len(QUESTIONS)
st.session_state.setdefault("participant", None)


def new_game_data(q_index):
    """주어진 문항 인덱스에 대한 빈 결과 기록 구조를 생성합니다."""
    q = QUESTIONS[q_index]
    return {
        "question_id": q["question_id"],
        "product": st.session_state.active_product,
        "participant_name": st.session_state.participant["name"],
        "participant_affiliation": st.session_state.participant["affiliation"],
        "participant_consent": st.session_state.participant["consent_given"],
        "source_url": q.get("source_url"),
        "source_label": q.get("source_label"),
        "selected_option": None,
        "is_correct": False,
        "attempt_count": 0,
        "hint_used": False,
        "response_time_seconds": 0.0,
        "confidence_level": None,
        "topic": q["topic"],
        "difficulty": q["difficulty"],
        "earned_points": 0
    }


# ==========================================
# 3. Streamlit 세션 상태(Session State) 초기화
# ==========================================
if "step" not in st.session_state:
    st.session_state.step = "REGISTER"  # REGISTER -> START -> MISSION -> RESULT

if (st.session_state.participant is None
        or st.session_state.participant.get("consent_version") != TEST_CONSENT_VERSION):
    st.session_state.step = "REGISTER"

if "current_q" not in st.session_state:
    st.session_state.current_q = 0

if "start_time" not in st.session_state:
    st.session_state.start_time = None

if "end_time" not in st.session_state:
    st.session_state.end_time = None

# 현재 진행 중인 문항의 결과 기록
if "game_data" not in st.session_state and st.session_state.step == "MISSION":
    st.session_state.game_data = new_game_data(st.session_state.current_q)

# 완료된 문항들의 결과 기록 누적 리스트
if "results" not in st.session_state:
    st.session_state.results = []

# 정답 제출 및 중복 점수 획득 방지 플래그
if "submitted" not in st.session_state:
    st.session_state.submitted = False

if "points_allocated" not in st.session_state:
    st.session_state.points_allocated = False


# ==========================================
# 4. 헬퍼 함수 및 로직 정의
# ==========================================
def clear_game_state():
    st.session_state.step = "START"
    st.session_state.current_q = 0
    st.session_state.start_time = None
    st.session_state.end_time = None
    st.session_state.submitted = False
    st.session_state.points_allocated = False
    st.session_state.results = []
    st.session_state.pop("game_data", None)
    for key in ("submission_id", "quiz_started_at", "quiz_completed_at",
                "save_attempted", "save_error", "result_saved"):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith(("radio_", "confidence_", "hint_")):
            del st.session_state[key]


def select_product():
    st.session_state.active_product = st.session_state.product_picker
    clear_game_state()


def reset_game():
    """상태를 초기화하고 첫 화면으로 리다이렉트합니다."""
    clear_game_state()
    st.rerun()


if st.session_state.get("question_bank_version") != QUESTION_BANK_VERSION:
    st.session_state.question_bank_version = QUESTION_BANK_VERSION
    reset_game()


# ==========================================
# 5. 화면 레이아웃 구성
# ==========================================

# ------------------------------------------
# [화면 1] 응시자 등록 (REGISTER)
# ------------------------------------------
if st.session_state.step == "REGISTER":
    st.badge("PLAYER PROFILE · 응시자 등록", icon=":material/person:", color="green")
    st.title(":green[플레이어 등록]")
    st.write("이름과 소속을 입력하면 학습 결과에서 누가 응시했는지 확인할 수 있습니다.")
    st.warning("테스트 모드입니다. 실명·실제 소속 대신 가명·가상 소속만 입력해 주세요.")
    with st.form("participant_form"):
        participant_name = st.text_input(
            "이름", placeholder="예: 테스트 참가자 01", key="participant_name_input"
        )
        participant_affiliation = st.text_input(
            "소속(예시:경북 북부팀)", placeholder="예: 가상 테스트팀", key="participant_affiliation_input"
        )
        participant_consent = st.checkbox(
            "가명·가상 소속과 퀴즈 결과를 테스트용 클라우드에 저장하는 데 동의합니다.",
            key="participant_consent_input",
        )
        if st.form_submit_button("등록하고 시작하기", icon=":material/arrow_forward:",
                                 type="primary", key="register_participant", width="stretch"):
            if participant_name is None or not participant_name.strip():
                st.error("이름을 입력해 주세요.")
            elif participant_affiliation is None or not participant_affiliation.strip():
                st.error("소속을 입력해 주세요.")
            elif not participant_consent:
                st.error("이름·소속 사용에 동의한 후 시작할 수 있습니다.")
            else:
                st.session_state.participant = {
                    "name": participant_name.strip(),
                    "affiliation": participant_affiliation.strip(),
                    "consent_given": True,
                    "consent_at": datetime.now(timezone.utc),
                    "consent_version": TEST_CONSENT_VERSION,
                }
                clear_game_state()
                st.rerun()

# ------------------------------------------
# [화면 2] 시작 화면 (START)
# ------------------------------------------
elif st.session_state.step == "START":
    st.badge("FIELD QUEST · 미션 로비", icon=":material/sports_esports:", color="green")
    st.title("🚀 :green[Technical Level-up!]")
    st.write("바이엘 제품 학습 미션")
    st.caption("제품을 선택하고, 스테이지를 하나씩 돌파하며 나만의 학습 포인트를 모아 보세요.")
    st.badge("TEST MODE · 가명 데이터만 사용", color="orange")
    st.text(f"응시자: {st.session_state.participant['name']} · 소속: {st.session_state.participant['affiliation']}")
    if st.button("응시자 변경", icon=":material/manage_accounts:",
                 key="change_participant", type="tertiary"):
        st.session_state.participant_name_input = st.session_state.participant["name"]
        st.session_state.participant_affiliation_input = st.session_state.participant["affiliation"]
        st.session_state.participant_consent_input = False
        st.session_state.participant = None
        clear_game_state()
        st.session_state.step = "REGISTER"
        st.rerun()
    st.session_state.setdefault("product_picker", st.session_state.active_product)
    with st.container(border=True):
        st.subheader("제품 선택", anchor=False)
        st.selectbox(
            "학습 제품",
            options=list(QUESTION_SETS),
            key="product_picker",
            on_change=select_product,
        )
        product = PRODUCTS.get(st.session_state.active_product)
        if product:
            st.badge(
                product["category"],
                color="yellow" if product["category"] == "제초제"
                else "violet" if product["category"] == "살균제" else "blue",
            )
        else:
            st.warning("기존 제공 자료로 만든 시반토 5문항입니다. 수치·안전성 설명은 일반화하지 마세요.")
        stage_col, reward_col = st.columns(2)
        with stage_col:
            st.metric("도전 스테이지", f"{TOTAL_QUESTIONS}개", icon=":material/flag:")
        with reward_col:
            st.metric("최대 획득 포인트", f"{TOTAL_QUESTIONS * 150:,} P", icon=":material/stars:")
        if st.button("퀘스트 시작하기", icon=":material/play_arrow:", type="primary",
                     key="start_mission", width="stretch"):
            st.session_state.submission_id = uuid4()
            st.session_state.quiz_started_at = datetime.now(timezone.utc)
            st.session_state.start_time = time.time()
            st.session_state.step = "MISSION"
            st.rerun()

    with st.expander("플레이 방법과 보상", icon=":material/help:"):
        st.write("문항마다 최대 2회 도전할 수 있으며, 시간제한은 없습니다.")
        st.write("정답 150 P · 힌트를 사용한 정답 120 P · 오답 참여 50 P")
        st.caption("포인트는 문항별 최종 결과를 기준으로 반영됩니다. 재도전해도 중복 적립되지 않습니다.")
    with st.expander("제품 정보와 학습 안내", icon=":material/info:"):
        if product:
            st.caption(product["launch_note"])
            if product["launch_source_url"]:
                st.markdown(f"[출시연도 근거]({product['launch_source_url']})")
        st.markdown(f"[팜한농 바이엘 제품 목록]({CATALOG_URL})")
        st.write("가명·가상 소속과 학습 결과는 테스트용 결과 취합에 사용됩니다.")
        st.caption("완료된 퀴즈 결과는 일본 도쿄의 Supabase DB에 저장됩니다. 실명·실제 소속은 입력하지 마세요.")
        st.write("학습 결과는 제품 사용 자격이나 전문 역량을 판정하지 않습니다.")
    st.caption("실제 사용은 최신 라벨의 등록 작물·방제 대상·희석배수·사용횟수·수확 전 사용기한과 안전수칙을 따르세요.")

# ------------------------------------------
# [화면 3] 미션 수행 및 제출 피드백 화면 (MISSION)
# ------------------------------------------
elif st.session_state.step == "MISSION":
    q = QUESTIONS[st.session_state.current_q]
    is_last_question = (st.session_state.current_q == TOTAL_QUESTIONS - 1)

    st.badge("FIELD QUEST · 플레이 중", icon=":material/sports_esports:", color="green")
    st.caption(st.session_state.active_product)
    hud = st.container()
    st.progress(
        len(st.session_state.results) / TOTAL_QUESTIONS,
        text=f"스테이지 {st.session_state.current_q + 1:02} / {TOTAL_QUESTIONS:02}",
    )
    st.markdown(" ".join(
        f":green-badge[{number:02} 완료]" if number <= len(st.session_state.results)
        else f":blue-badge[{number:02} 도전 중]" if number == st.session_state.current_q + 1
        else f":gray-badge[{number:02} 대기]"
        for number in range(1, TOTAL_QUESTIONS + 1)
    ))

    with st.container(border=True):
        st.badge(f"STAGE {st.session_state.current_q + 1:02} · {q['topic']}",
                 icon=":material/target:", color="blue")
        st.subheader(q["question_text"], anchor=False)
        st.caption(q["mission_text"])
        option_list = [f"{k}. {v}" for k, v in q["options"].items()]
        selected_display = st.radio(
            "정답을 선택하세요:",
            options=option_list,
            index=0,
            disabled=st.session_state.submitted,
            key=f"radio_{q['question_id']}"
        )

    # 선택된 Key 추출 ('A', 'B', 'C', 'D')
    selected_key = selected_display.split(".")[0]
    st.session_state.game_data["selected_option"] = selected_key
    
    confidence_options = [
        "1. 감으로 선택했어요",
        "2. 어느 정도 알고 있어요",
        "3. 다른 사람에게 설명할 수 있어요"
    ]
    with st.container(border=True):
        selected_confidence = st.selectbox(
            "자신감 체크",
            options=confidence_options,
            disabled=st.session_state.submitted,
            key=f"confidence_{q['question_id']}"
        )
        st.session_state.game_data["confidence_level"] = selected_confidence
        if not st.session_state.submitted:
            if st.checkbox("힌트 열기", value=st.session_state.game_data["hint_used"], key=f"hint_{q['question_id']}"):
                st.session_state.game_data["hint_used"] = True
                st.badge("HINT UNLOCKED", icon=":material/lightbulb:", color="orange")
                st.markdown(q["hint_html"], unsafe_allow_html=True)
                st.caption("힌트를 사용한 문항의 정답 보상은 120 P입니다.")
            
    # ------------------------------------------
    # 제출 로직 및 결과 피드백
    # ------------------------------------------
    if not st.session_state.submitted:
        if st.button("정답 확인하기", icon=":material/bolt:", type="primary",
                     key="submit_answer", width="stretch"):
            # 시간 기록 완료
            st.session_state.end_time = time.time()
            st.session_state.game_data["response_time_seconds"] = round(
                st.session_state.end_time - st.session_state.start_time, 2
            )
            
            # 시도 횟수 증가 및 상태 업데이트
            st.session_state.game_data["attempt_count"] += 1
            st.session_state.submitted = True
            st.rerun()
            
    else:
        # 정답 여부 판단
        is_correct = (selected_key == q["correct_option"])
        st.session_state.game_data["is_correct"] = is_correct
        
        # 점수 계산 아키텍처 (중복 계산 방지)
        if not st.session_state.points_allocated:
            points = 0
            if is_correct:
                # 정답: 100점 / 힌트 사용 후 정답: 70점
                if st.session_state.game_data["hint_used"]:
                    points += 70
                else:
                    points += 100
                # 정답 설명까지 도달 시 기본 학습 보너스 50점 가산
                points += 50
            else:
                # 오답이어도 학습 독려 차원의 참여/학습 포인트 50점 제공
                points += 50
                
            st.session_state.game_data["earned_points"] = points
            st.session_state.points_allocated = True
            
        if is_correct:
            st.success(f"STAGE CLEAR · 정답입니다! +{st.session_state.game_data['earned_points']} P",
                       icon=":material/check_circle:")
            with st.container(border=True):
                st.markdown(q["correct_feedback_html"], unsafe_allow_html=True)
        else:
            if st.session_state.game_data["attempt_count"] < 2:
                st.warning("아직 기회가 있어요! 한 번 더 도전해 보세요.", icon=":material/replay:")
            else:
                st.warning("이번에는 해설로 경험치를 쌓아 보세요. 참여 포인트 +50 P", icon=":material/menu_book:")
            st.info(q["wrong_feedback_text"])
            if st.session_state.game_data["attempt_count"] >= 2:
                st.markdown(f"**정답: {q['correct_option']}. {q['options'][q['correct_option']]}**")
                st.markdown(q["correct_feedback_html"], unsafe_allow_html=True)

        if is_correct or st.session_state.game_data["attempt_count"] >= 2:
            if q.get("source_label"):
                st.caption(f"문항 출처: {q['source_label']} · 확인일: {q['source_checked_on']}")
            elif q.get("source_url"):
                st.markdown(f"[제품 정보 출처]({q['source_url']}) · 확인일: {q['source_checked_on']}")
            
        with st.container(horizontal=True):
            if not is_correct and st.session_state.game_data["attempt_count"] < 2:
                if st.button("다시 도전하기", icon=":material/replay:",
                             key="retry_mission", width="stretch"):
                    st.session_state.submitted = False
                    st.session_state.points_allocated = False
                    st.rerun()
            next_label = "퀘스트 결과 보기" if is_last_question else "다음 스테이지"
            if st.button(next_label, icon=":material/arrow_forward:", type="primary",
                         key="next_mission", width="stretch"):
                # 현재 문항 결과를 누적 리스트에 저장
                st.session_state.results.append(dict(st.session_state.game_data))
                if is_last_question:
                    st.session_state.quiz_completed_at = datetime.now(timezone.utc)
                    st.session_state.step = "RESULT"
                else:
                    st.session_state.current_q += 1
                    st.session_state.submitted = False
                    st.session_state.points_allocated = False
                    st.session_state.game_data = new_game_data(st.session_state.current_q)
                    st.session_state.start_time = time.time()
                st.rerun()

    with hud:
        earned = sum(result["earned_points"] for result in st.session_state.results)
        if st.session_state.submitted:
            earned += st.session_state.game_data["earned_points"]
        score_col, chance_col = st.columns(2)
        with score_col:
            st.metric("획득 포인트", f"{earned:,} P", border=True, icon=":material/stars:")
        with chance_col:
            if st.session_state.submitted and st.session_state.game_data["is_correct"]:
                st.metric("스테이지 상태", "CLEAR", border=True, icon=":material/check_circle:")
            else:
                st.metric("남은 도전 기회", f"{2 - st.session_state.game_data['attempt_count']} / 2",
                          border=True, icon=":material/favorite:")

# ------------------------------------------
# [화면 4] 최종 결과 및 재시작 화면 (RESULT)
# ------------------------------------------
elif st.session_state.step == "RESULT":
    st.badge("QUEST COMPLETE", icon=":material/emoji_events:", color="green")
    st.title(":green[미션 완료!]")
    st.write(f"**{st.session_state.active_product}** 학습 결과")
    st.text(f"응시자: {st.session_state.participant['name']} · 소속: {st.session_state.participant['affiliation']}")
    st.caption("수고하셨습니다! 문항별 결과와 해설을 확인하며 학습한 내용을 정리해 보세요.")
    st.progress(1.0, text=f"{TOTAL_QUESTIONS} / {TOTAL_QUESTIONS} 스테이지 탐험 완료")
    
    total_points = sum(r["earned_points"] for r in st.session_state.results)
    correct_count = sum(1 for r in st.session_state.results if r["is_correct"])

    st.session_state.setdefault("result_saved", False)
    st.session_state.setdefault("save_error", None)
    if not st.session_state.result_saved and st.session_state.save_error is None:
        with st.spinner("테스트 결과를 클라우드에 저장하고 있습니다."):
            try:
                settings = load_database_settings()
                submission: QuizSubmission = {
                    "submission_id": st.session_state.submission_id,
                    "participant_name": st.session_state.participant["name"],
                    "participant_affiliation": st.session_state.participant["affiliation"],
                    "product": st.session_state.active_product,
                    "question_bank_version": QUESTION_BANK_VERSION,
                    "total_questions": TOTAL_QUESTIONS,
                    "correct_count": correct_count,
                    "total_points": total_points,
                    "answers": list(st.session_state.results),
                    "started_at": st.session_state.quiz_started_at,
                    "completed_at": st.session_state.quiz_completed_at,
                    "consent_at": st.session_state.participant["consent_at"],
                    "consent_version": st.session_state.participant["consent_version"],
                }
                save_submission(settings, submission)
            except (KeyError, StreamlitSecretNotFoundError):
                st.session_state.save_error = "연결 설정이 누락되었습니다. 운영자에게 문의해 주세요."
            except psycopg.Error as error:
                st.session_state.save_error = (
                    f"DB 연결 또는 저장에 실패했습니다. 잠시 후 다시 시도해 주세요. ({type(error).__name__})"
                )
            else:
                st.session_state.result_saved = True
                st.session_state.save_error = None

    if st.session_state.get("result_saved", False):
        st.success("테스트 결과가 클라우드에 저장되었습니다.", icon=":material/cloud_done:")
    else:
        st.error(st.session_state.save_error)
        st.caption("저장될 때까지 이 화면을 닫거나 새로고침하지 마세요. 현재 결과를 유지한 채 재시도할 수 있습니다.")
        if st.button("저장 다시 시도", icon=":material/cloud_upload:", key="retry_save"):
            st.session_state.save_error = None
            st.rerun()

    col_score1, col_score2 = st.columns(2)
    with col_score1:
        st.metric(label="맞힌 문제", value=f"{correct_count} / {TOTAL_QUESTIONS}",
                  border=True, icon=":material/task_alt:")
    with col_score2:
        st.metric(label="학습 포인트", value=f"{total_points:,} P",
                  border=True, icon=":material/stars:")

    st.subheader("문항별 돌아보기")
    for index, question in enumerate(QUESTIONS, start=1):
        result = st.session_state.results[index - 1]
        selected = result["selected_option"]
        status = ":green-badge[정답]" if result["is_correct"] else ":orange-badge[오답]"
        with st.container(border=True, key=f"result_{question['question_id']}"):
            st.markdown(f"**{index}. {question['topic']}** · {status}")
            st.write(f"선택한 답: {selected}. {question['options'][selected]}")
            st.caption(
                f"시도 {result['attempt_count']} / 2회 · "
                f"{'힌트 사용' if result['hint_used'] else '힌트 미사용'} · "
                f"풀이 {result['response_time_seconds']:.2f}초 · "
                f"{result['earned_points']} P"
            )
            with st.expander(f"{index}번 문제와 해설 보기"):
                st.write(question["question_text"])
                st.write(f"정답: {question['correct_option']}. {question['options'][question['correct_option']]}")
                st.markdown(question["correct_feedback_html"], unsafe_allow_html=True)
                if question.get("source_label"):
                    st.caption(f"문항 출처: {question['source_label']} · 확인일: {question['source_checked_on']}")
                elif question.get("source_url"):
                    st.markdown(f"[제품 정보 출처]({question['source_url']})")

    st.caption("학습 포인트는 참여를 격려하기 위한 기록이며, 인사 평가나 시험 성적으로 사용되지 않습니다.")
    
    # [화면 5] 다시 시작 버튼
    if st.button("다른 퀘스트 도전하기", icon=":material/sports_esports:", type="primary",
                 key="return_to_lobby", width="stretch",
                 disabled=not st.session_state.get("result_saved", False)):
        reset_game()
