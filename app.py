import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import json
import os
import tempfile
import urllib.request
from fpdf import FPDF
import streamlit.components.v1 as components

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
st.set_page_config(page_title="SMT", page_icon="🏭", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; color: #1e293b; }
    .stApp { background-color: #f8fafc; }
    .dashboard-header { background: linear-gradient(135deg, #3b82f6 0%, #1e3a8a 100%); padding: 20px 30px; border-radius: 12px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .metric-card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    
    /* 탭 스타일 개선 */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; flex-wrap: wrap; background-color: #f1f5f9; padding: 10px; border-radius: 12px; }
    .stTabs [data-baseweb="tab"] { 
        height: 45px; white-space: pre-wrap; background-color: white; border-radius: 8px; 
        box-shadow: 0 1px 2px rgba(0,0,0,0.05); padding: 0 24px; font-size: 1rem; font-weight: 500; border: none;
    }
    .stTabs [aria-selected="true"] { background-color: #3b82f6; color: white; font-weight: bold; }
    
    /* 라디오 버튼 가로 배치 */
    div.row-widget.stRadio > div { flex-direction: row !important; gap: 10px; }
    div.row-widget.stRadio > div > label { 
        background-color: #fff; padding: 4px 12px; border-radius: 5px; border: 1px solid #e2e8f0; 
        cursor: pointer; transition: all 0.2s; font-size: 0.85rem;
    }
    div.row-widget.stRadio > div > label:hover { background-color: #f1f5f9; }

    /* 일일점검 리스트 스타일 개선 */
    .check-item-container { padding: 5px 0; }
    .check-item-title { font-size: 1.15rem; font-weight: 700; color: #1e293b; margin-bottom: 4px; letter-spacing: -0.5px; }
    .check-item-content { font-size: 0.95rem; color: #64748b; margin-bottom: 2px; line-height: 1.4; }
    .check-item-badge { 
        display: inline-block; font-size: 0.8rem; font-weight: 600; color: #0f766e; 
        background-color: #f0fdfa; padding: 4px 8px; border-radius: 6px; border: 1px solid #ccfbf1;
    }
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
COLS_CHECK_RESULT = ["date", "line", "equip_id", "item_name", "value", "ox", "checker", "timestamp", "비고"]
COLS_CHECK_SIGNATURE = ["date", "line", "signer", "signature_data", "timestamp"]

# ------------------------------------------------------------------
# 2. 구글 시트 연결 및 데이터 핸들링
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
    except Exception as e:
        return pd.DataFrame(columns=cols) if cols else pd.DataFrame()

def clear_cache():
    load_data.clear()

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
            ws.append_row([str(data_dict.get(h, "")) if not pd.isna(data_dict.get(h, "")) else "" for h in headers])
            clear_cache()
            return True
        return False
    except: return False

def append_rows(rows, sheet_name, cols):
    try:
        ws = get_worksheet(sheet_name, create_cols=cols)
        if ws:
            safe_rows = [[str(cell) if cell is not None else "" for cell in row] for row in rows]
            ws.append_rows(safe_rows)
            clear_cache()
            return True
        return False
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
    
    # 현재고가 0인 항목 자동 삭제
    df = df[df['현재고'] != 0]
    
    save_data(df, SHEET_INVENTORY)
    hist = {"날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, "작성자": user, "입력시간": str(datetime.now())}
    append_data(hist, SHEET_INV_HISTORY)

def safe_float(value, default_val=None):
    try:
        if value is None or value == "" or pd.isna(value): return default_val
        return float(value)
    except: return default_val

# ------------------------------------------------------------------
# 3. 데이터 로딩 헬퍼 함수 (메뉴별 분리)
# ------------------------------------------------------------------
def load_dashboard_data():
    with st.spinner("대시보드 데이터 불러오는 중..."):
        return (
            load_data(SHEET_RECORDS, COLS_RECORDS),
            load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT),
            load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
        )

def get_daily_check_master_data():
    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    return df

def generate_all_daily_check_pdf(date_str):
    # PDF 생성 로직 (기존 유지)
    try:
        df_m = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
        df_r = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        
        checker_name = ""
        if not df_r.empty:
            df_r['date_only'] = df_r['date'].astype(str).str.split().str[0]
            df_r = df_r[df_r['date_only'] == date_str]
            df_r['timestamp'] = pd.to_datetime(df_r['timestamp'], errors='coerce')
            df_r = df_r.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
            
            checkers = df_r['checker'].unique()
            if len(checkers) > 0 and checkers[0]:
                checker_name = checkers[0]

        font_filename = 'NanumGothic.ttf'
        if not os.path.exists(font_filename):
            try:
                url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
                urllib.request.urlretrieve(url, font_filename)
            except: pass

        pdf = FPDF()
        font_name = 'Arial'
        try:
            pdf.add_font('Korean', '', font_filename, uni=True)
            font_name = 'Korean'
        except: pass

        lines = df_m['line'].unique()
        first_page = True 

        for line in lines:
            pdf.add_page()
            pdf.set_fill_color(63, 81, 181) 
            pdf.rect(0, 0, 210, 25, 'F')
            pdf.set_font(font_name, '', 20)
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(10, 5)
            pdf.cell(0, 15, "SMT Daily Check Report", 0, 0, 'L')
            
            pdf.set_font(font_name, '', 10)
            pdf.set_xy(10, 5)
            pdf.cell(0, 15, f"Date: {date_str}", 0, 0, 'R')
            
            if first_page and checker_name:
                pdf.set_xy(10, 12) 
                pdf.cell(0, 15, f"Checker: {checker_name}", 0, 0, 'R')
                first_page = False 

            pdf.ln(25)
            
            line_master = df_m[df_m['line'] == line]
            if not df_r.empty:
                df_final = pd.merge(line_master, df_r, on=['line', 'equip_id', 'item_name'], how='left')
            else:
                df_final = line_master.copy()
                df_final['value'] = '-'
                df_final['ox'] = '-'
                df_final['checker'] = ''
            
            fill_values = {'value': '-', 'ox': '-', 'checker': ''}
            if '비고' in df_final.columns: fill_values['비고'] = ''
            
            df_final = df_final.fillna(fill_values)
            
            total = len(df_final)
            ok = len(df_final[df_final['ox'] == 'OK'])
            ng = len(df_final[df_final['ox'] == 'NG'])
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_font(font_name, '', 16)
            pdf.cell(0, 10, f"{line}", 0, 1, 'L')
            pdf.set_font(font_name, '', 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 6, f"Total: {total}  |  OK: {ok}  |  NG: {ng}", 0, 1, 'L')
            pdf.ln(4)
            
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(240, 242, 245)
            pdf.set_text_color(60, 60, 60)
            pdf.set_draw_color(220, 220, 220)
            pdf.set_line_width(0.3)
            pdf.set_font(font_name, '', 10)
            
            headers = ["설비명", "점검항목", "기준", "측정값", "판정", "점검자"]
            widths = [45, 65, 30, 20, 15, 15]
            
            for i, h in enumerate(headers):
                pdf.cell(widths[i], 10, h, 1, 0, 'C', 1)
            pdf.ln()

            fill = False
            pdf.set_fill_color(250, 250, 250) 
            
            for _, row in df_final.iterrows():
                equip_name = str(row['equip_name'])
                if len(equip_name) > 18: equip_name = equip_name[:17] + ".."
                
                pdf.cell(45, 8, equip_name, 1, 0, 'L', fill)
                pdf.cell(65, 8, str(row['item_name']), 1, 0, 'L', fill)
                pdf.cell(30, 8, str(row['standard']), 1, 0, 'C', fill)
                pdf.cell(20, 8, str(row['value']), 1, 0, 'C', fill)
                
                ox = str(row['ox'])
                if ox == 'NG': 
                    pdf.set_text_color(220, 38, 38)
                    pdf.set_font(font_name, 'U', 10)
                elif ox == 'OK':
                    pdf.set_text_color(22, 163, 74)
                    pdf.set_font(font_name, '', 10)
                else:
                    pdf.set_text_color(150, 150, 150)
                    pdf.set_font(font_name, '', 10)
                    
                pdf.cell(15, 8, ox, 1, 0, 'C', fill)
                pdf.set_text_color(0, 0, 0)
                pdf.set_font(font_name, '', 10)
                pdf.cell(15, 8, str(row['checker']), 1, 1, 'C', fill)
                pdf.ln()
                
                if ox == 'NG' and '비고' in row and row['비고']:
                    pdf.set_font(font_name, 'I', 9)
                    pdf.set_text_color(100, 100, 100)
                    pdf.cell(190, 6, f"   └ 조치내역: {row['비고']}", 1, 1, 'L', fill)
                    pdf.set_font(font_name, '', 10)
                    pdf.set_text_color(0, 0, 0)

                fill = not fill
            pdf.ln(10)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf.output(tmp_file.name)
            with open(tmp_file.name, "rb") as f:
                pdf_bytes = f.read()
        os.unlink(tmp_file.name)
        return pdf_bytes
    except Exception as e:
        return None

def generate_production_report_pdf(df_prod, date_str):
    # 생산 일일 보고서 PDF 로직 (기존 유지)
    try:
        font_filename = 'NanumGothic.ttf'
        if not os.path.exists(font_filename):
            try:
                url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
                urllib.request.urlretrieve(url, font_filename)
            except: pass

        pdf = FPDF()
        font_name = 'Arial'
        try:
            pdf.add_font('Korean', '', font_filename, uni=True)
            font_name = 'Korean'
        except: pass
        
        pdf.add_page()
        
        # Header
        pdf.set_fill_color(50, 50, 50) 
        pdf.rect(0, 0, 210, 25, 'F')
        pdf.set_font(font_name, '', 20)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 5)
        pdf.cell(0, 15, "Production Daily Report", 0, 0, 'L')
        pdf.set_font(font_name, '', 10)
        pdf.set_xy(10, 5)
        pdf.cell(0, 15, f"Date: {date_str}", 0, 0, 'R')
        pdf.ln(25)
        
        # Table Header
        pdf.set_text_color(0, 0, 0)
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font(font_name, '', 10)
        
        headers = ["구분", "품목코드", "제품명", "수량", "작성자"]
        widths = [25, 35, 80, 25, 25]
        
        for i, h in enumerate(headers):
            pdf.cell(widths[i], 10, h, 1, 0, 'C', 1)
        pdf.ln()
        
        # Body
        fill = False
        pdf.set_fill_color(250, 250, 250)
        
        total_qty = 0
        for _, row in df_prod.iterrows():
            pdf.cell(widths[0], 8, str(row['구분']), 1, 0, 'C', fill)
            pdf.cell(widths[1], 8, str(row['품목코드']), 1, 0, 'C', fill)
            
            p_name = str(row['제품명'])
            if len(p_name) > 25: p_name = p_name[:24] + ".."
            pdf.cell(widths[2], 8, p_name, 1, 0, 'L', fill)
            
            qty = int(float(str(row['수량']).replace(',','')))
            total_qty += qty
            pdf.cell(widths[3], 8, f"{qty:,}", 1, 0, 'R', fill)
            pdf.cell(widths[4], 8, str(row['작성자']), 1, 1, 'C', fill)
            
            fill = not fill
            
        # Total
        pdf.ln(2)
        pdf.set_font(font_name, '', 12)
        pdf.cell(0, 10, f"Total Quantity: {total_qty:,} EA", 0, 1, 'R')

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf.output(tmp_file.name)
            with open(tmp_file.name, "rb") as f:
                pdf_bytes = f.read()
        os.unlink(tmp_file.name)
        return pdf_bytes
    except: return None

# ------------------------------------------------------------------
# 4. 사용자 인증
# ------------------------------------------------------------------
def make_hash(password): return hashlib.sha256(str.encode(password)).hexdigest()
USERS = {
    "박종선": {"name": "박종선", "password_hash": make_hash("1083"), "role": "admin"},
    "김윤석": {"name": "김윤석", "password_hash": make_hash("1734"), "role": "editor"},
    "kim": {"name": "Kim", "password_hash": make_hash("8943"), "role": "editor"}
}
def check_password():
    if "logged_in" not in st.session_state: 
        st.session_state.logged_in = False
    
    if not st.session_state.logged_in:
        try:
            qp = st.query_params
            if "session" in qp:
                saved_id = qp["session"]
                if saved_id in USERS:
                    st.session_state.logged_in = True
                    st.session_state.user_info = USERS[saved_id]
                    st.session_state.user_info['id'] = saved_id
        except: pass

    if st.session_state.logged_in: return True
    
    col1, col2, col3 = st.columns([5, 2, 5])
    with col2:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        st.title("SMT")
        with st.form("login"):
            id = st.text_input("ID")
            pw = st.text_input("PW", type="password")
            if st.form_submit_button("로그인", use_container_width=True):
                if id in USERS and make_hash(pw) == USERS[id]["password_hash"]:
                    st.session_state.logged_in = True
                    st.session_state.user_info = USERS[id]
                    st.session_state.user_info['id'] = id
                    try: st.query_params["session"] = id
                    except: pass
                    st.rerun()
                else: st.error("로그인 실패")
    return False

if not check_password(): st.stop()

with st.sidebar:
    if os.path.exists("logo.png"):
        st.image("logo.png", width=180)
    st.title("SMT")
    u = st.session_state.user_info
    role_badge = "👑 Admin" if u["role"] == "admin" else "👤 User"
    st.markdown(f"<div style='padding:10px; background:#f1f5f9; border-radius:8px; margin-bottom:10px;'><b>{u['name']}</b>님 ({role_badge})</div>", unsafe_allow_html=True)
    if st.button("로그아웃", use_container_width=True): 
        st.session_state.logged_in = False
        try: st.query_params.clear()
        except: pass
        st.rerun()

# ------------------------------------------------------------------
# 5. 메인 기능 구현 (Tab 구조 도입)
# ------------------------------------------------------------------

# 메인 탭 생성
main_tabs = st.tabs(["📊 대시보드", "🏭 생산관리", "🛠 설비보전", "✅ 일일점검", "⚙ 기준정보"])

# --- 1. 대시보드 탭 ---
with main_tabs[0]:
    try:
        # 데이터 분리 로딩
        df_prod, df_check, df_maint = load_dashboard_data()
        
        today = datetime.now()
        today_str = today.strftime("%Y-%m-%d")
        yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        this_month_start = today.replace(day=1)
        
        # 1. 생산량 KPI
        prod_today_val = 0
        prod_yesterday_val = 0
        
        if not df_prod.empty:
            df_prod['날짜'] = pd.to_datetime(df_prod['날짜'], errors='coerce')
            df_prod['수량'] = pd.to_numeric(df_prod['수량'], errors='coerce').fillna(0)
            
            prod_today_val = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == today_str]['수량'].sum()
            prod_yesterday_val = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == yesterday_str]['수량'].sum()
        
        delta_prod = prod_today_val - prod_yesterday_val
        
        # 2. 품질 KPI
        check_today_cnt = 0
        ng_today_cnt = 0
        ng_rate = 0.0
        
        if not df_check.empty:
            df_check['date_only'] = df_check['date'].astype(str).str.split().str[0]
            df_check['timestamp'] = pd.to_datetime(df_check['timestamp'], errors='coerce')
            
            df_today_chk = df_check[df_check['date_only'] == today_str]
            if not df_today_chk.empty:
                df_today_unique = df_today_chk.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
                check_today_cnt = len(df_today_unique)
                ng_today_cnt = len(df_today_unique[df_today_unique['ox'] == 'NG'])
                if check_today_cnt > 0:
                    ng_rate = (ng_today_cnt / check_today_cnt) * 100

        # 3. 보전 KPI
        maint_today_cnt = 0
        if not df_maint.empty:
            maint_today_cnt = len(df_maint[df_maint['날짜'].astype(str) == today_str])

        col1, col2, col3 = st.columns(3)
        col1.metric("오늘 생산량", f"{prod_today_val:,.0f} EA", f"{delta_prod:,.0f} (전일비)")
        col2.metric("금일 설비 정비", f"{maint_today_cnt} 건", "특이사항 없음" if maint_today_cnt == 0 else "확인 필요", delta_color="inverse")
        col3.metric("일일점검 (완료/NG)", f"{check_today_cnt} 건 / {ng_today_cnt} 건", f"불량률: {ng_rate:.1f}%", delta_color="inverse")

        st.markdown("---")

        c1, c2 = st.columns([2, 1])

        with c1:
            st.subheader("📈 주간 생산 추이 & 유형")
            if not df_prod.empty and HAS_ALTAIR:
                last_7_days = today - timedelta(days=7)
                chart_data = df_prod[df_prod['날짜'] >= last_7_days]
                
                if not chart_data.empty:
                    chart_agg = chart_data.groupby(['날짜', '구분'])['수량'].sum().reset_index()
                    
                    chart = alt.Chart(chart_agg).mark_line(point=True).encode(
                        x=alt.X('날짜:T', axis=alt.Axis(format="%m-%d", labelAngle=0, title="날짜")),
                        y=alt.Y('수량:Q', axis=alt.Axis(labelAngle=0, title="생\n산\n량", titleAngle=0, titlePadding=20, titleFontWeight="bold", titleFontSize=14)),
                        color=alt.Color('구분', legend=alt.Legend(title="공정 구분")),
                        tooltip=['날짜', '구분', '수량']
                    ).properties(height=300)
                    
                    st.altair_chart(chart, use_container_width=True)
                else:
                    st.info("최근 7일간 생산 데이터가 없습니다.")
            else:
                st.info("생산 데이터가 없습니다.")

        with c2:
            st.subheader("🏭 월간 생산 품목 비율")
            if not df_prod.empty:
                df_month_prod = df_prod[(df_prod['날짜'] >= this_month_start) & (df_prod['날짜'] <= today)]
                
                if not df_month_prod.empty:
                    pie_data = df_month_prod.groupby('구분')['수량'].sum().reset_index()
                    total_q = pie_data['수량'].sum()
                    pie_data['비율'] = (pie_data['수량'] / total_q * 100).round(1)
                    pie_data['Label'] = pie_data['수량'].astype(str) + " (" + pie_data['비율'].astype(str) + "%)"
                    pie_data['DisplayLabel'] = pie_data.apply(lambda x: x['Label'] if x['비율'] > 3 else "", axis=1)

                    base = alt.Chart(pie_data).encode(
                        theta=alt.Theta("수량", stack=True),
                        color=alt.Color("구분", legend=alt.Legend(title="공정 구분", orient="bottom")) 
                    )
                    pie = base.mark_arc(outerRadius=120, innerRadius=60).encode(
                        tooltip=["구분", "수량", "비율"]
                    )
                    text = base.mark_text(radius=140).encode(
                        text="DisplayLabel",
                        order=alt.Order("구분"),
                        color=alt.value("black") 
                    )
                    st.altair_chart((pie + text).properties(height=400), use_container_width=True)
                else:
                    st.info("이번 달 생산 실적이 없습니다.")
            else:
                st.info("데이터 없음")

        st.markdown("---")
        
        c3, c4 = st.columns(2)
        with c3:
            st.subheader("🚨 실시간 NG 현황 (Today)")
            if not df_check.empty and ng_today_cnt > 0:
                ng_df = df_today_unique[df_today_unique['ox'] == 'NG'][['line', 'equip_id', 'item_name', 'value', 'checker', '비고']]
                st.dataframe(ng_df, hide_index=True, use_container_width=True)
            elif ng_today_cnt == 0:
                st.success("🎉 현재까지 발견된 NG 항목이 없습니다. (All Green)")
            else:
                st.info("점검 데이터가 없습니다.")

        with c4:
            st.subheader("🛠 최근 설비 정비 이력 (Last 5)")
            if not df_maint.empty:
                recent_maint = df_maint.sort_values("날짜", ascending=False).head(5)[['날짜', '설비명', '작업구분', '작업내용']]
                st.dataframe(recent_maint, hide_index=True, use_container_width=True)
            else:
                st.info("정비 이력이 없습니다.")

    except Exception as e:
        st.error(f"대시보드 로딩 중 오류 발생: {e}")

# --- 2. 생산관리 탭 ---
with main_tabs[1]:
    try:
        t1, t2, t3, t4 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 스마트 생산 분석", "📑 일일 보고서"])
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
                    df_display = df.sort_values("입력시간", ascending=False).head(50)
                    df_display.insert(0, "삭제", False)
                    edited_df = st.data_editor(
                        df_display, 
                        hide_index=True, 
                        use_container_width=True,
                        column_config={"삭제": st.column_config.CheckboxColumn(required=True)},
                        disabled=COLS_RECORDS, 
                        key="recent_records_editor"
                    )
                    if st.button("선택 항목 삭제", type="secondary"):
                        to_delete = edited_df[edited_df["삭제"] == True]
                        if not to_delete.empty:
                            try:
                                ws = get_worksheet(SHEET_RECORDS)
                                all_records = get_as_dataframe(ws)
                                for t in to_delete['입력시간']:
                                    idx_to_drop = all_records[all_records['입력시간'].astype(str) == str(t)].index
                                    all_records = all_records.drop(idx_to_drop)
                                save_data(all_records, SHEET_RECORDS)
                                st.success(f"{len(to_delete)}건 삭제 완료")
                                time.sleep(1)
                                st.rerun()
                            except Exception as e: st.error(f"삭제 중 오류 발생: {e}")
                        else: st.info("삭제할 항목을 선택해주세요.")

        with t2:
            df_inv = load_data(SHEET_INVENTORY, COLS_INVENTORY)
            if not df_inv.empty:
                df_inv = df_inv[df_inv['현재고'] != 0]
                df_inv.insert(0, "삭제", False)
                edited_inv = st.data_editor(
                    df_inv,
                    hide_index=True,
                    use_container_width=True,
                    column_config={"삭제": st.column_config.CheckboxColumn(required=True)},
                    disabled=COLS_INVENTORY,
                    key="inventory_editor"
                )
                if st.button("선택 항목 삭제", type="primary", key="delete_inv_btn"):
                    to_delete = edited_inv[edited_inv["삭제"] == True]
                    if not to_delete.empty:
                        try:
                            ws = get_worksheet(SHEET_INVENTORY)
                            all_inv = get_as_dataframe(ws)
                            for code in to_delete['품목코드']:
                                idx_to_drop = all_inv[all_inv['품목코드'] == code].index
                                all_inv = all_inv.drop(idx_to_drop)
                            save_data(all_inv, SHEET_INVENTORY)
                            st.success(f"{len(to_delete)}개 품목 삭제 완료")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e: st.error(f"삭제 중 오류 발생: {e}")
                    else: st.info("삭제할 항목을 선택해주세요.")
            else: st.info("재고 데이터가 없습니다.")

        with t3:
            st.markdown("#### 📊 스마트 생산 분석")
            df = load_data(SHEET_RECORDS, COLS_RECORDS)
            if not df.empty:
                df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
                df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
                df = df.dropna(subset=['날짜']) 
                if df.empty: st.info("유효한 생산 데이터가 없습니다.")
                else:
                    min_date = df['날짜'].min().date()
                    max_date = df['날짜'].max().date()
                    c_filter1, c_filter2 = st.columns([1, 1])
                    with c_filter1:
                        default_start = max_date - timedelta(days=29)
                        if default_start < min_date: default_start = min_date
                        date_range = st.date_input("분석 기간 선택", value=(default_start, max_date), min_value=min_date, max_value=max_date)
                    
                    if isinstance(date_range, tuple) and len(date_range) == 2:
                        start_date, end_date = date_range
                        mask = (df['날짜'].dt.date >= start_date) & (df['날짜'].dt.date <= end_date)
                        df_filtered = df[mask]
                    else:
                        st.warning("종료 날짜를 선택해주세요.")
                        df_filtered = df.copy()

                    if not df_filtered.empty:
                        total_qty = df_filtered['수량'].sum()
                        daily_avg = total_qty / len(df_filtered['날짜'].unique()) if len(df_filtered['날짜'].unique()) > 0 else 0
                        top_cat = df_filtered.groupby('구분')['수량'].sum().idxmax() if not df_filtered.empty else "-"
                        
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("총 생산량", f"{total_qty:,.0f} EA")
                        m2.metric("일일 평균", f"{daily_avg:,.0f} EA")
                        m3.metric("최다 생산 공정", top_cat)
                        m4.metric("가동 일수", f"{len(df_filtered['날짜'].unique())} 일")
                        st.divider()

                        col_chart1, col_chart2 = st.columns([2, 1])
                        with col_chart1:
                            st.markdown("##### 📅 일별/공정별 생산 추이")
                            if HAS_ALTAIR:
                                chart_data = df_filtered.groupby(['날짜', '구분'])['수량'].sum().reset_index()
                                bar = alt.Chart(chart_data).mark_bar().encode(
                                    x=alt.X('날짜:T', axis=alt.Axis(format="%y-%m-%d", labelAngle=0, title="날짜")),
                                    y=alt.Y('수량:Q', axis=alt.Axis(title="생\n산\n량", titleAngle=0, titlePadding=20, titleFontWeight="bold", titleFontSize=14)),
                                    color=alt.Color('구분', legend=alt.Legend(title="공정", orient="top")),
                                    tooltip=['날짜', '구분', '수량']
                                ).properties(height=350)
                                st.altair_chart(bar, use_container_width=True)
                        with col_chart2:
                            st.markdown("##### 🥧 기간 내 공정 점유율")
                            if HAS_ALTAIR:
                                pie_data = df_filtered.groupby('구분')['수량'].sum().reset_index()
                                base = alt.Chart(pie_data).encode(
                                    theta=alt.Theta("수량", stack=True),
                                    color=alt.Color("구분", legend=None)
                                )
                                pie = base.mark_arc(outerRadius=120, innerRadius=0).encode(tooltip=["구분", "수량"])
                                text = base.mark_text(radius=140).encode(
                                    text=alt.Text("수량", format=",.0f"),
                                    order=alt.Order("구분"),
                                    color=alt.value("black")
                                )
                                st.altair_chart(pie + text, use_container_width=True)
                                st.dataframe(pie_data.sort_values('수량', ascending=False).assign(비중=lambda x: (x['수량']/x['수량'].sum()*100).round(1).astype(str)+'%'), hide_index=True, use_container_width=True)
                    else: st.info("선택한 기간에 데이터가 없습니다.")
            else: st.info("생산 데이터가 없습니다.")

        with t4:
            st.markdown("#### 📑 SMT 일일 생산현황 (PDF)")
            c_rep1, c_rep2 = st.columns([1, 2])
            report_date = c_rep1.date_input("보고서 날짜", datetime.now())
            if c_rep2.button("📄 PDF 다운로드"):
                df = load_data(SHEET_RECORDS, COLS_RECORDS)
                if not df.empty:
                    df['날짜'] = pd.to_datetime(df['날짜']).dt.date
                    daily_df = df[df['날짜'] == report_date].copy()
                    daily_df = daily_df[~daily_df['구분'].astype(str).str.contains("외주")]
                    if not daily_df.empty:
                        pdf_bytes = generate_production_report_pdf(daily_df, str(report_date))
                        if pdf_bytes:
                            st.download_button(label="PDF 파일 받기", data=pdf_bytes, file_name=f"Production_Report_{report_date}.pdf", mime='application/pdf')
                        else: st.error("PDF 생성 실패")
                    else: st.warning("해당 날짜에 생산 실적이 없습니다.")
                else: st.warning("데이터가 없습니다.")
            
            df = load_data(SHEET_RECORDS, COLS_RECORDS)
            if not df.empty:
                df['날짜'] = pd.to_datetime(df['날짜']).dt.date
                daily_df = df[df['날짜'] == report_date].copy()
                daily_df = daily_df[~daily_df['구분'].astype(str).str.contains("외주")]
                if not daily_df.empty:
                    st.dataframe(daily_df[['구분', '품목코드', '제품명', '수량']], use_container_width=True, hide_index=True)
                else: st.warning("해당 날짜에 생산 실적이 없습니다.")
    except Exception as e: st.error(f"생산관리 로딩 중 오류 발생: {e}")

# --- 3. 설비보전 탭 ---
with main_tabs[2]:
    try:
        t1, t2, t3 = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "📊 분석 및 리포트"])
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
                            st.toast("정비 이력이 저장되었습니다.", icon="✅")
                else: st.warning("권한이 없습니다.")
            with c2:
                st.markdown("#### 📋 최근 정비 내역")
                df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
                if not df.empty:
                    df = df.sort_values("입력시간", ascending=False).head(50)
                    st.dataframe(df, use_container_width=True, hide_index=True)
        with t2:
            df_hist = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
            st.dataframe(df_hist, use_container_width=True)
        with t3:
            st.markdown("#### 📊 설비 보전 분석")
            df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
            if not df.empty:
                df['비용'] = pd.to_numeric(df['비용'], errors='coerce').fillna(0)
                df['비가동시간'] = pd.to_numeric(df['비가동시간'], errors='coerce').fillna(0)
                total_cost = df['비용'].sum()
                total_downtime = df['비가동시간'].sum()
                count_maint = len(df)
                top_type = df['작업구분'].mode()[0] if not df.empty else "-"
                
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("총 소요 비용", f"{total_cost:,.0f} 원")
                k2.metric("총 비가동 시간", f"{total_downtime} 분")
                k3.metric("총 정비 건수", f"{count_maint} 건")
                k4.metric("주요 정비 유형", top_type)
                st.divider()
                
                if HAS_ALTAIR:
                    chart_col1, chart_col2 = st.columns(2)
                    with chart_col1:
                        st.markdown("##### 🥧 정비 유형별 비율")
                        base = alt.Chart(df).encode(theta=alt.Theta("count()", stack=True), color=alt.Color("작업구분"))
                        pie = base.mark_arc(outerRadius=120).encode(tooltip=["작업구분", "count()"])
                        text = base.mark_text(radius=140).encode(text=alt.Text("count()"), order=alt.Order("작업구분"), color=alt.value("black"))
                        st.altair_chart(pie + text, use_container_width=True)
                    with chart_col2:
                        st.markdown("##### 💸 설비별 유지보수 비용")
                        bar = alt.Chart(df).mark_bar().encode(x=alt.X('설비명', axis=alt.Axis(labelAngle=0)), y=alt.Y('sum(비용)', axis=alt.Axis(title="비\n용", titleAngle=0, titlePadding=20)), color='설비명', tooltip=['설비명', 'sum(비용)']).interactive()
                        st.altair_chart(bar, use_container_width=True)
            else: st.info("정비 데이터가 없습니다.")
    except: st.error("보전관리 페이지 오류")

# --- 4. 일일점검 탭 ---
with main_tabs[3]:
    try:
        tab1, tab2, tab3 = st.tabs(["✍ 점검 입력 (Native)", "📊 점검 현황", "📄 점검 이력 / PDF"])
        with tab1:
            if st.session_state.get('scroll_to_top'):
                components.html("""<script>var body = window.parent.document.querySelector(".main"); if (body) { body.scrollTop = 0; } window.parent.scrollTo(0, 0);</script>""", height=0)
                st.session_state['scroll_to_top'] = False
            
            st.info("💡 PC/태블릿 공용 입력 화면입니다.")
            st.caption("ℹ️ 라인을 선택하고 점검 결과를 입력하세요.")
            
            c_date, c_btn = st.columns([2, 1])
            with c_date:
                sel_date = st.date_input("점검 일자", datetime.now(), key="chk_date")
            
            df_res_check = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
            df_master_check = get_daily_check_master_data()
            
            if df_master_check.empty:
                st.warning("점검 항목 데이터가 없습니다.")
            else:
                lines = df_master_check['line'].unique()
                if len(lines) > 0:
                    st.markdown("### 📍 라인 선택")
                    selected_line = st.radio("점검할 라인을 선택하세요:", lines, horizontal=True, key="line_selector", label_visibility="collapsed")
                    line_data = df_master_check[df_master_check['line'] == selected_line]
                    
                    with c_btn:
                        st.write("") 
                        st.write("") 
                        if st.button(f"✅ {selected_line} 일괄 OK", type="secondary", use_container_width=True):
                            for _, row in line_data.iterrows():
                                uid = f"{row['line']}_{row['equip_id']}_{row['item_name']}"
                                widget_key = f"val_{uid}_{sel_date}"
                                if row['check_type'] == 'OX' and '온,습도' not in row['line']:
                                    st.session_state[widget_key] = "OK"
                            st.rerun()

                    prev_data = {}
                    if not df_res_check.empty:
                        df_res_check['date_only'] = df_res_check['date'].astype(str).str.split().str[0]
                        df_filtered = df_res_check[df_res_check['date_only'] == str(sel_date)]
                        df_filtered['timestamp'] = pd.to_datetime(df_filtered['timestamp'], errors='coerce')
                        df_filtered = df_filtered.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
                        for _, r in df_filtered.iterrows():
                            key = f"{r['line']}_{r['equip_id']}_{r['item_name']}"
                            memo_val = r['비고'] if '비고' in r else ""
                            prev_data[key] = {'val': r['value'], 'ox': r['ox'], 'memo': memo_val}

                    st.markdown(f"#### 📝 {selected_line} 점검 입력")
                    for equip_name, group in line_data.groupby("equip_name", sort=False):
                        st.markdown(f"**🛠 {equip_name}**")
                        with st.container(border=True):
                            for _, row in group.iterrows():
                                uid = f"{row['line']}_{row['equip_id']}_{row['item_name']}"
                                widget_key = f"val_{uid}_{sel_date}"
                                memo_key = f"memo_{uid}_{sel_date}"
                                default_val = prev_data.get(uid, {}).get('val', None)
                                default_memo = prev_data.get(uid, {}).get('memo', "")
                                c1, c2, c3 = st.columns([2, 2, 1])
                                item_html = f"""<div class="check-item-container"><div class="check-item-title">{row['item_name']}</div><div class="check-item-content">{row['check_content']}</div></div>"""
                                c1.markdown(item_html, unsafe_allow_html=True)
                                check_type = row['check_type']
                                is_numeric = False
                                if '온,습도' in row['line'] or '온습도' in row['line'] or check_type == 'NUMBER': is_numeric = True
                                is_ng = False
                                with c2:
                                    if not is_numeric and check_type == 'OX':
                                        idx = None
                                        if default_val == 'OK': idx = 0
                                        elif default_val == 'NG': idx = 1
                                        if widget_key in st.session_state:
                                            if st.session_state[widget_key] == "OK": idx = 0
                                            elif st.session_state[widget_key] == "NG": idx = 1
                                        val = st.radio("판정", ["OK", "NG"], key=widget_key, index=idx, horizontal=True, label_visibility="collapsed")
                                        if val == 'NG': is_ng = True
                                    else:
                                        num_val = None
                                        if default_val and default_val != 'nan' and default_val != '-':
                                            try: num_val = float(default_val)
                                            except: num_val = None
                                        val = st.number_input(f"수치 ({row['unit']})", value=num_val, key=widget_key, placeholder="입력", step=0.1, format="%.1f")
                                        if val is not None:
                                            try:
                                                min_v = safe_float(row['min_val'], -999999)
                                                max_v = safe_float(row['max_val'], 999999)
                                                if not (min_v <= val <= max_v): is_ng = True
                                            except: pass
                                with c3:
                                    std_html = f"<div class='check-item-badge'>기준: {row['standard']}</div>"
                                    st.markdown(std_html, unsafe_allow_html=True)
                                if is_ng:
                                    st.text_input("⚠️ 장비점검 (조치내역)", value=default_memo, key=memo_key, placeholder="NG 사유 및 조치내용 입력")
                            
                    st.divider()
                    st.markdown("#### ✍️ 전자 서명 (필수)")
                    signature_data = None
                    if HAS_CANVAS:
                        canvas_result = st_canvas(fill_color="rgba(255, 165, 0, 0.3)", stroke_width=2, stroke_color="#000000", background_color="#ffffff", height=150, width=400, drawing_mode="freedraw", key=f"canvas_{selected_line}")
                        if canvas_result.image_data is not None: signature_data = canvas_result.image_data
                    c_s1, c_s2 = st.columns([3, 1])
                    signer_name = c_s1.text_input("점검자 성명", value=st.session_state.user_info['name'], key=f"signer_{selected_line}")
                    st.caption("⚠️ 저장 시 서명 및 입력값이 최종 확정됩니다.")
                    
                    if st.button(f"💾 {selected_line} 점검 완료 및 저장", type="primary", use_container_width=True):
                        missing_values = []
                        rows_to_save = []
                        for _, row in line_data.iterrows():
                            check_type = row['check_type']
                            is_numeric = False
                            if '온,습도' in row['line'] or '온습도' in row['line'] or check_type == 'NUMBER': is_numeric = True
                            if is_numeric:
                                uid = f"{row['line']}_{row['equip_id']}_{row['item_name']}"
                                widget_key = f"val_{uid}_{sel_date}"
                                val = st.session_state.get(widget_key)
                                if val is None:
                                    missing_values.append(f"{row['equip_name']} > {row['item_name']}")
                                    continue
                            
                            uid = f"{row['line']}_{row['equip_id']}_{row['item_name']}"
                            widget_key = f"val_{uid}_{sel_date}"
                            memo_key = f"memo_{uid}_{sel_date}"
                            val = st.session_state.get(widget_key)
                            memo_val = st.session_state.get(memo_key, "")
                            ox = "OK"
                            final_val = ""
                            if not is_numeric and check_type == 'OX':
                                if val == 'NG': ox = 'NG'
                                elif val is None: ox = "NG"
                                final_val = str(val) if val else "-"
                            else:
                                final_val = str(val)
                                try:
                                    min_v = safe_float(row['min_val'], -999999)
                                    max_v = safe_float(row['max_val'], 999999)
                                    if not (min_v <= val <= max_v): ox = 'NG'
                                except: ox = 'NG'
                            rows_to_save.append([str(sel_date), row['line'], row['equip_id'], row['item_name'], final_val, ox, signer_name, str(datetime.now()), memo_val])

                        if not signer_name: st.error("⚠️ 점검자 성명을 입력해주세요.")
                        elif HAS_CANVAS and (canvas_result is None or canvas_result.image_data is None): st.error("⚠️ 서명(Canvas)이 누락되었습니다. 서명을 완료해주세요.")
                        elif missing_values: st.error(f"⚠️ 다음 항목의 수치를 입력해야 저장할 수 있습니다:\n {', '.join(missing_values[:3])} 등")
                        else:
                            try:
                                if rows_to_save:
                                    if append_rows(rows_to_save, SHEET_CHECK_RESULT, COLS_CHECK_RESULT):
                                        sig_type = "Canvas Signature" if signature_data is not None else "Text Signature"
                                        sig_row = [str(sel_date), selected_line, signer_name, sig_type, str(datetime.now())]
                                        append_rows([sig_row], SHEET_CHECK_SIGNATURE, COLS_CHECK_SIGNATURE)
                                        st.toast(f"✅ {selected_line} 점검 결과가 저장되었습니다.", icon="🎉")
                                        st.session_state['scroll_to_top'] = True
                                        time.sleep(0.5)
                                        st.rerun()
                                    else: st.error("저장 중 오류가 발생했습니다.")
                            except Exception as e: st.error(f"저장 중 오류 발생: {e}")
                else: st.info("표시할 라인 정보가 없습니다.")
        
        with tab2:
            st.markdown("##### 오늘의 점검 현황")
            today = datetime.now().strftime("%Y-%m-%d")
            df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
            df_master = get_daily_check_master_data()
            if not df_res.empty:
                df_res['date_only'] = df_res['date'].astype(str).str.split().str[0]
                df_today = df_res[df_res['date_only'] == today]
                if not df_today.empty:
                    df_today['timestamp'] = pd.to_datetime(df_today['timestamp'], errors='coerce')
                    df_today = df_today.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
                    df_master['key'] = df_master['line'] + "_" + df_master['equip_id'] + "_" + df_master['item_name']
                    df_today['key'] = df_today['line'] + "_" + df_today['equip_id'] + "_" + df_today['item_name']
                    df_today = df_today[df_today['key'].isin(df_master['key'])]
            else: df_today = pd.DataFrame()
            
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
        
        with tab3:
            c1, c2 = st.columns([1, 2])
            search_date = c1.date_input("조회 날짜 (PDF출력)", datetime.now())
            if st.button("📄 해당 날짜 전체 점검 리포트 생성 (PDF)"):
                pdf_bytes = generate_all_daily_check_pdf(str(search_date))
                if pdf_bytes:
                    st.download_button("PDF 다운로드", pdf_bytes, file_name=f"DailyCheck_All_{search_date}.pdf", mime='application/pdf')
                else: st.warning("데이터가 없습니다.")
    except Exception as e: st.error(f"일일점검관리 로딩 중 오류 발생: {e}")

# --- 5. 기준정보 탭 ---
with main_tabs[4]:
    try:
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
    except Exception as e: st.error("설정 페이지 로딩 중 오류가 발생했습니다.")