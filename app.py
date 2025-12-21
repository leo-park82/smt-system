import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import hashlib
import base64
from fpdf import FPDF
import streamlit.components.v1 as components

# [추가] 구글 시트 연동 라이브러리
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe

# [안전 장치] 시각화 라이브러리(Altair) 로드 시도
try:
    import altair as alt
    HAS_ALTAIR = True
except Exception as e:
    HAS_ALTAIR = False
    print(f"Warning: 시각화 라이브러리(Altair) 로드 실패 - {e}")

# ------------------------------------------------------------------
# 1. 기본 설정 및 디자인
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT Dashboard (Cloud)", 
    page_icon="☁️",
    layout="wide",
    initial_sidebar_state="auto" 
)

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; color: #1e293b; }
    .stApp { background-color: #f8fafc; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    .smart-card {
        background: #ffffff; border-radius: 16px; padding: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); border: 1px solid #f1f5f9; height: 100%;
    }
    .dashboard-header {
        background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
        padding: 30px 40px; border-radius: 20px; color: white; margin-bottom: 30px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .kpi-value { font-size: 2.2rem; font-weight: 800; color: #0f172a; }
    .trend-up { color: #10b981; background: #ecfdf5; padding: 2px 8px; border-radius: 12px; font-size: 0.9rem; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# [핵심] Google Sheets 연결 설정
# ------------------------------------------------------------------
# 구글 시트 파일 이름 (구글 드라이브에 생성한 시트 이름과 일치해야 함)
GOOGLE_SHEET_NAME = "SMT_Database" 

# 시트 탭(Worksheet) 이름 정의
SHEET_RECORDS = "production_data"
SHEET_ITEMS = "item_codes"
SHEET_INVENTORY = "inventory_data"
SHEET_INV_HISTORY = "inventory_history"
SHEET_MAINTENANCE = "maintenance_data"
SHEET_EQUIPMENT = "equipment_list"

@st.cache_resource
def get_gs_connection():
    """Google Sheets API 연결 객체 생성 (캐싱 사용)"""
    try:
        # st.secrets에서 인증 정보 가져오기
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        
        # .streamlit/secrets.toml 파일에 [gcp_service_account] 섹션이 있어야 함
        creds_dict = dict(st.session_state.get('gcp_creds', st.secrets["gcp_service_account"]))
        credentials = Credentials.from_service_account_info(
            creds_dict,
            scopes=scopes,
        )
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"⚠️ Google Cloud 연결 실패: {e}")
        st.info("Tip: .streamlit/secrets.toml 파일에 서비스 계정 키가 올바르게 설정되었는지 확인하세요.")
        return None

def get_worksheet(sheet_name, worksheet_name, create_if_missing=False, columns=None):
    """특정 워크시트를 가져오거나 없으면 생성"""
    client = get_gs_connection()
    if not client: return None
    
    try:
        sh = client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        st.error(f"⚠️ 구글 시트 '{sheet_name}'를 찾을 수 없습니다. 구글 드라이브에서 시트를 생성하고 서비스 계정에 공유해주세요.")
        return None

    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        if create_if_missing:
            ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)
            if columns:
                ws.append_row(columns) # 헤더 추가
        else:
            return None
    return ws

# ------------------------------------------------------------------
# 2. 로그인 및 보안 로직
# ------------------------------------------------------------------
def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

# (데모용) 사용자 정보는 코드 내에 하드코딩 (보안 강화 시 이것도 시트로 뺄 수 있음)
USERS = {
    "park": {"name": "Park", "password_hash": make_hash("1083"), "role": "admin", "desc": "System Administrator"},
    "suk": {"name": "Suk", "password_hash": make_hash("1734"), "role": "editor", "desc": "Production Manager"},
    "kim": {"name": "Kim", "password_hash": make_hash("8943"), "role": "editor", "desc": "Equipment Engineer"}
}

def check_password():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    
    if st.session_state.logged_in: return True

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br><h1 style='text-align:center;'>🏭 SMT Cloud System</h1>", unsafe_allow_html=True)
        with st.form(key="login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", type="primary", use_container_width=True)
            
            if submitted:
                if username in USERS and make_hash(password) == USERS[username]["password_hash"]:
                    st.session_state.logged_in = True
                    st.session_state.user_info = USERS[username]
                    st.session_state.user_info["id"] = username
                    st.rerun()
                else:
                    st.error("아이디 또는 비밀번호가 잘못되었습니다.")
            
            if st.form_submit_button("Guest Access (Viewer)"):
                st.session_state.logged_in = True
                st.session_state.user_info = {"id": "viewer", "name": "Guest", "role": "viewer", "desc": "Viewer Mode"}
                st.rerun()
    return False

if not check_password(): st.stop()
CURRENT_USER = st.session_state.user_info
IS_ADMIN, IS_EDITOR = (CURRENT_USER["role"] == "admin"), (CURRENT_USER["role"] in ["admin", "editor"])

# ------------------------------------------------------------------
# 3. 데이터 로드 및 저장 (Google Sheets 버전)
# ------------------------------------------------------------------
# 기본 컬럼 정의
COLS_RECORDS = ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"]
COLS_ITEMS = ["품목코드", "제품명"]
COLS_INVENTORY = ["품목코드", "제품명", "현재고"]
COLS_INV_HISTORY = ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"]
COLS_MAINTENANCE = ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"]
COLS_EQUIPMENT = ["id", "name", "func"]

# 설비 초기 데이터
DEFAULT_EQUIPMENT = [
    {"id": "CIMON-SMT34", "name": "Loader (SLD-120Y)", "func": "메거진 로딩"},
    {"id": "CIMON-SMT03", "name": "Screen Printer", "func": "솔더링 설비"},
    {"id": "CIMON-SMT08", "name": "REFLOW(1809MKⅢ)", "func": "리플로우 오븐"},
    {"id": "CIMON-SMT29", "name": "AOI검사(ZENITH)", "func": "비젼 검사"}
]

def init_sheets():
    """필요한 시트 탭이 없으면 생성"""
    defaults = {
        SHEET_RECORDS: COLS_RECORDS,
        SHEET_ITEMS: COLS_ITEMS,
        SHEET_INVENTORY: COLS_INVENTORY,
        SHEET_INV_HISTORY: COLS_INV_HISTORY,
        SHEET_MAINTENANCE: COLS_MAINTENANCE,
        SHEET_EQUIPMENT: COLS_EQUIPMENT
    }
    
    for s_name, cols in defaults.items():
        ws = get_worksheet(GOOGLE_SHEET_NAME, s_name, create_if_missing=True, columns=cols)
        # 설비 목록이 비어있으면 초기값 주입
        if s_name == SHEET_EQUIPMENT and len(ws.get_all_values()) <= 1:
            df_def = pd.DataFrame(DEFAULT_EQUIPMENT)
            set_with_dataframe(ws, df_def)

# 앱 시작 시 시트 초기화 확인 (속도 저하 방지를 위해 session_state 체크)
if 'sheets_initialized' not in st.session_state:
    init_sheets()
    st.session_state.sheets_initialized = True

def load_data(sheet_name):
    """구글 시트에서 데이터를 읽어와 DataFrame으로 반환"""
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if not ws: return pd.DataFrame()
    
    data = ws.get_all_records()
    df = pd.DataFrame(data)
    
    # 모든 컬럼을 문자열로 변환 (안전성 확보) 후 숫자 변환 필요한 곳만 처리
    # (여기서는 간단하게 반환)
    return df

def save_data(df, sheet_name):
    """DataFrame 전체를 구글 시트에 덮어쓰기 (가장 단순하고 확실한 방법)"""
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        ws.clear() # 기존 데이터 삭제
        set_with_dataframe(ws, df) # 새 데이터 쓰기
        return True
    return False

def append_data(data_dict, sheet_name):
    """행 추가"""
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        # 딕셔너리의 값들만 추출하여 리스트로 변환 (헤더 순서 보장 필요)
        # 여기서는 DataFrame을 통해 순서를 맞춤
        df_new = pd.DataFrame([data_dict])
        
        # 기존 시트의 헤더를 읽어서 순서 맞추기
        headers = ws.row_values(1)
        row_to_add = []
        for h in headers:
            row_to_add.append(str(data_dict.get(h, ""))) # 문자열로 변환하여 저장
            
        ws.append_row(row_to_add)
        return True
    return False

def update_inventory(code, name, change, reason, user):
    """재고 수량 업데이트"""
    df = load_data(SHEET_INVENTORY)
    
    # 데이터 타입 정리
    if not df.empty and '현재고' in df.columns:
        df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
    else:
        df = pd.DataFrame(columns=COLS_INVENTORY)

    # 로직 수행
    if code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    save_data(df, SHEET_INVENTORY)
    
    # 이력 저장
    hist = {
        "날짜": datetime.now().strftime("%Y-%m-%d"), 
        "품목코드": code, "구분": "입고" if change > 0 else "출고", 
        "수량": change, "비고": reason, 
        "작성자": user, "입력시간": str(datetime.now())
    }
    append_data(hist, SHEET_INV_HISTORY)

def get_user_id():
    return st.session_state.user_info["name"]

# ------------------------------------------------------------------
# 4. UI 구성 (Smart Layout)
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("<h2 style='text-align:center;'>Cloud SMT</h2>", unsafe_allow_html=True)
    if st.session_state.logged_in:
        u_info = st.session_state.user_info
        st.info(f"👤 {u_info['name']} ({u_info['role']})")
    
    menu = st.radio("메뉴", ["🏭 생산관리", "🛠️ 설비보전관리"])
    
    if st.button("로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# 메인 헤더
st.markdown(f"""
    <div class="dashboard-header">
        <div>
            <h2 style="margin:0;">{menu}</h2>
            <div style="opacity:0.8;">Google Sheets 연동 모드</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 5. 메뉴별 로직
# ------------------------------------------------------------------

if menu == "🏭 생산관리":
    t1, t2, t3, t4 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 대시보드", "⚙️ 기준정보"])
    
    # 1. 실적 등록
    with t1:
        c1, c2 = st.columns([1, 1.5])
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### 신규 생산 등록")
                    date = st.date_input("작업 일자")
                    cat = st.selectbox("공정", ["PC", "CM1", "CM3", "후공정", "후공정 외주"])
                    code = st.text_input("품목 코드")
                    name = st.text_input("제품명")
                    qty = st.number_input("수량", min_value=1, value=100)
                    
                    auto_deduct = False
                    if cat in ["후공정", "후공정 외주"]:
                        auto_deduct = st.checkbox("반제품 재고 자동 차감", value=True)
                        
                    if st.button("저장하기", type="primary", use_container_width=True):
                        rec = {
                            "날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, 
                            "수량":qty, "입력시간":str(datetime.now()), 
                            "작성자":get_user_id(), "수정자":"", "수정시간":""
                        }
                        if append_data(rec, SHEET_RECORDS):
                            if auto_deduct:
                                update_inventory(code, name, -qty, f"생산출고({cat})", get_user_id())
                            st.success("Cloud 저장 완료!")
                            time.sleep(1); st.rerun()
                        else: st.error("저장 실패")
            else: st.warning("뷰어 모드")

        with c2:
            st.markdown("#### 최근 등록 내역")
            df = load_data(SHEET_RECORDS)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(50)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else: st.info("데이터 없음")

    # 2. 재고 현황
    with t2:
        df_inv = load_data(SHEET_INVENTORY)
        if not df_inv.empty:
            # 숫자형 변환
            df_inv['현재고'] = pd.to_numeric(df_inv['현재고'], errors='coerce').fillna(0)
            st.dataframe(df_inv, use_container_width=True)
        else: st.info("재고 없음")

    # 3. 대시보드
    with t3:
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            total = df['수량'].sum()
            st.metric("총 생산량", f"{total:,} EA")
            
            if HAS_ALTAIR:
                chart_data = df.groupby('날짜')['수량'].sum().reset_index()
                c = alt.Chart(chart_data).mark_line(point=True).encode(x='날짜', y='수량').interactive()
                st.altair_chart(c, use_container_width=True)
        else: st.info("데이터 없음")

    # 4. 기준정보
    with t4:
        if IS_ADMIN:
            st.warning("주의: 데이터 수정 시 구글 시트에 즉시 반영됩니다.")
            df_items = load_data(SHEET_ITEMS)
            edited = st.data_editor(df_items, num_rows="dynamic", use_container_width=True)
            if st.button("품목 기준정보 저장"):
                save_data(edited, SHEET_ITEMS)
                st.success("저장 완료")

elif menu == "🛠️ 설비보전관리":
    t1, t2 = st.tabs(["📝 정비 이력", "⚙️ 설비 목록"])
    
    with t1:
        c1, c2 = st.columns([1, 2])
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### 정비 이력 등록")
                    # 설비 목록 로드
                    eq_df = load_data(SHEET_EQUIPMENT)
                    eq_list = eq_df['id'].tolist() if not eq_df.empty else []
                    
                    f_date = st.date_input("날짜", key="m_date")
                    f_eq = st.selectbox("설비", eq_list)
                    f_type = st.selectbox("구분", ["PM", "BM", "CM"])
                    f_desc = st.text_area("내용")
                    f_cost = st.number_input("비용", step=1000)
                    f_down = st.number_input("비가동(분)", step=10)
                    
                    if st.button("이력 저장", type="primary", use_container_width=True):
                        # 설비명 찾기
                        eq_name = ""
                        if not eq_df.empty:
                            row = eq_df[eq_df['id'] == f_eq]
                            if not row.empty: eq_name = row.iloc[0]['name']

                        rec = {
                            "날짜": str(f_date), "설비ID": f_eq, "설비명": eq_name,
                            "작업구분": f_type, "작업내용": f_desc, "교체부품": "",
                            "비용": f_cost, "작업자": get_user_id(), "비가동시간": f_down,
                            "입력시간": str(datetime.now()), "작성자": get_user_id()
                        }
                        append_data(rec, SHEET_MAINTENANCE)
                        st.success("저장 완료")
                        time.sleep(1); st.rerun()

        with c2:
            df_maint = load_data(SHEET_MAINTENANCE)
            if not df_maint.empty:
                st.dataframe(df_maint.sort_values("입력시간", ascending=False), use_container_width=True)
            else: st.info("이력 없음")

    with t2:
        if IS_ADMIN:
            df_eq = load_data(SHEET_EQUIPMENT)
            edited_eq = st.data_editor(df_eq, num_rows="dynamic", use_container_width=True)
            if st.button("설비 목록 저장"):
                save_data(edited_eq, SHEET_EQUIPMENT)
                st.success("저장됨")
        else:
            st.dataframe(load_data(SHEET_EQUIPMENT))