import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import base64
import os
from fpdf import FPDF
import streamlit.components.v1 as components

# 구글 시트 연동 라이브러리
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe

# [안전 장치] 시각화 라이브러리 로드
try:
    import altair as alt
    HAS_ALTAIR = True
except Exception as e:
    HAS_ALTAIR = False

# ------------------------------------------------------------------
# 1. 기본 설정 및 디자인
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT 통합시스템", 
    page_icon="🏭",
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
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. Google Sheets 연결 설정 (캐싱 최적화)
# ------------------------------------------------------------------
GOOGLE_SHEET_NAME = "SMT_Database" 

SHEET_RECORDS = "production_data"
SHEET_ITEMS = "item_codes"
SHEET_INVENTORY = "inventory_data"
SHEET_INV_HISTORY = "inventory_history"
SHEET_MAINTENANCE = "maintenance_data"
SHEET_EQUIPMENT = "equipment_list"

# 기본 컬럼 정의
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

@st.cache_resource
def get_gs_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" not in st.secrets:
             st.error("Secrets 설정 오류: .streamlit/secrets.toml 확인 필요")
             return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        st.error(f"Google Cloud 연결 실패: {e}")
        return None

@st.cache_resource
def get_spreadsheet_object(sheet_name):
    client = get_gs_connection()
    if not client: return None
    try:
        return client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        st.error(f"구글 시트 '{sheet_name}'를 찾을 수 없습니다.")
        return None
    except Exception as e:
        st.error(f"시트 열기 오류: {e}")
        return None

def get_worksheet(sheet_name, worksheet_name, create_if_missing=False, columns=None):
    sh = get_spreadsheet_object(sheet_name)
    if not sh: return None
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        if create_if_missing:
            ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)
            if columns: ws.append_row(columns)
        else: return None
    return ws

def init_sheets():
    sh = get_spreadsheet_object(GOOGLE_SHEET_NAME)
    if not sh: return
    existing_titles = [ws.title for ws in sh.worksheets()]
    defaults = {
        SHEET_RECORDS: COLS_RECORDS, SHEET_ITEMS: COLS_ITEMS,
        SHEET_INVENTORY: COLS_INVENTORY, SHEET_INV_HISTORY: COLS_INV_HISTORY,
        SHEET_MAINTENANCE: COLS_MAINTENANCE, SHEET_EQUIPMENT: COLS_EQUIPMENT
    }
    for s_name, cols in defaults.items():
        if s_name not in existing_titles:
            ws = sh.add_worksheet(title=s_name, rows=100, cols=20)
            ws.append_row(cols)
            if s_name == SHEET_EQUIPMENT:
                 set_with_dataframe(ws, pd.DataFrame(DEFAULT_EQUIPMENT))

if 'sheets_initialized' not in st.session_state:
    init_sheets()
    st.session_state.sheets_initialized = True

