import streamlit as st
import pandas as pd
from datetime import datetime
import time
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# [시각화 라이브러리 설정]
try:
    import altair as alt
    HAS_ALTAIR = True
except:
    HAS_ALTAIR = False

# ------------------------------------------------------------------
# 1. 페이지 설정 및 디자인
# ------------------------------------------------------------------
st.set_page_config(page_title="SMT 통합 관리 시스템", page_icon="🏭", layout="wide")

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; }
    .stApp { background-color: #f8fafc; }
    .main-header {
        background: linear-gradient(135deg, #1e293b 0%, #334155 100%);
        padding: 2rem; border-radius: 1rem; color: white; margin-bottom: 2rem;
        box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1);
    }
    .card {
        background: white; padding: 1.5rem; border-radius: 0.75rem;
        border: 1px solid #e2e8f0; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .kpi-title { color: #64748b; font-size: 0.875rem; font-weight: 600; }
    .kpi-value { color: #1e293b; font-size: 1.75rem; font-weight: 800; }
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
        headers = {
            "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"],
            "items": ["품목코드", "제품명", "규격"],
            "inventory": ["품목코드", "제품명", "현재고"],
            "maintenance": ["날짜", "설비명", "작업구분", "내용", "비용", "비가동시간", "작업자"],
            "equipment": ["설비ID", "설비명", "공정", "상태"]
        }
        new_ws = sh.add_worksheet(title=name, rows="1000", cols="20")
        if name in headers:
            new_ws.append_row(headers[name])
        return new_ws

def load_sheet_data(name):
    try:
        ws = get_worksheet(name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame()

def save_sheet_data(df, name):
    ws = get_worksheet(name)
    ws.clear()
    df_clean = df.fillna("").astype(str)
    # 리스트의 리스트 형태로 변환하여 시트 업데이트
    data = [df_clean.columns.values.tolist()] + df_clean.values.tolist()
    ws.update(data)

def append_sheet_row(row_list, name):
    ws = get_worksheet(name)
    ws.append_row(row_list)

# ------------------------------------------------------------------
# 3. 사용자 인증 및 보안
# ------------------------------------------------------------------
def make_hash(p): return hashlib.sha256(str.encode(p)).hexdigest()

USERS = {
    "park": {"name": "Park", "pw": make_hash("1083"), "role": "admin"},
    "suk": {"name": "Suk", "pw": make_hash("1734"), "role": "editor"},
    "kim": {"name": "Kim", "pw": make_hash("8943"), "role": "editor"}
}

if "logged_in" not in st.session_state: st.session_state.logged_in = False

if not st.session_state.logged_in:
    cols = st.columns([1, 2, 1])
    with cols[1]:
        st.markdown("<br><br><h2 style='text-align:center;'>🔐 SMT 통합 관리 로그인</h2>", unsafe_allow_html=True)
        with st.form("login"):
            u = st.text_input("아이디")
            p = st.text_input("비밀번호", type="password")
            if st.form_submit_button("로그인", use_container_width=True):
                if u in USERS and make_hash(p) == USERS[u]["pw"]:
                    st.session_state.logged_in = True
                    st.session_state.user = USERS[u]
                    st.rerun()
                else: st.error("정보가 일치하지 않습니다.")
    st.stop()

USER = st.session_state.user
IS_ADMIN = (USER['role'] == 'admin')

# ------------------------------------------------------------------
# 4. 메인 대시보드 구조
# ------------------------------------------------------------------
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/8066/8066532.png", width=80)
    st.title("SMT Dashboard")
    st.info(f"👤 접속자: **{USER['name']}** ({USER['role']})")
    menu = st.radio("메뉴 선택", ["📊 대시보드", "🏭 생산 관리", "🛠️ 설비 보전", "⚙️ 기준 정보"])
    st.markdown("---")
    if st.button("로그아웃"):
        st.session_state.logged_in = False
        st.rerun()

# ------------------------------------------------------------------
# [메뉴 1: 대시보드]
# ------------------------------------------------------------------
if menu == "📊 대시보드":
    st.markdown('<div class="main-header"><h1>📊 생산 현황 대시보드</h1></div>', unsafe_allow_html=True)
    df = load_sheet_data("records")
    if not df.empty:
        df['날짜'] = pd.to_datetime(df['날짜']).dt.date
        df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f'<div class="card"><div class="kpi-title">누적 생산량</div><div class="kpi-value">{int(df["수량"].sum()):,}</div></div>', unsafe_allow_html=True)
        with c2:
            today = datetime.now().date()
            t_qty = df[df['날짜'] == today]['수량'].sum()
            st.markdown(f'<div class="card"><div class="kpi-title">금일 생산량</div><div class="kpi-value">{int(t_qty):,}</div></div>', unsafe_allow_html=True)
            
        if HAS_ALTAIR:
            st.markdown("### 📈 생산 추이")
            chart_df = df.groupby('날짜')['수량'].sum().reset_index()
            chart = alt.Chart(chart_df).mark_line(point=True, color='#4f46e5').encode(x='날짜:T', y='수량:Q').interactive()
            st.altair_chart(chart, use_container_width=True)
    else:
        st.info("실적 데이터가 없습니다.")

# ------------------------------------------------------------------
# [메뉴 2: 생산 관리]
# ------------------------------------------------------------------
elif menu == "🏭 생산 관리":
    st.markdown('<div class="main-header"><h1>🏭 생산 실적 및 재고 관리</h1></div>', unsafe_allow_html=True)
    t1, t2, t3 = st.tabs(["📝 실적 등록", "🔍 현황 조회", "📦 재고 현황"])
    
    with t1:
        # 품목 정보 미리 로드
        items_df = load_sheet_data("items")
        item_list = items_df['품목코드'].tolist() if not items_df.empty else []
        
        with st.form("reg_form"):
            c1, c2 = st.columns(2)
            date = c1.date_input("작업일자", datetime.now())
            cat = c2.selectbox("공정 구분", ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "외주공정"])
            
            # 품목코드 선택
            code_select = st.selectbox("품목 코드", ["직접 입력"] + item_list)
            
            c3, c4 = st.columns(2)
            if code_select == "직접 입력":
                final_code = c3.text_input("신규 품목코드")
                final_name = c4.text_input("제품명")
            else:
                final_code = code_select
                # 제품명 자동 추출
                final_name = items_df[items_df['품목코드'] == code_select]['제품명'].values[0]
                c3.text_input("선택된 코드", value=final_code, disabled=True)
                c4.text_input("제품명(자동)", value=final_name, disabled=True)
                
            qty = st.number_input("생산 수량", min_value=1, value=1)
            
            if st.form_submit_button("🚀 실적 저장"):
                if not final_code or not final_name:
                    st.error("품목 정보를 정확히 입력해 주세요.")
                else:
                    # 1. 생산 실적 기록
                    append_sheet_row([str(date), cat, final_code, final_name, qty, str(datetime.now()), USER['name']], "records")
                    
                    # 2. 재고 자동 연동 (후공정, 외주공정 제외)
                    if cat not in ["후공정", "외주공정"]:
                        inv_df = load_sheet_data("inventory")
                        if not inv_df.empty and str(final_code) in inv_df['품목코드'].astype(str).values:
                            # 기존 품목이 있으면 합산
                            idx = inv_df[inv_df['품목코드'].astype(str) == str(final_code)].index[0]
                            try:
                                current_inv = int(inv_df.at[idx, '현재고'])
                            except:
                                current_inv = 0
                            inv_df.at[idx, '현재고'] = current_inv + qty
                        else:
                            # 신규 품목이면 추가
                            new_row = pd.DataFrame([{"품목코드": final_code, "제품명": final_name, "현재고": qty}])
                            inv_df = pd.concat([inv_df, new_row], ignore_index=True)
                        
                        save_sheet_data(inv_df, "inventory")
                        st.success(f"실적 및 재고 반영 완료! (재고 업데이트: {final_name})")
                    else:
                        st.success(f"실적 저장 완료! (공정: {cat}, 재고 제외 대상)")
                    
                    time.sleep(1); st.rerun()

    with t2:
        df = load_sheet_data("records")
        st.dataframe(df.sort_values("입력시간", ascending=False), use_container_width=True)

    with t3:
        st.subheader("📦 실시간 재고 (구글 시트 연동)")
        inv = load_sheet_data("inventory")
        st.dataframe(inv, use_container_width=True)

# ------------------------------------------------------------------
# [메뉴 3: 설비 보전]
# ------------------------------------------------------------------
elif menu == "🛠️ 설비 보전":
    st.markdown('<div class="main-header"><h1>🛠️ 설비 보전 관리</h1></div>', unsafe_allow_html=True)
    m_df = load_sheet_data("maintenance")
    st.dataframe(m_df, use_container_width=True)

# ------------------------------------------------------------------
# [메뉴 4: 기준 정보]
# ------------------------------------------------------------------
elif menu == "⚙️ 기준 정보":
    st.markdown('<div class="main-header"><h1>⚙️ 시스템 기준 정보</h1></div>', unsafe_allow_html=True)
    st.subheader("🍎 품목 마스터 정보 관리")
    it_df = load_sheet_data("items")
    
    if IS_ADMIN:
        # 데이터 에디터를 통해 직접 수정
        edited_it = st.data_editor(it_df, num_rows="dynamic", use_container_width=True, key="item_editor")
        if st.button("💾 품목 정보를 구글 시트에 업데이트"):
            save_sheet_data(edited_it, "items")
            st.success("구글 시트에 성공적으로 업데이트되었습니다!")
            time.sleep(1); st.rerun()
    else:
        st.dataframe(it_df, use_container_width=True)