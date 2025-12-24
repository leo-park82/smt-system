import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import json
import os
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
    .stApp { background-color: #f8fafc; }
    .dashboard-header { background: linear-gradient(135deg, #3b82f6 0%, #1e3a8a 100%); padding: 20px 30px; border-radius: 12px; color: white; margin-bottom: 20px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }
    .metric-card { background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
    /* 라디오 버튼 가로 배치 스타일 */
    div.row-widget.stRadio > div { flex-direction: row; gap: 10px; }
    div.row-widget.stRadio > div > label { background-color: #fff; padding: 5px 15px; border-radius: 5px; border: 1px solid #e2e8f0; }
    div.row-widget.stRadio > div > label[data-baseweb="radio"] { margin-right: 0; }
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

# 초기 마스터 데이터
DEFAULT_CHECK_MASTER = [
    # 1 LINE
    {"line": "1 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "AIR 압력", "check_content": "압력 게이지 지침 확인", "standard": "0.5 MPa ± 0.1", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "수/자동 전환", "check_content": "MODE 전환 스위치 작동", "standard": "정상 동작", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "매거진 상태", "check_content": "Locking 마모, 휨, 흔들림", "standard": "마모/휨 없을 것", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "HP-520S", "equip_name": "SCREEN PRINTER", "item_name": "AIR 압력", "check_content": "압력 게이지 지침 확인", "standard": "0.5 MPa ± 0.1", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "HP-520S", "equip_name": "SCREEN PRINTER", "item_name": "테이블 오염", "check_content": "테이블 위 솔더/이물 청결", "standard": "청결할 것", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "S2", "equip_name": "CHIP MOUNTER", "item_name": "AIR 압력", "check_content": "메인 공압 게이지 확인", "standard": "5 Kg/cm² ± 0.5", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "S2", "equip_name": "CHIP MOUNTER", "item_name": "필터 및 노즐", "check_content": "Head Air 필터 및 노즐 오염", "standard": "오염 및 변형 없을 것", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "1809MK", "equip_name": "REFLOW", "item_name": "N2 PPM", "check_content": "산소 농도 모니터 수치", "standard": "3000 ppm 이하", "check_type": "NUMBER", "min_val": "0", "max_val": "3000", "unit": "ppm"},
    {"line": "1 LINE", "equip_id": "1809MK", "equip_name": "REFLOW", "item_name": "배기관 OPEN", "check_content": "배기 댐퍼 열림 위치", "standard": "오픈 위치", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    
    # 2 LINE
    {"line": "2 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "AIR 압력", "check_content": "게이지 지침 확인", "standard": "0.5 MPa ± 0.1", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "2 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "수/자동 전환", "check_content": "스위치 작동 확인", "standard": "정상 동작", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "2 LINE", "equip_id": "SBSF-200Y", "equip_name": "VACUUM LOADER", "item_name": "PCB 흡착 패드", "check_content": "패드 손상 여부", "standard": "찢어짐 없을 것", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    
    # 공통/기타
    {"line": "AOI", "equip_id": "ZENITH", "equip_name": "AOI 검사", "item_name": "카메라 LED", "check_content": "LED 조명 점등 상태", "standard": "정상 동작", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "AOI", "equip_id": "ZENITH", "equip_name": "AOI 검사", "item_name": "검사 상태", "check_content": "마스터 샘플 검출 여부", "standard": "정상 검사 완료", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    
    {"line": "수삽 LINE", "equip_id": "SAF-700", "equip_name": "FLUX 도포기", "item_name": "플럭스 노즐", "check_content": "분사 상태 육안 확인", "standard": "육안 확인", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "수삽 LINE", "equip_id": "SAS-680L", "equip_name": "자동납땜기", "item_name": "납조 상태", "check_content": "납조 찌꺼기 청결 상태", "standard": "청결", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    
    {"line": "SOLDER 보관온도", "equip_id": "REF-01", "equip_name": "솔더크림 보관고", "item_name": "보관 온도", "check_content": "온도계 지침 확인", "standard": "0~10℃", "check_type": "NUMBER", "min_val": "0", "max_val": "10", "unit": "℃"},
    {"line": "온,습도 CHECK", "equip_id": "ENV-01", "equip_name": "현장 온습도", "item_name": "실내 온도", "check_content": "온도 관리 기준", "standard": "24±5℃", "check_type": "NUMBER", "min_val": "19", "max_val": "29", "unit": "℃"},
    {"line": "온,습도 CHECK", "equip_id": "ENV-01", "equip_name": "현장 온습도", "item_name": "실내 습도", "check_content": "습도 관리 기준", "standard": "40~60%", "check_type": "NUMBER", "min_val": "40", "max_val": "60", "unit": "%"}
]

DEFAULT_EQUIPMENT = [
    {"id": "SML-120Y", "name": "IN LOADER (1/2 LINE)", "func": "PCB 공급"},
    {"id": "SBSF-200", "name": "VACUUM LOADER", "func": "PCB 흡착 이송"},
    {"id": "L5000", "name": "MARKING MACHINE", "func": "PCB 마킹"},
    {"id": "HP-520S", "name": "SCREEN PRINTER", "func": "솔더 페이스트 도포"},
    {"id": "TROL-7700EL", "name": "SPI", "func": "솔더 검사"},
    {"id": "S2", "name": "CHIP MOUNTER (S2)", "func": "부품 실장"},
    {"id": "L2", "name": "이형 MOUNTER (L2)", "func": "이형 부품 실장"},
    {"id": "1809MK", "name": "REFLOW OVEN", "func": "솔더링 (경화)"},
    {"id": "SMU-120Y", "name": "UN LOADER", "func": "PCB 적재"},
    {"id": "ZENITH", "name": "AOI", "func": "외관 검사"},
    {"id": "SAF-700", "name": "FLUX SPRAYER", "func": "플럭스 도포"},
    {"id": "SAS-680L", "name": "WAVE SOLDER", "func": "웨이브 솔더링"}
]

# ------------------------------------------------------------------
# 2. 구글 시트 연결
# ------------------------------------------------------------------
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

def get_worksheet(sheet_name, create_cols=None):
    client = get_gs_connection()
    if not client: return None
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
    except:
        st.error(f"시트 '{GOOGLE_SHEET_NAME}'를 찾을 수 없습니다.")
        return None
    try:
        ws = sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        if create_cols:
            ws = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
            ws.append_row(create_cols)
        else: return None
    return ws

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
    
    hist = {
        "날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, 
        "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, 
        "작성자": user, "입력시간": str(datetime.now())
    }
    append_data(hist, SHEET_INV_HISTORY)

# ------------------------------------------------------------------
# 3. 서버 사이드 로직 (Python)
# ------------------------------------------------------------------
def get_daily_check_master_data():
    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    if df.empty or len(df) < 5:
        df = pd.DataFrame(DEFAULT_CHECK_MASTER)
        save_data(df, SHEET_CHECK_MASTER)
    return df

def generate_all_daily_check_pdf(date_str):
    df_m = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    
    df_r = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    df_r = df_r[df_r['date'] == date_str]
    
    if not df_r.empty:
        df_r = df_r.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')

    pdf = FPDF()
    font_path = 'NanumGothic.ttf' 
    if not os.path.exists(font_path): font_path = 'C:\\Windows\\Fonts\\malgun.ttf'
    try:
        pdf.add_font('Korean', '', font_path, uni=True)
    except:
        pass

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
        df_final = pd.merge(line_master, df_r, on=['line', 'equip_id', 'item_name'], how='left')
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

# ------------------------------------------------------------------
# 5. 메인 메뉴
# ------------------------------------------------------------------
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
# 6. 기능 구현
# ------------------------------------------------------------------

# [1] 대시보드
if menu == "📊 대시보드":
    df_prod = load_data(SHEET_RECORDS, COLS_RECORDS)
    df_check = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    today = datetime.now().strftime("%Y-%m-%d")

    prod_today = 0
    if not df_prod.empty:
        df_prod['날짜'] = pd.to_datetime(df_prod['날짜'], errors='coerce')
        df_prod['수량'] = pd.to_numeric(df_prod['수량'], errors='coerce').fillna(0)
        prod_today = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == today]['수량'].sum()
    
    check_today = len(df_check[df_check['date'] == today]) if not df_check.empty else 0
    ng_today = len(df_check[(df_check['date'] == today) & (df_check['ox'] == 'NG')]) if not df_check.empty else 0

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

# [2] 생산관리
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
                st.markdown("##### 📉 일별 생산량")
                c = alt.Chart(df.groupby('날짜')['수량'].sum().reset_index()).mark_bar().encode(x='날짜', y='수량').interactive()
                st.altair_chart(c, use_container_width=True)
            with c2:
                st.markdown("##### 🍰 공정별 비중")
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
                table_rows = "".join([f"<tr><td style='border:1px solid #ddd; padding:8px;'>{r['구분']}</td><td style='border:1px solid #ddd;'>{r['품목코드']}</td><td style='border:1px solid #ddd;'>{r['제품명']}</td><td style='border:1px solid #ddd; text-align:right;'>{r['수량']:,}</td></tr>" for _, r in daily_df.iterrows()])
                html_report = f"""
                <div id="pdf-content" style="display:none; width:210mm; background:white; padding:20mm; font-family:'Noto Sans KR', sans-serif;">
                    <h1 style="text-align:center; border-bottom:2px solid #333; padding-bottom:10px;">SMT Daily Report</h1>
                    <p>Date: {report_date}</p>
                    <table style="width:100%; border-collapse:collapse; margin-top:20px; font-size:12px;">
                        <tr style="background:#f5f5f5; font-weight:bold;"><th style="border:1px solid #ddd; padding:8px;">Category</th><th style="border:1px solid #ddd;">Code</th><th style="border:1px solid #ddd;">Name</th><th style="border:1px solid #ddd;">Qty</th></tr>
                        {table_rows}
                    </table>
                </div>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
                <script>
                    async function genPDF() {{
                        const {{ jsPDF }} = window.jspdf; const el = document.getElementById('pdf-content'); el.style.display = 'block'; el.style.position = 'absolute'; el.style.top = '-9999px';
                        const cvs = await html2canvas(el, {{ scale: 2 }}); const img = cvs.toDataURL('image/png');
                        const pdf = new jsPDF('p', 'mm', 'a4'); pdf.addImage(img, 'PNG', 0, 0, pdf.internal.pageSize.getWidth(), (cvs.height*pdf.internal.pageSize.getWidth())/cvs.width);
                        pdf.save("Production_Report_{report_date}.pdf"); el.style.display = 'none';
                    }}
                </script>
                <button onclick="genPDF()" style="background:#ef4444; color:white; padding:10px 20px; border:none; border-radius:5px; font-weight:bold; cursor:pointer;">📄 PDF 다운로드 (JS)</button>
                """
                components.html(html_report, height=100)
            else: st.warning("해당 날짜에 생산 실적이 없습니다.")

# [3] 설비보전관리
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
        st.markdown("#### 📊 설비 고장 분석")
        df = load_data(SHEET_MAINTENANCE, COLS_MAINTENANCE)
        if not df.empty:
            df['비용'] = pd.to_numeric(df['비용'], errors='coerce').fillna(0)
            if HAS_ALTAIR:
                c = alt.Chart(df).mark_bar().encode(x='작업구분', y='비용', color='작업구분').interactive()
                st.altair_chart(c, use_container_width=True)

# [4] 일일점검관리
elif menu == "✅ 일일점검관리":
    # [수정] 탭 순서 변경 (입력 -> 현황 -> 이력/PDF)
    tab1, tab2, tab3 = st.tabs(["✍ 점검 입력 (Native)", "📊 점검 현황", "📄 점검 이력 / PDF"])
    
    # 1. 점검 입력 (Native)
    with tab1:
        st.info("💡 PC/태블릿 공용 입력 화면입니다.")
        
        # 1. 설정 선택
        c_l, c_d = st.columns(2)
        sel_line = c_l.selectbox("점검 라인 선택", ["1 LINE", "2 LINE", "AOI", "수삽 LINE", "MASK 세척기", "SOLDER 보관온도", "온,습도 CHECK", "인두기 CHECK"], key="chk_line")
        sel_date = c_d.date_input("점검 일자", datetime.now(), key="chk_date")
        
        # 2. 마스터 데이터 로드 (정렬 유지)
        df_master = get_daily_check_master_data()
        df_master = df_master[df_master['line'] == sel_line]
        
        # 기존 결과 로드
        df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        prev_data = {}
        if not df_res.empty:
            df_filtered = df_res[(df_res['date'] == str(sel_date)) & (df_res['line'] == sel_line)]
            for _, r in df_filtered.iterrows():
                key = f"{r['equip_id']}_{r['item_name']}"
                prev_data[key] = {'val': r['value'], 'ox': r['ox']}

        # 일괄 합격 처리
        if st.button("✅ 일괄 합격 처리 (빈 항목 OK 채우기)"):
            for _, row in df_master.iterrows():
                widget_key = f"check_val_{row['equip_id']}_{row['item_name']}"
                if row['check_type'] == 'OX':
                    st.session_state[widget_key] = "OK"
            st.rerun()

        # 3. 입력 폼 생성
        with st.form("check_form"):
            for equip_name, group in df_master.groupby("equip_name", sort=False):
                st.subheader(f"🛠 {equip_name}")
                
                for _, row in group.iterrows():
                    uid = f"{row['equip_id']}_{row['item_name']}"
                    widget_key = f"check_val_{uid}"
                    
                    default_val = prev_data.get(uid, {}).get('val', None)
                    
                    c1, c2, c3 = st.columns([2, 2, 1])
                    c1.markdown(f"**{row['item_name']}**\n\n<span style='font-size:0.8em; color:gray'>{row['check_content']}</span>", unsafe_allow_html=True)
                    
                    with c2:
                        if row['check_type'] == 'OX':
                            idx = 0 
                            if default_val == "NG": idx = 1
                            if widget_key in st.session_state:
                                if st.session_state[widget_key] == "OK": idx = 0
                                elif st.session_state[widget_key] == "NG": idx = 1
                            
                            st.radio("판정", ["OK", "NG"], key=widget_key, horizontal=True, index=idx, label_visibility="collapsed")
                        else:
                            # [수정] 수치 입력란: value=None으로 설정하여 0.00 삭제 필요 없게 함
                            val_init = None
                            if default_val and default_val != '-' and default_val != 'None':
                                try:
                                    val_init = float(default_val)
                                except:
                                    val_init = None
                            
                            st.number_input(
                                f"수치 ({row['unit']})", 
                                value=val_init, 
                                step=0.1, 
                                key=widget_key, 
                                placeholder="터치하여 입력"
                            )
                    
                    with c3:
                        st.markdown(f"기준: {row['standard']}")
                st.divider()
            
            # [수정] 서명란 개선: 체크박스 제거, 직관적인 입력 유도
            st.markdown("#### ✍️ 전자 서명 (Sign)")
            
            sig_col1, sig_col2 = st.columns([3, 1])
            with sig_col1:
                signer_name = st.text_input("점검자 성명 (Name)", value=st.session_state.user_info['name'], placeholder="이름을 입력하세요")
            with sig_col2:
                if signer_name:
                    st.success("서명 가능")
                else:
                    st.warning("이름 필요")

            st.caption("※ 성명을 입력하고 아래 '서명 및 저장' 버튼을 누르면 전자 서명이 완료됩니다.")
            
            if st.form_submit_button("🖱️ 서명 및 저장 (Sign & Save)", type="primary", use_container_width=True):
                if signer_name:
                    rows_to_save = []
                    ng_list = []
                    
                    for _, row in df_master.iterrows():
                        uid = f"{row['equip_id']}_{row['item_name']}"
                        w_key = f"check_val_{uid}"
                        val = st.session_state.get(w_key)
                        
                        ox = "OK"
                        if val is None:
                            final_val = ""
                        else:
                            final_val = str(val)
                        
                        if row['check_type'] == 'OX':
                            if val == 'NG': ox = 'NG'
                        else:
                            if val is None:
                                ox = "OK" 
                            else:
                                try:
                                    num_val = float(val)
                                    min_v = float(row['min_val']) if row['min_val'] else -999999
                                    max_v = float(row['max_val']) if row['max_val'] else 999999
                                    if not (min_v <= num_val <= max_v): ox = 'NG'
                                except: ox = 'NG'
                        
                        if ox == 'NG': ng_list.append(f"{row['item_name']}")
                        
                        rows_to_save.append([
                            str(sel_date), sel_line, row['equip_id'], row['item_name'], 
                            final_val, ox, signer_name, str(datetime.now())
                        ])
                    
                    if rows_to_save:
                        append_rows(rows_to_save, SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
                        sig_row = [str(sel_date), sel_line, signer_name, "Electronic Signature (Native)", str(datetime.now())]
                        append_rows([sig_row], SHEET_CHECK_SIGNATURE, COLS_CHECK_SIGNATURE)
                        st.success("✅ 점검 결과 및 서명이 저장되었습니다.")
                        if ng_list: st.error(f"다음 항목에서 NG가 발생했습니다: {', '.join(ng_list)}")
                        time.sleep(1)
                        st.rerun()
                else:
                    st.error("⚠️ 성명을 입력해주세요.")

    # 2. 점검 현황
    with tab2:
        st.markdown("##### 오늘의 점검 현황")
        today = datetime.now().strftime("%Y-%m-%d")
        df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        df_today = df_res[df_res['date'] == today] if not df_res.empty else pd.DataFrame()
        
        c1, c2, c3 = st.columns(3)
        c1.metric("대상 라인", "2개 라인") 
        c2.metric("금일 점검 항목 수", f"{len(df_today)} 건")
        ng_today = df_today[df_today['ox']=='NG'] if not df_today.empty else pd.DataFrame()
        c3.metric("NG 발견", f"{len(ng_today)} 건")

        if not ng_today.empty:
            st.error("🚨 금일 NG 발생 항목")
            st.dataframe(ng_today)
        else: st.info("오늘 점검 데이터가 아직 없습니다.")

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

# [5] 기준정보관리
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
            st.caption("여기서 수정한 내용은 '일일점검관리' -> '점검 입력(HTML)'에 반영됩니다.")
            df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
            edited = st.data_editor(df, num_rows="dynamic", use_container_width=True, key="check_master")
            col_b1, col_b2 = st.columns(2)
            if col_b1.button("점검 기준 저장"): save_data(edited, SHEET_CHECK_MASTER); st.rerun()
            if col_b2.button("⚠️ 기본값으로 초기화 (복구용)", type="primary"):
                save_data(pd.DataFrame(DEFAULT_CHECK_MASTER), SHEET_CHECK_MASTER)
                st.success("초기화 완료"); time.sleep(1); st.rerun()
        else: st.dataframe(load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER))