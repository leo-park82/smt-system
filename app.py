import streamlit as st
import pandas as pd
# [수정] timezone 추가
from datetime import datetime, timedelta, timezone
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
# [수정] 타이틀 SMT로 변경
st.set_page_config(page_title="SMT", page_icon="🏭", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; color: #1e293b; }
    .stApp { background-color: #f8fafc; }
    .dashboard-header { background: linear-gradient(135deg, #3b82f6 0%, #1e3a8a 100%); padding: 20px 30px; border-radius: 12px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .metric-card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    
    /* 탭 스타일 개선 - 상단 고정 및 디자인 */
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
        white-space: pre-wrap; 
        background-color: transparent; 
        border-radius: 8px 8px 0 0; 
        padding: 0 24px; 
        font-size: 1.05rem; 
        font-weight: 600; 
        border: none;
        color: #64748b;
        transition: all 0.2s;
    }
    .stTabs [aria-selected="true"] { 
        background-color: #eff6ff; 
        color: #3b82f6; 
        border-bottom: 3px solid #3b82f6;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #3b82f6;
        background-color: #f8fafc;
    }
    
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

# [추가] 한국 시간(KST) 구하기 헬퍼 함수
def get_now():
    """시스템 시간이 UTC일 경우를 대비해 강제로 한국 시간(UTC+9)을 반환"""
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
    except Exception as e:
        return pd.DataFrame(columns=cols) if cols else pd.DataFrame()

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
    
    df = df[df['현재고'] != 0]
    
    save_data(df, SHEET_INVENTORY)
    # [수정] 한국 시간 적용
    now_kst = get_now()
    hist = {"날짜": now_kst.strftime("%Y-%m-%d"), "품목코드": code, "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, "작성자": user, "입력시간": str(now_kst)}
    append_data(hist, SHEET_INV_HISTORY)

def safe_float(value, default_val=None):
    try:
        if value is None or value == "" or pd.isna(value): return default_val
        return float(value)
    except: return default_val

# ------------------------------------------------------------------
# 3. 데이터 로딩 헬퍼 함수
# ------------------------------------------------------------------
@st.cache_data(ttl=60)
def get_dashboard_stats():
    df_prod = load_data(SHEET_RECORDS, COLS_RECORDS)
    df_check = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    df_maint = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
    
    # [수정] 한국 시간 적용 후 Naive 변환 (비교 오류 방지)
    today = get_now().replace(tzinfo=None) # 시간대 정보 제거
    today_str = today.strftime("%Y-%m-%d")
    yesterday_str = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    this_month_start = today.replace(day=1)
    
    prod_today_val = 0
    prod_yesterday_val = 0
    
    if not df_prod.empty:
        df_prod['날짜'] = pd.to_datetime(df_prod['날짜'], errors='coerce')
        df_prod['수량'] = pd.to_numeric(df_prod['수량'], errors='coerce').fillna(0)
        
        prod_today_val = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == today_str]['수량'].sum()
        prod_yesterday_val = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == yesterday_str]['수량'].sum()
    
    delta_prod = prod_today_val - prod_yesterday_val
    
    check_today_cnt = 0
    ng_today_cnt = 0
    ng_rate = 0.0
    
    df_today_unique = pd.DataFrame()
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

    maint_today_cnt = 0
    if not df_maint.empty:
        maint_today_cnt = len(df_maint[df_maint['날짜'].astype(str) == today_str])

    return {
        "prod_today": prod_today_val,
        "delta_prod": delta_prod,
        "check_cnt": check_today_cnt,
        "ng_cnt": ng_today_cnt,
        "ng_rate": ng_rate,
        "maint_cnt": maint_today_cnt,
        "df_prod": df_prod,
        "df_check_unique": df_today_unique,
        "df_maint": df_maint,
        "today_str": today_str,
        "month_start": this_month_start,
        "today_dt": today
    }

def get_daily_check_master_data():
    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    return df

def generate_all_daily_check_pdf(date_str):
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
            # [수정] PDF 컬럼 너비 조정 (점검항목 축소, 기준 확대)
            # 기존: [45, 65, 30, 20, 15, 15]
            widths = [45, 50, 45, 20, 15, 15]
            
            for i, h in enumerate(headers):
                pdf.cell(widths[i], 10, h, 1, 0, 'C', 1)
            pdf.ln()

            fill = False
            pdf.set_fill_color(250, 250, 250) 
            
            for _, row in df_final.iterrows():
                equip_name = str(row['equip_name'])
                if len(equip_name) > 18: equip_name = equip_name[:17] + ".."
                
                # [수정] 조정된 너비 적용
                pdf.cell(45, 8, equip_name, 1, 0, 'L', fill)
                pdf.cell(50, 8, str(row['item_name']), 1, 0, 'L', fill) # 65 -> 50
                pdf.cell(45, 8, str(row['standard']), 1, 0, 'C', fill)  # 30 -> 45
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
            with open(tmp_file.name, "rb") as f: pdf_bytes = f.read()
        os.unlink(tmp_file.name)
        return pdf_bytes
    except Exception as e:
        return None

def generate_production_report_pdf(df_prod, df_inv, date_str):
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
        pdf.set_fill_color(50, 50, 50) 
        pdf.rect(0, 0, 210, 25, 'F')
        pdf.set_font(font_name, '', 20)
        pdf.set_text_color(255, 255, 255)
        pdf.set_xy(10, 5)
        # [수정] 한글 제목 변경
        pdf.cell(0, 15, "생산 일일 보고서", 0, 0, 'L')
        pdf.set_font(font_name, '', 10)
        pdf.set_xy(10, 5)
        # [수정] 한글 제목 변경
        pdf.cell(0, 15, f"일자: {date_str}", 0, 0, 'R')
        pdf.ln(25)
        
        # 1. 생산 실적
        pdf.set_text_color(0, 0, 0)
        pdf.set_font(font_name, '', 14)
        # [수정] 한글 제목 변경
        pdf.cell(0, 10, "1. 일일 생산 실적", 0, 1, 'L')
        
        pdf.set_fill_color(240, 240, 240)
        pdf.set_font(font_name, '', 10)
        headers = ["구분", "품목코드", "제품명", "수량", "작성자"]
        widths = [25, 35, 80, 25, 25]
        for i, h in enumerate(headers): pdf.cell(widths[i], 10, h, 1, 0, 'C', 1)
        pdf.ln()
        
        fill = False
        pdf.set_fill_color(250, 250, 250)
        total_qty = 0
        if not df_prod.empty:
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
        else:
            # [수정] 한글 제목 변경
            pdf.cell(sum(widths), 10, "생산 실적 없음", 1, 1, 'C', fill)
            
        pdf.ln(2)
        pdf.set_font(font_name, '', 12)
        # [수정] 한글 제목 변경
        pdf.cell(0, 10, f"총 생산량: {total_qty:,} EA", 0, 1, 'R')
        
        # 2. 재고 현황
        if df_inv is not None and not df_inv.empty:
            pdf.ln(10)
            pdf.set_font(font_name, '', 14)
            # [수정] 한글 제목 변경
            pdf.cell(0, 10, "2. 현재 재고 현황", 0, 1, 'L')
            
            pdf.set_font(font_name, '', 10)
            pdf.set_fill_color(240, 240, 240)
            
            inv_headers = ["품목코드", "제품명", "현재고"]
            inv_widths = [40, 100, 50]
            
            for i, h in enumerate(inv_headers):
                pdf.cell(inv_widths[i], 10, h, 1, 0, 'C', 1)
            pdf.ln()
            
            fill = False
            pdf.set_fill_color(250, 250, 250)
            
            for _, row in df_inv.iterrows():
                pdf.cell(inv_widths[0], 8, str(row['품목코드']), 1, 0, 'C', fill)
                
                p_name = str(row['제품명'])
                if len(p_name) > 35: p_name = p_name[:34] + ".."
                pdf.cell(inv_widths[1], 8, p_name, 1, 0, 'L', fill)
                
                curr_stock = int(float(str(row['현재고']).replace(',', '')))
                pdf.cell(inv_widths[2], 8, f"{curr_stock:,}", 1, 1, 'R', fill)
                
                fill = not fill

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            pdf.output(tmp_file.name)
            with open(tmp_file.name, "rb") as f: pdf_bytes = f.read()
        os.unlink(tmp_file.name)
        return pdf_bytes
    except: return None

# ------------------------------------------------------------------
# 4. 사용자 인증
# ------------------------------------------------------------------
def make_hash(password): return hashlib.sha256(str.encode(password)).hexdigest()
USERS = {
    "cimon": {"name": "관리자", "password_hash": make_hash("7801083"), "role": "admin"},
    "박종선": {"name": "박종선", "password_hash": make_hash("1083"), "role": "worker"},
    "김윤석": {"name": "김윤석", "password_hash": make_hash("1734"), "role": "worker"},
    "김명숙": {"name": "김명숙", "password_hash": make_hash("8943"), "role": "worker"}
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
                # 뷰어 자동 로그인 처리
                elif saved_id == "guest":
                    st.session_state.logged_in = True
                    st.session_state.user_info = {"name": "게스트", "role": "viewer", "id": "guest"}
        except: pass

    if st.session_state.logged_in: return True
    
    # [수정] 로그인 창 크기 및 로고 크기 조절 (컬럼 비율 변경 5:2:5 -> 4:3:4)
    col1, col2, col3 = st.columns([4, 3, 4])
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
        
        if st.button("👀 게스트(뷰어)로 입장", use_container_width=True):
            st.session_state.logged_in = True
            st.session_state.user_info = {"name": "게스트", "role": "viewer", "id": "guest"}
            try: st.query_params["session"] = "guest"
            except: pass
            st.rerun()
            
    return False

# ------------------------------------------------------------------
# 5. 메인 앱 실행 함수 (run_app)
# ------------------------------------------------------------------
def run_app():
    # 사이드바
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

    # 메인 기능 탭
    main_tabs = st.tabs(["📊 대시보드", "🏭 생산관리", "🛠 설비보전", "✅ 일일점검", "⚙ 기준정보"])

    # --- 1. 대시보드 탭 ---
    with main_tabs[0]:
        with st.spinner("대시보드 분석 중..."):
            try:
                metrics = get_dashboard_stats()
                
                c1, c2, c3 = st.columns(3)
                c1.metric("오늘 생산량", f"{metrics['prod_today']:,.0f} EA", f"{metrics['delta_prod']:,.0f} (전일비)")
                c2.metric("금일 설비 정비", f"{metrics['maint_cnt']} 건", "확인 필요" if metrics['maint_cnt'] > 0 else "특이사항 없음", delta_color="inverse")
                c3.metric("일일점검 (완료/NG)", f"{metrics['check_cnt']} 건 / {metrics['ng_cnt']} 건", f"불량률: {metrics['ng_rate']:.1f}%", delta_color="inverse")

                st.markdown("---")

                col_g1, col_g2 = st.columns([2, 1])

                with col_g1:
                    st.subheader("📈 주간 생산 추이 & 유형")
                    df_prod = metrics['df_prod']
                    if not df_prod.empty and HAS_ALTAIR:
                        last_7_days = metrics['today_dt'] - timedelta(days=7)
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
                        else: st.info("최근 데이터가 없습니다.")
                    else: st.info("생산 데이터가 없습니다.")

                with col_g2:
                    st.subheader("🏭 월간 생산 품목 비율")
                    if not df_prod.empty:
                        df_month_prod = df_prod[(df_prod['날짜'] >= metrics['month_start']) & (df_prod['날짜'] <= metrics['today_dt'])]
                        if not df_month_prod.empty:
                            pie_data = df_month_prod.groupby('구분')['수량'].sum().reset_index()
                            total_q = pie_data['수량'].sum()
                            pie_data['비율'] = (pie_data['수량'] / total_q * 100).round(1)
                            pie_data['Label'] = pie_data['수량'].astype(str) + " (" + pie_data['비율'].astype(str) + "%)"
                            pie_data['DisplayLabel'] = pie_data.apply(lambda x: x['Label'] if x['비율'] > 3 else "", axis=1)

                            base = alt.Chart(pie_data).encode(theta=alt.Theta("수량", stack=True), color=alt.Color("구분", legend=alt.Legend(title="공정", orient="bottom")))
                            pie = base.mark_arc(outerRadius=120, innerRadius=60).encode(tooltip=["구분", "수량", "비율"])
                            text = base.mark_text(radius=140).encode(text="DisplayLabel", order=alt.Order("구분"), color=alt.value("black"))
                            st.altair_chart((pie + text).properties(height=400), use_container_width=True)
                        else: st.info("이번 달 실적 없음")
                    else: st.info("데이터 없음")

                st.markdown("---")
                
                c3, c4 = st.columns(2)
                with c3:
                    st.subheader("🚨 실시간 NG 현황 (Today)")
                    df_ng = metrics['df_check_unique']
                    if not df_ng.empty and metrics['ng_cnt'] > 0:
                        ng_display = df_ng[df_ng['ox'] == 'NG'][['line', 'equip_id', 'item_name', 'value', 'checker', '비고']]
                        st.dataframe(ng_display, hide_index=True, use_container_width=True)
                    elif metrics['ng_cnt'] == 0:
                        st.success("🎉 현재까지 발견된 NG 항목이 없습니다.")
                    else:
                        st.info("점검 데이터가 없습니다.")

                with c4:
                    st.subheader("🛠 최근 설비 정비 이력 (Last 5)")
                    df_m = metrics['df_maint']
                    if not df_m.empty:
                        recent_maint = df_m.sort_values("날짜", ascending=False).head(5)[['날짜', '설비명', '작업구분', '작업내용']]
                        st.dataframe(recent_maint, hide_index=True, use_container_width=True)
                    else:
                        st.info("정비 이력이 없습니다.")

            except Exception as e:
                st.error(f"대시보드 로딩 오류: {e}")

    # --- 2. 생산관리 탭 ---
    with main_tabs[1]:
        try:
            # [수정] 탭 이름 변경: "스마트 생산 분석" -> "생산분석"
            t1, t2, t3, t4 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 생산분석", "📑 일일 보고서"])
            with t1:
                c1, c2 = st.columns([1, 1.5])
                with c1:
                    if st.session_state.user_info['role'] in ['admin', 'worker']:
                        with st.container(border=True):
                            st.markdown("#### ✏️ 신규 생산 등록")
                            with st.spinner("로딩 중..."):
                                item_df = load_data(SHEET_ITEMS, COLS_ITEMS)
                            # [수정] 한국 시간 적용 (기본값)
                            date = st.date_input("작업 일자", value=get_now())
                            cat = st.selectbox("공정 구분", ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"])
                            item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
                            
                            def on_code():
                                # [수정] 입력값을 대문자로 변환하여 세션 상태 업데이트 (UI 반영)
                                st.session_state.code_in = st.session_state.code_in.upper().strip()
                                c = st.session_state.code_in
                                if c in item_map: st.session_state.name_in = item_map[c]
                            
                            code = st.text_input("품목 코드", key="code_in", on_change=on_code)
                            name = st.text_input("제품명", key="name_in")
                            qty = st.number_input("생산 수량", min_value=1, value=100, key="prod_qty")
                            auto_deduct = st.checkbox("재고 차감 적용", value=True) if cat in ["후공정", "후공정 외주"] else False
                            
                            def save_production():
                                # [수정] 저장 시에도 대문자 강제 변환 확인
                                c_code = st.session_state.code_in.upper().strip()
                                c_name = st.session_state.name_in
                                c_qty = st.session_state.prod_qty
                                
                                if c_name:
                                    # [수정] 한국 시간 적용
                                    rec = {"날짜":str(date), "구분":cat, "품목코드":c_code, "제품명":c_name, "수량":c_qty, "입력시간":str(get_now()), "작성자": st.session_state.user_info['id']}
                                    if append_data(rec, SHEET_RECORDS):
                                        # [수정] 배전 공정은 재고 반영에서 제외
                                        if cat == "배전":
                                            pass
                                        elif cat in ["후공정", "후공정 외주"] and auto_deduct: 
                                            update_inventory(c_code, c_name, -c_qty, f"생산출고({cat})", st.session_state.user_info['id'])
                                        else: 
                                            update_inventory(c_code, c_name, c_qty, f"생산입고({cat})", st.session_state.user_info['id'])
                                        
                                        st.session_state.code_in = ""; st.session_state.name_in = ""; st.session_state.prod_qty = 100
                                        st.toast("저장되었습니다.", icon="✅")
                                else: st.toast("제품명을 입력하세요.", icon="⚠️")
                            st.button("실적 저장", type="primary", use_container_width=True, on_click=save_production)
                    else: st.info("🔒 뷰어 모드입니다.")
                with c2:
                    st.markdown("#### 📋 최근 등록 내역")
                    df = load_data(SHEET_RECORDS, COLS_RECORDS)
                    if not df.empty:
                        if st.session_state.user_info['role'] == 'admin':
                            df_display = df.sort_values("입력시간", ascending=False).head(50)
                            df_display.insert(0, "삭제", False)
                            edited_df = st.data_editor(df_display, hide_index=True, use_container_width=True, column_config={"삭제": st.column_config.CheckboxColumn(required=True)}, disabled=COLS_RECORDS, key="recent_records_editor")
                            if st.button("선택 항목 삭제", type="secondary"):
                                to_delete = edited_df[edited_df["삭제"] == True]
                                if not to_delete.empty:
                                    try:
                                        ws = get_worksheet(SHEET_RECORDS)
                                        # [수정] 데이터 로드 후 빈 행 제거 및 타입 통일
                                        all_records = get_as_dataframe(ws)
                                        all_records = all_records.dropna(how='all')
                                        all_records['입력시간'] = all_records['입력시간'].astype(str)
                                        
                                        for t in to_delete['입력시간']:
                                            idx_to_drop = all_records[all_records['입력시간'] == str(t)].index
                                            all_records = all_records.drop(idx_to_drop)
                                        
                                        save_data(all_records, SHEET_RECORDS)
                                        st.success("삭제 완료")
                                        time.sleep(0.5)
                                        st.rerun()
                                    except Exception as e: st.error(f"삭제 실패: {e}")
                        else: st.dataframe(df.sort_values("입력시간", ascending=False).head(50), hide_index=True, use_container_width=True)

            with t2:
                df_inv = load_data(SHEET_INVENTORY, COLS_INVENTORY)
                if not df_inv.empty:
                    df_inv = df_inv[df_inv['현재고'] != 0]
                    if st.session_state.user_info['role'] == 'admin':
                        df_inv.insert(0, "삭제", False)
                        edited_inv = st.data_editor(df_inv, hide_index=True, use_container_width=True, column_config={"삭제": st.column_config.CheckboxColumn(required=True)}, disabled=COLS_INVENTORY, key="inventory_editor")
                        if st.button("선택 항목 삭제", type="primary", key="del_inv"):
                            to_delete = edited_inv[edited_inv["삭제"] == True]
                            if not to_delete.empty:
                                try:
                                    ws = get_worksheet(SHEET_INVENTORY)
                                    # [수정] 데이터 로드 후 빈 행 제거 및 타입 통일
                                    all_inv = get_as_dataframe(ws)
                                    all_inv = all_inv.dropna(how='all')
                                    all_inv['품목코드'] = all_inv['품목코드'].astype(str)
                                    
                                    for code in to_delete['품목코드']:
                                        idx = all_inv[all_inv['품목코드'] == str(code)].index
                                        all_inv = all_inv.drop(idx)
                                    
                                    save_data(all_inv, SHEET_INVENTORY)
                                    st.success("삭제 완료")
                                    st.rerun()
                                except Exception as e: st.error(f"오류: {e}")
                    else: st.dataframe(df_inv, use_container_width=True)
                else: st.info("재고 데이터가 없습니다.")

            with t3:
                # [수정] 헤더 제목 변경: "스마트 생산 분석" -> "생산분석"
                st.markdown("#### 📊 생산분석")
                
                # [수정] 분석 로직 - 버튼 트리거 방식 (초기 로딩 시 자동 실행 방지)
                df = load_data(SHEET_RECORDS, COLS_RECORDS)
                if not df.empty:
                    df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
                    df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
                    df = df.dropna(subset=['날짜']) 
                    
                    min_date = df['날짜'].min().date()
                    max_date_val = df['날짜'].max().date()
                    
                    c1, c2 = st.columns([1, 1])
                    with c1:
                        default_start = max_date_val - timedelta(days=29)
                        if default_start < min_date: default_start = min_date
                        date_range = st.date_input("기간 선택", value=(default_start, max_date_val), min_value=min_date, max_value=max_date_val)
                    
                    # [수정] 버튼을 눌러야 분석 실행
                    if st.button("분석 실행"):
                        if df.empty:
                            st.info("데이터 없음")
                        else:
                            # 1. 시스템 알림 (7일 추이)
                            max_date = df['날짜'].max()
                            recent_start = max_date - timedelta(days=6)
                            recent = df[df['날짜'] >= recent_start]
                            
                            prev_start = recent_start - timedelta(days=7)
                            prev_end = recent_start - timedelta(days=1)
                            prev = df[(df['날짜'] >= prev_start) & (df['날짜'] <= prev_end)]

                            recent_avg = recent['수량'].mean()
                            prev_avg = prev['수량'].mean() if not prev.empty else 0

                            if prev_avg > 0:
                                diff_rate = (recent_avg - prev_avg) / prev_avg * 100
                                if diff_rate < -10:
                                    st.error(f"⚠️ 최근 생산량이 전주 대비 {abs(diff_rate):.1f}% 감소했습니다. (최근 7일 평균: {recent_avg:.1f} vs 전주: {prev_avg:.1f})")
                                elif diff_rate > 10:
                                    st.success(f"📈 최근 생산량이 전주 대비 {diff_rate:.1f}% 증가했습니다. (최근 7일 평균: {recent_avg:.1f} vs 전주: {prev_avg:.1f})")

                            # 2. 기간별 상세 분석
                            if isinstance(date_range, tuple) and len(date_range) == 2:
                                mask = (df['날짜'].dt.date >= date_range[0]) & (df['날짜'].dt.date <= date_range[1])
                                df_filtered = df[mask].copy()
                                if not df_filtered.empty:
                                    # [수정] 시간 성분 제거 (00:00:00으로 통일)하여 같은 날짜가 여러 번 나오는 문제 해결
                                    df_filtered['날짜'] = df_filtered['날짜'].dt.normalize()
                                    
                                    total = df_filtered['수량'].sum()
                                    avg = total / len(df_filtered['날짜'].unique())
                                    m1, m2 = st.columns(2)
                                    m1.metric("총 생산", f"{total:,.0f}")
                                    m2.metric("일 평균", f"{avg:,.0f}")
                                    
                                    chart_data = df_filtered.groupby(['날짜', '구분'])['수량'].sum().reset_index()
                                    bar = alt.Chart(chart_data).mark_bar().encode(
                                        x=alt.X('날짜:T', axis=alt.Axis(format="%y-%m-%d", labelAngle=0, title="날짜")),
                                        y=alt.Y('수량:Q', axis=alt.Axis(title="생\n산\n량", titleAngle=0, titlePadding=20, titleFontWeight="bold", titleFontSize=14)),
                                        color='구분', tooltip=['날짜', '구분', '수량']
                                    ).properties(height=350)
                                    st.altair_chart(bar, use_container_width=True)

                                    # [추가] SMT 생산(PC, CM1, CM3, 배전) 모델별 분석 섹션
                                    st.markdown("---")
                                    st.subheader("🧩 SMT 생산 모델별 분석 (PC/CM/배전 합산)")
                                    
                                    smt_cats = ["PC", "CM1", "CM3", "배전"]
                                    df_smt = df_filtered[df_filtered['구분'].isin(smt_cats)]
                                    
                                    if not df_smt.empty:
                                        smt_agg = df_smt.groupby('제품명')['수량'].sum().reset_index().sort_values('수량', ascending=False)
                                        smt_total = smt_agg['수량'].sum()
                                        
                                        c_s1, c_s2 = st.columns([1, 2])
                                        with c_s1:
                                            st.metric("SMT 총 생산량", f"{smt_total:,.0f} EA", help="PC, CM1, CM3, 배전 공정 합계")
                                            # 전체 데이터는 표로 확인
                                            st.dataframe(smt_agg, hide_index=True, use_container_width=True, height=400)
                                        
                                        with c_s2:
                                            # [수정] 모델이 많을 경우를 대비해 상위 N개만 표시하는 슬라이더 추가
                                            top_n = st.slider("차트 표시 개수 (상위 N개)", min_value=5, max_value=50, value=15, key="smt_chart_limit")
                                            
                                            chart_data_smt = smt_agg.head(top_n)
                                            
                                            smt_chart = alt.Chart(chart_data_smt).mark_bar().encode(
                                                x=alt.X('제품명', sort='-y', axis=alt.Axis(labelAngle=-45, title="모델명")),
                                                y=alt.Y('수량', axis=alt.Axis(title="생산 수량")),
                                                color=alt.value("#3b82f6"), # 파란색 계열 단일 색상
                                                tooltip=['제품명', alt.Tooltip('수량', format=',')]
                                            ).properties(
                                                title=f"SMT 생산 상위 {top_n}개 모델"
                                            )
                                            st.altair_chart(smt_chart, use_container_width=True)
                                    else:
                                        st.info("선택된 기간에 SMT 생산(PC, CM, 배전) 데이터가 없습니다.")

                                else: st.info("선택된 기간에 데이터가 없습니다.")
                else: st.info("생산 데이터가 없습니다.")

            with t4:
                st.markdown("#### 📑 일일 보고서")
                c1, c2 = st.columns([1,2])
                # [수정] 한국 시간 적용
                r_date = c1.date_input("날짜", get_now(), key="rep_date")
                if c2.button("📄 PDF 다운로드"):
                    df = load_data(SHEET_RECORDS, COLS_RECORDS)
                    df_inv = load_data(SHEET_INVENTORY, COLS_INVENTORY)
                    
                    if not df_inv.empty:
                        df_inv['현재고'] = pd.to_numeric(df_inv['현재고'], errors='coerce').fillna(0)
                        df_inv = df_inv[df_inv['현재고'] != 0]

                    if not df.empty:
                        df['날짜'] = pd.to_datetime(df['날짜']).dt.date
                        daily = df[df['날짜'] == r_date]
                        if not daily.empty:
                            pdf_bytes = generate_production_report_pdf(daily, df_inv, str(r_date))
                            if pdf_bytes:
                                st.download_button("다운로드", pdf_bytes, file_name=f"Report_{r_date}.pdf", mime='application/pdf')
                        else: st.warning("생산 데이터가 없습니다.")

        except Exception as e: st.error(f"생산관리 오류: {e}")

    # --- 3. 설비보전 탭 ---
    with main_tabs[2]:
        try:
            t1, t2, t3 = st.tabs(["📝 정비 등록", "📋 이력 조회", "📊 분석 리포트"])
            with t1:
                c1, c2 = st.columns([1, 1.5])
                with c1:
                    if st.session_state.user_info['role'] in ['admin', 'worker']:
                        with st.container(border=True):
                            st.markdown("#### 🔧 정비 등록")
                            eq_df = load_data(SHEET_EQUIPMENT, COLS_EQUIPMENT)
                            eq_map = dict(zip(eq_df['id'], eq_df['name'])) if not eq_df.empty else {}
                            # [수정] 한국 시간 적용
                            f_date = st.date_input("날짜", key="maint_date", value=get_now())
                            f_eq = st.selectbox("설비", list(eq_map.keys()), format_func=lambda x: f"[{x}] {eq_map[x]}")
                            f_type = st.selectbox("구분", ["PM (예방)", "BM (고장)", "CM (개선)"])
                            f_desc = st.text_area("내용")
                            
                            # [수정] 부품 추가 로직 (리스트에 담기)
                            if 'maint_parts' not in st.session_state: st.session_state.maint_parts = []
                            
                            col_p1, col_p2, col_p3 = st.columns([2, 1, 0.8])
                            with col_p1:
                                p_in = st.text_input("부품명", key="p_in_val")
                            with col_p2:
                                c_in = st.number_input("금액", step=1000, key="c_in_val")
                            with col_p3:
                                st.write("")
                                st.write("")
                                def add_part():
                                    if st.session_state.p_in_val:
                                        st.session_state.maint_parts.append({"부품명": st.session_state.p_in_val, "금액": st.session_state.c_in_val})
                                        st.session_state.p_in_val = ""
                                        st.session_state.c_in_val = 0
                                
                                st.button("추가", on_click=add_part)

                            if st.session_state.maint_parts:
                                st.caption("등록된 부품 목록")
                                st.dataframe(pd.DataFrame(st.session_state.maint_parts), use_container_width=True, hide_index=True)
                                if st.button("목록 초기화", type="secondary"):
                                    st.session_state.maint_parts = []
                                    st.rerun()

                            # 비용 자동 합산
                            calc_cost = sum([p['금액'] for p in st.session_state.maint_parts])
                            f_cost = st.number_input("총 정비 비용", value=calc_cost, step=1000)
                            f_down = st.number_input("비가동(분)", step=10)
                            
                            if st.button("저장", type="primary"):
                                # 부품 목록 문자열 변환
                                parts_text = ", ".join([f"{item['부품명']}({item['금액']:,})" for item in st.session_state.maint_parts])
                                if not parts_text and p_in: # 입력창에만 있고 추가 안 누른 경우 처리
                                    parts_text = f"{p_in}({c_in:,})"
                                    if f_cost == 0: f_cost = c_in

                                # [수정] 한국 시간 적용
                                rec = {"날짜": str(f_date), "설비ID": f_eq, "설비명": eq_map[f_eq], "작업구분": f_type.split()[0], "작업내용": f_desc, "교체부품": parts_text, "비용": f_cost, "비가동시간": f_down, "입력시간": str(get_now()), "작성자": st.session_state.user_info['id']}
                                append_data(rec, SHEET_MAINTENANCE)
                                st.session_state.maint_parts = [] # 초기화
                                st.toast("저장 완료", icon="✅")
                                time.sleep(0.5)
                                st.rerun()
                    else: st.info("🔒 뷰어 모드입니다.")
                with c2:
                    # [수정] 최근 정비 내역 - 관리자만 수정/삭제 가능
                    st.markdown("#### 📋 최근 정비 내역")
                    df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
                    if not df.empty:
                        # 관리자인 경우 수정/삭제 가능 (Data Editor)
                        if st.session_state.user_info['role'] == 'admin':
                            df_display = df.sort_values("입력시간", ascending=False).head(50)
                            df_display.insert(0, "삭제", False)

                            edited_df = st.data_editor(
                                df_display,
                                hide_index=True,
                                use_container_width=True,
                                column_config={
                                    "삭제": st.column_config.CheckboxColumn(required=True),
                                    "입력시간": st.column_config.TextColumn(disabled=True) # 키 값 보호
                                },
                                disabled=["입력시간"], # 입력시간은 절대 수정 불가
                                key="maint_editor"
                            )
                            
                            c_btn1, c_btn2 = st.columns(2)
                            with c_btn1:
                                if st.button("선택 항목 삭제", type="secondary", key="del_maint"):
                                    to_delete = edited_df[edited_df["삭제"] == True]
                                    if not to_delete.empty:
                                        try:
                                            ws = get_worksheet(SHEET_MAINTENANCE)
                                            all_data = get_as_dataframe(ws)
                                            # 입력시간 기준 삭제
                                            for t in to_delete['입력시간']:
                                                idx_to_drop = all_data[all_data['입력시간'].astype(str) == str(t)].index
                                                all_data = all_data.drop(idx_to_drop)
                                            
                                            save_data(all_data, SHEET_MAINTENANCE)
                                            st.success(f"{len(to_delete)}건 삭제 완료")
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"삭제 중 오류: {e}")
                                    else:
                                        st.info("삭제할 항목 선택 필요")
                            
                            with c_btn2:
                                if st.button("수정사항 저장", type="primary", key="save_maint"):
                                    try:
                                        ws = get_worksheet(SHEET_MAINTENANCE)
                                        all_data = get_as_dataframe(ws)
                                        all_data['입력시간'] = all_data['입력시간'].astype(str) # 비교 위해 문자열 변환
                                        
                                        # 변경된 내용 반영
                                        for index, row in edited_df.iterrows():
                                            if row['삭제']: continue # 삭제 체크된건 건너뜀
                                            
                                            # 입력시간이 일치하는 원본 행 찾기
                                            match_idx = all_data[all_data['입력시간'] == str(row['입력시간'])].index
                                            if not match_idx.empty:
                                                # 컬럼별 업데이트
                                                for col in COLS_MAINTENANCE:
                                                    if col != '입력시간': # 키 값 제외
                                                        all_data.at[match_idx[0], col] = row[col]
                                        
                                        save_data(all_data, SHEET_MAINTENANCE)
                                        st.success("수정사항 저장 완료")
                                        time.sleep(1)
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"저장 중 오류: {e}")
                        else:
                            # 관리자 아니면 조회만
                            st.dataframe(df.sort_values("입력시간", ascending=False).head(20), hide_index=True, use_container_width=True)
            
            with t2:
                df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
                st.dataframe(df, use_container_width=True)
            
            with t3:
                st.markdown("#### 📊 보전 분석 리포트")
                
                # [수정] 분석 로직 - 버튼 트리거 방식
                if st.button("보전 분석 실행"):
                    df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
                    
                    if df.empty:
                        st.info("데이터가 없습니다.")
                    else:
                        df['비가동시간'] = pd.to_numeric(df['비가동시간'], errors='coerce').fillna(0)
                        
                        # [추가] 1. 문제 설비 TOP 3 (비가동시간 기준)
                        top_down = df.groupby('설비명')['비가동시간'].sum().sort_values(ascending=False).head(3)
                        
                        # [수정] 소수점 제거 및 단위(분) 추가
                        top_down_display = top_down.astype(int).reset_index()
                        top_down_display.columns = ['설비명', '비가동시간(분)']
                        
                        # [추가] 2. BM 비율 경고
                        bm_count = len(df[df['작업구분'] == 'BM'])
                        total_count = len(df)
                        bm_rate = 0
                        if total_count > 0:
                            bm_rate = (bm_count / total_count) * 100
                        
                        # [추가] 3. 반복 고장 설비 (BM 횟수)
                        repeat_fail = df[df['작업구분'] == 'BM']['설비명'].value_counts().head(3)

                        # --- UI 배치 ---
                        c_a1, c_a2 = st.columns(2)
                        
                        with c_a1:
                            st.error("🚨 비가동시간 상위 설비 (TOP 3)")
                            st.table(top_down_display)

                        with c_a2:
                            if bm_rate > 40:
                                st.error(f"⚠️ 고장정비(BM) 비율 {bm_rate:.1f}% → 예방정비 강화 필요")
                            else:
                                st.success(f"✅ 고장정비(BM) 비율 {bm_rate:.1f}% (관리 양호)")
                            
                            st.warning("🔁 반복 고장 설비 (BM 빈도 TOP 3)")
                            if not repeat_fail.empty:
                                st.table(repeat_fail.reset_index(name="고장횟수"))
                            else:
                                st.info("반복 고장 데이터 없음")

                        st.markdown("---")
                        st.subheader("💰 유형별 정비 비용 분석")
                        
                        df['비용'] = pd.to_numeric(df['비용'], errors='coerce').fillna(0)
                        
                        if not df.empty:
                            cost_agg = df.groupby('작업구분')['비용'].sum().reset_index()
                            
                            base = alt.Chart(cost_agg).encode(
                                x=alt.X('작업구분', sort='-y', axis=alt.Axis(labelAngle=0, title="작업 구분")),
                                y=alt.Y('비용', axis=alt.Axis(format=',d', title="총 비용 (원)")),
                                color=alt.Color('작업구분', legend=None)
                            )

                            bars = base.mark_bar(cornerRadiusTopLeft=10, cornerRadiusTopRight=10).encode(
                                tooltip=['작업구분', alt.Tooltip('비용', format=',d', title="비용(원)")]
                            )

                            text = base.mark_text(
                                align='center',
                                baseline='bottom',
                                dy=-5,
                                fontSize=12,
                                fontWeight='bold'
                            ).encode(
                                text=alt.Text('비용', format=',d')
                            )

                            chart = (bars + text).properties(
                                height=400,
                                title="작업 유형별 총 비용 비교"
                            ).configure_axis(
                                grid=False,
                                labelFontSize=12,
                                titleFontSize=14
                            ).configure_title(
                                fontSize=16,
                                anchor='start'
                            )

                            st.altair_chart(chart, use_container_width=True)
                        else:
                            st.info("비용 데이터가 없습니다.")

        except Exception as e: st.error(f"설비보전 오류: {e}")

    # --- 4. 일일점검 탭 ---
    with main_tabs[3]:
        try:
            tab1, tab2 = st.tabs(["✍ 점검 입력", "📄 리포트"])
            with tab1:
                # [수정] 저장 후 스크롤 상단 이동 (부모 창 스크롤 제어)
                if st.session_state.get('scroll_to_top'):
                    components.html("""
                        <script>
                            window.parent.scrollTo({top: 0, behavior: 'smooth'});
                        </script>
                    """, height=0)
                    st.session_state['scroll_to_top'] = False

                c_date, c_line = st.columns([1, 2])
                with c_date:
                    # [수정] 한국 시간 적용
                    sel_date = st.date_input("점검 일자", get_now(), key="check_date_input")
                
                df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
                df_master = get_daily_check_master_data()
                
                if df_master.empty:
                    st.warning("점검 항목이 없습니다.")
                else:
                    lines = df_master['line'].unique()
                    with c_line:
                        sel_line = st.selectbox("라인 선택", lines)
                    
                    line_data = df_master[df_master['line'] == sel_line]
                    
                    # [추가] 선택된 날짜의 점검 상태 판단 로직
                    total_items = len(line_data)
                    checked_count = 0
                    
                    if not df_res.empty:
                        # 날짜 비교를 위한 전처리
                        df_res['date_only'] = df_res['date'].astype(str).str.split().str[0]
                        
                        # 현재 날짜 및 라인에 해당하는 점검 이력 필터링
                        status_df = df_res[
                            (df_res['date_only'] == str(sel_date)) & 
                            (df_res['line'] == sel_line)
                        ]
                        
                        # 중복 제거(동일 항목 여러번 저장 시) 후 카운트
                        if not status_df.empty:
                            checked_count = len(status_df.drop_duplicates(['equip_id', 'item_name']))

                    # 상태 알림 메시지 표시
                    if checked_count == 0:
                        st.error(f"❌ {sel_date} : 점검 미실시 (0/{total_items})")
                    elif checked_count < total_items:
                        st.warning(f"⚠️ {sel_date} : 점검 진행 중 ({checked_count}/{total_items})")
                    else:
                        st.success(f"✅ {sel_date} : 점검 완료 ({checked_count}/{total_items})")

                    prev_data = {}
                    if not df_res.empty:
                        df_res['date_only'] = df_res['date'].astype(str).str.split().str[0]
                        df_filtered = df_res[(df_res['date_only'] == str(sel_date)) & (df_res['line'] == sel_line)]
                        if not df_filtered.empty:
                            df_filtered = df_filtered.sort_values('timestamp').drop_duplicates(['equip_id', 'item_name'], keep='last')
                            for _, r in df_filtered.iterrows():
                                prev_data[f"{r['equip_id']}_{r['item_name']}"] = {'val': r['value'], 'ox': r['ox'], 'memo': r.get('비고', '')}

                    st.markdown(f"##### 📝 {sel_line} 점검 입력")
                    
                    # 뷰어 모드 체크
                    is_viewer = st.session_state.user_info['role'] == 'viewer'

                    for equip_name, group in line_data.groupby("equip_name", sort=False):
                        with st.container(border=True):
                            st.markdown(f"**🛠 {equip_name}**")
                            for _, row in group.iterrows():
                                uid = f"{row['equip_id']}_{row['item_name']}"
                                c1, c2, c3 = st.columns([2, 2, 1])
                                c1.markdown(f"**{row['item_name']}**\n<span style='color:gray;font-size:0.9em'>{row['check_content']}</span>", unsafe_allow_html=True)
                                
                                key_val = f"v_{uid}_{sel_date}"
                                key_memo = f"m_{uid}_{sel_date}"
                                prev = prev_data.get(uid, {})
                                
                                # [추가] NG 판단 및 메모 입력을 위한 현재 상태 추적
                                current_val = None
                                is_ng_condition = False

                                with c2:
                                    if row['check_type'] == 'OX':
                                        # st.radio 값을 변수로 받아 즉시 판단
                                        current_val = st.radio("판정", ["OK", "NG"], key=key_val, horizontal=True, label_visibility="collapsed", index=0 if prev.get('ox')=='OK' else 1 if prev.get('ox')=='NG' else 0, disabled=is_viewer)
                                        if current_val == 'NG':
                                            is_ng_condition = True
                                    else:
                                        current_val = st.number_input("수치", key=key_val, step=0.1, value=float(prev.get('val')) if prev.get('val') and str(prev.get('val')).replace('.','',1).isdigit() else None, disabled=is_viewer)
                                        # 수치형 NG 판단 로직
                                        if current_val is not None:
                                            try:
                                                v_f = float(current_val)
                                                mn = float(row['min_val']) if row['min_val'] != "" else None
                                                mx = float(row['max_val']) if row['max_val'] != "" else None
                                                if mn is not None and v_f < mn: is_ng_condition = True
                                                if mx is not None and v_f > mx: is_ng_condition = True
                                            except: pass

                                    # [추가] NG 발생 시 사유 입력 필드 표시
                                    if is_ng_condition:
                                        st.text_input("📝 불량 사유 / 조치 내역", value=prev.get('memo', ''), key=key_memo, placeholder="사유를 입력하세요")
                                
                                with c3:
                                    st.caption(f"기준: {row['standard']}")
                    
                    st.markdown("---")
                    signer = st.text_input("점검자", value=st.session_state.user_info['name'], disabled=is_viewer)
                    
                    if not is_viewer:
                        if st.button(f"💾 {sel_line} 저장", type="primary", use_container_width=True):
                            # [복구] 점검 데이터 수집 및 저장 로직
                            rows_to_add = []
                            now_ts = str(get_now())
                            
                            for _, row in line_data.iterrows():
                                uid = f"{row['equip_id']}_{row['item_name']}"
                                key_val = f"v_{uid}_{sel_date}"
                                key_memo = f"m_{uid}_{sel_date}" # 메모 키
                                
                                val = st.session_state.get(key_val)
                                memo_val = st.session_state.get(key_memo, "") # 메모 값 가져오기
                                
                                # 값이 입력된 경우에만 저장
                                if val is not None:
                                    final_ox = "OK"
                                    final_val = str(val)
                                    
                                    if row['check_type'] == 'OX':
                                        final_ox = val # "OK" or "NG"
                                        final_val = "" 
                                    else:
                                        # 수치형 판단 로직 (기준값 있다면)
                                        try:
                                            v_num = float(val)
                                            mn = float(row['min_val']) if row['min_val'] != '' else None
                                            mx = float(row['max_val']) if row['max_val'] != '' else None
                                            
                                            if mn is not None and v_num < mn: final_ox = "NG"
                                            if mx is not None and v_num > mx: final_ox = "NG"
                                        except:
                                            pass
                                    
                                    rows_to_add.append([
                                        str(sel_date),
                                        sel_line,
                                        row['equip_id'],
                                        row['item_name'],
                                        final_val,
                                        final_ox,
                                        signer,
                                        now_ts,
                                        memo_val # [수정] 비고란에 메모 저장
                                    ])
                            
                            if rows_to_add:
                                append_rows(rows_to_add, SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
                                st.toast("저장되었습니다.")
                                st.session_state['scroll_to_top'] = True
                                time.sleep(0.5)
                                st.rerun()
                            else:
                                st.warning("저장할 내용이 없습니다.")
                    else:
                        st.info("🔒 뷰어 모드입니다.")

            with tab2:
                st.markdown("#### 📄 일일점검 리포트 출력")
                c_r1, c_r2 = st.columns([1, 2])
                
                # [수정] 한국 시간 적용
                report_date = c_r1.date_input("리포트 날짜", get_now(), key="daily_report_date")
                
                c_r2.write("") # 여백
                c_r2.write("") 
                
                if c_r2.button("PDF 생성", key="btn_generate_daily_pdf"):
                    with st.spinner("PDF 생성 중..."):
                        pdf_bytes = generate_all_daily_check_pdf(str(report_date))
                        if pdf_bytes:
                            st.download_button(
                                label="📥 PDF 다운로드",
                                data=pdf_bytes,
                                file_name=f"Daily_Check_Report_{report_date}.pdf",
                                mime="application/pdf",
                                key="download_daily_pdf"
                            )
                            st.success("생성 완료! 위 버튼을 눌러 다운로드하세요.")
                        else:
                            st.error("해당 날짜의 데이터가 없거나 생성 중 오류가 발생했습니다.")

        except Exception as e: st.error(f"일일점검 오류: {e}")

    # --- 5. 기준정보 탭 ---
    with main_tabs[4]:
        if st.session_state.user_info['role'] == 'admin':
            try:
                t1, t2, t3 = st.tabs(["📦 품목 기준정보", "🏭 설비 기준정보", "✅ 일일점검 기준정보"])
                with t1:
                    st.markdown("#### 품목 마스터 관리")
                    df = load_data(SHEET_ITEMS, COLS_ITEMS)
                    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="item_master")
                    if st.button("품목 저장"): 
                        save_data(edited, SHEET_ITEMS)
                        st.rerun()
                with t2:
                    st.markdown("#### 설비 마스터 관리")
                    df = load_data(SHEET_EQUIPMENT, COLS_EQUIPMENT)
                    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="eq_master")
                    if st.button("설비 저장"): 
                        save_data(edited, SHEET_EQUIPMENT)
                        st.rerun()
                with t3:
                    st.markdown("#### 일일점검 항목 관리 (Master)")
                    st.caption("여기서 수정한 내용은 '일일점검관리' -> '점검 입력'에 반영됩니다.")
                    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
                    edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="check_master")
                    if st.button("점검 기준 저장"): 
                        save_data(edited, SHEET_CHECK_MASTER)
                        st.rerun()
            except Exception as e:
                st.error(f"기준정보 관리 로딩 오류: {e}")
        else:
            st.error("🚫 접근 권한이 없습니다. (관리자 전용)")

# ------------------------------------------------------------------
# 메인 실행
# ------------------------------------------------------------------
if check_password():
    run_app()