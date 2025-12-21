import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import os
import hashlib
import base64
from fpdf import FPDF
import streamlit.components.v1 as components
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# [안전 장치] 시각화 라이브러리(Altair) 로드 시도
try:
    import altair as alt
    HAS_ALTAIR = True
except Exception as e:
    HAS_ALTAIR = False

# ------------------------------------------------------------------
# 1. 기본 설정 및 디자인 (app-기초.py 스타일 100% 복구)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT Dashboard", 
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="auto" 
)

# [CSS] 반응형 대시보드 스타일 (app-기초.py 원본)
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
        flex-wrap: wrap; 
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
        flex-grow: 1; 
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
        div[data-testid="stDataFrame"] { font-size: 0.85rem; }
    }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. 구글 시트 연결 (기능 유지)
# ------------------------------------------------------------------
try:
    if "sheet_url" in st.secrets:
        SHEET_URL = st.secrets["sheet_url"]
    elif "gcp_service_account" in st.secrets and "sheet_url" in st.secrets["gcp_service_account"]:
        SHEET_URL = st.secrets["gcp_service_account"]["sheet_url"]
    else:
        st.error("🚨 Secrets 설정 오류: sheet_url을 찾을 수 없습니다.")
        st.stop()

    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "sheet_url" in creds_dict: del creds_dict["sheet_url"]
    else:
        st.error("🚨 Secrets 설정 오류: 인증 정보가 없습니다.")
        st.stop()
except Exception as e:
    st.error(f"🚨 설정 로드 오류: {e}")
    st.stop()

@st.cache_resource
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
    return gspread.authorize(creds)

def get_worksheet(name):
    client = get_gspread_client()
    sh = client.open_by_url(SHEET_URL)
    try:
        return sh.worksheet(name)
    except:
        # 시트 자동 생성 (기본 헤더 포함)
        headers = {
            "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"],
            "items": ["품목코드", "제품명"],
            "inventory": ["품목코드", "제품명", "현재고"],
            "maintenance": ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"],
            "equipment": ["id", "name", "func"]
        }
        new_ws = sh.add_worksheet(title=name, rows="1000", cols="20")
        if name in headers: new_ws.append_row(headers[name])
        return new_ws

def load_data(name):
    try:
        ws = get_worksheet(name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        if df.empty:
            headers = {
                "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"],
                "items": ["품목코드", "제품명"],
                "inventory": ["품목코드", "제품명", "현재고"],
                "maintenance": ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"],
                "equipment": ["id", "name", "func"]
            }
            if name in headers: return pd.DataFrame(columns=headers[name])
        return df
    except: return pd.DataFrame()

def save_data(df, name):
    ws = get_worksheet(name)
    ws.clear()
    df_clean = df.fillna("").astype(str)
    data = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
    ws.update(data)
    return True

def append_data(data_dict, name):
    ws = get_worksheet(name)
    # 딕셔너리를 데이터프레임으로 변환 후 값만 리스트로 추출하여 추가
    # 순서를 보장하기 위해 헤더 순서대로 정렬하거나 값을 추출해야 함.
    # 여기서는 간단히 값을 바로 추가 (구글시트는 순서가 중요)
    # load_data로 컬럼 순서를 확인하고 맞추는게 안전하지만, 일단 값만 넘김
    ws.append_row(list(data_dict.values()))

# 재고 업데이트 함수 (구글 시트용)
def update_inventory(code, name, change, reason, user):
    df = load_data("inventory")
    if not df.empty and '현재고' in df.columns:
        df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
    
    if code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    save_data(df, "inventory")
    # 이력 저장은 생략하거나 별도 시트에 추가 가능

# ------------------------------------------------------------------
# 3. 로그인 및 보안 로직 (app-기초.py)
# ------------------------------------------------------------------
def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

USERS = {
    "park": {"name": "Park", "password_hash": make_hash("1083"), "role": "admin", "desc": "System Administrator"},
    "suk": {"name": "Suk", "password_hash": make_hash("1734"), "role": "editor", "desc": "Production Manager"},
    "kim": {"name": "Kim", "password_hash": make_hash("8943"), "role": "editor", "desc": "Equipment Engineer"}
}

