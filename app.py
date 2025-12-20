import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import hashlib
import base64
import socket
from fpdf import FPDF
import streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# [안전 장치] 시각화 라이브러리(Altair) 로드
try:
    import altair as alt
    HAS_ALTAIR = True
except Exception as e:
    HAS_ALTAIR = False

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
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; }
    .stApp { background-color: #f8fafc; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    .smart-card {
        background: #ffffff; border-radius: 16px; padding: 24px;
        box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); border: 1px solid #f1f5f9;
    }
    .dashboard-header {
        background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
        padding: 30px 40px; border-radius: 20px; color: white; margin-bottom: 30px;
    }
    .kpi-value { font-size: 2.2rem; font-weight: 800; color: #0f172a; }
    
    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] {
        height: 45px; border-radius: 12px; background-color: #ffffff;
        border: 1px solid #e2e8f0; font-weight: 600; padding: 0 24px;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4f46e5 !important; color: white !important;
        border-color: #4f46e5 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. 구글 시트 연결 설정 (핵심 변경 사항)
# ------------------------------------------------------------------
try:
    # 1. 시트 주소 가져오기
    if "sheet_url" in st.secrets:
        SHEET_URL = st.secrets["sheet_url"]
    else:
        st.error("🚨 Secrets에 'sheet_url'이 없습니다. 설정 파일을 확인해주세요.")
        st.stop()
        
    # 2. 인증 정보 가져오기
    if "gcp_service_account" in st.secrets:
        credentials_dict = dict(st.secrets["gcp_service_account"])
    else:
        st.error("🚨 Secrets에 '[gcp_service_account]' 섹션이 없습니다.")
        st.stop()
        
except Exception as e:
    st.error(f"🚨 Secrets 설정 오류: {e}")
    st.stop()

# 구글 시트 연결 캐싱 (속도 향상)
@st.cache_resource
def init_connection():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client = gspread.authorize(creds)
    return client

def get_worksheet(sheet_name):
    client = init_connection()
    sh = client.open_by_url(SHEET_URL)
    try:
        # 시트(탭)가 있으면 가져옴
        return sh.worksheet(sheet_name)
    except:
        # 없으면 새로 만듦
        return sh.add_worksheet(title=sheet_name, rows=1000, cols=20)

# 데이터 읽기/쓰기 함수 (판다스 대신 구글시트 사용)
def load_data(sheet_name):
    try:
        ws = get_worksheet(sheet_name)
        data = ws.get_all_records()
        if not data: return pd.DataFrame()
        # 모든 컬럼을 문자열로 처리하여 오류 방지
        df = pd.DataFrame(data)
        return df
    except Exception as e:
        return pd.DataFrame()

def save_data(df, sheet_name):
    ws = get_worksheet(sheet_name)
    ws.clear() # 기존 데이터 지우기
    # 데이터프레임 헤더와 내용 업데이트 (판다스 -> 리스트 변환)
    # NaN 값은 빈 문자열로 변환
    df_str = df.fillna("").astype(str)
    ws.update([df_str.columns.values.tolist()] + df_str.values.tolist())
    return True

def append_data(data_dict, sheet_name):
    # 기존 데이터 로드 -> 행 추가 -> 전체 저장 (안전한 방식)
    df = load_data(sheet_name)
    new_df = pd.DataFrame([data_dict])
    final = pd.concat([df, new_df], ignore_index=True)
    save_data(final, sheet_name)

# ------------------------------------------------------------------
# 3. 로그인 및 보안 로직
# ------------------------------------------------------------------
def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

USERS = {
    "park": {"name": "Park", "password_hash": make_hash("1083"), "role": "admin", "desc": "System Admin"},
    "suk": {"name": "Suk", "password_hash": make_hash("1734"), "role": "editor", "desc": "Production Manager"},
    "kim": {"name": "Kim", "password_hash": make_hash("8943"), "role": "editor", "desc": "Equipment Engineer"}
}

if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "user_info" not in st.session_state: st.session_state.user_info = None

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 10, 1])
    with c2:
        st.markdown("<div style='text-align:center; margin-top:50px;'><h2>🔐 SMT Cloud System</h2></div>", unsafe_allow_html=True)
        with st.form("login_form"):
            user = st.text_input("Username")
            pw = st.text_input("Password", type="password")
            if st.form_submit_button("Login", type="primary", use_container_width=True):
                if user in USERS and make_hash(pw) == USERS[user]["password_hash"]:
                    st.session_state.logged_in = True
                    st.session_state.user_info = USERS[user]
                    st.rerun()
                else: st.error("Login Failed")
    st.stop()

CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")
IS_EDITOR = (CURRENT_USER["role"] in ["admin", "editor"])

def get_user_id(): return st.session_state.user_info["name"]

# ------------------------------------------------------------------
# 4. 시트 이름 정의 (CSV 파일명 대신 시트 탭 이름 사용)
# ------------------------------------------------------------------
SHEET_RECORDS = "records"       # 생산실적
SHEET_ITEMS = "items"           # 품목코드
SHEET_INVENTORY = "inventory"   # 재고
SHEET_MAINTENANCE = "maintenance" # 설비보전
SHEET_EQUIPMENT = "equipment"   # 설비목록

# 초기 데이터 구조가 시트에 없으면 헤더 생성 (최초 1회 실행용)
def init_headers():
    cols_map = {
        SHEET_RECORDS: ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"],
        SHEET_ITEMS: ["품목코드", "제품명"],
        SHEET_INVENTORY: ["품목코드", "제품명", "현재고"],
        SHEET_MAINTENANCE: ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"],
        SHEET_EQUIPMENT: ["id", "name", "func"]
    }
    # 설비 초기값
    DEFAULT_EQUIPMENT = [
        {"id": "CIMON-SMT34", "name": "Loader (SLD-120Y)", "func": "메거진 로딩"},
        {"id": "CIMON-SMT03", "name": "Screen Printer (HP-520S)", "func": "솔더링 설비"}
        # 필요시 더 추가
    ]

    for s_name, cols in cols_map.items():
        df = load_data(s_name)
        if df.empty:
            # 설비 시트의 경우 기본값 넣어주기
            if s_name == SHEET_EQUIPMENT:
                save_data(pd.DataFrame(DEFAULT_EQUIPMENT), s_name)
            else:
                save_data(pd.DataFrame(columns=cols), s_name)

# 앱 시작 시 헤더 확인 (최초 1회 느릴 수 있음)
if "init_done" not in st.session_state:
    with st.spinner("구글 시트 연결 중..."):
        init_headers()
    st.session_state.init_done = True

# ------------------------------------------------------------------
# 5. UI 구성 및 로직
# ------------------------------------------------------------------
with st.sidebar:
    # 로고 표시
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    
    st.title("SMT Cloud")
    st.markdown(f"User: **{CURRENT_USER['name']}**")
    
    # 메뉴 선택
    menu = st.radio("Menu", ["🏭 생산관리", "🛠️ 설비보전관리"])
    
    st.markdown("---")
    if st.button("Logout", type="secondary"):
        st.session_state.logged_in = False
        st.rerun()

CATEGORIES = ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"]

