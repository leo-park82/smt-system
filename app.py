import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import json
import os
from fpdf import FPDF

# [선택] 그리기 서명 라이브러리
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS = True
except ImportError:
    HAS_CANVAS = False

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
# 1. 기본 설정 및 데이터 스키마
# ------------------------------------------------------------------
st.set_page_config(page_title="SMT 통합 관리 시스템", page_icon="🏭", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; color: #1e293b; }
    .stApp { background-color: #f8fafc; }
    .dashboard-header { background: linear-gradient(135deg, #3b82f6 0%, #1e3a8a 100%); padding: 20px 30px; border-radius: 12px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .metric-card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    
    /* 탭 스타일 개선 */
    .stTabs [data-baseweb="tab-list"] { gap: 4px; flex-wrap: wrap; }
    .stTabs [data-baseweb="tab"] { 
        height: 40px; white-space: pre-wrap; background-color: white; border-radius: 8px 8px 0px 0px; 
        box-shadow: 0 -1px 2px rgba(0,0,0,0.05); padding: 0 16px; font-size: 0.9rem;
    }
    .stTabs [aria-selected="true"] { background-color: #eff6ff; color: #1e40af; font-weight: bold; border-top: 2px solid #1e40af; }
    
    /* 라디오 버튼 가로 배치 */
    div.row-widget.stRadio > div { flex-direction: row !important; gap: 10px; }
    div.row-widget.stRadio > div > label { 
        background-color: #fff; padding: 4px 12px; border-radius: 5px; border: 1px solid #e2e8f0; 
        cursor: pointer; transition: all 0.2s; font-size: 0.85rem;
    }
    div.row-widget.stRadio > div > label:hover { background-color: #f1f5f9; }
    </style>
""", unsafe_allow_html=True)

GOOGLE_SHEET_NAME = "SMT_Database" 

# 시트 이름 정의
SHEET_RECORDS = "production_data"
SHEET_ITEMS = "item_codes"
SHEET_INVENTORY = "inventory_data"
SHEET_INV_HISTORY = "inventory_history"
SHEET_MAINTENANCE = "maintenance_data"
SHEET_EQUIPMENT = "equipment_list"
SHEET_CHECK_MASTER = "daily_check_master"
SHEET_CHECK_RESULT = "daily_check_result"
SHEET_CHECK_SIGNATURE = "daily_check_signature"

# 컬럼 정의
COLS_RECORDS = ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"]
COLS_ITEMS = ["품목코드", "제품명"]
COLS_INVENTORY = ["품목코드", "제품명", "현재고"]
COLS_INV_HISTORY = ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"]
COLS_MAINTENANCE = ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"]
COLS_EQUIPMENT = ["id", "name", "func"]
COLS_CHECK_MASTER = ["line", "equip_id", "equip_name", "item_name", "check_content", "standard", "check_type", "min_val", "max_val", "unit"]
COLS_CHECK_RESULT = ["date", "line", "equip_id", "item_name", "value", "ox", "checker", "timestamp"]
COLS_CHECK_SIGNATURE = ["date", "line", "signer", "signature_data", "timestamp"]

# [필수] 초기 마스터 데이터 (시트가 비어있을 때 복구용)
DEFAULT_CHECK_MASTER = [
    # 1 LINE
    {"line": "1 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "AIR 압력", "check_content": "게이지 확인", "standard": "0.5 MPa", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "수/자동 전환", "check_content": "스위치 작동", "standard": "정상 동작", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "HP-520S", "equip_name": "SCREEN PRINTER", "item_name": "테이블 오염", "check_content": "이물 청결", "standard": "청결", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "1809MK", "equip_name": "REFLOW", "item_name": "N2 PPM", "check_content": "산소 농도", "standard": "3000이하", "check_type": "NUMBER", "min_val": "0", "max_val": "3000", "unit": "ppm"},
    
    # 2 LINE
    {"line": "2 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "AIR 압력", "check_content": "게이지 확인", "standard": "0.5 MPa", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "2 LINE", "equip_id": "SBSF-200Y", "equip_name": "VACUUM LOADER", "item_name": "PCB 패드", "check_content": "손상 여부", "standard": "양호", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    
    # 인두기 CHECK (수분상태 2호 포함)
    {"line": "인두기 CHECK", "equip_id": "SOLD-01", "equip_name": "수동 인두기 1호기", "item_name": "팁 온도", "check_content": "온도 측정", "standard": "370±5℃", "check_type": "NUMBER", "min_val": "365", "max_val": "375", "unit": "℃"},
    {"line": "인두기 CHECK", "equip_id": "SOLD-01", "equip_name": "수동 인두기 1호기", "item_name": "수분 상태", "check_content": "스펀지 습윤", "standard": "양호", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "인두기 CHECK", "equip_id": "SOLD-02", "equip_name": "수동 인두기 2호기", "item_name": "팁 온도", "check_content": "온도 측정", "standard": "370±5℃", "check_type": "NUMBER", "min_val": "365", "max_val": "375", "unit": "℃"},
    {"line": "인두기 CHECK", "equip_id": "SOLD-02", "equip_name": "수동 인두기 2호기", "item_name": "수분 상태", "check_content": "스펀지 습윤", "standard": "양호", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},

    # 기타 라인
    {"line": "온,습도 CHECK", "equip_id": "ENV-01", "equip_name": "현장 온습도", "item_name": "실내 온도", "check_content": "온도 관리", "standard": "24±5℃", "check_type": "NUMBER", "min_val": "19", "max_val": "29", "unit": "℃"},
    {"line": "온,습도 CHECK", "equip_id": "ENV-01", "equip_name": "현장 온습도", "item_name": "실내 습도", "check_content": "습도 관리", "standard": "40~60%", "check_type": "NUMBER", "min_val": "40", "max_val": "60", "unit": "%"}
]
DEFAULT_EQUIPMENT = [{"id": "SML-120Y", "name": "IN LOADER", "func": "PCB 공급"}]

# ------------------------------------------------------------------
# 2. 구글 시트 연결
# ------------------------------------------------------------------
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
    except:
        return None
    try:
        return sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        if create_cols:
            ws = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
            ws.append_row(create_cols)
            return ws
        return None

@st.cache_data(ttl=5)
def load_data(sheet_name, cols=None):
    ws = get_worksheet(sheet_name, create_cols=cols)
    if not ws: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()
    try:
        df = get_as_dataframe(ws, evaluate_formulas=True)
        df = df.dropna(how='all').dropna(axis=1, how='all')
        if cols:
            for c in cols: 
                if c not in df.columns: df[c] = ""
        return df
    except: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()

def clear_cache():
    load_data.clear()

def save_data(df, sheet_name):
    ws = get_worksheet(sheet_name)
    if ws:
        ws.clear()
        set_with_dataframe(ws, df)
        clear_cache()
        return True
    return False

def append_data(data_dict, sheet_name):
    ws = get_worksheet(sheet_name)
    if ws:
        try: headers = ws.row_values(1)
        except: headers = list(data_dict.keys())
        ws.append_row([str(data_dict.get(h, "")) if not pd.isna(data_dict.get(h, "")) else "" for h in headers])
        clear_cache()
        return True
    return False

def append_rows(rows, sheet_name, cols):
    ws = get_worksheet(sheet_name, create_cols=cols)
    if ws:
        ws.append_rows(rows)
        clear_cache()
        return True
    return False

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
    save_data(df, SHEET_INVENTORY)
    hist = {"날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, "작성자": user, "입력시간": str(datetime.now())}
    append_data(hist, SHEET_INV_HISTORY)

# ------------------------------------------------------------------
# 3. 서버 사이드 로직
# ------------------------------------------------------------------
def get_daily_check_master_data():
    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    if df.empty or len(df) < 5:
        # 안전장치: 비어있으면 초기값 로드
        df = pd.DataFrame(DEFAULT_CHECK_MASTER)
        save_data(df, SHEET_CHECK_MASTER)
    return df

def generate_all_daily_check_pdf(date_str):
    df_m = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    df_r = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    if not df_r.empty:
        df_r = df_r[df_r['date'] == date_str]
        df_r = df_r.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')

    pdf = FPDF()
    font_path = 'NanumGothic.ttf' 
    if not os.path.exists(font_path): font_path = 'C:\\Windows\\Fonts\\malgun.ttf'
    try: pdf.add_font('Korean', '', font_path, uni=True)
    except: pass

    lines = df_m['line'].unique()
    for line in lines:
        pdf.add_page()
        try: pdf.set_font('Korean', '', 16)
        except: pdf.set_font('Arial', '', 16)
        
        pdf.cell(0, 10, f"일일점검 결과 보고서 ({date_str})", ln=True, align='C')
        pdf.set_font_size(12)
        pdf.cell(0, 10, f"Line: {line}", ln=True)
        pdf.ln(5)

        pdf.set_font_size(10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(40, 8, "설비명", 1, 0, 'C', 1)
        pdf.cell(60, 8, "점검항목", 1, 0, 'C', 1)
        pdf.cell(30, 8, "측정값", 1, 0, 'C', 1)
        pdf.cell(20, 8, "판정", 1, 0, 'C', 1)
        pdf.cell(30, 8, "점검자", 1, 1, 'C', 1)

        line_master = df_m[df_m['line'] == line]
        if not df_r.empty:
            df_final = pd.merge(line_master, df_r, on=['line', 'equip_id', 'item_name'], how='left')
        else:
            df_final = line_master.copy()
            df_final['value'] = '-'
            df_final['ox'] = '-'
            df_final['checker'] = ''

        df_final['value'] = df_final['value'].fillna('-')
        df_final['ox'] = df_final['ox'].fillna('-')
        df_final['checker'] = df_final['checker'].fillna('')

        for _, row in df_final.iterrows():
            equip_name = str(row['equip_name'])
            if len(equip_name) > 15: equip_name = equip_name[:15] + ".."
            pdf.cell(40, 8, equip_name, 1)
            pdf.cell(60, 8, str(row['item_name']), 1)
            pdf.cell(30, 8, str(row['value']), 1, 0, 'C')
            
            ox = str(row['ox'])
            if ox == 'NG': pdf.set_text_color(255, 0, 0)
            else: pdf.set_text_color(0, 0, 0)
            pdf.cell(20, 8, ox, 1, 0, 'C')
            pdf.set_text_color(0, 0, 0)
            
            pdf.cell(30, 8, str(row['checker']), 1, 1, 'C')

    return pdf.output(dest='S').encode('latin-1')

def safe_float(value, default_val=None):
    try:
        if value is None or value == "" or pd.isna(value): return default_val
        return float(value)
    except: return default_val

# ------------------------------------------------------------------
# 4. 사용자 인증
# ------------------------------------------------------------------
def make_hash(password): return hashlib.sha256(str.encode(password)).hexdigest()
USERS = {
    "park": {"name": "Park", "password_hash": make_hash("1083"), "role": "admin"},
    "suk": {"name": "Suk", "password_hash": make_hash("1734"), "role": "editor"},
    "kim": {"name": "Kim", "password_hash": make_hash("8943"), "role": "editor"}
}
def check_password():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: return True
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("SMT 통합 시스템")
        with st.form("login"):
            id = st.text_input("ID")
            pw = st.text_input("PW", type="password")
            if st.form_submit_button("로그인", use_container_width=True):
                if id in USERS and make_hash(pw) == USERS[id]["password_hash"]:
                    st.session_state.logged_in = True
                    st.session_state.user_info = USERS[id]
                    st.session_state.user_info['id'] = id
                    st.rerun()
                else: st.error("로그인 실패")
    return False

if not check_password(): st.stop()

with st.sidebar:
    st.title("Cloud SMT")
    u = st.session_state.user_info
    role_badge = "👑 Admin" if u["role"] == "admin" else "👤 User"
    st.markdown(f"<div style='padding:10px; background:#f1f5f9; border-radius:8px; margin-bottom:10px;'><b>{u['name']}</b>님 ({role_badge})</div>", unsafe_allow_html=True)
    menu = st.radio("업무 선택", ["📊 대시보드", "🏭 생산관리", "🛠 설비보전관리", "✅ 일일점검관리", "⚙ 기준정보관리"])
    st.divider()
    if st.button("로그아웃"): st.session_state.logged_in = False; st.rerun()

st.markdown(f'<div class="dashboard-header"><h3>{menu}</h3></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------
# 5. 기능 구현
# ------------------------------------------------------------------

if menu == "📊 대시보드":
    df_prod = load_data(SHEET_RECORDS, COLS_RECORDS)
    df_check = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    today = datetime.now().strftime("%Y-%m-%d")
    
    prod_today = 0
    if not df_prod.empty:
        df_prod['날짜'] = pd.to_datetime(df_prod['날짜'], errors='coerce')
        df_prod['수량'] = pd.to_numeric(df_prod['수량'], errors='coerce').fillna(0)
        prod_today = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == today]['수량'].sum()
    
    check_today = 0
    ng_today = 0
    if not df_check.empty:
        df_check_today = df_check[df_check['date'] == today]
        if not df_check_today.empty:
            df_unique = df_check_today.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
            check_today = len(df_unique)
            ng_today = len(df_unique[df_unique['ox'] == 'NG'])

    col1, col2, col3 = st.columns(3)
    col1.metric("오늘 생산량", f"{prod_today:,.0f} EA")
    col2.metric("일일점검 완료", f"{check_today} 건")
    col3.metric("NG 발생", f"{ng_today} 건", delta_color="inverse")

elif menu == "🏭 생산관리":
    t1, t2, t3, t4 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 생산 분석", "📑 일일 보고서"])
    # (생산관리 코드는 기존과 동일 유지 - 생략 없이 포함)
    with t1:
        c1, c2 = st.columns([1, 1.5])
        with c1:
            if st.session_state.user_info['role'] in ['admin', 'editor']:
                with st.container(border=True):
                    st.markdown("#### ✏️ 신규 생산 등록")
                    date = st.date_input("작업 일자")
                    cat = st.selectbox("공정 구분", ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"])
                    item_df = load_data(SHEET_ITEMS, COLS_ITEMS)
                    item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
                    def on_code():
                        c = st.session_state.code_in.upper().strip()
                        if c in item_map: st.session_state.name_in = item_map[c]
                    code = st.text_input("품목 코드", key="code_in", on_change=on_code)
                    name = st.text_input("제품명", key="name_in")
                    qty = st.number_input("생산 수량", min_value=1, value=100, key="prod_qty")
                    auto_deduct = st.checkbox("재고 차감 적용", value=True) if cat in ["후공정", "후공정 외주"] else False
                    def save_production():
                        c_code = st.session_state.code_in; c_name = st.session_state.name_in; c_qty = st.session_state.prod_qty
                        if c_name:
                            rec = {"날짜":str(date), "구분":cat, "품목코드":c_code, "제품명":c_name, "수량":c_qty, "입력시간":str(datetime.now()), "작성자": st.session_state.user_info['id']}
                            if append_data(rec, SHEET_RECORDS):
                                if cat in ["후공정", "후공정 외주"] and auto_deduct: update_inventory(c_code, c_name, -c_qty, f"생산출고({cat})", st.session_state.user_info['id'])
                                else: update_inventory(c_code, c_name, c_qty, f"생산입고({cat})", st.session_state.user_info['id'])
                                st.session_state.code_in = ""; st.session_state.name_in = ""; st.session_state.prod_qty = 100
                                st.toast("저장되었습니다.", icon="✅")
                        else: st.toast("제품명을 입력하세요.", icon="⚠️")
                    st.button("실적 저장", type="primary", use_container_width=True, on_click=save_production)
            else: st.warning("쓰기 권한이 없습니다.")
        with c2:
            st.markdown("#### 📋 최근 등록 내역")
            df = load_data(SHEET_RECORDS, COLS_RECORDS)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(50)
                if st.session_state.user_info['role'] == 'admin':
                    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic", key="prod_editor")
                    if st.button("변경사항 저장 (생산)", type="secondary"): save_data(edited_df, SHEET_RECORDS); st.rerun()
                else: st.dataframe(df, use_container_width=True, hide_index=True)
    with t2:
        df_inv = load_data(SHEET_INVENTORY, COLS_INVENTORY)
        if not df_inv.empty:
            df_inv['현재고'] = pd.to_numeric(df_inv['현재고'], errors='coerce').fillna(0).astype(int)
            search = st.text_input("🔍 재고 검색", placeholder="품목명 또는 코드")
            if search: df_inv = df_inv[df_inv['품목코드'].str.contains(search, case=False) | df_inv['제품명'].str.contains(search, case=False)]
            if st.session_state.user_info['role'] == 'admin':
                edited_inv = st.data_editor(df_inv, use_container_width=True, hide_index=True, num_rows="dynamic", key="inv_editor")
                if st.button("재고 저장"): save_data(edited_inv, SHEET_INVENTORY); st.rerun()
            else: st.dataframe(df_inv, use_container_width=True, hide_index=True)
        else: st.info("재고 데이터가 없습니다.")
    with t3:
        df = load_data(SHEET_RECORDS, COLS_RECORDS)
        if not df.empty and HAS_ALTAIR:
            df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            c1, c2 = st.columns(2)
            with c1:
                c = alt.Chart(df.groupby('날짜')['수량'].sum().reset_index()).mark_bar().encode(x='날짜', y='수량').interactive()
                st.altair_chart(c, use_container_width=True)
            with c2:
                c = alt.Chart(df.groupby('구분')['수량'].sum().reset_index()).mark_arc().encode(theta='수량', color='구분')
                st.altair_chart(c, use_container_width=True)
    with t4:
        st.markdown("#### 📑 SMT 일일 생산현황 (PDF)")
        report_date = st.date_input("보고서 날짜", datetime.now())
        df = load_data(SHEET_RECORDS, COLS_RECORDS)
        if not df.empty:
            df['날짜'] = pd.to_datetime(df['날짜']).dt.date
            daily_df = df[df['날짜'] == report_date].copy()
            daily_df = daily_df[~daily_df['구분'].astype(str).str.contains("외주")]
            if not daily_df.empty:
                st.dataframe(daily_df[['구분', '품목코드', '제품명', '수량']], use_container_width=True, hide_index=True)
            else: st.warning("해당 날짜에 생산 실적이 없습니다.")

elif menu == "🛠 설비보전관리":
    t1, t2, t3 = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "📊 분석 및 리포트"])
    # (설비보전관리 코드 유지)
    with t1:
        c1, c2 = st.columns([1, 1.5])
        with c1:
            if st.session_state.user_info['role'] in ['admin', 'editor']:
                with st.container(border=True):
                    st.markdown("#### 🔧 정비 이력 등록")
                    eq_df = load_data(SHEET_EQUIPMENT, COLS_EQUIPMENT)
                    eq_map = dict(zip(eq_df['id'], eq_df['name'])) if not eq_df.empty else {}
                    f_date = st.date_input("작업 날짜")
                    f_eq = st.selectbox("대상 설비", list(eq_map.keys()), format_func=lambda x: f"[{x}] {eq_map[x]}")
                    f_type = st.selectbox("작업 구분", ["PM (예방)", "BM (고장)", "CM (개선)"])
                    f_desc = st.text_area("작업 내용", height=80)
                    if 'parts_buffer' not in st.session_state: st.session_state.parts_buffer = []
                    col_p1, col_p2, col_p3 = st.columns([2, 1, 1])
                    p_name = col_p1.text_input("교체부품명")
                    p_cost = col_p2.number_input("비용", step=1000)
                    if col_p3.button("부품 추가"):
                        if p_name: st.session_state.parts_buffer.append({"내역": p_name, "비용": int(p_cost)})
                    if st.session_state.parts_buffer:
                        st.dataframe(pd.DataFrame(st.session_state.parts_buffer), use_container_width=True, hide_index=True)
                        if st.button("목록 초기화"): st.session_state.parts_buffer = []
                    total_cost = sum([p['비용'] for p in st.session_state.parts_buffer])
                    f_final_cost = st.number_input("총 소요 비용", value=total_cost)
                    f_down = st.number_input("비가동 시간(분)", step=10)
                    if st.button("이력 저장", type="primary", use_container_width=True):
                        parts_str = ", ".join([f"{p['내역']}" for p in st.session_state.parts_buffer])
                        rec = {"날짜": str(f_date), "설비ID": f_eq, "설비명": eq_map[f_eq], "작업구분": f_type.split()[0], "작업내용": f_desc, "교체부품": parts_str, "비용": f_final_cost, "비가동시간": f_down, "입력시간": str(datetime.now()), "작성자": st.session_state.user_info['id']}
                        append_data(rec, SHEET_MAINTENANCE)
                        st.session_state.parts_buffer = []
                        st.toast("정비 이력이 저장되었습니다.", icon="✅")
            else: st.warning("권한이 없습니다.")
        with c2:
            st.markdown("#### 📋 최근 정비 내역")
            df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(50)
                if st.session_state.user_info['role'] == 'admin':
                    edited = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic", key="maint_edit")
                    if st.button("변경사항 저장 (정비)"): save_data(edited, SHEET_MAINTENANCE); st.rerun()
                else: st.dataframe(df, use_container_width=True, hide_index=True)
    with t2:
        df_hist = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
        st.dataframe(df_hist, use_container_width=True)
    with t3:
        df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
        if not df.empty:
            df['비용'] = pd.to_numeric(df['비용'], errors='coerce').fillna(0)
            if HAS_ALTAIR:
                c = alt.Chart(df).mark_bar().encode(x='작업구분', y='비용', color='작업구분').interactive()
                st.altair_chart(c, use_container_width=True)

elif menu == "✅ 일일점검관리":
    # [수정] 탭 구성 (입력, 현황, 이력)
    tab1, tab2, tab3 = st.tabs(["✍ 점검 입력 (Native)", "📊 점검 현황", "📄 점검 이력 / PDF"])
    
    # 1. 점검 입력 (Native UI - One Page Save)
    with tab1:
        st.info("💡 PC/태블릿 공용 입력 화면입니다.")
        
        c_date = st.columns([1])[0]
        sel_date = c_date.date_input("점검 일자", datetime.now(), key="chk_date")
        
        # 전체 마스터 데이터 로드 (라인 구분 없이)
        df_master_all = get_daily_check_master_data()
        
        if df_master_all.empty:
            st.warning("점검 항목 데이터가 없습니다. 기준정보관리에서 항목을 추가해주세요.")
        
        # 라인별 탭 생성
        lines = df_master_all['line'].unique()
        line_tabs = st.tabs([f"📍 {l}" for l in lines])
        
        # 기존 결과 로드 (입력값 복원용)
        df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        prev_data = {}
        if not df_res.empty:
            df_filtered = df_res[df_res['date'] == str(sel_date)]
            for _, r in df_filtered.iterrows():
                key = f"{r['line']}_{r['equip_id']}_{r['item_name']}"
                prev_data[key] = {'val': r['value'], 'ox': r['ox']}

        # 라인별 탭 내부에 입력 폼 렌더링
        for i, line in enumerate(lines):
            with line_tabs[i]:
                line_data = df_master_all[df_master_all['line'] == line]
                
                # 설비별 그룹핑
                for equip_name, group in line_data.groupby("equip_name", sort=False):
                    st.markdown(f"**🛠 {equip_name}**")
                    
                    for _, row in group.iterrows():
                        uid = f"{row['line']}_{row['equip_id']}_{row['item_name']}"
                        widget_key = f"val_{uid}"
                        
                        # 이전 값 가져오기
                        default_val = prev_data.get(uid, {}).get('val', None)
                        default_ox = prev_data.get(uid, {}).get('ox', None)
                        
                        c1, c2, c3 = st.columns([2, 2, 1])
                        c1.markdown(f"{row['item_name']}<br><span style='font-size:0.8em; color:gray'>{row['check_content']}</span>", unsafe_allow_html=True)
                        
                        with c2:
                            if row['check_type'] == 'OX':
                                # OX 선택 (라디오 버튼)
                                # 세션 상태에 값이 없으면 초기화
                                if widget_key not in st.session_state:
                                    # 이전에 저장된 값이 있으면 그 값 사용, 없으면 None(선택안함)
                                    # st.radio는 None 선택이 안되므로, index를 사용하거나 default를 설정해야 함
                                    # 여기서는 편의상 저장된 값이 있으면 반영, 없으면 첫번째(OK)나 별도 처리
                                    # 하지만 "저장 안됨" 상태를 표현하기 위해 index=None을 지원하는 최신 Streamlit 기능 활용 가능
                                    # 여기서는 단순하게 OK/NG 두 개만 둠.
                                    pass
                                
                                idx = 0 if default_val == 'OK' else (1 if default_val == 'NG' else 0)
                                st.radio("판정", ["OK", "NG"], key=widget_key, index=idx, horizontal=True, label_visibility="collapsed")
                            
                            else:
                                # 수치 입력 (Text Input)
                                val_str = str(default_val) if default_val and default_val != 'nan' else ""
                                st.text_input(f"수치 ({row['unit']})", value=val_str, key=widget_key, placeholder="입력")
                        
                        with c3:
                            st.caption(f"기준: {row['standard']}")
                    st.divider()

        # [공통] 서명 및 전체 저장 (탭 밖, 맨 아래)
        st.markdown("---")
        st.markdown("#### ✍️ 전자 서명 및 저장")
        
        signature_data = None
        if HAS_CANVAS:
            st.caption("아래 박스에 마우스나 터치로 서명하세요.")
            canvas_result = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)", stroke_width=2, stroke_color="#000000",
                background_color="#ffffff", height=150, width=400, drawing_mode="freedraw",
                key="canvas_signature",
            )
            if canvas_result.image_data is not None:
                signature_data = "Signed via Canvas" 
        
        c_s1, c_s2 = st.columns([3, 1])
        signer_name = c_s1.text_input("점검자 성명", value=st.session_state.user_info['name'])
        
        if st.button("💾 점검 결과 전체 저장 (All Lines)", type="primary", use_container_width=True):
            if signer_name:
                rows_to_save = []
                ng_list = []
                
                # 전체 마스터 데이터를 순회하며 세션 스테이트(입력값) 수집
                for _, row in df_master_all.iterrows():
                    uid = f"{row['line']}_{row['equip_id']}_{row['item_name']}"
                    widget_key = f"val_{uid}"
                    
                    # 위젯에서 값 가져오기
                    val = st.session_state.get(widget_key)
                    
                    ox = "OK"
                    final_val = str(val) if val is not None else ""
                    
                    if row['check_type'] == 'OX':
                        if val == 'NG': ox = 'NG'
                    else:
                        # 수치 입력 검증
                        if not final_val: 
                            ox = "NG" # 빈 값은 NG
                        else:
                            try:
                                num_val = float(final_val)
                                min_v = safe_float(row['min_val'], -999999)
                                max_v = safe_float(row['max_val'], 999999)
                                if not (min_v <= num_val <= max_v): ox = 'NG'
                            except: ox = 'NG'
                    
                    if ox == 'NG': ng_list.append(f"{row['line']} > {row['item_name']}")
                    
                    rows_to_save.append([
                        str(sel_date), row['line'], row['equip_id'], row['item_name'], 
                        final_val, ox, signer_name, str(datetime.now())
                    ])
                
                if rows_to_save:
                    append_rows(rows_to_save, SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
                    sig_type = "Canvas Signature" if signature_data else "Text Signature"
                    sig_row = [str(sel_date), "ALL", signer_name, sig_type, str(datetime.now())]
                    append_rows([sig_row], SHEET_CHECK_SIGNATURE, COLS_CHECK_SIGNATURE)
                    
                    st.success("✅ 전체 점검 결과가 저장되었습니다.")
                    if ng_list: st.error(f"NG 항목 발견: {', '.join(ng_list)}")
                    time.sleep(1)
                    st.rerun()
            else:
                st.warning("성명을 입력해주세요.")

    # 2. 점검 현황
    with tab2:
        st.markdown("##### 오늘의 점검 현황")
        today = datetime.now().strftime("%Y-%m-%d")
        df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        df_master = get_daily_check_master_data()
        
        if not df_res.empty:
            df_today = df_res[df_res['date'] == today]
            if not df_today.empty:
                df_today = df_today.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
        else:
            df_today = pd.DataFrame()

        total_items = len(df_master)
        done_items = len(df_today)
        ok_items = len(df_today[df_today['ox'] == 'OK']) if not df_today.empty else 0
        ng_items = len(df_today[df_today['ox'] == 'NG']) if not df_today.empty else 0
        
        c1, c2, c3 = st.columns(3)
        c1.metric("진행률", f"{done_items} / {total_items}")
        c2.metric("OK", f"{ok_items}")
        c3.metric("NG", f"{ng_items}", delta_color="inverse")

        if ng_items > 0:
            st.error("🚨 금일 NG 발생 항목")
            st.dataframe(df_today[df_today['ox']=='NG'])
        else: 
            if done_items == 0: st.info("오늘 점검 데이터가 아직 없습니다.")
            elif done_items >= total_items * 0.9: st.success("오늘의 점검이 완료되었습니다.")

    # 3. 이력/PDF
    with tab3:
        c1, c2 = st.columns([1, 2])
        search_date = c1.date_input("조회 날짜 (PDF출력)", datetime.now())
        
        if st.button("📄 해당 날짜 전체 점검 리포트 생성 (PDF)"):
            pdf_bytes = generate_all_daily_check_pdf(str(search_date))
            if pdf_bytes:
                st.download_button("PDF 다운로드", pdf_bytes, file_name=f"DailyCheck_All_{search_date}.pdf", mime='application/pdf')
            else:
                st.warning("데이터가 없습니다.")

elif menu == "⚙ 기준정보관리":
    t1, t2, t3 = st.tabs(["📦 품목 기준정보", "🏭 설비 기준정보", "✅ 일일점검 기준정보"])
    with t1:
        if st.session_state.user_info['role'] == 'admin':
            st.markdown("#### 품목 마스터 관리")
            df = load_data(SHEET_ITEMS, COLS_ITEMS)
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="item_master")
            if st.button("품목 저장"): save_data(edited, SHEET_ITEMS); st.rerun()
        else: st.dataframe(load_data(SHEET_ITEMS, COLS_ITEMS))
    with t2:
        if st.session_state.user_info['role'] == 'admin':
            st.markdown("#### 설비 마스터 관리")
            df = load_data(SHEET_EQUIPMENT, COLS_EQUIPMENT)
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="eq_master")
            if st.button("설비 저장"): save_data(edited, SHEET_EQUIPMENT); st.rerun()
        else: st.dataframe(load_data(SHEET_EQUIPMENT, COLS_EQUIPMENT))
    with t3:
        if st.session_state.user_info['role'] == 'admin':
            st.markdown("#### 일일점검 항목 관리 (Master)")
            st.caption("여기서 수정한 내용은 '일일점검관리' -> '점검 입력'에 반영됩니다.")
            df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="check_master")
            if st.button("점검 기준 저장"): 
                save_data(edited, SHEET_CHECK_MASTER)
                st.rerun()
        else: st.dataframe(load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER))