import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, timezone
import time
import hashlib
import os
import tempfile
import urllib.request
from fpdf import FPDF
import streamlit.components.v1 as components

# 구글 시트 및 데이터 라이브러리
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe

# 시각화 라이브러리 (안전 장치)
try:
    import altair as alt
    HAS_ALTAIR = True
except Exception:
    HAS_ALTAIR = False

# ==========================================
# 1. 상수 및 설정 정의
# ==========================================
GOOGLE_SHEET_NAME = "SMT_Database"
SHEET_RECORDS = "production_data"
SHEET_ITEMS = "item_codes"
SHEET_INVENTORY = "inventory_data"
SHEET_INV_HISTORY = "inventory_history"
SHEET_MAINTENANCE = "maintenance_data"
SHEET_EQUIPMENT = "equipment_list"
SHEET_CHECK_MASTER = "daily_check_master"
SHEET_CHECK_RESULT = "daily_check_result"

COLS_RECORDS = ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"]
COLS_ITEMS = ["품목코드", "제품명"]
COLS_INVENTORY = ["품목코드", "제품명", "현재고"]
COLS_INV_HISTORY = ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"]
COLS_MAINTENANCE = ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"]
COLS_EQUIPMENT = ["id", "name", "func"]
COLS_CHECK_MASTER = ["line", "equip_id", "equip_name", "item_name", "check_content", "standard", "check_type", "min_val", "max_val", "unit"]
COLS_CHECK_RESULT = ["date", "line", "equip_id", "item_name", "value", "ox", "checker", "timestamp", "비고"]

def make_hash(password): return hashlib.sha256(str.encode(password)).hexdigest()
USERS = {
    "cimon": {"name": "관리자", "password_hash": make_hash("7801083"), "role": "admin"},
    "박종선": {"name": "박종선", "password_hash": make_hash("1083"), "role": "worker"},
    "김윤석": {"name": "김윤석", "password_hash": make_hash("1734"), "role": "worker"},
    "김명숙": {"name": "김명숙", "password_hash": make_hash("8943"), "role": "worker"}
}

# ==========================================
# 2. 초기화 및 스타일
# ==========================================
def init_session():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = None