# 1. 생산관리 화면
if menu == "🏭 생산관리":
    # 탭 구성
    tab1, tab2, tab3 = st.tabs(["📝 실적등록", "📦 재고현황", "📊 대시보드"])
    
    # 1-1. 실적 등록
    with tab1:
        if IS_EDITOR:
            with st.container():
                st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                st.markdown("### ✏️ 생산 실적 등록")
                
                c1, c2 = st.columns(2)
                date = c1.date_input("작업일자", datetime.now())
                cat = c2.selectbox("공정", CATEGORIES)
                
                # 품목 코드 매핑 (시트에서 로드)
                item_df = load_data(SHEET_ITEMS)
                item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
                
                def on_code_change():
                    c = st.session_state.code_input.upper().strip()
                    if c in item_map: st.session_state.name_input = item_map[c]
                
                code = st.text_input("품목코드", key="code_input", on_change=on_code_change)
                name = st.text_input("제품명", key="name_input")
                qty = st.number_input("수량", min_value=1, value=100)
                
                if st.button("저장 (Google Sheet)", type="primary", use_container_width=True):
                    if name:
                        rec = {
                            "날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, "수량":qty,
                            "입력시간":str(datetime.now()), "작성자":get_user_id(), "수정자":"", "수정시간":""
                        }
                        append_data(rec, SHEET_RECORDS)
                        
                        # 재고 차감 로직 (반제품일 경우)
                        if cat in ["후공정", "후공정 외주"]:
                            inv_df = load_data(SHEET_INVENTORY)
                            
                            # 재고 시트가 비어있지 않고, 해당 코드가 있다면 차감
                            if not inv_df.empty and code in inv_df['품목코드'].values:
                                idx = inv_df[inv_df['품목코드'] == code].index[0]
                                try:
                                    cur = int(float(inv_df.at[idx, '현재고']))
                                except:
                                    cur = 0
                                inv_df.at[idx, '현재고'] = cur - qty
                            else:
                                # 없으면 마이너스 재고로 신규 생성
                                new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": -qty}])
                                inv_df = pd.concat([inv_df, new_row], ignore_index=True)
                            
                            save_data(inv_df, SHEET_INVENTORY)
                            
                        st.toast("클라우드 저장 완료!", icon="☁️")
                        time.sleep(1); st.rerun()
                    else: st.error("제품명을 입력하세요.")
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.warning("뷰어 권한으로는 입력할 수 없습니다.")
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### 📋 최근 실적")
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            st.dataframe(df.sort_values("입력시간", ascending=False), use_container_width=True)
        else:
            st.info("등록된 실적이 없습니다.")

    # 1-2. 재고 현황
    with tab2: 
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("### 📦 실시간 재고 (Cloud)")
        df = load_data(SHEET_INVENTORY)
        if not df.empty:
            st.dataframe(df, use_container_width=True)
        else:
            st.info("재고 데이터가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    # 1-3. 대시보드
    with tab3: 
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            total = pd.to_numeric(df['수량'], errors='coerce').fillna(0).sum()
            
            # KPI 카드
            c1, c2 = st.columns(2)
            c1.markdown(f"""
                <div class="smart-card">
                    <div style="color:#64748b; font-size:0.9rem;">Total Production</div>
                    <div class="kpi-value">{int(total):,} EA</div>
                </div>
            """, unsafe_allow_html=True)
            
            # 차트
            if HAS_ALTAIR:
                chart_data = df.groupby('날짜')['수량'].sum().reset_index()
                c = alt.Chart(chart_data).mark_line(point=True, color='#4f46e5').encode(
                    x='날짜', y='수량', tooltip=['날짜', '수량']
                ).interactive()
                st.altair_chart(c, use_container_width=True)
        else:
            st.info("데이터가 없어 대시보드를 표시할 수 없습니다.")

# 2. 설비보전관리 화면
elif menu == "🛠️ 설비보전관리":
    st.markdown("### 🛠️ 설비 보전 이력")
    
    # 이력 등록 (Expander 사용)
    with st.expander("📝 신규 이력 등록", expanded=False):
        if IS_EDITOR:
            eq_df = load_data(SHEET_EQUIPMENT)
            eq_list = eq_df['name'].tolist() if not eq_df.empty else ["직접입력"]
            
            f_date = st.date_input("일자")
            f_eq = st.selectbox("설비", eq_list)
            f_type = st.selectbox("구분", ["BM(고장)", "PM(예방)", "CM(개조)"])
            f_desc = st.text_area("내용")
            f_cost = st.number_input("비용", step=1000)
            f_time = st.number_input("비가동(분)", step=10)
            
            if st.button("이력 저장"):
                rec = {
                    "날짜": str(f_date), "설비명": f_eq, "작업구분": f_type, "작업내용": f_desc,
                    "비용": f_cost, "비가동시간": f_time, "입력시간": str(datetime.now()),
                    "작성자": get_user_id()
                }
                append_data(rec, SHEET_MAINTENANCE)
                st.success("저장되었습니다.")
                time.sleep(1); st.rerun()
        else:
            st.warning("입력 권한이 없습니다.")
    
    # 이력 조회
    df = load_data(SHEET_MAINTENANCE)
    if not df.empty:
        st.dataframe(df.sort_values("날짜", ascending=False), use_container_width=True)
    else:
        st.info("등록된 이력이 없습니다.")
    
    # 관리자 전용 설비 목록 관리
    if IS_ADMIN:
        st.markdown("<br>", unsafe_allow_html=True)
        with st.expander("⚙️ 설비 목록 관리 (관리자 전용)"):
            eq_df = load_data(SHEET_EQUIPMENT)
            edited = st.data_editor(eq_df, num_rows="dynamic", use_container_width=True)
            if st.button("설비 목록 업데이트"):
                save_data(edited, SHEET_EQUIPMENT)
                st.success("반영 완료")
                time.sleep(1); st.rerun()