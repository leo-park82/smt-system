import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import hashlib
import base64
import socket # IP 확인을 위해 추가
from fpdf import FPDF
import streamlit.components.v1 as components

# [안전 장치] 시각화 라이브러리(Altair) 로드 시도
try:
    import altair as alt
    HAS_ALTAIR = True
except Exception as e:
    HAS_ALTAIR = False
    print(f"Warning: 시각화 라이브러리(Altair) 로드 실패 - {e}")

# ------------------------------------------------------------------
# 1. 기본 설정 및 디자인 (Tablet/Mobile Responsive)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT Dashboard", 
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="auto" 
)

# [CSS] 반응형 대시보드 스타일 적용
st.markdown("""
    <style>
    /* 폰트 및 기본 배경 설정 */
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', sans-serif !important;
        color: #1e293b;
    }
    
    /* 전체 앱 배경 */
    .stApp {
        background-color: #f8fafc;
    }

    /* 상단 헤더 감추기 및 여백 조정 */
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    [data-testid="stDecoration"] { display: none; }
    .block-container { padding-top: 1rem; padding-bottom: 5rem; }

    /* 1. 스마트 카드 스타일 (공통) */
    .smart-card {
        background: #ffffff;
        border-radius: 16px;
        padding: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
        border: 1px solid #f1f5f9;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
        height: 100%;
    }
    .smart-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.05), 0 4px 6px -2px rgba(0, 0, 0, 0.025);
    }

    /* 2. 대시보드 헤더 스타일 */
    .dashboard-header {
        background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
        padding: 30px 40px;
        border-radius: 20px;
        color: white;
        margin-bottom: 30px;
        box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.3);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .header-title { font-size: 2rem; font-weight: 800; margin: 0; letter-spacing: -0.02em; }
    .header-subtitle { font-size: 1rem; opacity: 0.9; margin-top: 5px; font-weight: 400; }

    /* 3. KPI 메트릭 스타일 */
    .kpi-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    .kpi-value {
        font-size: 2.2rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 4px;
    }
    .kpi-trend {
        font-size: 0.9rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 6px;
    }
    .trend-up { color: #10b981; background: #ecfdf5; padding: 2px 8px; border-radius: 12px; }
    .trend-neutral { color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 12px; }

    /* 4. 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
        background-color: transparent;
        padding-bottom: 10px;
        flex-wrap: wrap; /* 모바일에서 탭 줄바꿈 허용 */
    }
    .stTabs [data-baseweb="tab"] {
        height: 45px;
        border-radius: 12px;
        background-color: #ffffff;
        border: 1px solid #e2e8f0;
        color: #64748b;
        font-weight: 600;
        padding: 0 24px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05);
        flex-grow: 1; /* 모바일에서 탭 꽉 차게 */
    }
    .stTabs [aria-selected="true"] {
        background-color: #4f46e5 !important;
        color: #ffffff !important;
        border-color: #4f46e5 !important;
        box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.3);
    }

    /* 5. 사이드바 스타일 */
    section[data-testid="stSidebar"] {
        background-color: #ffffff;
        border-right: 1px solid #e2e8f0;
    }
    .sidebar-user-card {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 12px;
        padding: 16px;
        text-align: center;
        margin-bottom: 20px;
    }

    /* 6. 로그인 화면 스타일 */
    .login-spacer { height: 10vh; }
    .login-card {
        background: white;
        border-radius: 24px;
        padding: 40px 30px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.08);
        border: 1px solid #e2e8f0;
        text-align: center;
    }
    .login-icon {
        background: linear-gradient(135deg, #4f46e5 0%, #818cf8 100%);
        width: 70px;
        height: 70px;
        border-radius: 20px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 32px;
        color: white;
        margin: 0 auto 20px auto;
        box-shadow: 0 10px 20px rgba(79, 70, 229, 0.3);
    }
    .login-title {
        font-size: 1.8rem;
        font-weight: 800;
        color: #1e293b;
        margin-bottom: 5px;
        letter-spacing: -0.5px;
    }
    .login-subtitle {
        color: #64748b;
        font-size: 0.95rem;
        margin-bottom: 30px;
    }
    div[data-testid="stForm"] {
        border: none;
        padding: 0;
        box-shadow: none;
    }
    
    /* 접속 정보 카드 스타일 */
    .network-card {
        background: #f1f5f9;
        border-radius: 8px;
        padding: 12px;
        font-size: 0.85rem;
        color: #475569;
        border: 1px dashed #cbd5e1;
        margin-top: 20px;
    }

    /* [중요] 7. 태블릿/모바일 반응형 미디어 쿼리 */
    @media (max-width: 768px) {
        .dashboard-header {
            padding: 20px;
            flex-direction: column;
            text-align: center;
            gap: 15px;
        }
        .header-title { font-size: 1.5rem; }
        .smart-card { padding: 15px; }
        .kpi-value { font-size: 1.8rem; }
        .login-card { padding: 30px 20px; }
        /* 모바일에서 테이블 폰트 조절 */
        div[data-testid="stDataFrame"] { font-size: 0.85rem; }
    }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. 로그인 및 보안 로직
# ------------------------------------------------------------------

def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

USERS = {
    "park": {
        "name": "Park",
        "password_hash": make_hash("1083"),
        "role": "admin",
        "desc": "System Administrator"
    },
    "suk": {
        "name": "Suk",
        "password_hash": make_hash("1734"),
        "role": "editor",
        "desc": "Production Manager"
    },
    "kim": {
        "name": "Kim",
        "password_hash": make_hash("8943"),
        "role": "editor",
        "desc": "Equipment Engineer"
    }
}

def check_password():
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_info" not in st.session_state:
        st.session_state.user_info = None

    if st.session_state.logged_in:
        return True

    # 로그인 화면 레이아웃 (중앙 정렬 - 반응형 고려)
    c1, c2, c3 = st.columns([1, 10, 1]) 
    with c2:
        sc1, sc2, sc3 = st.columns([1, 1.2, 1])
        if st.sidebar.empty: # 모바일 감지 힌트
             sc1, sc2, sc3 = st.columns([0.1, 1, 0.1])

        with sc2:
            st.markdown("<div class='login-spacer'></div>", unsafe_allow_html=True)
            
            logo_html = '<div class="login-icon">🏭</div>'
            if os.path.exists("logo.png"):
                try:
                    with open("logo.png", "rb") as f:
                        img_data = f.read()
                        b64_data = base64.b64encode(img_data).decode()
                        logo_html = f'<div style="text-align:center; margin-bottom:20px;"><img src="data:image/png;base64,{b64_data}" style="max-width: 150px; height: auto;"></div>'
                except:
                    pass

            st.markdown(f"""
                <div class="login-card">
                    {logo_html}
                    <div class="login-title">SMT</div>
                    <div class="login-subtitle">Smart Manufacturing System</div>
            """, unsafe_allow_html=True)
            
            with st.form(key="login_form"):
                username = st.text_input("Username", key="login_id", placeholder="Enter your ID")
                password = st.text_input("Password", type="password", key="login_pw", placeholder="Enter your password")
                
                # 모바일 키보드 자동완성 방지
                components.html("""<script>
                    window.parent.document.querySelectorAll('input[type="password"]').forEach(i=>{
                        i.setAttribute('autocomplete','new-password');
                    });
                </script>""", height=0, width=0)
                
                st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
                login_btn = st.form_submit_button("Sign In", type="primary", use_container_width=True)
            
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div style='text-align: center; margin-top: 20px;'>", unsafe_allow_html=True)
            if st.button("Guest Access (Viewer)", type="secondary"):
                st.session_state.logged_in = True
                st.session_state.user_info = {"id": "viewer", "name": "Guest", "role": "viewer", "desc": "Viewer Mode"}
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)

            if login_btn:
                if username in USERS:
                    hashed_input = make_hash(password)
                    if hashed_input == USERS[username]["password_hash"]:
                        st.session_state.logged_in = True
                        st.session_state.user_info = {
                            "id": username,
                            "name": USERS[username]["name"],
                            "role": USERS[username]["role"],
                            "desc": USERS[username]["desc"]
                        }
                        st.toast(f"Welcome back, {USERS[username]['name']}!", icon="🚀")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.toast("비밀번호가 일치하지 않습니다.", icon="🔒")
                else:
                    st.toast("존재하지 않는 계정입니다.", icon="🚫")
                
    return False

if not check_password():
    st.stop()

CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")
IS_EDITOR = (CURRENT_USER["role"] in ["admin", "editor"])

st.markdown("""<style>[data-testid="stSidebar"] { display: block; }</style>""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 3. 데이터 및 파일 처리 함수
# ------------------------------------------------------------------
def create_pdf_report(daily_df, report_date):
    pdf = FPDF()
    pdf.add_page()
    font_path = 'C:\\Windows\\Fonts\\malgun.ttf'
    if not os.path.exists(font_path):
        font_path = "NanumGothic.ttf"
    
    if os.path.exists(font_path):
        try:
            pdf.add_font('Malgun', '', font_path, uni=True)
            pdf.set_font('Malgun', '', 12)
        except:
            pdf.set_font('Arial', '', 12)
    else:
        pdf.set_font('Arial', '', 12) 
    
    pdf.set_font_size(24)
    pdf.cell(0, 20, 'SMT Daily Production Report', ln=True, align='C')
    pdf.set_font_size(12)
    pdf.cell(0, 10, f'Date: {report_date.strftime("%Y-%m-%d")}', ln=True, align='R')
    pdf.ln(5)
    
    total_qty = daily_df['수량'].sum()
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font_size(14)
    pdf.cell(0, 15, f'  Total Qty: {total_qty:,} EA', ln=True, fill=True)
    pdf.ln(10)
    
    pdf.set_font_size(11)
    pdf.set_fill_color(79, 70, 229)
    pdf.set_text_color(255, 255, 255)
    col_w = [30, 40, 90, 30]
    headers = ['Category', 'Item Code', 'Item Name', 'Qty']
    for i, h in enumerate(headers): pdf.cell(col_w[i], 10, h, border=1, align='C', fill=True)
    pdf.ln()
    
    pdf.set_text_color(0, 0, 0)
    pdf.set_font_size(10)
    daily_df = daily_df.sort_values(by=['구분', '제품명'])
    for _, row in daily_df.iterrows():
        line_height = 8
        pdf.cell(col_w[0], line_height, str(row['구분']), border=1, align='C')
        pdf.cell(col_w[1], line_height, str(row['품목코드']), border=1, align='C')
        p_name = str(row['제품명'])
        if len(p_name) > 35: p_name = p_name[:32] + "..."
        pdf.cell(col_w[2], line_height, "  " + p_name, border=1, align='L')
        pdf.cell(col_w[3], line_height, f"{row['수량']:,}", border=1, align='R')
        pdf.ln()
        
    pdf.ln(20)
    pdf.set_font_size(11)
    pdf.cell(95, 10, "Writer: __________________", align='C')
    pdf.cell(95, 10, "Approver: __________________", align='C')
    return bytes(pdf.output())

def read_uploaded_file(upl):
    try:
        upl.seek(0)
        return pd.read_excel(upl)
    except:
        pass 

    encodings = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
    separators = [',', '\t']
    
    for enc in encodings:
        for sep in separators:
            try:
                upl.seek(0)
                df = pd.read_csv(upl, encoding=enc, sep=sep, on_bad_lines='skip', engine='python')
                if not df.empty and len(df.columns) >= 2: 
                    return df
            except:
                pass
    
    raise ValueError("파일 형식을 인식할 수 없습니다.")

# ------------------------------------------------------------------
# 4. 데이터 로드 및 저장
# ------------------------------------------------------------------
FILE_RECORDS = "production_data.csv"
FILE_ITEMS = "item_codes.csv"
FILE_INVENTORY = "inventory_data.csv"
FILE_INV_HISTORY = "inventory_history.csv"
FILE_MAINTENANCE = "maintenance_data.csv"
FILE_EQUIPMENT = "equipment_list.csv"

# 전체 35개 설비 목록 (초기 데이터)
DEFAULT_EQUIPMENT = [
    {"id": "CIMON-SMT34", "name": "Loader (SLD-120Y)", "func": "메거진 로딩"},
    {"id": "CIMON-SMT17", "name": "Loader (SLD-120Y)", "func": "메거진 로딩"},
    {"id": "CIMON-SMT02", "name": "VACUUM LOADER(SBSF-200)", "func": "VACUUM 로딩"},
    {"id": "CIMON-SMT18", "name": "VACUUM LOADER(SBSF-200Y)", "func": "VACUUM 로딩"},
    {"id": "CIMON-SMT41", "name": "Marking (L5000)", "func": "PCB Marking"},
    {"id": "CIMON-SMT42", "name": "Marking (L5000)", "func": "PCB Marking"},
    {"id": "CIMON-SMT03", "name": "Screen Printer (HP-520S)", "func": "솔더링 설비 (크림솔더)"},
    {"id": "CIMON-SMT19", "name": "Screen Printer (HP-520S)", "func": "솔더링 설비 (크림솔더)"},
    {"id": "CIMON-SMT32", "name": "TROL-7700EL (SPI)", "func": "솔더프린터 검사"},
    {"id": "CIMON-SMT33", "name": "TROL-7700EL (SPI)", "func": "솔더프린터 검사"},
    {"id": "CIMON-SMT36", "name": "칩마운터(S2)", "func": "칩부품 마운팅 설비"},
    {"id": "CIMON-SMT37", "name": "칩마운터(S2)", "func": "칩부품 마운팅 설비"},
    {"id": "CIMON-SMT38", "name": "칩마운터(L2)", "func": "이형부품 마운팅 설비"},
    {"id": "CIMON-SMT39", "name": "칩마운터(L2)", "func": "이형부품 마운팅 설비"},
    {"id": "CIMON-SMT07", "name": "TRAY FEEDER(STF100S)", "func": "트레이부품 공급설비"},
    {"id": "CIMON-SMT23", "name": "TRAY FEEDER(STF100S)", "func": "트레이부품 공급설비"},
    {"id": "CIMON-SMT08", "name": "REFLOW(1809MKⅢ)", "func": "리플로우 오븐"},
    {"id": "CIMON-SMT24", "name": "REFLOW(1809MKⅢ)", "func": "리플로우 오븐"},
    {"id": "CIMON-SMT35", "name": "Un Loader (SUD-120Y)", "func": "메거진 언로딩"},
    {"id": "CIMON-SMT25", "name": "Un Loader (SUD-120Y)", "func": "메거진 언로딩"},
    {"id": "CIMON-SMT10", "name": "N2 발생기(PP-N15R-99)", "func": "질소 발생기"},
    {"id": "CIMON-SMT26", "name": "N2 발생기(PP-N15R-99)", "func": "질소 발생기"},
    {"id": "CIMON-SMT28", "name": "HKU-50L", "func": "초음파세척기"},
    {"id": "CIMON-SMT40", "name": "CO-150 (오븐기)", "func": "자재 Baking"},
    {"id": "CIMON-SMT29", "name": "AOI검사(ZENITH) 고영", "func": "비젼 검사"},
    {"id": "CIMON-SMT30", "name": "SML-120X (Loader)", "func": "AOI 로더"},
    {"id": "CIMON-SMT31", "name": "SMU-120X (UN Loader)", "func": "AOI 언로더"},
    {"id": "CIMON-SMT45", "name": "교반기", "func": "솔더크림 믹싱"},
    {"id": "CIMON-SMT44", "name": "Profile Checker", "func": "온도 프로파일"},
    {"id": "CIMON-SMT12", "name": "JBMMC-3S/4S", "func": "마스크 세척기"},
    {"id": "CIMON-SMT13", "name": "INSERT CONVEYOR(3M)", "func": "작업 콘베어"},
    {"id": "CIMON-SMT14", "name": "FLUX도포기(SAF-700)", "func": "FLUX 도포기"},
    {"id": "CIMON-SMT15", "name": "Soldering Machine", "func": "웨이브 솔더링"},
    {"id": "CIMON-SMT16", "name": "COOLING CONVEYOR", "func": "PCB 쿨링"},
    {"id": "CIMON-SMT46", "name": "후공정 작업대", "func": "수작업대"}
]

DEFAULT_HISTORY = []

def init_files():
    files = {
        FILE_ITEMS: ["품목코드", "제품명"],
        FILE_INVENTORY: ["품목코드", "제품명", "현재고"],
        FILE_RECORDS: ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"],
        FILE_INV_HISTORY: ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"],
        FILE_MAINTENANCE: ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"],
        FILE_EQUIPMENT: ["id", "name", "func"]
    }
    for fname, cols in files.items():
        if not os.path.exists(fname):
            if fname == FILE_EQUIPMENT:
                pd.DataFrame(DEFAULT_EQUIPMENT).to_csv(fname, index=False, encoding='utf-8-sig')
            elif fname == FILE_MAINTENANCE:
                pd.DataFrame(DEFAULT_HISTORY).to_csv(fname, index=False, encoding='utf-8-sig')
            else:
                pd.DataFrame(columns=cols).to_csv(fname, index=False, encoding='utf-8-sig')
        else:
            try:
                if fname in [FILE_RECORDS, FILE_MAINTENANCE]:
                    df = pd.read_csv(fname)
                    for col in ["수정자", "수정시간"]:
                        if col not in df.columns: df[col] = ""
                    if "작성자" not in df.columns: df["작성자"] = "Admin"
                    
                    if fname == FILE_MAINTENANCE:
                        if len(df) == 5 and "노즐 흡착 에러 발생으로 인한 노즐 세척 및 교체" in df['작업내용'].values:
                            df = pd.DataFrame(columns=cols) 
                            
                    df.to_csv(fname, index=False, encoding='utf-8-sig')
            except: pass

init_files()

def load_data(fname):
    try: return pd.read_csv(fname)
    except: return pd.DataFrame()

def save_data(df, fname):
    df.to_csv(fname, index=False, encoding='utf-8-sig')
    return True

def append_data(data_dict, fname):
    df = load_data(fname)
    new_df = pd.DataFrame([data_dict])
    final = pd.concat([df, new_df], ignore_index=True)
    save_data(final, fname)

def update_inventory(code, name, change, reason, user):
    df = load_data(FILE_INVENTORY)
    if not df.empty and '현재고' in df.columns:
        df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
    if code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    save_data(df, FILE_INVENTORY)
    hist = {"날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, "작성자": user, "입력시간": str(datetime.now())}
    append_data(hist, FILE_INV_HISTORY)

def get_user_id():
    if st.session_state.logged_in and st.session_state.user_info:
        return st.session_state.user_info["name"]
    return "Unknown"

def save_all_items(df): return save_data(df, FILE_ITEMS)
def delete_all_items(): 
    pd.DataFrame(columns=["품목코드", "제품명"]).to_csv(FILE_ITEMS, index=False, encoding='utf-8-sig')
    return True

def save_with_history(new_df, file_name, key_col, modifier_name):
    if not modifier_name:
        st.error("⚠️ 수정자 이름 오류")
        return False
        
    old_df = load_data(file_name)
    cnt = 0
    now_str = str(datetime.now().strftime("%Y-%m-%d %H:%M"))
    
    for idx, new_row in new_df.iterrows():
        match = old_df[old_df[key_col] == new_row[key_col]]
        if not match.empty:
            old_row = match.iloc[0]
            is_changed = False
            for col in new_df.columns:
                if col in ['수정자', '수정시간', '작성자']: continue
                if str(new_row[col]) != str(old_row[col]):
                    is_changed = True
                    break
            
            if is_changed:
                new_df.at[idx, '수정자'] = modifier_name
                new_df.at[idx, '수정시간'] = now_str
                cnt += 1
    
    full_df = load_data(file_name)
    new_keys = new_df[key_col].tolist()
    
    original_top_5 = full_df.sort_values("입력시간", ascending=False).head(5)
    original_keys = original_top_5[key_col].tolist()
    
    keys_to_delete = [k for k in original_keys if k not in new_keys]
    
    if keys_to_delete:
        full_df = full_df[~full_df[key_col].isin(keys_to_delete)]
        
    full_df = full_df[~full_df[key_col].isin(new_keys)]
    
    final_df = pd.concat([full_df, new_df], ignore_index=True)
    
    save_data(final_df, file_name)
    return cnt + len(keys_to_delete)

# ------------------------------------------------------------------
# [신규 기능] 내부 IP 조회 함수
# ------------------------------------------------------------------
def get_ip_address():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # 실제 연결하지 않고 IP만 확인
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# ------------------------------------------------------------------
# 5. UI 구성 및 메뉴 로직 (Smart Layout)
# ------------------------------------------------------------------
CATEGORIES = ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"]

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    
    st.markdown("<h2 style='text-align:center; color:#1e293b; margin-top:0;'>SMT System</h2>", unsafe_allow_html=True)
    
    if st.session_state.logged_in:
        u_info = st.session_state.user_info
        
        role_badge = "👑 Admin" if u_info["role"] == "admin" else "👤 User" if u_info["role"] == "editor" else "👀 Viewer"
        role_style = "background:#dcfce7; color:#15803d;" if u_info["role"] == "admin" else "background:#dbeafe; color:#1d4ed8;"
        
        st.markdown(f"""
            <div class="sidebar-user-card">
                <div style="font-size:1.2rem; font-weight:bold;">{u_info['name']}</div>
                <div style="font-size:0.8rem; color:#64748b; margin-bottom:8px;">{u_info['desc']}</div>
                <span style="font-size:0.75rem; padding:4px 10px; border-radius:12px; font-weight:bold; {role_style}">
                    {role_badge}
                </span>
            </div>
        """, unsafe_allow_html=True)
    
    menu = st.radio("Navigation", [
        "🏭 생산관리", 
        "🛠️ 설비보전관리"
    ], label_visibility="collapsed")
    
    st.markdown("---")
    
    # [신규] 접속 정보 표시 (내부 IP)
    with st.expander("📡 접속 정보 확인 (IP)", expanded=False):
        my_ip = get_ip_address()
        st.markdown(f"""
        <div class="network-card">
            <b>🏠 같은 와이파이 접속 시:</b><br>
            <span style="color:#2563eb; font-weight:bold;">http://{my_ip}:8501</span><br>
            <br>
            <small>PC 방화벽에서 8501 포트가 허용되어 있어야 접속 가능합니다.</small>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")
    
    if st.button("Sign Out", type="secondary", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.rerun()

# ------------------------------------------------------------------
# 6. 메뉴별 화면 표시 (Smart UI Content)
# ------------------------------------------------------------------

titles = {
    "🏭 생산관리": {"t": "Production Management", "d": "실시간 생산 실적 및 재고 통합 관리", "color": "linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)"},
    "🛠️ 설비보전관리": {"t": "Maintenance System", "d": "설비 예방 정비 및 고장 이력 분석", "color": "linear-gradient(135deg, #059669 0%, #10b981 100%)"}
}

if menu in titles:
    info = titles[menu]
    st.markdown(f"""
        <div class="dashboard-header" style="background: {info['color']};">
            <div>
                <h2 class="header-title">{info['t']}</h2>
                <div class="header-subtitle">{info['d']}</div>
            </div>
            <div style="font-size: 2.5rem; opacity: 0.8;">📊</div>
        </div>
    """, unsafe_allow_html=True)

# 1. 생산관리
if menu == "🏭 생산관리":
    tab_prod, tab_inv, tab_dash, tab_rpt, tab_std = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 대시보드", "📑 보고서", "⚙️ 기준정보"])

    # 1-1. 생산실적등록
    with tab_prod:
        item_df = load_data(FILE_ITEMS)
        item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
        
        c1, c2 = st.columns([1, 1.6], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container():
                    st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                    st.markdown("#### ✏️ 신규 생산 등록")
                    st.markdown("<br>", unsafe_allow_html=True)
                    
                    date = st.date_input("작업 일자", datetime.now())
                    cat = st.selectbox("공정 구분", CATEGORIES)
                    
                    def on_code():
                        c = st.session_state.code_in.upper().strip()
                        if c in item_map: st.session_state.name_in = item_map[c]
                    
                    code = st.text_input("품목 코드", key="code_in", on_change=on_code)
                    name = st.text_input("제품명", key="name_in")
                    qty = st.number_input("생산 수량", min_value=1, value=100)
                    writer = st.text_input("작성자", value=get_user_id(), disabled=True)
                    
                    auto_deduct = False
                    if cat in ["후공정", "후공정 외주"]:
                        st.markdown("---")
                        auto_deduct = st.checkbox("📦 반제품 재고 자동 차감", value=True)
                    
                    keep_input = st.checkbox("저장 후 입력내용 유지", value=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("저장하기", type="primary", use_container_width=True):
                        if name:
                            rec = {
                                "날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, 
                                "수량":qty, "입력시간":str(datetime.now()), 
                                "작성자":writer, "수정자":"", "수정시간":""
                            }
                            append_data(rec, FILE_RECORDS)
                            if auto_deduct:
                                update_inventory(code, name, -qty, f"생산출고({cat})", writer)
                            st.toast("저장 완료!", icon="✅")
                            
                            if not keep_input:
                                st.session_state['code_in'] = ""
                                st.session_state['name_in'] = ""
                            
                            time.sleep(0.5); st.rerun()
                        else: st.error("제품명을 입력해주세요.")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.warning("🔒 뷰어 모드에서는 데이터를 입력할 수 없습니다.")

        with c2:
            st.markdown("""<div class="smart-card" style="height:auto;">""", unsafe_allow_html=True)
            st.markdown("#### 📋 최근 등록 내역 (수정 가능)")
            df = load_data(FILE_RECORDS)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False)
                if IS_EDITOR:
                    modifier = st.text_input("수정자 (자동 입력)", value=get_user_id(), key="prod_mod", disabled=True)
                    row_mode = "dynamic" if IS_ADMIN else "fixed"
                    edited = st.data_editor(df, use_container_width=True, hide_index=True, num_rows=row_mode, key="edit_rec", height=500)
                    
                    if st.button("수정사항 저장", type="primary", use_container_width=True):
                        cnt = save_with_history(edited, FILE_RECORDS, "입력시간", modifier)
                        st.toast("수정 완료!", icon="✅")
                        time.sleep(0.5); st.rerun()
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True, height=600)
            else:
                st.info("데이터가 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)

    # 1-2. 반제품 현황
    with tab_inv:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        c_search, c_dummy = st.columns([1, 2])
        search = c_search.text_input("🔍 재고 검색", placeholder="품목명 또는 코드")
        
        df = load_data(FILE_INVENTORY)
        if not df.empty:
            if search:
                mask = df['품목코드'].astype(str).str.contains(search, case=False) | df['제품명'].astype(str).str.contains(search, case=False)
                df = df[mask]
            if '현재고' in df.columns:
                df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
                df = df[df['현재고'] > 0]
            st.dataframe(df, use_container_width=True, hide_index=True, height=600)
        else: st.info("등록된 재고 데이터가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    # 1-3. 통합 대시보드
    with tab_dash:
        df = load_data(FILE_RECORDS)
        if not df.empty:
            if '구분' in df.columns: df['구분'] = df['구분'].astype(str).str.strip()
            unique_cats = df['구분'].unique().tolist()
            combined_cats = sorted(list(set(CATEGORIES + unique_cats)))

            with st.container():
                st.markdown("""<div class="smart-card" style="padding: 15px 24px; margin-bottom: 20px;">""", unsafe_allow_html=True)
                c_f1, c_f2 = st.columns([1, 2])
                d_range = c_f1.date_input("조회 기간", (datetime.now().replace(day=1), datetime.now()), label_visibility="collapsed")
                cats = c_f2.multiselect("공정 필터", combined_cats, default=combined_cats, key="dash_filter", label_visibility="collapsed")
                st.markdown("</div>", unsafe_allow_html=True)

            if len(d_range) == 2:
                mask = (pd.to_datetime(df['날짜']).dt.date >= d_range[0]) & (pd.to_datetime(df['날짜']).dt.date <= d_range[1]) & (df['구분'].isin(cats))
                df_filtered = df[mask]
                
                if not df_filtered.empty:
                    total_qty = df_filtered['수량'].sum()
                    days = (d_range[1] - d_range[0]).days + 1
                    avg_qty = int(total_qty / days) if days > 0 else 0
                    top_proc = df_filtered.groupby('구분')['수량'].sum().idxmax() if not df_filtered['구분'].empty else "-"
                    
                    # Smart KPI Cards
                    k1, k2, k3 = st.columns(3)
                    
                    k1.markdown(f"""
                        <div class="smart-card">
                            <div class="kpi-title">Total Production</div>
                            <div class="kpi-value">{total_qty:,}</div>
                            <div class="kpi-trend trend-up">📅 {days}일간 누적</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    k2.markdown(f"""
                        <div class="smart-card">
                            <div class="kpi-title">Daily Average</div>
                            <div class="kpi-value">{avg_qty:,}</div>
                            <div class="kpi-trend trend-neutral">📈 일평균 생산</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    k3.markdown(f"""
                        <div class="smart-card">
                            <div class="kpi-title">Top Process</div>
                            <div class="kpi-value" style="font-size: 1.8rem; margin-top: 5px;">{top_proc}</div>
                            <div class="kpi-trend trend-up">🏆 최다 생산</div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
                    
                    if HAS_ALTAIR:
                        cc1, cc2 = st.columns([2, 1])
                        with cc1:
                            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                            st.markdown("##### 📈 일별 생산 추이")
                            daily_trend = df_filtered.groupby('날짜')['수량'].sum().reset_index()
                            daily_trend['날짜'] = pd.to_datetime(daily_trend['날짜'])
                            line = alt.Chart(daily_trend).mark_line(point=True, color='#4f46e5', strokeWidth=3).encode(
                                x=alt.X('날짜:T', axis=alt.Axis(format='%m-%d', title=None)),
                                y=alt.Y('수량', title=None),
                                tooltip=[alt.Tooltip('날짜', format='%Y-%m-%d'), '수량']
                            ).interactive()
                            st.altair_chart(line, use_container_width=True)
                            st.markdown("</div>", unsafe_allow_html=True)
                        
                        with cc2:
                            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                            st.markdown("##### 🍰 공정 점유율")
                            dist = df_filtered.groupby('구분')['수량'].sum().reset_index()
                            pie = alt.Chart(dist).mark_arc(innerRadius=60).encode(
                                theta=alt.Theta("수량", stack=True),
                                color=alt.Color("구분", scale=alt.Scale(scheme='tableau10'), legend=None),
                                tooltip=["구분", "수량"]
                            )
                            st.altair_chart(pie, use_container_width=True)
                            st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.warning("⚠️ 차트 기능을 사용할 수 없습니다.")

                    with st.expander("📋 상세 데이터 펼쳐보기"):
                        st.dataframe(df_filtered, use_container_width=True)
                else: st.warning("조건에 맞는 데이터가 없습니다.")
        else: st.info("데이터가 없습니다.")

    # 1-4. 보고서 출력
    with tab_rpt:
        if IS_ADMIN:
            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
            t_d, t_p = st.tabs(["📅 일일 보고서 (PDF)", "📆 기간별 보고서 (CSV)"])
            with t_d:
                c1, c2 = st.columns([1, 3])
                report_date = c1.date_input("날짜 선택", datetime.now(), key="daily_date")
                col_b1, col_b2 = st.columns(2)
                with col_b1: gen = st.button("미리보기", use_container_width=True)
                with col_b2: save = st.button("📂 서버 저장", use_container_width=True, type="primary")

                df = load_data(FILE_RECORDS)
                if not df.empty:
                    mask = pd.to_datetime(df['날짜']).dt.date == report_date
                    daily = df[mask]
                    if not daily.empty:
                        summ = daily.groupby(['구분', '제품명', '품목코드'])['수량'].sum().reset_index()
                        if gen or save:
                            st.success(f"총 {daily['수량'].sum():,} EA 생산")
                            st.dataframe(summ, use_container_width=True, hide_index=True)
                        if gen or save:
                            try:
                                pdf_bytes = create_pdf_report(summ, report_date)
                                if gen: st.download_button("📄 PDF 다운로드", pdf_bytes, f"SMT_{report_date}.pdf", "application/pdf", use_container_width=True)
                                if save:
                                    target = r"\\172.30.10.241\부서자료\공장\창조경영실\생산본부\SMT 생산팀\SMT 생산업무일지"
                                    fpath = os.path.join(target, f"SMT_일일보고서_{report_date.strftime('%Y%m%d')}.pdf")
                                    try:
                                        if os.path.exists(target):
                                            with open(fpath, "wb") as f: f.write(pdf_bytes)
                                            st.success(f"저장 완료: {fpath}")
                                        else: st.error("경로 없음")
                                    except: st.error("저장 실패")
                            except: st.error("PDF 생성 실패")
                    else: 
                        if gen or save: st.warning("실적 없음")
            with t_p:
                c1, c2 = st.columns(2)
                s = c1.date_input("시작", datetime.now()-timedelta(7))
                e = c2.date_input("종료", datetime.now())
                if st.button("조회", use_container_width=True):
                    df = load_data(FILE_RECORDS)
                    mask = (pd.to_datetime(df['날짜']).dt.date >= s) & (pd.to_datetime(df['날짜']).dt.date <= e)
                    p_df = df[mask]
                    if not p_df.empty:
                        st.dataframe(p_df, use_container_width=True)
                        csv = p_df.to_csv(index=False).encode('utf-8-sig')
                        st.download_button("CSV 다운로드", csv, f"내역_{s}_{e}.csv", "text/csv", use_container_width=True)
                    else: st.warning("데이터 없음")
            st.markdown("</div>", unsafe_allow_html=True)
        else: st.warning("⚠️ 관리자 권한 필요")

    # 1-5. 기준정보 관리
    with tab_std:
        if IS_ADMIN:
            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
            st.markdown("#### ⚙️ 기준정보 관리")
            t1, t2 = st.tabs(["업로드", "백업"])
            with t1:
                upl = st.file_uploader("품목 일괄 등록 (Excel/CSV)")
                if upl and st.button("등록", use_container_width=True):
                    try:
                        new = read_uploaded_file(upl)
                        new.columns = ["품목코드", "제품명"] + list(new.columns[2:])
                        old = load_data(FILE_ITEMS)
                        merged = pd.concat([old, new], ignore_index=True).drop_duplicates(subset=['품목코드'], keep='last')
                        save_all_items(merged)
                        st.success(f"완료! (총 {len(merged)}개)")
                    except Exception as e: st.error(f"오류: {e}")
                if st.button("품목 전체 삭제", type="primary"):
                    delete_all_items(); st.warning("삭제됨")
            with t2:
                for f in [FILE_RECORDS, FILE_INVENTORY, FILE_ITEMS, FILE_MAINTENANCE, FILE_EQUIPMENT]:
                    if os.path.exists(f):
                        with open(f, "rb") as file: st.download_button(f"{f} 다운로드", file, f, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        else: st.warning("⚠️ 관리자 권한 필요")

# 2. 설비보전관리
elif menu == "🛠️ 설비보전관리":
    tab_reg, tab_hist, tab_dash, tab_set = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "📊 분석 및 히트맵", "⚙️ 설비 관리"])
    
    equip_df = load_data(FILE_EQUIPMENT)
    maint_df = load_data(FILE_MAINTENANCE)
    
    # 2-1. 이력 등록
    with tab_reg:
        c1, c2 = st.columns([1, 1.6], gap="large") 
        with c1:
            if IS_EDITOR:
                with st.container():
                    st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                    st.markdown("##### 📝 신규 이력 작성")
                    
                    if 'parts_buffer' not in st.session_state:
                        st.session_state['parts_buffer'] = []
                    if 'form_key' not in st.session_state:
                        st.session_state['form_key'] = 0
                    def get_key(base): return f"{base}_{st.session_state['form_key']}"

                    f_date = st.date_input("📅 작업 일자", key=get_key("date"))
                    
                    equip_options = {}
                    if not equip_df.empty:
                        equip_options = {row['id']: f"[{row['id']}] {row['name']}" for _, row in equip_df.iterrows()}
                    f_eq_id = st.selectbox("🏭 설비 선택", options=list(equip_options.keys()), format_func=lambda x: equip_options[x] if x in equip_options else x, key=get_key("eq_id"))
                    f_type = st.selectbox("🔧 구분", ["PM (예방정비)", "BM (고장수리)", "CM (개조/개선)"], key=get_key("type"))
                    f_desc = st.text_area("📝 작업 내용", placeholder="고장 증상 및 조치 내용", height=100, key=get_key("desc"))
                    
                    st.markdown("---")
                    st.markdown("###### 🔩 교체 부품")
                    c_p1, c_p2, c_p3 = st.columns([2, 1, 1])
                    if 'part_input_key' not in st.session_state: st.session_state['part_input_key'] = 0
                    p_name = c_p1.text_input("부품명", key=f"part_name_in_{st.session_state['part_input_key']}")
                    p_cost = c_p2.number_input("단가", min_value=0, step=1000, key=f"part_cost_in_{st.session_state['part_input_key']}", format="%d")
                    c_p3.markdown("<div style='height: 28px'></div>", unsafe_allow_html=True)
                    if c_p3.button("추가", use_container_width=True):
                        if p_name:
                            st.session_state['parts_buffer'].append({"name": p_name, "cost": p_cost})
                            st.session_state['part_input_key'] += 1
                            st.rerun()
                    
                    if st.session_state['parts_buffer']:
                        p_df = pd.DataFrame(st.session_state['parts_buffer'])
                        st.dataframe(p_df.style.format({"cost": "{:,.0f}"}), use_container_width=True, hide_index=True)
                        total_part_cost = p_df['cost'].sum()
                    else: total_part_cost = 0
                    
                    st.markdown("---")
                    f_cost = st.number_input("💰 총 비용 (원)", value=total_part_cost, min_value=0, step=1000, format="%d", key=get_key("total_cost"))
                    f_down = st.number_input("⏱️ 비가동 시간 (분)", min_value=0, step=10, key=get_key("down"))
                    f_worker = st.text_input("👷 작업자", value=get_user_id(), key=get_key("worker"), disabled=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("💾 이력 저장", type="primary", use_container_width=True):
                        eq_name = equip_df[equip_df['id'] == f_eq_id]['name'].values[0] if not equip_df.empty else "Unknown"
                        parts_str = ", ".join([f"{p['name']} ({p['cost']:,}원)" for p in st.session_state['parts_buffer']])
                        new_rec = {
                            "날짜": str(f_date), "설비ID": f_eq_id, "설비명": eq_name,
                            "작업구분": f_type.split()[0], "작업내용": f_desc, "교체부품": parts_str,
                            "비용": f_cost, "작업자": f_worker, "비가동시간": f_down,
                            "입력시간": str(datetime.now()), "작성자": f_worker, "수정자": "", "수정시간": ""
                        }
                        append_data(new_rec, FILE_MAINTENANCE)
                        st.session_state['parts_buffer'] = []
                        st.session_state['form_key'] += 1
                        st.toast("저장 완료!", icon="✅")
                        time.sleep(0.5); st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.warning("관리자만 입력할 수 있습니다.")
                
        with c2:
            st.markdown("""<div class="smart-card" style="height:auto;">""", unsafe_allow_html=True)
            st.markdown("#### 🚀 최근 등록 내역")
            if not maint_df.empty:
                recent_df = maint_df.sort_values("입력시간", ascending=False).head(5)
                modifier = st.text_input("수정자 (자동 입력)", value=get_user_id(), key="maint_mod_recent", disabled=True)
                
                row_mode = "dynamic" if IS_ADMIN else "fixed"
                edited_recent = st.data_editor(recent_df, use_container_width=True, hide_index=True, key="recent_maint_edit", num_rows=row_mode, column_config={"비용": st.column_config.NumberColumn(format="%,d 원")})
                
                if st.button("최근 내역 수정 저장", type="primary", use_container_width=True):
                    if IS_EDITOR:
                        cnt = save_with_history(edited_recent, FILE_MAINTENANCE, "입력시간", modifier)
                        st.toast("수정 완료!", icon="✅")
                        time.sleep(0.5); st.rerun() 
                    else: st.error("권한이 없습니다.")
            else: st.info("등록된 이력이 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)

    # 2-2. 이력 조회
    with tab_hist:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("#### 🔍 설비 이력 전체 조회")
        if not maint_df.empty:
            if IS_EDITOR:
                modifier_hist = st.text_input("수정자 (자동 입력)", value=get_user_id(), key="maint_mod_hist", disabled=True)
                row_mode = "dynamic" if IS_ADMIN else "fixed"
                edited_maint = st.data_editor(maint_df.sort_values("날짜", ascending=False), use_container_width=True, num_rows=row_mode, key="maint_editor", column_config={"비용": st.column_config.NumberColumn(format="%,d 원")})
                
                if st.button("수정사항 반영 (이력)", type="secondary"):
                    cnt = save_with_history(edited_maint, FILE_MAINTENANCE, "입력시간", modifier_hist)
                    st.toast("수정 완료!", icon="✅")
                    time.sleep(0.5); st.rerun()
            else:
                st.dataframe(maint_df, use_container_width=True)
        else: st.info("데이터가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    # 2-3. 분석 및 히트맵
    with tab_dash:
        if not maint_df.empty and '날짜' in maint_df.columns:
            maint_df['날짜'] = pd.to_datetime(maint_df['날짜'], errors='coerce')
            maint_df = maint_df.dropna(subset=['날짜'])
            maint_df['Year'] = maint_df['날짜'].dt.year
            maint_df['Month'] = maint_df['날짜'].dt.month

            current_year = datetime.now().year
            available_years = sorted(maint_df['Year'].unique().tolist(), reverse=True)
            if current_year not in available_years: available_years.insert(0, current_year)
            
            with st.container():
                st.markdown("""<div class="smart-card" style="padding:15px; margin-bottom:20px;">""", unsafe_allow_html=True)
                col_y1, col_y2 = st.columns([1, 4])
                with col_y1: selected_year = st.selectbox("📅 조회 연도", available_years)
                st.markdown("</div>", unsafe_allow_html=True)

            df_year = maint_df[maint_df['Year'] == selected_year]
        else:
            selected_year = datetime.now().year
            df_year = pd.DataFrame()

        if not df_year.empty:
            total_down = df_year['비가동시간'].sum()
            total_cost = df_year['비용'].sum()
            if '작업구분' in df_year.columns:
                is_bm_year = df_year['작업구분'].astype(str).str.strip().str.upper() == 'BM'
                bm_count = len(df_year[is_bm_year])
            else: bm_count = 0
            
            if selected_year == datetime.now().year:
                total_days = (datetime.now() - datetime(selected_year, 1, 1)).days + 1
            else: total_days = 365
            if total_days < 1: total_days = 1

            total_op_time = (total_days * 24 * 60) - total_down
            mtbf = round(total_op_time / bm_count / 60 / 24, 1) if bm_count > 0 else 0 
            mttr = round(total_down / bm_count, 1) if bm_count > 0 else 0 
            avail = round((total_op_time / (total_days * 24 * 60)) * 100, 2)
        else:
            total_down, total_cost, bm_count, mtbf, mttr, avail = 0, 0, 0, 0, 0, 0

        k1, k2, k3, k4 = st.columns(4)
        k1.markdown(f"""<div class="smart-card"><div class="kpi-title">Availability</div><div class="kpi-value">{avail}%</div><div class="kpi-trend trend-up">✅ {selected_year} 가동률</div></div>""", unsafe_allow_html=True)
        k2.markdown(f"""<div class="smart-card"><div class="kpi-title">MTBF</div><div class="kpi-value">{mtbf} <span style='font-size:1.2rem'>Days</span></div><div class="kpi-trend trend-neutral">⏳ 평균 고장 간격</div></div>""", unsafe_allow_html=True)
        k3.markdown(f"""<div class="smart-card"><div class="kpi-title">MTTR</div><div class="kpi-value">{mttr} <span style='font-size:1.2rem'>Min</span></div><div class="kpi-trend trend-neutral">🔧 평균 수리 시간</div></div>""", unsafe_allow_html=True)
        k4.markdown(f"""<div class="smart-card"><div class="kpi-title">Total Cost</div><div class="kpi-value">{total_cost:,.0f}</div><div class="kpi-trend trend-neutral">💰 연간 비용</div></div>""", unsafe_allow_html=True)

        st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)

        if HAS_ALTAIR:
            chart_df = pd.DataFrame({'월': range(1, 13)})
            chart_df['건수'] = 0
            chart_df['월_label'] = chart_df['월'].apply(lambda x: f"{x}월") 

            bm_df = pd.DataFrame()
            if not df_year.empty:
                if '작업구분' in df_year.columns:
                    is_bm = df_year['작업구분'].astype(str).str.strip().str.upper() == 'BM'
                    bm_df = df_year[is_bm].copy()
                if not bm_df.empty:
                    monthly_counts = bm_df.groupby('Month').size().reset_index(name='실적')
                    merged = pd.merge(chart_df[['월', '월_label']], monthly_counts, left_on='월', right_on='Month', how='left')
                    merged['건수'] = merged['실적'].fillna(0).astype(int)
                    chart_df = merged[['월', '월_label', '건수']]

            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
            st.markdown("##### 📉 월별 고장 추이")
            base = alt.Chart(chart_df).encode(
                x=alt.X('월_label:O', title='월', sort=list(chart_df['월_label']), axis=alt.Axis(labelAngle=0)), 
                y=alt.Y('건수:Q', title='건수', axis=alt.Axis(tickMinStep=1, format='d', titleAngle=0))
            )
            bar = base.mark_bar().encode(
                color=alt.condition(alt.datum.건수 >= 3, alt.value('#ef4444'), alt.value('#4f46e5')),
                tooltip=['월_label', '건수']
            )
            text = base.mark_text(dy=-10, color='black').encode(text='건수:Q')
            st.altair_chart(bar + text, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
            st.markdown("##### 🔥 설비별 고장(BM) 히트맵")
            if not bm_df.empty:
                heatmap_data = bm_df.groupby(['설비명', 'Month']).size().reset_index(name='건수')
                heatmap_data['MonthLabel'] = heatmap_data['Month'].apply(lambda x: f"{x}월")
                heatmap = alt.Chart(heatmap_data).mark_rect().encode(
                    x=alt.X('MonthLabel:O', title='월', sort=[f"{i}월" for i in range(1,13)], axis=alt.Axis(labelAngle=0)), 
                    y=alt.Y('설비명:N', title=None),
                    color=alt.Color('건수:Q', scale=alt.Scale(scheme='reds')),
                    tooltip=['설비명', 'MonthLabel', '건수']
                ).properties(height=400)
                st.altair_chart(heatmap, use_container_width=True)
            else: st.info("표시할 히트맵 데이터가 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)
        else: st.warning("⚠️ 차트 라이브러리(Altair) 오류")

    # 2-4. 설비 관리
    with tab_set:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("#### ⚙️ 설비 기준정보 관리")
        if IS_ADMIN:
            st.markdown("---")
            col_left, col_right = st.columns([1, 4])
            with col_left:
                if st.button("🗑️ 설비 전체 삭제", type="primary", key="del_all_eq"):
                    empty_df = pd.DataFrame(columns=["id", "name", "func"])
                    empty_df.to_csv(FILE_EQUIPMENT, index=False, encoding='utf-8-sig')
                    st.warning("⚠️ 모든 설비 데이터가 삭제되었습니다.")
                    time.sleep(1); st.rerun()

            edited_equip = st.data_editor(equip_df, num_rows="dynamic", use_container_width=True, key="equip_editor")
            if st.button("설비 목록 저장", type="primary"):
                save_data(edited_equip, FILE_EQUIPMENT)
                st.success("설비 목록이 갱신되었습니다.")
                time.sleep(0.5); st.rerun()
        else: st.error("🔒 이 메뉴는 관리자만 접근할 수 있습니다.")
        st.markdown("</div>", unsafe_allow_html=True)