@st.cache_data(ttl=5)
def load_data(sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if not ws: return pd.DataFrame()
    try:
        df = get_as_dataframe(ws, evaluate_formulas=True)
        return df.dropna(how='all').dropna(axis=1, how='all')
    except: return pd.DataFrame()

def clear_cache():
    load_data.clear()

def save_data(df, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        ws.clear() 
        set_with_dataframe(ws, df) 
        clear_cache()
        return True
    return False

def append_data(data_dict, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        try: headers = ws.row_values(1)
        except: headers = list(data_dict.keys())
        row_to_add = [str(data_dict.get(h, "")) if not pd.isna(data_dict.get(h, "")) else "" for h in headers]
        ws.append_row(row_to_add)
        clear_cache()
        return True
    return False

def update_inventory(code, name, change, reason, user):
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
    
    save_data(df, SHEET_INVENTORY)
    
    hist = {
        "날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, 
        "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, 
        "작성자": user, "입력시간": str(datetime.now())
    }
    append_data(hist, SHEET_INV_HISTORY)

# ------------------------------------------------------------------
# 3. 로그인 및 사용자 관리
# ------------------------------------------------------------------
def make_hash(password): return hashlib.sha256(str.encode(password)).hexdigest()

USERS = {
    "park": {"name": "Park", "password_hash": make_hash("1083"), "role": "admin", "desc": "System Administrator"},
    "suk": {"name": "Suk", "password_hash": make_hash("1734"), "role": "editor", "desc": "Production Manager"},
    "kim": {"name": "Kim", "password_hash": make_hash("8943"), "role": "editor", "desc": "Equipment Engineer"}
}

def check_password():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: return True

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True) 
        st.markdown("<h1 style='text-align:center;'>SMT 통합시스템</h1>", unsafe_allow_html=True)
        with st.container(border=True):
            with st.form(key="login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                    if username in USERS and make_hash(password) == USERS[username]["password_hash"]:
                        st.session_state.logged_in = True
                        st.session_state.user_info = USERS[username]
                        st.session_state.user_info["id"] = username
                        st.rerun()
                    else: st.error("아이디 또는 비밀번호가 잘못되었습니다.")
            
            if st.button("Guest Access (Viewer)", use_container_width=True):
                st.session_state.logged_in = True
                st.session_state.user_info = {"id": "viewer", "name": "Guest", "role": "viewer", "desc": "Viewer Mode"}
                st.rerun()
    return False

if not check_password(): st.stop()
CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")
IS_EDITOR = (CURRENT_USER["role"] in ["admin", "editor"])
def get_user_id(): return st.session_state.user_info["name"]

# ------------------------------------------------------------------
# 4. 메인 UI 및 메뉴
# ------------------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown("<h2 style='text-align:center;'>Cloud SMT</h2>", unsafe_allow_html=True)
    if st.session_state.logged_in:
        u_info = st.session_state.user_info
        role_badge = "👑 Admin" if u_info["role"] == "admin" else "👤 User" if u_info["role"] == "editor" else "👀 Viewer"
        role_style = "background:#dcfce7; color:#15803d;" if u_info["role"] == "admin" else "background:#dbeafe; color:#1d4ed8;"
        st.markdown(f"""
            <div class="smart-card" style="padding:15px; margin-bottom:20px; text-align:center;">
                <div style="font-weight:bold; font-size:1.1rem;">{u_info['name']}</div>
                <div style="font-size:0.8rem; color:#64748b; margin-bottom:5px;">{u_info['desc']}</div>
                <span style="font-size:0.75rem; padding:4px 10px; border-radius:12px; font-weight:bold; {role_style}">{role_badge}</span>
            </div>
        """, unsafe_allow_html=True)
    
    menu = st.radio("Navigation", ["🏭 생산관리", "🛠️ 설비보전관리"])
    st.markdown("---")
    if st.button("로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

st.markdown(f"""<div class="dashboard-header"><div><h2 style="margin:0;">{menu}</h2><div style="opacity:0.8; margin-top:5px;">Real-time Management System</div></div></div>""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 5. [메뉴 1] 생산관리
# ------------------------------------------------------------------
if menu == "🏭 생산관리":
    t1, t2, t3, t4 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 대시보드", "⚙️ 기준정보"])
    
    # 5-1. 생산 등록
    with t1:
        c1, c2 = st.columns([1, 1.5], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### ✏️ 신규 생산 등록")
                    date = st.date_input("작업 일자")
                    cat = st.selectbox("공정 구분", ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"])
                    
                    item_df = load_data(SHEET_ITEMS)
                    item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
                    
                    def on_code():
                        c = st.session_state.code_in.upper().strip()
                        if c in item_map: st.session_state.name_in = item_map[c]
                    
                    code = st.text_input("품목 코드", key="code_in", on_change=on_code)
                    name = st.text_input("제품명", key="name_in")
                    qty = st.number_input("생산 수량", min_value=1, value=100, key="prod_qty")
                    
                    auto_deduct = False
                    if cat in ["후공정", "후공정 외주"]:
                        st.divider()
                        auto_deduct = st.checkbox("📦 반제품 재고 자동 차감 (체크 시 감소)", value=True)
                    else:
                        st.divider()
                        st.info("ℹ️ 생산 등록 시 재고가 자동으로 증가합니다.")

                    if st.button("저장하기", type="primary", use_container_width=True):
                        if name:
                            rec = {
                                "날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, 
                                "수량":qty, "입력시간":str(datetime.now()), 
                                "작성자":get_user_id(), "수정자":"", "수정시간":""
                            }
                            with st.spinner("저장 중..."):
                                if append_data(rec, SHEET_RECORDS):
                                    # 재고 연동 로직
                                    if cat in ["후공정", "후공정 외주"]:
                                        if auto_deduct: update_inventory(code, name, -qty, f"생산출고({cat})", get_user_id())
                                    else:
                                        update_inventory(code, name, qty, f"생산입고({cat})", get_user_id())
                                    
                                    st.success("저장 완료!")
                                    # 입력창 초기화
                                    st.session_state.code_in = ""
                                    st.session_state.name_in = ""
                                    st.session_state.prod_qty = 100
                                    time.sleep(0.5); st.rerun()
                                else: st.error("저장 실패")
                        else: st.error("제품명을 입력해주세요.")
            else: st.warning("🔒 뷰어 모드입니다.")

        with c2:
            st.markdown("#### 📋 최근 등록 내역 (삭제 가능)")
            df = load_data(SHEET_RECORDS)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(50)
                if IS_EDITOR:
                    st.caption("💡 행을 선택하고 Del 키를 누르면 삭제됩니다.")
                    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic", key="prod_editor")
                    if st.button("변경사항 저장 (삭제 반영)", type="secondary"):
                        save_data(edited_df, SHEET_RECORDS) 
                        st.success("반영되었습니다.")
                        time.sleep(1); st.rerun()
                else: st.dataframe(df, use_container_width=True, hide_index=True)
            else: st.info("데이터가 없습니다.")

    # 5-2. 재고 현황
    with t2:
        df_inv = load_data(SHEET_INVENTORY)
        if not df_inv.empty:
            df_inv['현재고'] = pd.to_numeric(df_inv['현재고'], errors='coerce').fillna(0).astype(int)
            c_s, _ = st.columns([1, 2])
            search = c_s.text_input("🔍 재고 검색", placeholder="품목명/코드")
            if search:
                mask = df_inv['품목코드'].astype(str).str.contains(search, case=False) | df_inv['제품명'].astype(str).str.contains(search, case=False)
                df_inv = df_inv[mask]
            
            # [수정 1] 재고 현황 편집 및 삭제 기능 추가
            if IS_EDITOR:
                st.caption("💡 수량 수정 및 Del 키로 삭제 가능")
                edited_inv = st.data_editor(
                    df_inv, 
                    use_container_width=True, 
                    hide_index=True, 
                    num_rows="dynamic", 
                    key="inv_editor"
                )
                if st.button("재고 현황 저장", type="primary"):
                    save_data(edited_inv, SHEET_INVENTORY)
                    st.success("재고가 업데이트되었습니다.")
                    time.sleep(1); st.rerun()
            else:
                st.dataframe(df_inv, use_container_width=True, hide_index=True)
        else: st.info("재고 데이터가 없습니다.")

    # 5-3. 대시보드
    with t3:
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            df['날짜'] = pd.to_datetime(df['날짜'])
            k1, k2 = st.columns(2)
            k1.metric("총 누적 생산량", f"{df['수량'].sum():,} EA")
            k2.metric("최근 생산일", df['날짜'].max().strftime('%Y-%m-%d'))
            st.divider()
            if HAS_ALTAIR:
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown("##### 📈 일별 생산 추이")
                    chart_data = df.groupby('날짜')['수량'].sum().reset_index()
                    c = alt.Chart(chart_data).mark_line(point=True).encode(x=alt.X('날짜', axis=alt.Axis(format='%m-%d')), y='수량', tooltip=['날짜', '수량']).interactive()
                    st.altair_chart(c, use_container_width=True)
                with c2:
                    st.markdown("##### 🍰 공정별 비중")
                    pie_data = df.groupby('구분')['수량'].sum().reset_index()
                    pie = alt.Chart(pie_data).mark_arc(innerRadius=50).encode(theta=alt.Theta("수량", stack=True), color=alt.Color("구분"), tooltip=["구분", "수량"])
                    st.altair_chart(pie, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    # 5-4. 기준정보
    with t4:
        if IS_ADMIN:
            st.warning("⚠️ 구글 시트에 즉시 반영됩니다.")
            t_item, t_raw = st.tabs(["품목 관리", "데이터 원본(Admin)"])
            with t_item:
                df_items = load_data(SHEET_ITEMS)
                edited = st.data_editor(df_items, num_rows="dynamic", use_container_width=True)
                if st.button("품목 기준정보 저장", type="primary"):
                    save_data(edited, SHEET_ITEMS); st.success("저장 완료"); time.sleep(1); st.rerun()
            with t_raw: st.markdown("전체 데이터 직접 편집 모드")
        else: st.warning("관리자 권한 필요")

# ------------------------------------------------------------------
# 6. [메뉴 2] 설비보전관리
# ------------------------------------------------------------------
elif menu == "🛠️ 설비보전관리":
    # [복구] 분석 및 리포트 탭 포함 4개 탭
    t1, t2, t3, t4 = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "📊 분석 및 리포트", "⚙️ 설비 목록"])
    
    # 6-1. 정비 이력 등록
    with t1:
        c1, c2 = st.columns([1, 1.5], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### 🔧 정비 이력 등록")
                    eq_df = load_data(SHEET_EQUIPMENT)
                    eq_map = dict(zip(eq_df['id'], eq_df['name'])) if not eq_df.empty else {}
                    eq_list = list(eq_map.keys())
                    
                    f_date = st.date_input("작업 날짜", key="m_date")
                    f_eq = st.selectbox("대상 설비", eq_list, format_func=lambda x: f"[{x}] {eq_map[x]}" if x in eq_map else x, key="m_eq")
                    f_type = st.selectbox("작업 구분", ["PM (예방)", "BM (고장)", "CM (개선)"], key="m_type")
                    f_desc = st.text_area("작업 내용", height=80, key="m_desc")
                    
                    st.markdown("---")
                    st.caption("🔩 교체 부품 / 상세 비용 추가")
                    
                    if 'parts_buffer' not in st.session_state: st.session_state.parts_buffer = []
                    col_p1, col_p2, col_p3 = st.columns([2, 1, 0.8])
                    p_name = col_p1.text_input("내역/부품명", key="p_name_in")
                    p_cost = col_p2.number_input("비용(원)", step=1000, key="p_cost_in")
                    
                    if col_p3.button("추가", use_container_width=True):
                        if p_name: st.session_state.parts_buffer.append({"내역": p_name, "비용": int(p_cost)})
                        else: st.toast("내역을 입력하세요.")
                    
                    total_p_cost = 0
                    if st.session_state.parts_buffer:
                        p_df = pd.DataFrame(st.session_state.parts_buffer)
                        st.dataframe(p_df, use_container_width=True, hide_index=True)
                        total_p_cost = p_df['비용'].sum()
                        if st.button("목록 초기화"):
                            st.session_state.parts_buffer = []
                            st.rerun()

                    st.markdown("---")
                    f_cost = st.number_input("💰 총 소요 비용 (원)", value=total_p_cost, step=1000, key="m_cost")
                    f_down = st.number_input("⏱️ 비가동 시간 (분)", step=10, key="m_down")
                    
                    if st.button("이력 저장", type="primary", use_container_width=True):
                        eq_name = eq_map.get(f_eq, "")
                        parts_str = ", ".join([f"{p['내역']}({p['비용']:,})" for p in st.session_state.parts_buffer]) if st.session_state.parts_buffer else ""
                        rec = {
                            "날짜": str(f_date), "설비ID": f_eq, "설비명": eq_name,
                            "작업구분": f_type.split()[0], "작업내용": f_desc, 
                            "교체부품": parts_str, "비용": f_cost, "작업자": get_user_id(), 
                            "비가동시간": f_down, "입력시간": str(datetime.now()), "작성자": get_user_id()
                        }
                        with st.spinner("저장 중..."):
                            append_data(rec, SHEET_MAINTENANCE)
                            # 입력 초기화
                            st.session_state.parts_buffer = [] 
                            st.session_state.m_desc = ""
                            st.session_state.m_cost = 0
                            st.session_state.m_down = 0
                            st.success("저장 완료")
                            time.sleep(0.5); st.rerun()
            else: st.warning("권한이 없습니다.")

        with c2:
            st.markdown("#### 📋 최근 정비 내역 (삭제 가능)")
            df_maint = load_data(SHEET_MAINTENANCE)
            if not df_maint.empty:
                df_maint = df_maint.sort_values("입력시간", ascending=False).head(50)
                if IS_EDITOR:
                    st.caption("💡 행을 선택하고 Del 키를 누르면 삭제됩니다.")
                    edited_maint = st.data_editor(df_maint, use_container_width=True, hide_index=True, num_rows="dynamic", key="maint_editor_recent")
                    if st.button("변경사항 저장 (정비내역)", type="secondary"):
                        save_data(edited_maint, SHEET_MAINTENANCE)
                        st.success("반영되었습니다.")
                        time.sleep(1); st.rerun()
                else: st.dataframe(df_maint, use_container_width=True, hide_index=True)
            else: st.info("이력이 없습니다.")

    # 6-2. 이력 조회
    with t2:
        df_hist = load_data(SHEET_MAINTENANCE)
        if not df_hist.empty: 
            # [수정 2] 이력 조회 전체 수정 및 삭제 기능 추가
            if IS_EDITOR:
                st.caption("💡 전체 이력 수정 및 삭제 모드")
                # 최신순 정렬하여 편집
                df_hist_sorted = df_hist.sort_values("날짜", ascending=False)
                edited_hist = st.data_editor(
                    df_hist_sorted, 
                    use_container_width=True, 
                    num_rows="dynamic",
                    key="hist_editor_full"
                )
                if st.button("이력 수정 저장", type="primary"):
                    save_data(edited_hist, SHEET_MAINTENANCE)
                    st.success("이력이 전체 업데이트되었습니다.")
                    time.sleep(1); st.rerun()
            else:
                st.dataframe(df_hist, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    # 6-3. [복구 완료] 분석 및 리포트
    with t3:
        st.markdown("#### 📊 설비 고장 및 정비 분석")
        df = load_data(SHEET_MAINTENANCE)
        if not df.empty and '날짜' in df.columns:
            df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
            df['비용'] = pd.to_numeric(df['비용'], errors='coerce').fillna(0)
            df['비가동시간'] = pd.to_numeric(df['비가동시간'], errors='coerce').fillna(0)
            df['Year'] = df['날짜'].dt.year
            df['Month'] = df['날짜'].dt.month
            
            avail_years = sorted(df['Year'].dropna().unique().astype(int), reverse=True)
            if not avail_years: avail_years = [datetime.now().year]
            sel_year = st.selectbox("조회 연도", avail_years)
            df_year = df[df['Year'] == sel_year]
            
            if not df_year.empty:
                k1, k2, k3 = st.columns(3)
                k1.metric("💰 연간 정비비용", f"{df_year['비용'].sum():,.0f} 원")
                k2.metric("⏱️ 연간 비가동", f"{df_year['비가동시간'].sum():,} 분")
                k3.metric("🔥 고장(BM) 발생", f"{len(df_year[df_year['작업구분'].astype(str).str.contains('BM', na=False)])} 건")
                st.divider()
                if HAS_ALTAIR:
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown("##### 📉 월별 비용 추이")
                        # [수정 3] X축 글씨 각도 0도로 수정 (axis=alt.Axis(labelAngle=0))
                        chart = alt.Chart(df_year.groupby('Month')['비용'].sum().reset_index()).mark_bar().encode(
                            x=alt.X('Month:O', title='월', axis=alt.Axis(labelAngle=0)), 
                            y=alt.Y('비용', title='비용')
                        )
                        st.altair_chart(chart, use_container_width=True)
                    with c2:
                        st.markdown("##### 🥧 유형별 비율")
                        pie = alt.Chart(df_year.groupby('작업구분')['비용'].sum().reset_index()).mark_arc(innerRadius=40).encode(theta=alt.Theta("비용", stack=True), color="작업구분")
                        st.altair_chart(pie, use_container_width=True)
            else: st.info(f"{sel_year}년 데이터가 없습니다.")
        else: st.info("데이터가 없습니다.")

    # 6-4. 설비 목록
    with t4:
        if IS_ADMIN:
            st.markdown("#### 설비 리스트 관리")
            df_eq = load_data(SHEET_EQUIPMENT)
            edited_eq = st.data_editor(df_eq, num_rows="dynamic", use_container_width=True)
            if st.button("설비 목록 저장", type="primary"):
                save_data(edited_eq, SHEET_EQUIPMENT); st.success("갱신 완료"); time.sleep(1); st.rerun()
        else: st.dataframe(load_data(SHEET_EQUIPMENT))