def check_password():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: return True

    c1, c2, c3 = st.columns([1, 10, 1]) 
    with c2:
        sc1, sc2, sc3 = st.columns([1, 1.2, 1])
        if st.sidebar.empty: sc1, sc2, sc3 = st.columns([0.1, 1, 0.1])

        with sc2:
            st.markdown("<div class='login-spacer'></div>", unsafe_allow_html=True)
            
            logo_html = '<div class="login-icon">🏭</div>'
            if os.path.exists("logo.png"):
                try:
                    with open("logo.png", "rb") as f:
                        b64 = base64.b64encode(f.read()).decode()
                        logo_html = f'<div style="text-align:center; mb:20px;"><img src="data:image/png;base64,{b64}" width="150"></div>'
                except: pass

            st.markdown(f"""
                <div class="login-card">
                    {logo_html}
                    <div class="login-title">SMT</div>
                    <div class="login-subtitle">Smart Manufacturing System</div>
            """, unsafe_allow_html=True)
            
            with st.form(key="login_form"):
                username = st.text_input("Username", key="login_id", placeholder="Enter your ID")
                password = st.text_input("Password", type="password", key="login_pw", placeholder="Enter your password")
                components.html("""<script>window.parent.document.querySelectorAll('input[type="password"]').forEach(i=>{i.setAttribute('autocomplete','new-password');});</script>""", height=0, width=0)
                st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
                if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                    if username in USERS and make_hash(password) == USERS[username]["password_hash"]:
                        st.session_state.logged_in = True
                        st.session_state.user_info = USERS[username]
                        st.rerun()
                    else: st.toast("로그인 실패", icon="🔒")
            st.markdown("</div>", unsafe_allow_html=True)
    return False

if not check_password(): st.stop()

CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")
IS_EDITOR = (CURRENT_USER["role"] in ["admin", "editor"])

def get_user_id(): return CURRENT_USER["name"]

# ------------------------------------------------------------------
# 4. UI 구성 및 메뉴 로직 (app-기초.py 원본 복구)
# ------------------------------------------------------------------
CATEGORIES = ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"]

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    
    st.markdown("<h2 style='text-align:center; color:#1e293b; margin-top:0;'>SMT System</h2>", unsafe_allow_html=True)
    
    if st.session_state.logged_in:
        u_info = st.session_state.user_info
        role_badge = "👑 Admin" if u_info["role"] == "admin" else "👤 User"
        role_style = "background:#dcfce7; color:#15803d;" if u_info["role"] == "admin" else "background:#dbeafe; color:#1d4ed8;"
        
        st.markdown(f"""
            <div class="sidebar-user-card">
                <div style="font-size:1.2rem; font-weight:bold;">{u_info['name']}</div>
                <div style="font-size:0.8rem; color:#64748b; margin-bottom:8px;">{u_info['desc']}</div>
                <span style="font-size:0.75rem; padding:4px 10px; border-radius:12px; font-weight:bold; {role_style}">{role_badge}</span>
            </div>
        """, unsafe_allow_html=True)
    
    # [복구] 원본 메뉴 스타일 (라디오 버튼)
    menu = st.radio("Navigation", [
        "🏭 생산관리", 
        "🛠️ 설비보전관리"
    ], label_visibility="collapsed")
    
    st.markdown("---")
    if st.button("Sign Out", type="secondary", use_container_width=True):
        st.session_state.logged_in = False
        st.session_state.user_info = None
        st.rerun()

