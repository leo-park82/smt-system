import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import base64
import os  # [추가] 파일 존재 여부 확인용
from fpdf import FPDF
import streamlit.components.v1 as components

# [추가] 구글 시트 연동 라이브러리
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe

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
    .kpi-title { font-size: 0.85rem; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }
    .kpi-value { font-size: 2.2rem; font-weight: 800; color: #0f172a; margin-bottom: 4px; }
    .trend-up { color: #10b981; background: #ecfdf5; padding: 2px 8px; border-radius: 12px; font-size: 0.9rem; }
    .trend-neutral { color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 12px; font-size: 0.9rem; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# [핵심] Google Sheets 연결 설정 (최적화 적용)
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
    """Google Sheets API 클라이언트 연결 객체 생성 (캐싱 사용)"""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        if "gcp_service_account" not in st.secrets:
             st.error("Secrets 설정이 없습니다. .streamlit/secrets.toml 파일을 확인해주세요.")
             return None

        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        return client
    except Exception as e:
        st.error(f"⚠️ Google Cloud 연결 실패: {e}")
        return None

@st.cache_resource
def get_spreadsheet_object(sheet_name):
    """
    [중요] 스프레드시트 파일 자체를 여는 객체를 캐싱합니다.
    이 함수가 없으면 페이지가 리로드될 때마다 client.open()을 호출하여 API 한도를 초과하게 됩니다.
    """
    client = get_gs_connection()
    if not client: return None
    try:
        return client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        st.error(f"⚠️ 구글 시트 '{sheet_name}'를 찾을 수 없습니다.")
        return None
    except Exception as e:
        st.error(f"⚠️ 시트 열기 오류: {e}")
        return None

def get_worksheet(sheet_name, worksheet_name, create_if_missing=False, columns=None):
    """특정 워크시트를 가져오거나 없으면 생성"""
    sh = get_spreadsheet_object(sheet_name)
    if not sh: return None
    
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
        # [수정] 로그인 화면에 로고 표시
        if os.path.exists("logo.png"):
             st.image("logo.png", width=120) # 로고 크기 조절 가능
        
        st.markdown("<h1 style='text-align:center;'>☁️ SMT Cloud System</h1>", unsafe_allow_html=True)
        with st.container(border=True):
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
            
            if st.button("Guest Access (Viewer)", use_container_width=True):
                st.session_state.logged_in = True
                st.session_state.user_info = {"id": "viewer", "name": "Guest", "role": "viewer", "desc": "Viewer Mode"}
                st.rerun()
    return False

if not check_password(): st.stop()
CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")
IS_EDITOR = (CURRENT_USER["role"] in ["admin", "editor"])

# ------------------------------------------------------------------
# 3. 데이터 로드 및 저장 (캐싱 최적화 적용)
# ------------------------------------------------------------------
COLS_RECORDS = ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"]
COLS_ITEMS = ["품목코드", "제품명"]
COLS_INVENTORY = ["품목코드", "제품명", "현재고"]
COLS_INV_HISTORY = ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"]
COLS_MAINTENANCE = ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"]
COLS_EQUIPMENT = ["id", "name", "func"]

DEFAULT_EQUIPMENT = [
    {"id": "CIMON-SMT34", "name": "Loader (SLD-120Y)", "func": "메거진 로딩"},
    {"id": "CIMON-SMT03", "name": "Screen Printer", "func": "솔더링 설비"},
    {"id": "CIMON-SMT08", "name": "REFLOW(1809MKⅢ)", "func": "리플로우 오븐"},
    {"id": "CIMON-SMT29", "name": "AOI검사(ZENITH)", "func": "비젼 검사"}
]

def init_sheets():
    """필요한 시트 탭이 없으면 생성"""
    # Spreadsheet 객체 하나로 여러 워크시트 확인 (API 호출 절약)
    sh = get_spreadsheet_object(GOOGLE_SHEET_NAME)
    if not sh: return
    
    existing_titles = [ws.title for ws in sh.worksheets()]
    
    defaults = {
        SHEET_RECORDS: COLS_RECORDS,
        SHEET_ITEMS: COLS_ITEMS,
        SHEET_INVENTORY: COLS_INVENTORY,
        SHEET_INV_HISTORY: COLS_INV_HISTORY,
        SHEET_MAINTENANCE: COLS_MAINTENANCE,
        SHEET_EQUIPMENT: COLS_EQUIPMENT
    }
    
    for s_name, cols in defaults.items():
        if s_name not in existing_titles:
            ws = sh.add_worksheet(title=s_name, rows=100, cols=20)
            ws.append_row(cols)
            if s_name == SHEET_EQUIPMENT:
                 set_with_dataframe(ws, pd.DataFrame(DEFAULT_EQUIPMENT))

# 앱 시작 시 초기화
if 'sheets_initialized' not in st.session_state:
    init_sheets()
    st.session_state.sheets_initialized = True

@st.cache_data(ttl=5) # [핵심] 5초 동안은 다시 로드하지 않음 (API 보호)
def load_data(sheet_name):
    """구글 시트에서 데이터를 읽어와 DataFrame으로 반환"""
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if not ws: return pd.DataFrame()
    
    try:
        df = get_as_dataframe(ws, evaluate_formulas=True)
        # 빈 행/열 제거
        df = df.dropna(how='all').dropna(axis=1, how='all')
        return df
    except Exception as e:
        # st.error(f"데이터 로드 중 오류: {e}")
        return pd.DataFrame()

def clear_cache():
    """데이터 변경 시 캐시를 비워 즉시 반영되도록 함"""
    load_data.clear()

def save_data(df, sheet_name):
    """데이터 덮어쓰기"""
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        ws.clear() 
        set_with_dataframe(ws, df) 
        clear_cache() # 캐시 초기화
        return True
    return False

def append_data(data_dict, sheet_name):
    """행 추가"""
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        df_new = pd.DataFrame([data_dict])
        
        # 헤더 순서 맞추기
        try:
            # 첫 행(헤더)만 가져오기 (전체 데이터 로드 X)
            headers = ws.row_values(1)
        except:
            headers = list(data_dict.keys())
            
        row_to_add = []
        for h in headers:
            val = data_dict.get(h, "")
            if pd.isna(val): val = ""
            row_to_add.append(str(val))
            
        ws.append_row(row_to_add)
        clear_cache() # 캐시 초기화
        return True
    return False

def update_inventory(code, name, change, reason, user):
    """재고 수량 업데이트"""
    # 캐시 무시하고 최신 데이터 로드 필요할 수 있으므로, 로직 내에서 처리하거나
    # load_data를 그대로 쓰되, 앞선 작업에서 clear_cache()가 호출되었는지 확인
    df = load_data(SHEET_INVENTORY)
    
    if not df.empty and '현재고' in df.columns:
        df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
    else:
        df = pd.DataFrame(columns=COLS_INVENTORY)

    if not df.empty and code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    save_data(df, SHEET_INVENTORY) # 내부에서 clear_cache 호출됨
    
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
# 4. UI 구성
# ------------------------------------------------------------------
CATEGORIES = ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"]

with st.sidebar:
    # [수정] 사이드바 로고 표시 (GitHub에 파일이 있어야 함)
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    
    st.markdown("<h2 style='text-align:center;'>Cloud SMT</h2>", unsafe_allow_html=True)
    if st.session_state.logged_in:
        u_info = st.session_state.user_info
        
        role_badge = "👑 Admin" if u_info["role"] == "admin" else "👤 User" if u_info["role"] == "editor" else "👀 Viewer"
        role_style = "background:#dcfce7; color:#15803d;" if u_info["role"] == "admin" else "background:#dbeafe; color:#1d4ed8;"
        
        st.markdown(f"""
            <div class="smart-card" style="padding:15px; margin-bottom:20px; text-align:center;">
                <div style="font-weight:bold; font-size:1.1rem;">{u_info['name']}</div>
                <div style="font-size:0.8rem; color:#64748b; margin-bottom:5px;">{u_info['desc']}</div>
                <span style="font-size:0.75rem; padding:4px 10px; border-radius:12px; font-weight:bold; {role_style}">
                    {role_badge}
                </span>
            </div>
        """, unsafe_allow_html=True)
    
    menu = st.radio("Navigation", ["🏭 생산관리", "🛠️ 설비보전관리"])
    
    st.markdown("---")
    if st.button("로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.rerun()

st.markdown(f"""
    <div class="dashboard-header">
        <div>
            <h2 style="margin:0;">{menu}</h2>
            <div style="opacity:0.8; margin-top:5px;">Google Sheets Real-time System</div>
        </div>
    </div>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 5. 메뉴별 로직
# ------------------------------------------------------------------

if menu == "🏭 생산관리":
    t1, t2, t3, t4 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 대시보드", "⚙️ 기준정보"])
    
    with t1:
        c1, c2 = st.columns([1, 1.5], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### ✏️ 신규 생산 등록")
                    date = st.date_input("작업 일자")
                    cat = st.selectbox("공정 구분", CATEGORIES)
                    
                    item_df = load_data(SHEET_ITEMS)
                    item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
                    
                    def on_code():
                        c = st.session_state.code_in.upper().strip()
                        if c in item_map: st.session_state.name_in = item_map[c]
                    
                    code = st.text_input("품목 코드", key="code_in", on_change=on_code)
                    name = st.text_input("제품명", key="name_in")
                    qty = st.number_input("생산 수량", min_value=1, value=100)
                    
                    auto_deduct = False
                    if cat in ["후공정", "후공정 외주"]:
                        st.divider()
                        auto_deduct = st.checkbox("📦 반제품 재고 자동 차감", value=True)
                        
                    if st.button("저장하기", type="primary", use_container_width=True):
                        if name:
                            rec = {
                                "날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, 
                                "수량":qty, "입력시간":str(datetime.now()), 
                                "작성자":get_user_id(), "수정자":"", "수정시간":""
                            }
                            with st.spinner("클라우드에 저장 중..."):
                                if append_data(rec, SHEET_RECORDS):
                                    if auto_deduct:
                                        update_inventory(code, name, -qty, f"생산출고({cat})", get_user_id())
                                    st.success("저장 완료!")
                                    time.sleep(1); st.rerun()
                                else: st.error("저장 실패 (네트워크 확인 필요)")
                        else: st.error("제품명을 입력해주세요.")
            else: st.warning("🔒 뷰어 모드입니다.")

        with c2:
            st.markdown("#### 📋 최근 등록 내역")
            df = load_data(SHEET_RECORDS)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(20)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else: st.info("등록된 데이터가 없습니다.")

    with t2:
        df_inv = load_data(SHEET_INVENTORY)
        if not df_inv.empty:
            df_inv['현재고'] = pd.to_numeric(df_inv['현재고'], errors='coerce').fillna(0).astype(int)
            c_s, _ = st.columns([1, 2])
            search = c_s.text_input("🔍 재고 검색", placeholder="품목명/코드")
            if search:
                mask = df_inv['품목코드'].astype(str).str.contains(search, case=False) | df_inv['제품명'].astype(str).str.contains(search, case=False)
                df_inv = df_inv[mask]
            st.dataframe(df_inv, use_container_width=True, hide_index=True)
        else: st.info("재고 데이터가 없습니다.")

    with t3:
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            df['날짜'] = pd.to_datetime(df['날짜'])
            total = df['수량'].sum()
            recent_day = df['날짜'].max().strftime('%Y-%m-%d')
            k1, k2 = st.columns(2)
            k1.metric("총 누적 생산량", f"{total:,} EA")
            k2.metric("최근 생산일", recent_day)
            st.divider()
            if HAS_ALTAIR:
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown("##### 📈 일별 생산 추이")
                    chart_data = df.groupby('날짜')['수량'].sum().reset_index()
                    c = alt.Chart(chart_data).mark_line(point=True).encode(
                        x=alt.X('날짜', axis=alt.Axis(format='%m-%d')), 
                        y='수량', tooltip=['날짜', '수량']
                    ).interactive()
                    st.altair_chart(c, use_container_width=True)
                with c2:
                    st.markdown("##### 🍰 공정별 비중")
                    pie_data = df.groupby('구분')['수량'].sum().reset_index()
                    pie = alt.Chart(pie_data).mark_arc(innerRadius=50).encode(
                        theta=alt.Theta("수량", stack=True), color=alt.Color("구분"), tooltip=["구분", "수량"]
                    )
                    st.altair_chart(pie, use_container_width=True)
        else: st.info("분석할 데이터가 없습니다.")

    with t4:
        if IS_ADMIN:
            st.warning("⚠️ 주의: 여기서 수정하면 구글 시트에 즉시 반영됩니다.")
            t_item, t_raw = st.tabs(["품목 관리", "데이터 원본(Admin)"])
            with t_item:
                df_items = load_data(SHEET_ITEMS)
                edited = st.data_editor(df_items, num_rows="dynamic", use_container_width=True)
                if st.button("품목 기준정보 저장", type="primary"):
                    save_data(edited, SHEET_ITEMS)
                    st.success("저장 완료")
                    time.sleep(1); st.rerun()
            with t_raw:
                st.markdown("구글 시트 전체 데이터 직접 편집 (조심해서 사용하세요)")
        else: st.warning("🔒 관리자 전용 메뉴입니다.")

elif menu == "🛠️ 설비보전관리":
    t1, t2, t3 = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "⚙️ 설비 목록"])
    
    with t1:
        c1, c2 = st.columns([1, 1.5], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### 🔧 정비 이력 등록")
                    eq_df = load_data(SHEET_EQUIPMENT)
                    
                    # [수정] 설비 선택 시 ID와 이름을 같이 표시하기 위한 매핑
                    eq_map = {}
                    if not eq_df.empty:
                        eq_map = dict(zip(eq_df['id'], eq_df['name']))
                    
                    eq_list = list(eq_map.keys())
                    
                    f_date = st.date_input("작업 날짜", key="m_date")
                    
                    # [수정] format_func를 사용하여 드롭다운 표시 형식 변경 ([ID] 설비명)
                    f_eq = st.selectbox(
                        "대상 설비", 
                        eq_list,
                        format_func=lambda x: f"[{x}] {eq_map[x]}" if x in eq_map else x
                    )
                    
                    f_type = st.selectbox("작업 구분", ["PM (예방)", "BM (고장)", "CM (개선)"])
                    f_desc = st.text_area("작업 내용", height=100)
                    f_cost = st.number_input("소요 비용 (원)", step=1000)
                    f_down = st.number_input("비가동 시간 (분)", step=10)
                    
                    if st.button("이력 저장", type="primary", use_container_width=True):
                        eq_name = ""
                        if not eq_df.empty:
                            row = eq_df[eq_df['id'] == f_eq]
                            if not row.empty: eq_name = row.iloc[0]['name']

                        rec = {
                            "날짜": str(f_date), "설비ID": f_eq, "설비명": eq_name,
                            "작업구분": f_type.split()[0], "작업내용": f_desc, "교체부품": "",
                            "비용": f_cost, "작업자": get_user_id(), "비가동시간": f_down,
                            "입력시간": str(datetime.now()), "작성자": get_user_id()
                        }
                        with st.spinner("저장 중..."):
                            append_data(rec, SHEET_MAINTENANCE)
                            st.success("저장 완료")
                            time.sleep(1); st.rerun()
            else: st.warning("입력 권한이 없습니다.")

        with c2:
            st.markdown("#### 📋 최근 정비 내역")
            df_maint = load_data(SHEET_MAINTENANCE)
            if not df_maint.empty:
                df_maint = df_maint.sort_values("입력시간", ascending=False).head(10)
                st.dataframe(df_maint, use_container_width=True, hide_index=True)
            else: st.info("이력이 없습니다.")

    with t2:
        df_hist = load_data(SHEET_MAINTENANCE)
        if not df_hist.empty:
            st.dataframe(df_hist, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with t3:
        if IS_ADMIN:
            st.markdown("#### 설비 리스트 관리")
            df_eq = load_data(SHEET_EQUIPMENT)
            edited_eq = st.data_editor(df_eq, num_rows="dynamic", use_container_width=True)
            if st.button("설비 목록 저장", type="primary"):
                save_data(edited_eq, SHEET_EQUIPMENT)
                st.success("설비 목록이 갱신되었습니다.")
                time.sleep(1); st.rerun()
        else:
            st.dataframe(load_data(SHEET_EQUIPMENT))