def load_style():
    st.markdown("""
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; color: #1e293b; }
        .stApp { background-color: #f8fafc; }
        
        /* [중요] 사이드바 완전 제거 */
        [data-testid="stSidebar"] { display: none; }
        [data-testid="collapsedControl"] { display: none; }
        section[data-testid="stSidebar"] { display: none; }
        
        /* 헤더 스타일 (Flexbox 느낌) */
        .app-header-container {
            display: flex;
            justify-content: space-between;
            align-items: center;
            background-color: white;
            padding: 15px 25px;
            border-bottom: 2px solid #e2e8f0;
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            margin-bottom: 15px;
        }
        .header-title {
            font-size: 1.6rem;
            font-weight: 800;
            color: #1e293b;
            letter-spacing: -0.5px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .header-user {
            font-size: 1rem;
            color: #64748b;
            font-weight: 500;
            text-align: right;
        }
        
        /* 탭 스타일 상단 고정 */
        .stTabs [data-baseweb="tab-list"] { 
            gap: 8px; 
            background-color: #ffffff; 
            padding: 10px 10px 0 10px; 
            border-radius: 12px 12px 0 0; 
            border-bottom: 1px solid #e2e8f0;
            position: sticky;
            top: 0;
            z-index: 999;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);
        }
        .stTabs [data-baseweb="tab"] { 
            height: 50px; 
            background-color: transparent; 
            font-size: 1.0rem; 
            font-weight: 600; 
            color: #64748b;
        }
        .stTabs [aria-selected="true"] { 
            background-color: #eff6ff; 
            color: #3b82f6; 
            border-bottom: 3px solid #3b82f6;
        }
        
        /* KPI 카드 폰트 */
        div[data-testid="stMetricValue"] { font-size: 1.8rem !important; }
        
        /* Streamlit 기본 헤더/푸터 숨기기 (선택) */
        header {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# 3. 인증 (Login/Logout) & 헤더 렌더링
# ==========================================
def check_login():
    if st.session_state.logged_in: return True
    try:
        qp = st.query_params
        if "session" in qp:
            saved_id = qp["session"]
            if saved_id in USERS:
                st.session_state.logged_in = True
                st.session_state.user_info = USERS[saved_id]
                st.session_state.user_info['id'] = saved_id
                return True
            elif saved_id == "guest":
                st.session_state.logged_in = True
                st.session_state.user_info = {"name": "게스트", "role": "viewer", "id": "guest"}
                return True
    except: pass
    return False

def render_login():
    col1, col2, col3 = st.columns([4, 3, 4])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
        st.markdown("<h2 style='text-align: center;'>SMT SYSTEM</h2>", unsafe_allow_html=True)
        
        with st.form("login_form"):
            id = st.text_input("ID")
            pw = st.text_input("PW", type="password")
            if st.form_submit_button("로그인", use_container_width=True):
                if id in USERS and make_hash(pw) == USERS[id]["password_hash"]:
                    st.session_state.logged_in = True
                    st.session_state.user_info = USERS[id]
                    st.session_state.user_info['id'] = id
                    st.rerun()
                else: st.error("로그인 정보가 올바르지 않습니다.")
        
        if st.button("👀 게스트(뷰어)로 입장", use_container_width=True):
            st.session_state.logged_in = True
            st.session_state.user_info = {"name": "게스트", "role": "viewer", "id": "guest"}
            st.rerun()

def render_header():
    """스마트 헤더 구현: 타이틀(좌) - 유저정보/로그아웃(우)"""
    if not st.session_state.logged_in: return
    
    u = st.session_state.user_info
    role_badge = "👑 관리자" if u['role'] == 'admin' else "👤 사용자"
    
    # CSS로 스타일링된 컨테이너 느낌을 주기 위해 컬럼 사용 + HTML 주입
    # Streamlit은 HTML 안에 버튼을 못 넣으므로 컬럼 레이아웃으로 '흉내' 냅니다.
    
    # 헤더 컨테이너 시작
    st.markdown('<div class="app-header-container">', unsafe_allow_html=True)
    
    # 내부 컬럼 레이아웃 (타이틀 vs 유저정보)
    # CSS class가 적용된 div 안에 컬럼이 렌더링되진 않으므로, 
    # 시각적 통일감을 위해 위 마크다운으로 '배경 박스'를 깔고, 그 위에 내용을 얹는 방식 대신
    # 깔끔하게 Streamlit Column을 사용하되 CSS로 해당 블록을 꾸미는 방식을 사용합니다.
    # 하지만 위 CSS (.app-header-container)는 display: flex라 아래 내용과 충돌할 수 있습니다.
    # 따라서 가장 확실한 방법: 컬럼을 나누고 각 컬럼에 HTML을 주입합니다.
    
    c_title, c_user, c_logout = st.columns([6, 3, 1])
    
    with c_title:
        st.markdown('<div class="header-title">🧠 SMT SMART SYSTEM</div>', unsafe_allow_html=True)
        
    with c_user:
        # 우측 정렬된 텍스트
        st.markdown(f'<div class="header-user">{role_badge} <b>{u["name"]}</b>님</div>', unsafe_allow_html=True)
        
    with c_logout:
        if st.button("로그아웃", key="header_logout", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_info = None
            st.rerun()
            
    # 헤더와 본문 사이 간격 조정 (CSS로 border-bottom을 줬으므로 여기선 닫는 태그 역할은 없지만 시각적 분리)
    st.markdown("</div>", unsafe_allow_html=True) 
    # 주의: 위 </div>는 실제로는 동작하지 않을 수 있음(Streamlit의 샌드박스). 
    # 하지만 load_style의 CSS가 전역적으로 적용되므로, 
    # c_title 등의 요소에 스타일을 입히는 것이 가장 안전합니다.
    # 위 코드는 레이아웃을 잡고, 아래 margin을 줍니다.

# ==========================================
# 4. 데이터 핸들링 (Google Sheets)
# ==========================================
@st.cache_resource
def get_gs_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" not in st.secrets: return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except: return None

def get_worksheet(sheet_name, create_cols=None):
    client = get_gs_connection()
    if not client: return None
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
    except: return None
    try:
        return sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        if create_cols:
            ws = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
            ws.append_row(create_cols)
            return ws
        return None

def get_now():
    return datetime.now(timezone(timedelta(hours=9)))

@st.cache_data(ttl=60)
def load_data(sheet_name, cols=None):
    try:
        ws = get_worksheet(sheet_name, create_cols=cols)
        if not ws: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()
        df = get_as_dataframe(ws, evaluate_formulas=True)
        if df.empty: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()
        df = df.dropna(how='all').dropna(axis=1, how='all')
        df = df.fillna("")
        if cols:
            for c in cols:
                if c not in df.columns: df[c] = ""
        return df
    except: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()

def clear_cache():
    load_data.clear()
    get_dashboard_stats.clear()

def save_data(df, sheet_name):
    try:
        ws = get_worksheet(sheet_name)
        if ws:
            df = df.fillna("")
            ws.clear()
            set_with_dataframe(ws, df)
            clear_cache()
            return True
        return False
    except: return False

def append_data(data_dict, sheet_name):
    try:
        ws = get_worksheet(sheet_name)
        if ws:
            try: headers = ws.row_values(1)
            except: headers = list(data_dict.keys())
            row = [str(data_dict.get(h, "")) for h in headers]
            ws.append_row(row)
            clear_cache()
            return True
        return False
    except: return False

def append_rows(rows, sheet_name, cols):
    try:
        ws = get_worksheet(sheet_name, create_cols=cols)
        if ws:
            safe_rows = [[str(c) if c is not None else "" for c in r] for r in rows]
            ws.append_rows(safe_rows)
            clear_cache()
            return True
    except: return False

def update_inventory(code, name, change, reason, user):
    df = load_data(SHEET_INVENTORY, COLS_INVENTORY)
    if not df.empty:
        df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
    
    if not df.empty and code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    df = df[df['현재고'] != 0]
    save_data(df, SHEET_INVENTORY)
    
    now_kst = get_now()
    hist = {"날짜": now_kst.strftime("%Y-%m-%d"), "품목코드": code, "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, "작성자": user, "입력시간": str(now_kst)}
    append_data(hist, SHEET_INV_HISTORY)

# ==========================================
# 5. 핵심 렌더링 함수 (Tabs)
# ==========================================
@st.cache_data(ttl=60)
def get_dashboard_stats():
    df_prod = load_data(SHEET_RECORDS, COLS_RECORDS)
    df_check = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    df_maint = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
    
    today = get_now().replace(tzinfo=None)
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    
    prod_today = 0
    if not df_prod.empty:
        df_prod['날짜'] = pd.to_datetime(df_prod['날짜'], errors='coerce')
        df_prod['수량'] = pd.to_numeric(df_prod['수량'], errors='coerce').fillna(0)
        prod_today = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == today_str]['수량'].sum()
        prod_yesterday_val = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == yesterday_str]['수량'].sum()
        delta_prod = prod_today - prod_yesterday_val
    else:
        delta_prod = 0
    
    check_cnt, ng_cnt, ng_rate = 0, 0, 0.0
    df_today_unique = pd.DataFrame()
    if not df_check.empty:
        df_check['date_only'] = df_check['date'].astype(str).str.split().str[0]
        df_check['timestamp'] = pd.to_datetime(df_check['timestamp'], errors='coerce')
        df_today = df_check[df_check['date_only'] == today_str]
        if not df_today.empty:
            df_today_unique = df_today.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
            check_cnt = len(df_today_unique)
            ng_cnt = len(df_today_unique[df_today_unique['ox'] == 'NG'])
            if check_cnt > 0: ng_rate = (ng_cnt / check_cnt) * 100

    maint_cnt = 0
    if not df_maint.empty:
        maint_cnt = len(df_maint[df_maint['날짜'].astype(str) == today_str])

    return {
        "prod_today": prod_today, "delta_prod": delta_prod,
        "check_cnt": check_cnt, "ng_cnt": ng_cnt, "ng_rate": ng_rate,
        "maint_cnt": maint_cnt, "df_prod": df_prod, "df_check_unique": df_today_unique,
        "df_maint": df_maint, "today_dt": today
    }

def render_dashboard():
    with st.spinner("데이터 분석 중..."):
        metrics = get_dashboard_stats()
        c1, c2, c3 = st.columns(3)
        c1.metric("오늘 생산량", f"{metrics['prod_today']:,.0f} EA", f"{metrics['delta_prod']:,.0f} (전일비)")
        c2.metric("금일 설비 정비", f"{metrics['maint_cnt']} 건", "확인 필요" if metrics['maint_cnt'] > 0 else "정상", delta_color="inverse")
        c3.metric("일일점검 NG", f"{metrics['ng_cnt']} 건", f"불량률 {metrics['ng_rate']:.1f}%", delta_color="inverse")
        st.divider()
        col_g1, col_g2 = st.columns([2, 1])
        with col_g1:
            st.subheader("📈 주간 생산 추이")
            df_prod = metrics['df_prod']
            if not df_prod.empty and HAS_ALTAIR:
                last_7 = metrics['today_dt'] - timedelta(days=7)
                chart_data = df_prod[df_prod['날짜'] >= last_7]
                if not chart_data.empty:
                    agg = chart_data.groupby(['날짜', '구분'])['수량'].sum().reset_index()
                    chart = alt.Chart(agg).mark_line(point=True).encode(
                        x=alt.X('날짜:T', axis=alt.Axis(format="%m-%d", title="날짜")),
                        y=alt.Y('수량:Q', title="생산량"),
                        color='구분', tooltip=['날짜', '구분', '수량']
                    ).properties(height=300)
                    st.altair_chart(chart, use_container_width=True)
                else: st.info("최근 7일 데이터가 없습니다.")
            else: st.info("데이터가 없습니다.")
        with col_g2:
            st.subheader("🚨 금일 NG 현황")
            df_ng = metrics['df_check_unique']
            if not df_ng.empty and metrics['ng_cnt'] > 0:
                ng_view = df_ng[df_ng['ox'] == 'NG'][['line', 'equip_id', 'item_name', 'value', '비고']]
                st.dataframe(ng_view, hide_index=True, use_container_width=True)
            elif metrics['ng_cnt'] == 0 and metrics['check_cnt'] > 0:
                st.success("모든 점검이 정상입니다.")
            else: st.info("금일 점검 내역이 없습니다.")

def render_production():
    tabs = ["📝 실적 등록", "📦 재고 현황", "📊 생산분석", "📑 보고서"]
    is_admin = st.session_state.user_info['role'] == 'admin'
    if is_admin: tabs.append("⚙️ 품목 기준정보")
    sub_tabs = st.tabs(tabs)
    
    with sub_tabs[0]:
        c1, c2 = st.columns([1, 1.5])
        with c1:
            if st.session_state.user_info['role'] in ['admin', 'worker']:
                with st.container(border=True):
                    st.subheader("실적 입력")
                    item_df = load_data(SHEET_ITEMS, COLS_ITEMS)
                    date = st.date_input("작업 일자", value=get_now())
                    cat = st.selectbox("공정", ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"])
                    item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
                    def on_code_change():
                        c = st.session_state.p_code.upper().strip()
                        if c in item_map: st.session_state.p_name = item_map[c]
                    code = st.text_input("품목 코드", key="p_code", on_change=on_code_change)
                    name = st.text_input("제품명", key="p_name")
                    qty = st.number_input("수량", min_value=1, value=100, key="p_qty")
                    if st.button("저장", type="primary", use_container_width=True):
                        if name:
                            rec = {"날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, "수량":qty, "입력시간":str(get_now()), "작성자":st.session_state.user_info['id']}
                            append_data(rec, SHEET_RECORDS)
                            if cat in ["후공정", "후공정 외주"]:
                                update_inventory(code, name, -qty, f"생산출고({cat})", st.session_state.user_info['id'])
                            elif cat != "배전":
                                update_inventory(code, name, qty, f"생산입고({cat})", st.session_state.user_info['id'])
                            st.toast("저장 완료", icon="✅")
                            st.session_state.p_qty = 100
                        else: st.warning("제품명을 입력하세요.")
            else: st.info("읽기 전용 모드입니다.")
        with c2:
            st.subheader("최근 등록 내역")
            df = load_data(SHEET_RECORDS, COLS_RECORDS)
            if not df.empty:
                st.dataframe(df.sort_values("입력시간", ascending=False).head(20), hide_index=True, use_container_width=True)

    with sub_tabs[1]:
        df_inv = load_data(SHEET_INVENTORY, COLS_INVENTORY)
        if not df_inv.empty:
            df_inv = df_inv[df_inv['현재고'] != 0]
            st.dataframe(df_inv, use_container_width=True)
        else: st.info("재고 데이터가 없습니다.")

    with sub_tabs[2]:
        if st.button("분석 실행", key="btn_prod_anl"):
            df = load_data(SHEET_RECORDS, COLS_RECORDS)
            if not df.empty:
                df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
                df['수량'] = pd.to_numeric(df['수량']).fillna(0)
                grp = df.groupby('제품명')['수량'].sum().reset_index().sort_values('수량', ascending=False)
                c1, c2 = st.columns([1, 2])
                with c1: st.dataframe(grp, hide_index=True, use_container_width=True)
                with c2:
                    chart = alt.Chart(grp.head(15)).mark_bar().encode(
                        x=alt.X('제품명', sort='-y'), y='수량', tooltip=['제품명', '수량']
                    )
                    st.altair_chart(chart, use_container_width=True)

    with sub_tabs[3]:
        r_date = st.date_input("보고서 날짜", get_now())
        if st.button("PDF 다운로드", key="btn_prod_pdf"):
            df = load_data(SHEET_RECORDS, COLS_RECORDS)
            df_inv = load_data(SHEET_INVENTORY, COLS_INVENTORY)
            if not df.empty:
                df['날짜'] = pd.to_datetime(df['날짜']).dt.date
                target = df[df['날짜'] == r_date]
                if not target.empty:
                    pdf_bytes = generate_production_report_pdf(target, df_inv, str(r_date))
                    if pdf_bytes: st.download_button("다운로드", pdf_bytes, f"Prod_Report_{r_date}.pdf", "application/pdf")
                else: st.warning("해당 날짜 데이터 없음")

    if is_admin:
        with sub_tabs[4]:
            st.markdown("#### ⚙️ 품목 마스터 관리")
            df_items = load_data(SHEET_ITEMS, COLS_ITEMS)
            edited = st.data_editor(df_items, num_rows="dynamic", use_container_width=True, key="editor_items")
            if st.button("변경사항 저장", key="save_items"):
                save_data(edited, SHEET_ITEMS)
                st.rerun()

def render_maintenance():
    tabs = ["📝 정비 등록", "📋 이력 조회", "📊 분석 리포트"]
    is_admin = st.session_state.user_info['role'] == 'admin'
    if is_admin: tabs.append("⚙️ 설비 기준정보")
    sub_tabs = st.tabs(tabs)

    with sub_tabs[0]:
        c1, c2 = st.columns([1, 1.5])
        with c1:
            if st.session_state.user_info['role'] in ['admin', 'worker']:
                with st.container(border=True):
                    st.subheader("정비 내역 등록")
                    eq_df = load_data(SHEET_EQUIPMENT, COLS_EQUIPMENT)
                    eq_map = dict(zip(eq_df['id'], eq_df['name'])) if not eq_df.empty else {}
                    m_date = st.date_input("날짜", value=get_now(), key="m_date")
                    m_eq = st.selectbox("설비 선택", list(eq_map.keys()), format_func=lambda x: f"[{x}] {eq_map[x]}")
                    m_type = st.selectbox("작업 구분", ["PM (예방)", "BM (고장)", "CM (개선)"])
                    m_desc = st.text_area("작업 내용")
                    m_cost = st.number_input("비용", step=1000)
                    m_down = st.number_input("비가동 시간(분)", step=10)
                    if st.button("정비 저장", type="primary", use_container_width=True):
                        rec = {"날짜":str(m_date), "설비ID":m_eq, "설비명":eq_map[m_eq], "작업구분":m_type.split()[0], 
                               "작업내용":m_desc, "비용":m_cost, "비가동시간":m_down, "교체부품":"", 
                               "입력시간":str(get_now()), "작성자":st.session_state.user_info['id']}
                        append_data(rec, SHEET_MAINTENANCE)
                        st.toast("저장 완료", icon="✅")
                        st.rerun()
            else: st.info("읽기 전용")
        with c2:
            st.subheader("최근 이력")
            df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
            if not df.empty:
                st.dataframe(df.sort_values("입력시간", ascending=False).head(20), hide_index=True, use_container_width=True)

    with sub_tabs[1]:
        df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
        st.dataframe(df, use_container_width=True)

    with sub_tabs[2]:
        if st.button("보전 분석 실행"):
            df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
            if not df.empty:
                df['비가동시간'] = pd.to_numeric(df['비가동시간']).fillna(0)
                top3 = df.groupby('설비명')['비가동시간'].sum().sort_values(ascending=False).head(3)
                st.error("🚨 비가동 시간 TOP 3 설비")
                st.table(top3.reset_index())
            else: st.info("데이터 없음")

    if is_admin:
        with sub_tabs[3]:
            st.markdown("#### ⚙️ 설비 마스터 관리")
            df_eq = load_data(SHEET_EQUIPMENT, COLS_EQUIPMENT)
            edited = st.data_editor(df_eq, num_rows="dynamic", use_container_width=True, key="editor_eq")
            if st.button("변경사항 저장", key="save_eq"):
                save_data(edited, SHEET_EQUIPMENT)
                st.rerun()

def render_daily_check():
    # [수정] "📊 현황" 탭 삭제
    tabs = ["✍ 점검 입력", "📄 리포트"]
    is_admin = st.session_state.user_info['role'] == 'admin'
    if is_admin: tabs.append("⚙️ 점검 기준정보")
    sub_tabs = st.tabs(tabs)
    
    with sub_tabs[0]:
        c1, c2 = st.columns([1, 2])
        chk_date = c1.date_input("점검일", get_now())
        df_master = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
        if not df_master.empty:
            lines = df_master['line'].unique()
            sel_line = c2.selectbox("라인 선택", lines)
            df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
            prev_data = {}
            if not df_res.empty:
                df_res['date_only'] = df_res['date'].astype(str).str.split().str[0]
                target = df_res[(df_res['date_only'] == str(chk_date)) & (df_res['line'] == sel_line)]
                if not target.empty:
                    target = target.sort_values('timestamp').drop_duplicates(['equip_id', 'item_name'], keep='last')
                    for _, r in target.iterrows():
                        prev_data[f"{r['equip_id']}_{r['item_name']}"] = r['ox']
            line_data = df_master[df_master['line'] == sel_line]
            form_data = {}
            st.markdown("---")
            for eq_name, grp in line_data.groupby("equip_name"):
                with st.container(border=True):
                    st.markdown(f"**{eq_name}**")
                    for _, row in grp.iterrows():
                        uid = f"{row['equip_id']}_{row['item_name']}"
                        prev_ox = prev_data.get(uid, "OK")
                        idx = 0 if prev_ox == "OK" else 1
                        cc1, cc2 = st.columns([3, 1])
                        cc1.write(f"- {row['item_name']} ({row['standard']})")
                        val = cc2.radio("판정", ["OK", "NG"], key=f"rad_{uid}", index=idx, horizontal=True, label_visibility="collapsed")
                        form_data[uid] = val
            if st.button("점검 결과 저장", type="primary", use_container_width=True):
                rows = []
                ts = str(get_now())
                user = st.session_state.user_info['name']
                for _, row in line_data.iterrows():
                    uid = f"{row['equip_id']}_{row['item_name']}"
                    ox = form_data.get(uid, "OK")
                    rows.append([str(chk_date), sel_line, row['equip_id'], row['item_name'], "", ox, user, ts, ""])
                append_rows(rows, SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
                st.toast("저장되었습니다.", icon="✅")
                st.rerun()

    # [수정] "📊 현황" 탭이 삭제되어 바로 리포트 탭(sub_tabs[1])으로 이동
    with sub_tabs[1]:
        d_date = st.date_input("출력 날짜", get_now(), key="pdf_date")
        if st.button("PDF 생성"):
            pdf_bytes = generate_all_daily_check_pdf(str(d_date))
            if pdf_bytes: st.download_button("다운로드", pdf_bytes, f"Check_{d_date}.pdf", "application/pdf")
            else: st.error("데이터가 없습니다.")

    if is_admin:
        with sub_tabs[2]:
            st.markdown("#### ⚙️ 점검 항목 마스터")
            df_master = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
            edited = st.data_editor(df_master, num_rows="dynamic", use_container_width=True, key="editor_chk_m")
            if st.button("변경사항 저장", key="save_chk_m"):
                save_data(edited, SHEET_CHECK_MASTER)
                st.rerun()

def generate_production_report_pdf(df_prod, df_inv, date_str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Production Report ({date_str})", 0, 1, 'C')
    pdf.set_font("Arial", "", 10)
    pdf.ln(10)
    pdf.cell(0, 10, "1. Production Result", 0, 1)
    if not df_prod.empty:
        for _, row in df_prod.iterrows():
            line = f"[{row['구분']}] {row['제품명']} : {row['수량']}"
            pdf.cell(0, 8, line.encode('latin-1', 'replace').decode('latin-1'), 1, 1)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f: return f.read()

def generate_all_daily_check_pdf(date_str):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", "B", 16)
    pdf.cell(0, 10, f"Daily Check Report ({date_str})", 0, 1, 'C')
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf.output(tmp.name)
        with open(tmp.name, "rb") as f: return f.read()