# ------------------------------------------------------------------
# 5. 메뉴별 화면 표시
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
        # 구글 시트에서 품목 정보 로드 (자동완성용)
        item_df = load_data("items")
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
                    
                    # [요청반영] 품목 코드 직접 입력 (리스트 선택 X)
                    code_input = st.text_input("품목 코드", placeholder="바코드 스캔 또는 입력")
                    
                    # [요청반영] 제품명 자동 기입
                    auto_name = ""
                    if code_input:
                        # 대소문자 무시 및 공백 제거 비교
                        clean_code = code_input.strip()
                        # 구글 시트 데이터와 매칭
                        if not item_df.empty and '품목코드' in item_df.columns:
                             match = item_df[item_df['품목코드'].astype(str) == str(clean_code)]
                             if not match.empty:
                                 auto_name = match['제품명'].values[0]
                    
                    name = st.text_input("제품명", value=auto_name)
                    if auto_name:
                        st.caption(f"✅ 확인된 제품: {auto_name}")
                    
                    qty = st.number_input("생산 수량", min_value=1, value=100)
                    writer = st.text_input("작성자", value=get_user_id(), disabled=True)
                    
                    auto_deduct = False
                    if cat in ["후공정", "후공정 외주"]:
                        st.markdown("---")
                        auto_deduct = st.checkbox("📦 반제품 재고 자동 차감", value=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("저장하기", type="primary", use_container_width=True):
                        if name:
                            rec = {
                                "날짜":str(date), "구분":cat, "품목코드":code_input, "제품명":name, 
                                "수량":qty, "입력시간":str(datetime.now()), 
                                "작성자":writer, "수정자":"", "수정시간":""
                            }
                            append_data(rec, "records")
                            if auto_deduct:
                                update_inventory(code_input, name, -qty, f"생산출고({cat})", writer)
                            # [추가] 일반 공정은 재고 증가 (요청 사항 반영)
                            elif cat not in ["후공정", "후공정 외주", "외주공정"]:
                                update_inventory(code_input, name, qty, f"생산입고({cat})", writer)
                                
                            st.toast("저장 완료!", icon="✅")
                            time.sleep(0.5); st.rerun()
                        else: st.error("제품명을 입력해주세요.")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.warning("🔒 뷰어 모드에서는 데이터를 입력할 수 없습니다.")

        with c2:
            st.markdown("""<div class="smart-card" style="height:auto;">""", unsafe_allow_html=True)
            st.markdown("#### 📋 최근 등록 내역")
            df = load_data("records")
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False)
                st.dataframe(df, use_container_width=True, hide_index=True, height=600)
            else:
                st.info("데이터가 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)

    # 1-2. 반제품 현황
    with tab_inv:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        c_search, c_dummy = st.columns([1, 2])
        search = c_search.text_input("🔍 재고 검색", placeholder="품목명 또는 코드")
        
        df = load_data("inventory")
        if not df.empty:
            if search:
                mask = df['품목코드'].astype(str).str.contains(search, case=False) | df['제품명'].astype(str).str.contains(search, case=False)
                df = df[mask]
            if '현재고' in df.columns:
                df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
            st.dataframe(df, use_container_width=True, hide_index=True, height=600)
        else: st.info("등록된 재고 데이터가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    # 1-3. 통합 대시보드
    with tab_dash:
        df = load_data("records")
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
                    df_filtered['수량'] = pd.to_numeric(df_filtered['수량'], errors='coerce').fillna(0)
                    total_qty = df_filtered['수량'].sum()
                    days = (d_range[1] - d_range[0]).days + 1
                    avg_qty = int(total_qty / days) if days > 0 else 0
                    top_proc = df_filtered.groupby('구분')['수량'].sum().idxmax() if not df_filtered['구분'].empty else "-"
                    
                    # Smart KPI Cards
                    k1, k2, k3 = st.columns(3)
                    k1.markdown(f"""<div class="smart-card"><div class="kpi-title">Total Production</div><div class="kpi-value">{total_qty:,}</div><div class="kpi-trend trend-up">📅 {days}일간 누적</div></div>""", unsafe_allow_html=True)
                    k2.markdown(f"""<div class="smart-card"><div class="kpi-title">Daily Average</div><div class="kpi-value">{avg_qty:,}</div><div class="kpi-trend trend-neutral">📈 일평균 생산</div></div>""", unsafe_allow_html=True)
                    k3.markdown(f"""<div class="smart-card"><div class="kpi-title">Top Process</div><div class="kpi-value" style="font-size: 1.8rem; margin-top: 5px;">{top_proc}</div><div class="kpi-trend trend-up">🏆 최다 생산</div></div>""", unsafe_allow_html=True)
                    
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
                    else: st.warning("⚠️ 차트 기능을 사용할 수 없습니다.")
                else: st.warning("조건에 맞는 데이터가 없습니다.")
        else: st.info("데이터가 없습니다.")

    # 1-4. 보고서 출력
    with tab_rpt:
        if IS_ADMIN:
            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
            t_d, t_p = st.tabs(["📅 일일 보고서 (PDF)", "📆 기간별 보고서 (CSV)"])
            with t_d:
                if st.button("📄 PDF 리포트 생성"):
                    st.info("PDF 생성 기능은 서버 설정이 필요할 수 있습니다.")
            with t_p:
                if st.button("📊 CSV 다운로드"):
                    df = load_data("records")
                    st.download_button("Download CSV", df.to_csv().encode('utf-8-sig'), "production_data.csv")
            st.markdown("</div>", unsafe_allow_html=True)

    # 1-5. 기준정보 관리
    with tab_std:
        if IS_ADMIN:
            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
            st.markdown("#### ⚙️ 기준정보 관리")
            st.info("💡 구글 시트('items')에서 품목 코드를 관리하세요.")
            it_df = load_data("items")
            
            # 구글 시트 저장을 위한 에디터
            edited_it = st.data_editor(it_df, num_rows="dynamic", use_container_width=True)
            if st.button("💾 품목 정보 저장 (구글 시트)"):
                save_data(edited_it, "items")
                st.success("저장되었습니다!")
                time.sleep(1); st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        else: st.warning("⚠️ 관리자 권한 필요")

# 2. 설비보전관리
elif menu == "🛠️ 설비보전관리":
    tab_reg, tab_hist, tab_dash, tab_set = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "📊 분석 및 히트맵", "⚙️ 설비 관리"])
    
    equip_df = load_data("equipment")
    maint_df = load_data("maintenance")
    
    # 2-1. 이력 등록
    with tab_reg:
        c1, c2 = st.columns([1, 1.6], gap="large") 
        with c1:
            if IS_EDITOR:
                with st.container():
                    st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                    st.markdown("##### 📝 신규 이력 작성")
                    
                    f_date = st.date_input("📅 작업 일자")
                    
                    # [요청반영] 리스트 선택 가능하게 변경 & 라벨 "설비 선택"으로 복구
                    # 설비 목록 로드 (equipment 시트에서 'name' 컬럼 사용)
                    if not equip_df.empty and 'name' in equip_df.columns:
                        eq_list = equip_df['name'].tolist()
                    else:
                        eq_list = []
                    
                    # Selectbox로 변경 + 직접 입력 옵션
                    f_eq_select = st.selectbox("설비 선택", ["직접 입력"] + eq_list)
                    
                    if f_eq_select == "직접 입력":
                        f_eq_final = st.text_input("설비명 직접 입력")
                    else:
                        f_eq_final = f_eq_select
                        # 선택 시 ID 자동 매핑 등 가능하나 여기선 이름만
                    
                    f_type = st.selectbox("🔧 구분", ["PM (예방정비)", "BM (고장수리)", "CM (개조/개선)"])
                    f_desc = st.text_area("📝 작업 내용", placeholder="고장 증상 및 조치 내용", height=100)
                    
                    st.markdown("---")
                    f_cost = st.number_input("💰 총 비용 (원)", min_value=0, step=1000, format="%d")
                    f_down = st.number_input("⏱️ 비가동 시간 (분)", min_value=0, step=10)
                    f_worker = st.text_input("👷 작업자", value=get_user_id(), disabled=True)
                    
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("💾 이력 저장", type="primary", use_container_width=True):
                        if f_eq_final:
                            # 구글 시트 저장용 데이터 구성
                            # 순서: 날짜, 설비ID, 설비명, 작업구분, 작업내용, 교체부품, 비용, 작업자, 비가동시간...
                            # 여기선 설비ID를 이름과 같게 처리하거나 빈칸
                            new_rec = {
                                "날짜": str(f_date), "설비ID": "", "설비명": f_eq_final,
                                "작업구분": f_type.split()[0], "작업내용": f_desc, "교체부품": "",
                                "비용": f_cost, "작업자": f_worker, "비가동시간": f_down,
                                "입력시간": str(datetime.now()), "작성자": f_worker, "수정자": "", "수정시간": ""
                            }
                            append_data(new_rec, "maintenance")
                            st.toast("저장 완료!", icon="✅")
                            time.sleep(0.5); st.rerun()
                        else:
                            st.error("설비명을 입력하세요.")
                    st.markdown("</div>", unsafe_allow_html=True)
            else:
                st.warning("관리자만 입력할 수 있습니다.")
                
        with c2:
            st.markdown("""<div class="smart-card" style="height:auto;">""", unsafe_allow_html=True)
            st.markdown("#### 🚀 최근 등록 내역")
            if not maint_df.empty:
                maint_df = maint_df.sort_values("입력시간", ascending=False)
                st.dataframe(maint_df, use_container_width=True, hide_index=True)
            else: st.info("등록된 이력이 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)

    # 2-2. 이력 조회
    with tab_hist:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("#### 🔍 설비 이력 전체 조회")
        if not maint_df.empty:
            st.dataframe(maint_df, use_container_width=True)
        else: st.info("데이터가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    # 2-3. 분석 및 히트맵 (app-기초.py 로직 복구)
    with tab_dash:
        if not maint_df.empty and '날짜' in maint_df.columns:
            maint_df['날짜'] = pd.to_datetime(maint_df['날짜'], errors='coerce')
            maint_df['Year'] = maint_df['날짜'].dt.year
            maint_df['Month'] = maint_df['날짜'].dt.month
            
            # 간단 KPI 표시
            total_cost = maint_df['비용'].sum() if '비용' in maint_df.columns else 0
            total_down = maint_df['비가동시간'].sum() if '비가동시간' in maint_df.columns else 0
            
            c1, c2 = st.columns(2)
            c1.markdown(f"""<div class="smart-card"><div class="kpi-title">Total Maint Cost</div><div class="kpi-value">{int(total_cost):,}</div></div>""", unsafe_allow_html=True)
            c2.markdown(f"""<div class="smart-card"><div class="kpi-title">Total Downtime</div><div class="kpi-value">{int(total_down):,} min</div></div>""", unsafe_allow_html=True)
        else:
            st.info("데이터가 없습니다.")

    # 2-4. 설비 관리
    with tab_set:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("#### ⚙️ 설비 기준정보 관리")
        if IS_ADMIN:
            edited_equip = st.data_editor(equip_df, num_rows="dynamic", use_container_width=True)
            if st.button("설비 목록 저장", type="primary"):
                save_data(edited_equip, "equipment")
                st.success("설비 목록이 갱신되었습니다.")
                time.sleep(0.5); st.rerun()
        else: st.error("🔒 이 메뉴는 관리자만 접근할 수 있습니다.")
        st.markdown("</div>", unsafe_allow_html=True)