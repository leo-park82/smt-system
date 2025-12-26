import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import json
import os
import tempfile
import urllib.request  # 폰트 다운로드용
from fpdf import FPDF

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
    .stApp { background-color: #f1f5f9; } /* 배경색을 조금 더 진한 회색으로 변경 (카드 부각) */
    
    .dashboard-header { background: linear-gradient(135deg, #3b82f6 0%, #1e3a8a 100%); padding: 20px 30px; border-radius: 12px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    
    /* --- [일일점검 디자인 리뉴얼] --- */
    
    /* 설비 카드 스타일 */
    .equip-card {
        background-color: white;
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        border: 1px solid #e2e8f0;
    }
    
    /* 설비 헤더 */
    .equip-header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: 20px;
        padding-bottom: 12px;
        border-bottom: 2px solid #f8fafc;
    }
    .equip-icon {
        background-color: #eff6ff;
        color: #3b82f6;
        padding: 10px;
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
    }
    .equip-title {
        font-size: 1.25rem;
        font-weight: 800;
        color: #1e293b;
    }
    
    /* 점검 항목 Row */
    .check-row {
        padding: 16px 0;
        border-bottom: 1px solid #f1f5f9;
    }
    .check-row:last-child { border-bottom: none; }
    
    /* 항목 텍스트 스타일 */
    .item-name { font-size: 1.05rem; font-weight: 700; color: #334155; margin-bottom: 4px; }
    .item-content { font-size: 0.85rem; color: #64748b; margin-bottom: 8px; }
    .item-standard { 
        display: inline-block;
        background-color: #f8fafc; 
        color: #475569;
        font-size: 0.75rem; 
        font-weight: 600;
        padding: 4px 8px; 
        border-radius: 6px;
        border: 1px solid #e2e8f0;
    }

    /* OK/NG 버튼 스타일 (라디오 버튼 커스텀) */
    div[data-testid="stRadio"] > div {
        display: flex;
        flex-direction: row !important;
        gap: 8px !important;
        width: 100% !important;
    }

    div[data-testid="stRadio"] > div > label {
        flex: 1 !important;
        height: 56px !important;
        background-color: white;
        border: 2px solid #cbd5e1;
        border-radius: 12px !important;
        display: flex;
        justify-content: center;
        align-items: center;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    
    div[data-testid="stRadio"] > div > label:hover {
        background-color: #f8fafc;
        transform: translateY(-1px);
    }

    /* 선택된 상태의 텍스트 스타일링은 Streamlit 한계로 CSS만으론 완벽 분리가 어렵지만,
       전체적인 크기와 레이아웃을 HTML 시안처럼 1:1 비율의 꽉 찬 버튼으로 만듦 */
    div[data-testid="stRadio"] label p {
        font-size: 20px !important;
        font-weight: 800 !important;
        color: #475569;
    }
    
    /* 사이드바는 영향 안 받도록 격리 */
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div {
        gap: 0px !important;
    }
    section[data-testid="stSidebar"] div[data-testid="stRadio"] > div > label {
        height: auto !important;
        border: none !important;
        justify-content: flex-start !important;
    }
    
    /* 통계 카드 */
    .stat-card {
        background: white;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #e2e8f0;
        text-align: center;
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .stat-label { font-size: 0.8rem; font-weight: 700; color: #94a3b8; text-transform: uppercase; margin-bottom: 4px; }
    .stat-value { font-size: 1.5rem; font-weight: 900; line-height: 1; }
    .stat-total { color: #475569; }
    .stat-ok { color: #10b981; }
    .stat-ng { color: #ef4444; }

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

def save_data(df, sheet_name):
    ws = get_worksheet(sheet_name)
    if ws:
        df = df.fillna("")
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
        safe_rows = [[str(cell) if cell is not None else "" for cell in row] for row in rows]
        ws.append_rows(safe_rows)
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

def safe_float(value, default_val=None):
    try:
        if value is None or value == "" or pd.isna(value): return default_val
        return float(value)
    except: return default_val

# ------------------------------------------------------------------
# 3. 서버 사이드 로직 (Helper)
# ------------------------------------------------------------------
def get_daily_check_master_data():
    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    return df

def generate_all_daily_check_pdf(date_str):
    df_m = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    df_r = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    
    # 1. 해당 날짜 데이터 필터링
    if df_r.empty:
        return None
    
    df_r['date'] = df_r['date'].astype(str)
    df_r = df_r[df_r['date'] == date_str]
    
    if df_r.empty:
        return None
        
    df_r = df_r.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')

    # 폰트 설정
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

    # 실제 점검 데이터가 있는 라인만 추출
    lines_with_data = df_r['line'].unique()
    
    for line in lines_with_data:
        pdf.add_page()
        
        # 헤더
        pdf.set_fill_color(63, 81, 181) 
        pdf.rect(0, 0, 210, 25, 'F')
        pdf.set_font(font_name, '', 20)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 5)
        pdf.cell(0, 15, "SMT Daily Check Report", 0, 0, 'L')
        pdf.set_font(font_name, '', 10)
        pdf.set_xy(10, 5)
        pdf.cell(0, 15, f"Date: {date_str}  |  Line: {line}", 0, 0, 'R')
        pdf.ln(25)
        
        # 데이터 병합 (Master Left Join Result)
        line_master = df_m[df_m['line'] == line]
        df_merged = pd.merge(line_master, df_r, on=['line', 'equip_id', 'item_name'], how='left')
        df_merged = df_merged.fillna({'value':'-', 'ox':'-', 'checker':''})

        # 요약 통계
        total = len(df_merged)
        ok = len(df_merged[df_merged['ox'] == 'OK'])
        ng = len(df_merged[df_merged['ox'] == 'NG'])
        
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font_name, '', 12)
        pdf.cell(0, 10, f"Summary: Total {total}  /  Pass {ok}  /  Fail {ng}", 0, 1, 'L')
        pdf.ln(2)

        # 테이블 헤더
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

        # 테이블 바디
        fill = False
        pdf.set_fill_color(250, 250, 250) 
        
        for _, row in df_merged.iterrows():
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
            
            fill = not fill
        pdf.ln(10)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        pdf.output(tmp_file.name)
        with open(tmp_file.name, "rb") as f:
            pdf_bytes = f.read()
    try: os.unlink(tmp_file.name)
    except: pass
    
    return pdf_bytes

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
# 5. 기능 구현 (메인)
# ------------------------------------------------------------------

if menu == "📊 대시보드":
    try:
        df_prod = load_data(SHEET_RECORDS, COLS_RECORDS)
        df_check = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        today = datetime.now().strftime("%Y-%m-%d")
        
        prod_today = 0
        if not df_prod.empty:
            df_prod['날짜'] = pd.to_datetime(df_prod['날짜'], errors='coerce')
            df_prod['수량'] = pd.to_numeric(df_prod['수량'], errors='coerce').fillna(0)
            today_mask = df_prod['날짜'].dt.strftime("%Y-%m-%d") == today
            if today_mask.any():
                prod_today = df_prod[today_mask]['수량'].sum()
        
        check_today = 0
        ng_today = 0
        if not df_check.empty:
            df_check['date'] = df_check['date'].astype(str)
            df_check_today = df_check[df_check['date'] == today]
            if not df_check_today.empty:
                df_unique = df_check_today.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
                check_today = len(df_unique)
                ng_today = len(df_unique[df_unique['ox'] == 'NG'])

        col1, col2, col3 = st.columns(3)
        col1.metric("오늘 생산량", f"{prod_today:,.0f} EA")
        col2.metric("일일점검 완료", f"{check_today} 건")
        col3.metric("NG 발생", f"{ng_today} 건", delta_color="inverse")

        st.markdown("#### 📅 주간 생산 추이")
        if not df_prod.empty and HAS_ALTAIR:
            chart_data = df_prod.groupby('날짜')['수량'].sum().reset_index()
            c = alt.Chart(chart_data).mark_line(point=True).encode(x='날짜', y='수량', tooltip=['날짜', '수량']).interactive()
            st.altair_chart(c, use_container_width=True)
        elif df_prod.empty:
            st.info("생산 데이터가 없습니다.")
    except Exception as e:
        st.error(f"대시보드 로드 중 오류: {e}")

elif menu == "🏭 생산관리":
    t1, t2, t3, t4 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 생산 분석", "📑 일일 보고서"])
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
                st.dataframe(df, use_container_width=True, hide_index=True)
    with t2:
        df_inv = load_data(SHEET_INVENTORY, COLS_INVENTORY)
        st.dataframe(df_inv, use_container_width=True)
    with t3:
        df = load_data(SHEET_RECORDS, COLS_RECORDS)
        if not df.empty and HAS_ALTAIR:
            df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            st.altair_chart(alt.Chart(df.groupby('날짜')['수량'].sum().reset_index()).mark_bar().encode(x='날짜', y='수량').interactive(), use_container_width=True)
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
        st.markdown("#### 📊 설비 고장 분석")
        df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
        if not df.empty:
            df['비용'] = pd.to_numeric(df['비용'], errors='coerce').fillna(0)
            if HAS_ALTAIR:
                c = alt.Chart(df).mark_bar().encode(x='작업구분', y='비용', color='작업구분').interactive()
                st.altair_chart(c, use_container_width=True)

elif menu == "✅ 일일점검관리":
    # [수정: 디자인 전면 리뉴얼] 카드형 UI & 직관적인 입력 폼
    tab1, tab2, tab3 = st.tabs(["✍ 점검 입력", "📊 점검 현황", "📄 리포트"])
    
    with tab1:
        # 상단 설정 및 요약 바
        c_date, c_line, c_blank = st.columns([1, 1.5, 2])
        sel_date = c_date.date_input("점검 일자", datetime.now(), key="chk_date")
        
        df_master_all = get_daily_check_master_data()
        
        if df_master_all.empty:
            st.warning("등록된 점검 항목이 없습니다.")
        else:
            lines = df_master_all['line'].unique()
            sel_line = c_line.selectbox("라인 선택", lines)
            
            # 해당 라인/날짜의 마스터 및 결과 데이터 로드
            df_master_line = df_master_all[df_master_all['line'] == sel_line].copy()
            df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
            
            current_vals = {}
            if not df_res.empty:
                df_res['date'] = df_res['date'].astype(str)
                df_filtered = df_res[(df_res['date'] == str(sel_date)) & (df_res['line'] == sel_line)]
                if not df_filtered.empty:
                    df_filtered = df_filtered.sort_values('timestamp').drop_duplicates(['equip_id', 'item_name'], keep='last')
                    for _, r in df_filtered.iterrows():
                        key = f"{r['equip_id']}_{r['item_name']}"
                        current_vals[key] = {'val': r['value'], 'ox': r['ox']}

            # 상단 통계 카드 (HTML 디자인 유사 구현)
            total_cnt = len(df_master_line)
            done_cnt = len([k for k in current_vals.keys() if k.split('_')[0] in df_master_line['equip_id'].values])
            # 정확한 통계는 복잡하므로 단순 진행률 표시
            
            # 통계 표시 영역
            st.markdown(f"""
                <div style="display: flex; gap: 10px; margin-bottom: 20px;">
                    <div class="stat-card" style="flex:1;">
                        <div class="stat-label stat-total">Total Items</div>
                        <div class="stat-value stat-total">{total_cnt}</div>
                    </div>
                    <div class="stat-card" style="flex:1;">
                        <div class="stat-label stat-ok">Done</div>
                        <div class="stat-value stat-ok">{len(current_vals)}</div>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            
            st.write(f"**점검자**: {st.session_state.user_info['name']}")
            signer = st.session_state.user_info['name'] 

            with st.form("daily_check_form", clear_on_submit=False):
                rows_data = [] 
                
                # 설비별로 그룹화하여 카드 생성
                # 데이터 프레임 정렬 (설비 순서) -> 설비 ID 기준 그룹핑
                for equip_id in df_master_line['equip_id'].unique():
                    equip_group = df_master_line[df_master_line['equip_id'] == equip_id]
                    equip_name = equip_group.iloc[0]['equip_name']
                    
                    # --- 설비 카드 시작 ---
                    st.markdown(f"""
                    <div class="equip-card">
                        <div class="equip-header">
                            <div class="equip-icon">⚙️</div>
                            <div class="equip-title">{equip_name}</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    for index, row in equip_group.iterrows():
                        key_base = f"{row['equip_id']}_{row['item_name']}"
                        prev = current_vals.get(key_base, {})
                        
                        check_type = row['check_type']
                        
                        # 기본값 세팅
                        if check_type == 'OX':
                            default_val = prev.get('ox', 'OK') # 기본 OK
                        else:
                            default_val = prev.get('val', "")
                            
                        widget_key = f"chk_{index}_{key_base}"
                        
                        # 아이템 Row 시작 (Streamlit 레이아웃 사용)
                        col_info, col_input = st.columns([1.8, 1])
                        
                        with col_info:
                            st.markdown(f"""
                                <div class="item-name">{row['item_name']}</div>
                                <div class="item-content">{row['check_content']}</div>
                                <div class="item-standard">기준: {row['standard']}</div>
                            """, unsafe_allow_html=True)
                        
                        with col_input:
                            if check_type == 'OX':
                                idx = 0
                                if default_val == 'NG': idx = 1
                                # 라디오 버튼 (커스텀 CSS 적용됨)
                                st.radio(f"{row['item_name']} 판정", ["OK", "NG"], key=widget_key, index=idx, horizontal=True, label_visibility="collapsed")
                            else:
                                val_str = str(default_val) if default_val and default_val != 'nan' and default_val is not None else ""
                                st.text_input(f"수치 ({row['unit']})", value=val_str, key=widget_key, placeholder=f"입력 ({row['unit']})", label_visibility="collapsed")
                        
                        st.markdown('<div class="check-row"></div>', unsafe_allow_html=True) # Divider

                        rows_data.append({
                            "master": row,
                            "widget_key": widget_key,
                            "check_type": check_type
                        })
                    
                    st.markdown("</div>", unsafe_allow_html=True) # 설비 카드 끝

                # 플로팅 버튼처럼 보이게 하기 위해 컨테이너 하단 배치
                submitted = st.form_submit_button("💾 전체 점검 결과 저장", type="primary", use_container_width=True)
                
                if submitted:
                    rows_to_save = []
                    ng_list = []
                    save_flag = True
                    
                    for item in rows_data:
                        row = item['master']
                        widget_key = item['widget_key']
                        input_val = st.session_state.get(widget_key)
                        
                        val_str = ""
                        ox = "OK" 

                        if item['check_type'] == 'OX':
                            ox = input_val
                        else:
                            val_str = str(input_val).strip() if input_val else ""
                            if not val_str:
                                # 수치형인데 빈칸이면 넘어갈지, 에러낼지 결정. 여기선 OK처리하되 값 비움 (선택적)
                                # 엄격 모드: 에러
                                pass 
                            else:
                                try:
                                    f_val = float(val_str)
                                    min_v = safe_float(row['min_val'], -999999)
                                    max_v = safe_float(row['max_val'], 999999)
                                    if not (min_v <= f_val <= max_v):
                                        ox = 'NG'
                                except:
                                    st.error(f"[{row['item_name']}] 수치 오류")
                                    save_flag = False

                        if ox == 'NG':
                            ng_list.append(row['item_name'])
                            
                        rows_to_save.append([
                            str(sel_date), sel_line, row['equip_id'], row['item_name'],
                            val_str, ox, signer, str(datetime.now())
                        ])
                        
                    if save_flag:
                        df_new = pd.DataFrame(rows_to_save, columns=COLS_CHECK_RESULT)
                        append_rows(df_new.values.tolist(), SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
                        st.success("✅ 저장 완료!")
                        if ng_list:
                            st.error(f"NG 발생: {len(ng_list)}건")
                        time.sleep(1)
                        st.rerun()

    with tab2:
        st.markdown("##### 오늘의 점검 현황")
        today = datetime.now().strftime("%Y-%m-%d")
        
        df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        df_master = get_daily_check_master_data()
        
        if not df_res.empty:
            df_res['date'] = df_res['date'].astype(str)
            df_today = df_res[df_res['date'] == today]
            if not df_today.empty:
                df_today = df_today.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
                df_master['key'] = df_master['line'] + "_" + df_master['equip_id'] + "_" + df_master['item_name']
                df_today['key'] = df_today['line'] + "_" + df_today['equip_id'] + "_" + df_today['item_name']
                df_today = df_today[df_today['key'].isin(df_master['key'])]
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
            st.dataframe(df_today[df_today['ox']=='NG'][['line','equip_id','item_name','value','checker']])

    with tab3:
        c1, c2 = st.columns([1, 2])
        search_date = c1.date_input("조회 날짜 (PDF출력)", datetime.now())
        
        if st.button("📄 해당 날짜 점검 리포트 생성 (PDF)"):
            pdf_bytes = generate_all_daily_check_pdf(str(search_date))
            if pdf_bytes:
                st.download_button("PDF 다운로드", pdf_bytes, file_name=f"DailyCheck_{search_date}.pdf", mime='application/pdf')
            else:
                st.warning("해당 날짜에 점검 데이터가 없습니다.")

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