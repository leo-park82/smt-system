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
# 1. 기본 설정 및 디자인 (오전 버전 스타일 복구)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT Dashboard", 
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="auto" 
)

# [CSS] 반응형 대시보드 스타일 적용 (오전 코드 원본 복구)
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    
    html, body, [class*="css"] {
        font-family: 'Pretendard', sans-serif !important;
        color: #1e293b;
    }
    .stApp { background-color: #f8fafc; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    [data-testid="stDecoration"] { display: none; }
    .block-container { padding-top: 1rem; padding-bottom: 5rem; }

    /* 스마트 카드 스타일 */
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

    /* 대시보드 헤더 스타일 */
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

    /* KPI 메트릭 스타일 */
    .kpi-title {
        font-size: 0.85rem; font-weight: 600; color: #64748b;
        text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 8px;
    }
    .kpi-value {
        font-size: 2.2rem; font-weight: 800; color: #0f172a; margin-bottom: 4px;
    }
    .kpi-trend {
        font-size: 0.9rem; font-weight: 600; display: flex; align-items: center; gap: 6px;
    }
    .trend-up { color: #10b981; background: #ecfdf5; padding: 2px 8px; border-radius: 12px; }
    .trend-neutral { color: #64748b; background: #f1f5f9; padding: 2px 8px; border-radius: 12px; }

    /* 탭 스타일 */
    .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: transparent; padding-bottom: 10px; flex-wrap: wrap; }
    .stTabs [data-baseweb="tab"] {
        height: 45px; border-radius: 12px; background-color: #ffffff;
        border: 1px solid #e2e8f0; color: #64748b; font-weight: 600; padding: 0 24px;
        box-shadow: 0 1px 2px rgba(0,0,0,0.05); flex-grow: 1;
    }
    .stTabs [aria-selected="true"] {
        background-color: #4f46e5 !important; color: #ffffff !important;
        border-color: #4f46e5 !important; box-shadow: 0 4px 6px -1px rgba(79, 70, 229, 0.3);
    }

    /* 사이드바 스타일 */
    section[data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e2e8f0; }
    .sidebar-user-card {
        background-color: #f8fafc; border: 1px solid #e2e8f0;
        border-radius: 12px; padding: 16px; text-align: center; margin-bottom: 20px;
    }

    /* 로그인 화면 스타일 */
    .login-spacer { height: 10vh; }
    .login-card {
        background: white; border-radius: 24px; padding: 40px 30px;
        box-shadow: 0 20px 40px rgba(0, 0, 0, 0.08); border: 1px solid #e2e8f0; text-align: center;
    }
    .login-icon {
        background: linear-gradient(135deg, #4f46e5 0%, #818cf8 100%);
        width: 70px; height: 70px; border-radius: 20px;
        display: flex; align-items: center; justify-content: center;
        font-size: 32px; color: white; margin: 0 auto 20px auto;
        box-shadow: 0 10px 20px rgba(79, 70, 229, 0.3);
    }
    .login-title { font-size: 1.8rem; font-weight: 800; color: #1e293b; margin-bottom: 5px; }
    .login-subtitle { color: #64748b; font-size: 0.95rem; margin-bottom: 30px; }
    div[data-testid="stForm"] { border: none; padding: 0; box-shadow: none; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. 구글 시트 연결 및 데이터 함수
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
            "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"],
            "items": ["품목코드", "제품명", "규격"],
            "inventory": ["품목코드", "제품명", "현재고"],
            "maintenance": ["날짜", "설비명", "작업구분", "내용", "비용", "비가동시간", "작업자"],
            "equipment": ["설비ID", "설비명", "공정", "상태"]
        }
        new_ws = sh.add_worksheet(title=name, rows="1000", cols="20")
        if name in headers: new_ws.append_row(headers[name])
        return new_ws

# [수정] 데이터 로드 시 빈 데이터프레임 처리 강화
def load_sheet_data(name):
    try:
        ws = get_worksheet(name)
        data = ws.get_all_records()
        df = pd.DataFrame(data)
        
        # 데이터가 없을 때 기본 컬럼 구조 반환 (에러 방지)
        if df.empty:
            headers = {
                "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"],
                "items": ["품목코드", "제품명", "규격"],
                "inventory": ["품목코드", "제품명", "현재고"],
                "maintenance": ["날짜", "설비명", "작업구분", "내용", "비용", "비가동시간", "작업자"],
                "equipment": ["설비ID", "설비명", "공정", "상태"]
            }
            if name in headers:
                return pd.DataFrame(columns=headers[name])
        return df
    except:
        return pd.DataFrame()

def save_sheet_data(df, name):
    ws = get_worksheet(name)
    ws.clear()
    df_clean = df.fillna("").astype(str)
    data = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
    ws.update(data)
    return True

def append_sheet_row(row_list, name):
    ws = get_worksheet(name)
    ws.append_row(row_list)

# ------------------------------------------------------------------
# 3. 로그인 로직 (오전 버전 복구)
# ------------------------------------------------------------------
def make_hash(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

USERS = {
    "park": {"name": "Park", "password_hash": make_hash("1083"), "role": "admin", "desc": "System Admin"},
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
                with open("logo.png", "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                    logo_html = f'<div style="text-align:center; mb:20px;"><img src="data:image/png;base64,{b64}" width="150"></div>'

            st.markdown(f"""
                <div class="login-card">
                    {logo_html}
                    <div class="login-title">SMT System</div>
                    <div class="login-subtitle">Smart Manufacturing System</div>
            """, unsafe_allow_html=True)
            
            with st.form("login_form"):
                u = st.text_input("Username", placeholder="Enter ID")
                p = st.text_input("Password", type="password", placeholder="Enter Password")
                st.markdown("<div style='height: 20px'></div>", unsafe_allow_html=True)
                if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                    if u in USERS and make_hash(p) == USERS[u]["password_hash"]:
                        st.session_state.logged_in = True
                        st.session_state.user_info = USERS[u]
                        st.rerun()
                    else: st.toast("로그인 정보가 일치하지 않습니다.", icon="🔒")
            st.markdown("</div>", unsafe_allow_html=True)
    return False

if not check_password(): st.stop()

CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")
IS_EDITOR = (CURRENT_USER["role"] in ["admin", "editor"])

# ------------------------------------------------------------------
# 4. 메뉴 구성 (오전 버전 복구)
# ------------------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown("<h2 style='text-align:center;'>SMT System</h2>", unsafe_allow_html=True)
    
    # 유저 카드
    role_badge = "👑 Admin" if IS_ADMIN else "👤 User"
    st.markdown(f"""
        <div class="sidebar-user-card">
            <div style="font-size:1.2rem; font-weight:bold;">{CURRENT_USER['name']}</div>
            <div style="font-size:0.8rem; color:#64748b; mb:8px;">{CURRENT_USER['desc']}</div>
            <span style="font-size:0.75rem; padding:4px 10px; border-radius:12px; background:#dbeafe; color:#1d4ed8;">{role_badge}</span>
        </div>
    """, unsafe_allow_html=True)
    
    menu = st.radio("Navigation", ["🏭 생산관리", "🛠️ 설비보전관리"], label_visibility="collapsed")
    st.markdown("---")
    if st.button("Sign Out", type="secondary", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

# 타이틀 표시
titles = {
    "🏭 생산관리": {"t": "Production Management", "d": "실시간 생산 실적 및 재고 통합 관리", "c": "linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%)"},
    "🛠️ 설비보전관리": {"t": "Maintenance System", "d": "설비 예방 정비 및 고장 이력 분석", "c": "linear-gradient(135deg, #059669 0%, #10b981 100%)"}
}
info = titles.get(menu, titles["🏭 생산관리"])
st.markdown(f"""
    <div class="dashboard-header" style="background: {info['c']};">
        <div><h2 class="header-title">{info['t']}</h2><div class="header-subtitle">{info['d']}</div></div>
        <div style="font-size: 2.5rem; opacity: 0.8;">📊</div>
    </div>
""", unsafe_allow_html=True)

CATEGORIES = ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "외주공정"]

# ------------------------------------------------------------------
# 5. 메인 기능 구현 (구글 시트 연동)
# ------------------------------------------------------------------

# [1] 생산관리 메뉴
if menu == "🏭 생산관리":
    tab_prod, tab_inv, tab_dash, tab_rpt, tab_std = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 대시보드", "📑 보고서", "⚙️ 기준정보"])

    # 1-1. 실적 등록
    with tab_prod:
        # 품목 정보 로드
        item_df = load_sheet_data("items")
        item_list = item_df['품목코드'].tolist() if not item_df.empty and '품목코드' in item_df.columns else []
        
        c1, c2 = st.columns([1, 1.6], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container():
                    st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                    st.markdown("#### ✏️ 신규 생산 등록")
                    
                    date = st.date_input("작업 일자", datetime.now())
                    cat = st.selectbox("공정 구분", CATEGORIES)
                    
                    # [개선] 품목 코드 선택 시 자동 기입
                    code_select = st.selectbox("품목 코드", ["직접 입력"] + item_list)
                    
                    if code_select == "직접 입력":
                        code = st.text_input("품목 코드 직접 입력")
                        name = st.text_input("제품명 직접 입력")
                    else:
                        code = code_select
                        try:
                            name = item_df[item_df['품목코드'] == code]['제품명'].values[0]
                        except:
                            name = ""
                        st.text_input("제품명 (자동)", value=name, disabled=True)
                    
                    qty = st.number_input("생산 수량", min_value=1, value=100)
                    
                    if st.button("저장하기", type="primary", use_container_width=True):
                        if name:
                            # 1. 실적 저장
                            append_sheet_row([str(date), cat, code, name, qty, str(datetime.now()), CURRENT_USER['name']], "records")
                            
                            # 2. 재고 연동 (후공정, 외주공정 제외)
                            if cat not in ["후공정", "외주공정"]:
                                inv_df = load_sheet_data("inventory")
                                # 기존 재고 확인
                                if not inv_df.empty and '품목코드' in inv_df.columns and str(code) in inv_df['품목코드'].astype(str).values:
                                    idx = inv_df[inv_df['품목코드'].astype(str) == str(code)].index[0]
                                    try: cur_val = int(inv_df.at[idx, '현재고'])
                                    except: cur_val = 0
                                    inv_df.at[idx, '현재고'] = cur_val + qty
                                else:
                                    # 신규 추가
                                    new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": qty}])
                                    inv_df = pd.concat([inv_df, new_row], ignore_index=True)
                                save_sheet_data(inv_df, "inventory")
                                st.toast(f"저장 및 재고 업데이트 완료! ({name})", icon="✅")
                            else:
                                st.toast(f"실적 저장 완료! (재고 미반영 공정)", icon="✅")
                            
                            time.sleep(1); st.rerun()
                        else: st.error("제품명을 입력해주세요.")
                    st.markdown("</div>", unsafe_allow_html=True)
            else: st.warning("뷰어 모드입니다.")

        with c2:
            st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
            st.markdown("#### 📋 최근 등록 내역")
            df = load_sheet_data("records")
            if not df.empty and '입력시간' in df.columns:
                st.dataframe(df.sort_values("입력시간", ascending=False), use_container_width=True, height=500)
            else: st.info("데이터가 없습니다.")
            st.markdown("</div>", unsafe_allow_html=True)

    # 1-2. 재고 현황
    with tab_inv:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("#### 📦 실시간 재고 현황")
        df = load_sheet_data("inventory")
        if not df.empty:
            st.dataframe(df, use_container_width=True, height=600)
        else: st.info("재고 데이터가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    # 1-3. 대시보드 (오전 버전 복구)
    with tab_dash:
        df = load_sheet_data("records")
        if not df.empty and '수량' in df.columns:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            total_qty = df['수량'].sum()
            today_qty = df[pd.to_datetime(df['날짜']).dt.date == datetime.now().date()]['수량'].sum()
            
            k1, k2, k3 = st.columns(3)
            k1.markdown(f"""<div class="smart-card"><div class="kpi-title">Total Production</div><div class="kpi-value">{int(total_qty):,}</div><div class="kpi-trend trend-up">누적 생산량</div></div>""", unsafe_allow_html=True)
            k2.markdown(f"""<div class="smart-card"><div class="kpi-title">Today's Output</div><div class="kpi-value">{int(today_qty):,}</div><div class="kpi-trend trend-up">금일 생산량</div></div>""", unsafe_allow_html=True)
            k3.markdown(f"""<div class="smart-card"><div class="kpi-title">Status</div><div class="kpi-value" style="color:#10b981">Normal</div><div class="kpi-trend trend-neutral">가동 상태</div></div>""", unsafe_allow_html=True)
            
            st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)
            
            if HAS_ALTAIR:
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown("""<div class="smart-card"><h5>📈 일별 생산 추이</h5>""", unsafe_allow_html=True)
                    daily = df.groupby('날짜')['수량'].sum().reset_index()
                    chart = alt.Chart(daily).mark_line(point=True, color='#4f46e5').encode(x='날짜', y='수량').interactive()
                    st.altair_chart(chart, use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                with c2:
                    st.markdown("""<div class="smart-card"><h5>🍰 공정별 점유율</h5>""", unsafe_allow_html=True)
                    pie = df.groupby('구분')['수량'].sum().reset_index()
                    chart_pie = alt.Chart(pie).mark_arc(innerRadius=50).encode(theta='수량', color='구분')
                    st.altair_chart(chart_pie, use_container_width=True)
                    st.markdown("</div>", unsafe_allow_html=True)
        else: st.info("데이터가 없습니다.")

    # 1-4. 보고서 (PDF)
    with tab_rpt:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("#### 📑 일일 생산 리포트")
        if st.button("📄 PDF 다운로드 (금일 실적)", type="primary"):
            df = load_sheet_data("records")
            # PDF 생성 로직 (약식)
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=12)
            pdf.cell(200, 10, txt="SMT Daily Report", ln=True, align='C')
            pdf.cell(200, 10, txt=f"Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True, align='C')
            pdf.ln(10)
            
            if not df.empty:
                today_df = df[pd.to_datetime(df['날짜']).dt.date == datetime.now().date()]
                for _, row in today_df.iterrows():
                    pdf.cell(0, 10, txt=f"[{row['구분']}] {row['제품명']} : {row['수량']} EA", ln=True)
                
            pdf.output("report.pdf")
            with open("report.pdf", "rb") as f:
                st.download_button("⬇️ 파일 받기", f, f"Report_{datetime.now().strftime('%Y%m%d')}.pdf")
        st.markdown("</div>", unsafe_allow_html=True)

    # 1-5. 기준정보 (품목 관리)
    with tab_std:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        st.markdown("#### ⚙️ 품목 코드 관리")
        st.info("💡 이곳에서 품목을 등록해야 실적 등록 시 자동완성이 됩니다.")
        
        it_df = load_sheet_data("items")
        if IS_ADMIN:
            edited_it = st.data_editor(it_df, num_rows="dynamic", use_container_width=True, key="item_editor")
            if st.button("💾 구글 시트에 저장하기"):
                save_sheet_data(edited_it, "items")
                st.success("저장되었습니다!")
                time.sleep(1); st.rerun()
        else:
            st.dataframe(it_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# [2] 설비보전관리 메뉴
elif menu == "🛠️ 설비보전관리":
    tab_reg, tab_hist, tab_eq = st.tabs(["📝 이력 등록", "📋 이력 조회", "⚙️ 설비 목록"])
    
    with tab_reg:
        if IS_EDITOR:
            with st.container():
                st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
                st.markdown("#### 📝 설비 보전 이력 등록")
                
                eq_df = load_sheet_data("equipment")
                # [수정] 컬럼명 안전하게 가져오기 (에러 방지)
                if not eq_df.empty and '설비명' in eq_df.columns:
                    eq_list = eq_df['설비명'].tolist()
                else:
                    eq_list = ["직접 입력"]
                
                f_date = st.date_input("작업 일자", datetime.now(), key="m_date")
                f_eq = st.selectbox("대상 설비", eq_list)
                f_type = st.selectbox("작업 구분", ["BM(고장)", "PM(예방)", "CM(개조)"])
                f_desc = st.text_area("작업 내용")
                f_cost = st.number_input("비용 (원)", step=1000)
                f_time = st.number_input("비가동 시간 (분)", step=10)
                
                if st.button("이력 저장", type="primary", use_container_width=True):
                    append_sheet_row([str(f_date), f_eq, f_type, f_desc, f_cost, f_time, CURRENT_USER['name']], "maintenance")
                    st.success("저장 완료!")
                    time.sleep(1); st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)
        else: st.warning("권한이 없습니다.")

    with tab_hist:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        df = load_sheet_data("maintenance")
        if not df.empty:
            st.dataframe(df.sort_values("날짜", ascending=False), use_container_width=True)
        else: st.info("이력이 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)

    with tab_eq:
        st.markdown("""<div class="smart-card">""", unsafe_allow_html=True)
        eq_df = load_sheet_data("equipment")
        if IS_ADMIN:
            edited_eq = st.data_editor(eq_df, num_rows="dynamic", use_container_width=True)
            if st.button("설비 목록 업데이트"):
                save_sheet_data(edited_eq, "equipment")
                st.success("업데이트 완료")
                time.sleep(1); st.rerun()
        else:
            st.dataframe(eq_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)