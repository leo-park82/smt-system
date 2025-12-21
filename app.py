import streamlit as st
import pandas as pd
from datetime import datetime
import time
import hashlib
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fpdf import FPDF

# [시각화 라이브러리 설정]
try:
    import altair as alt
    HAS_ALTAIR = True
except:
    HAS_ALTAIR = False

# ------------------------------------------------------------------
# 1. 페이지 설정 및 프리미엄 디자인 (초기 버전 디자인 복구)
# ------------------------------------------------------------------
st.set_page_config(page_title="SMT 통합 관리 시스템", page_icon="🏭", layout="wide")

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; }
    .stApp { background-color: #f8fafc; }
    
    /* 초기 버전의 그라데이션 헤더 */
    .main-header {
        background: linear-gradient(135deg, #1e293b 0%, #3b82f6 100%);
        padding: 2.5rem; border-radius: 1.25rem; color: white; margin-bottom: 2rem;
        box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.2);
    }
    
    /* 카드 스타일 복구 */
    .card {
        background: white; padding: 1.5rem; border-radius: 1rem;
        border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05);
        transition: transform 0.2s ease;
    }
    .card:hover { transform: translateY(-2px); }
    .kpi-title { color: #64748b; font-size: 0.9rem; font-weight: 600; margin-bottom: 0.5rem; }
    .kpi-value { color: #1e293b; font-size: 2rem; font-weight: 800; }
    
    /* 탭 디자인 강조 */
    .stTabs [data-baseweb="tab-list"] { gap: 12px; }
    .stTabs [data-baseweb="tab"] {
        height: 50px; border-radius: 10px; background-color: white;
        border: 1px solid #e2e8f0; font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #3b82f6 !important; color: white !important;
        border-color: #3b82f6 !important;
    }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. 구글 시트 연결 핵심 로직
# ------------------------------------------------------------------
try:
    if "sheet_url" in st.secrets:
        SHEET_URL = st.secrets["sheet_url"]
    elif "gcp_service_account" in st.secrets and "sheet_url" in st.secrets["gcp_service_account"]:
        SHEET_URL = st.secrets["gcp_service_account"]["sheet_url"]
    else:
        st.error("🚨 Secrets에 'sheet_url'이 설정되지 않았습니다.")
        st.stop()

    if "gcp_service_account" in st.secrets:
        creds_dict = dict(st.secrets["gcp_service_account"])
        if "sheet_url" in creds_dict: del creds_dict["sheet_url"]
    else:
        st.error("🚨 구글 서비스 계정 인증 정보가 없습니다.")
        st.stop()
except Exception as e:
    st.error(f"🚨 설정 로드 중 오류: {e}")
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
        # 시트가 없으면 기본 헤더와 함께 생성
        headers = {
            "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"],
            "items": ["품목코드", "제품명", "규격"],
            "inventory": ["품목코드", "제품명", "현재고"],
            "maintenance": ["날짜", "설비명", "작업구분", "내용", "비용", "작업자"],
            "equipment": ["설비ID", "설비명", "공정", "상태"]
        }
        new_ws = sh.add_worksheet(title=name, rows="1000", cols="20")
        if name in headers: new_ws.append_row(headers[name])
        return new_ws

def load_sheet_data(name):
    try:
        ws = get_worksheet(name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except: return pd.DataFrame()

def save_sheet_data(df, name):
    ws = get_worksheet(name)
    ws.clear()
    df_clean = df.fillna("").astype(str)
    data = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
    ws.update(data)

def append_sheet_row(row_list, name):
    ws = get_worksheet(name)
    ws.append_row(row_list)

# ------------------------------------------------------------------
# 3. 보안 및 사용자 인증
# ------------------------------------------------------------------
def make_hash(p): return hashlib.sha256(str.encode(p)).hexdigest()

USERS = {
    "park": {"name": "Park", "pw": make_hash("1083"), "role": "admin"},
    "suk": {"name": "Suk", "pw": make_hash("1734"), "role": "editor"},
    "kim": {"name": "Kim", "pw": make_hash("8943"), "role": "editor"}
}

if "logged_in" not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    c1, c2, c3 = st.columns([1, 1.5, 1])
    with c2:
        st.markdown("<br><br><h2 style='text-align:center;'>🔐 SMT 통합 관리 로그인</h2>", unsafe_allow_html=True)
        with st.form("login_form"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.form_submit_button("Sign In", use_container_width=True):
                if u in USERS and make_hash(p) == USERS[u]["pw"]:
                    st.session_state.logged_in = True
                    st.session_state.user = USERS[u]
                    st.rerun()
                else: st.error("로그인 정보가 올바르지 않습니다.")
    st.stop()

USER = st.session_state.user
IS_ADMIN = (USER['role'] == 'admin')

# ------------------------------------------------------------------
# 4. 사이드바 구성
# ------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/8066/8066532.png", width=100)
    st.title("SMT OS 1.0")
    st.markdown(f"**Welcome, {USER['name']}!**")
    st.info(f"Role: {USER['role'].upper()}")
    
    menu = st.radio("MAIN MENU", ["📊 대시보드", "🏭 생산 관리", "🛠️ 설비 보전", "⚙️ 기준 정보"])
    st.markdown("---")
    if st.button("Logout", type="secondary"):
        st.session_state.logged_in = False
        st.rerun()

# ------------------------------------------------------------------
# [메뉴 1: 대시보드] - 초기 디자인 복구
# ------------------------------------------------------------------
if menu == "📊 대시보드":
    st.markdown('<div class="main-header"><h1>📊 생산 현황 대시보드</h1><p>Real-time Production Analytics & KPI</p></div>', unsafe_allow_html=True)
    
    df = load_sheet_data("records")
    if not df.empty:
        df['날짜'] = pd.to_datetime(df['날짜']).dt.date
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(f'<div class="card"><div class="kpi-title">누적 생산량</div><div class="kpi-value">{int(df["수량"].sum()):,}</div></div>', unsafe_allow_html=True)
        with c2:
            today_qty = df[df['날짜'] == datetime.now().date()]['수량'].sum()
            st.markdown(f'<div class="card"><div class="kpi-title">금일 생산량</div><div class="kpi-value">{int(today_qty):,}</div></div>', unsafe_allow_html=True)
        with c3:
            st.markdown(f'<div class="card"><div class="kpi-title">가동 효율</div><div class="kpi-value" style="color:#10b981;">98.2%</div></div>', unsafe_allow_html=True)
        with c4:
            st.markdown(f'<div class="card"><div class="kpi-title">품질 지수</div><div class="kpi-value" style="color:#3b82f6;">99.5%</div></div>', unsafe_allow_html=True)

        if HAS_ALTAIR:
            st.markdown("<br>### 📈 생산 추이 분석", unsafe_allow_html=True)
            chart_df = df.groupby('날짜')['수량'].sum().reset_index()
            chart = alt.Chart(chart_df).mark_area(
                line={'color':'#3b82f6'},
                color=alt.Gradient(
                    gradient='linear',
                    stops=[alt.GradientStop(color='white', offset=0), alt.GradientStop(color='#3b82f6', offset=1)],
                    x1=1, x2=1, y1=1, y2=0
                )
            ).encode(x='날짜:T', y='수량:Q', tooltip=['날짜', '수량']).interactive()
            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("실적 데이터를 등록하면 대시보드가 활성화됩니다.")

# ------------------------------------------------------------------
# [메뉴 2: 생산 관리] - 기능 버그 수정 완료
# ------------------------------------------------------------------
elif menu == "🏭 생산 관리":
    st.markdown('<div class="main-header"><h1>🏭 생산 실적 및 재고 관리</h1></div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["📝 실적 등록", "🔍 현황 조회", "📦 재고 관리"])
    
    # 1. 품목 정보 로드 (자동기입용)
    items_df = load_sheet_data("items")
    item_list = items_df['품목코드'].tolist() if not items_df.empty else []
    
    with t1:
        with st.form("reg_form", clear_on_submit=True):
            st.markdown("### ✏️ 실적 입력")
            c1, c2 = st.columns(2)
            date = c1.date_input("작업일자", datetime.now())
            cat = c2.selectbox("공정 구분", ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "외주공정"])
            
            # [수정] 품목코드 선택박스
            selected_code = st.selectbox("품목 코드", ["직접 입력"] + item_list)
            
            c3, c4 = st.columns(2)
            if selected_code == "직접 입력":
                final_code = c3.text_input("신규 품목코드")
                final_name = c4.text_input("제품명 입력")
            else:
                final_code = selected_code
                # [수정] 제품명 자동 기입 (구글 시트 연동)
                final_name = items_df[items_df['품목코드'] == selected_code]['제품명'].values[0]
                c3.text_input("코드(확인)", value=final_code, disabled=True)
                c4.text_input("제품명(자동)", value=final_name, disabled=True)
                
            qty = st.number_input("생산 수량", min_value=1, value=1)
            
            if st.form_submit_button("🚀 데이터 저장 및 시트 전송", use_container_width=True):
                if not final_code or not final_name:
                    st.error("품목 정보가 누락되었습니다.")
                else:
                    # 1. 실적 시트 기록
                    append_sheet_row([str(date), cat, final_code, final_name, qty, str(datetime.now()), USER['name']], "records")
                    
                    # 2. [수정] 재고 관리 로직 (후공정, 외주공정 제외)
                    if cat not in ["후공정", "외주공정"]:
                        inv_df = load_sheet_data("inventory")
                        if not inv_df.empty and str(final_code) in inv_df['품목코드'].astype(str).values:
                            idx = inv_df[inv_df['품목코드'].astype(str) == str(final_code)].index[0]
                            try:
                                inv_df.at[idx, '현재고'] = int(inv_df.at[idx, '현재고']) + qty
                            except: inv_df.at[idx, '현재고'] = qty
                        else:
                            new_inv = pd.DataFrame([{"품목코드": final_code, "제품명": final_name, "현재고": qty}])
                            inv_df = pd.concat([inv_df, new_inv], ignore_index=True)
                        save_sheet_data(inv_df, "inventory")
                        st.success(f"{final_name} 실적 및 재고 반영 완료!")
                    else:
                        st.success(f"{final_name} 실적 저장 완료! (재고 제외 공정)")
                    time.sleep(1); st.rerun()

    with t2:
        df = load_sheet_data("records")
        st.markdown("### 📋 전체 생산 이력")
        st.dataframe(df.sort_values("입력시간", ascending=False), use_container_width=True)

    with t3:
        st.markdown("### 📦 현재고 현황 (구글 시트 연동)")
        inv = load_sheet_data("inventory")
        st.dataframe(inv, use_container_width=True)

# ------------------------------------------------------------------
# [메뉴 3: 설비 보전]
# ------------------------------------------------------------------
elif menu == "🛠️ 설비 보전":
    st.markdown('<div class="main-header"><h1>🛠️ 설비 보전 및 관리</h1></div>', unsafe_allow_html=True)
    m_df = load_sheet_data("maintenance")
    st.dataframe(m_df.sort_values("날짜", ascending=False), use_container_width=True)

# ------------------------------------------------------------------
# [메뉴 4: 기준 정보] - 품목 업로드 버그 수정
# ------------------------------------------------------------------
elif menu == "⚙️ 기준 정보":
    st.markdown('<div class="main-header"><h1>⚙️ 시스템 기준 정보</h1></div>', unsafe_allow_html=True)
    st.subheader("🍎 품목 마스터 관리 (Master Data)")
    
    it_df = load_sheet_data("items")
    
    if IS_ADMIN:
        # [수정] 에디터에서 수정 후 시트에 즉시 반영하는 로직
        st.info("💡 표에서 내용을 수정한 후 하단의 [업데이트] 버튼을 누르면 구글 시트에 저장됩니다.")
        edited_it = st.data_editor(it_df, num_rows="dynamic", use_container_width=True, key="item_master")
        if st.button("💾 품목 정보를 구글 시트에 즉시 업데이트"):
            save_sheet_data(edited_it, "items")
            st.success("구글 시트에 품목 정보가 저장되었습니다!")
            time.sleep(1); st.rerun()
    else:
        st.dataframe(it_df, use_container_width=True)