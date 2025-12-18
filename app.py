import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import time
import os
import getpass
import json

# ------------------------------------------------------------------
# 1. 기본 설정 및 보안 (로그인 기능 복구)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT 생산/재고 통합 관리",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# [보안] 접속 비밀번호 설정 (원하는 비밀번호로 변경하세요)
ACCESS_PASSWORD = "smt1234" 

def check_password():
    """비밀번호 확인 함수"""
    if "password_correct" not in st.session_state:
        st.session_state.password_correct = False

    if st.session_state.password_correct:
        return True

    # 로그인 화면 디자인
    st.markdown(
        """
        <style>
        .stApp { background-color: #f3f4f6; }
        .login-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 2rem;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }
        </style>
        """, 
        unsafe_allow_html=True
    )
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br><h2 style='text-align: center; color: #4f46e5;'>🔒 시스템 접속</h2>", unsafe_allow_html=True)
        st.info("인가된 사용자만 접속할 수 있습니다.")
        pwd = st.text_input("비밀번호를 입력하세요", type="password", key="login_pw")
        
        if st.button("로그인 (Login)", use_container_width=True, type="primary"):
            if pwd == ACCESS_PASSWORD:
                st.session_state.password_correct = True
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")
    return False

# 비밀번호가 틀리면 여기서 코드 실행 중단 (로그인 창만 보임)
if not check_password():
    st.stop()

# ------------------------------------------------------------------
# 2. 데이터 저장소 연결 (구글 시트 필수)
# ------------------------------------------------------------------
try:
    import gspread
    from google.oauth2.service_account import Credentials
    HAS_GOOGLE_LIB = True
except ImportError:
    HAS_GOOGLE_LIB = False

# 클라우드 환경과 로컬 환경 모두 지원하는 인증 함수
def get_google_client():
    # 1. Streamlit Cloud (Secrets) 방식
    if hasattr(st, "secrets") and "gcp_service_account" in st.secrets:
        try:
            key_dict = dict(st.secrets["gcp_service_account"])
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(key_dict, scopes=SCOPES)
            return gspread.authorize(creds)
        except Exception as e:
            st.error(f"클라우드 인증 오류: {e}")
            return None

    # 2. 로컬 파일 (google_key.json) 방식
    elif os.path.exists("google_key.json"):
        try:
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_file("google_key.json", scopes=SCOPES)
            return gspread.authorize(creds)
        except: return None
        
    return None

# 저장소 상태 확인
client = get_google_client()
if client:
    STORAGE_TYPE = "GOOGLE"
    STORAGE_MSG = "구글 시트 연동됨 (클라우드)"
else:
    STORAGE_TYPE = "LOCAL"
    STORAGE_MSG = "로컬 모드 (데이터 공유 불가)"

# 시트/파일 이름 정의
FILE_RECORDS = "production_data.csv"
FILE_ITEMS = "item_codes.csv"
FILE_INVENTORY = "inventory_data.csv"
FILE_INV_HISTORY = "inventory_history.csv"

# --- 데이터 로드/저장 함수 (구글 시트 우선) ---
def load_data(data_type="records"):
    # 구글 시트 로드
    if STORAGE_TYPE == "GOOGLE":
        try:
            client = get_google_client()
            spreadsheet = client.open("production_data") # 시트 이름: production_data
            
            sheet_names = {
                "records": "Sheet1", 
                "items": "item_codes",
                "inventory": "inventory_data",
                "inv_history": "inventory_history"
            }
            target_sheet = sheet_names.get(data_type, "Sheet1")
            
            try:
                ws = spreadsheet.worksheet(target_sheet)
            except gspread.WorksheetNotFound:
                # 시트가 없으면 생성
                ws = spreadsheet.add_worksheet(title=target_sheet, rows=1000, cols=10)
                # 헤더 추가
                headers = {
                    "items": ["품목코드", "제품명"],
                    "inventory": ["품목코드", "제품명", "현재고"],
                    "inv_history": ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"],
                    "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"]
                }
                if data_type in headers:
                    ws.append_row(headers[data_type])

            data = ws.get_all_records()
            df = pd.DataFrame(data)
            
            # 숫자형 변환 (문자열로 들어온 경우)
            if data_type in ["records", "inventory", "inv_history"]:
                for col in ["수량", "현재고"]:
                    if col in df.columns:
                        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

            return df
        except Exception as e:
            # st.error(f"데이터 로드 실패: {e}")
            return pd.DataFrame()

    # 로컬 파일 로드 (Fallback)
    else:
        file_map = {"records": FILE_RECORDS, "items": FILE_ITEMS, "inventory": FILE_INVENTORY, "inv_history": FILE_INV_HISTORY}
        fname = file_map.get(data_type, FILE_RECORDS)
        if os.path.exists(fname):
            try: return pd.read_csv(fname)
            except: pass
        return pd.DataFrame()

def save_data(df_new, data_type="records"):
    if STORAGE_TYPE == "GOOGLE":
        try:
            client = get_google_client()
            sh = client.open("production_data")
            sheet_names = {"records": "Sheet1", "items": "item_codes", "inventory": "inventory_data", "inv_history": "inventory_history"}
            
            try: ws = sh.worksheet(sheet_names.get(data_type, "Sheet1"))
            except: ws = sh.add_worksheet(title=sheet_names.get(data_type, "Sheet1"), rows=1000, cols=10)
            
            ws.clear()
            # DataFrame을 리스트로 변환 (헤더 포함)
            val_list = [df_new.columns.values.tolist()] + df_new.values.tolist()
            ws.update(val_list)
            return True
        except: return False
    else:
        file_map = {"records": FILE_RECORDS, "items": FILE_ITEMS, "inventory": FILE_INVENTORY, "inv_history": FILE_INV_HISTORY}
        df_new.to_csv(file_map.get(data_type), index=False, encoding='utf-8-sig')
        return True

def append_data(data_dict, data_type="records"):
    if STORAGE_TYPE == "GOOGLE":
        try:
            client = get_google_client()
            sh = client.open("production_data")
            sheet_names = {"records": "Sheet1", "items": "item_codes", "inventory": "inventory_data", "inv_history": "inventory_history"}
            
            try: ws = sh.worksheet(sheet_names.get(data_type, "Sheet1"))
            except: ws = sh.add_worksheet(title=sheet_names.get(data_type, "Sheet1"), rows=1000, cols=10)
            
            # 컬럼 순서 보장
            cols_map = {
                "records": ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"],
                "inv_history": ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"],
                "inventory": ["품목코드", "제품명", "현재고"],
                "items": ["품목코드", "제품명"]
            }
            target_cols = cols_map.get(data_type, list(data_dict.keys()))
            row = [data_dict.get(c, "") for c in target_cols]
            
            ws.append_row(row)
            return True
        except: return False
    else:
        df = load_data(data_type)
        new_df = pd.DataFrame([data_dict])
        final = pd.concat([df, new_df], ignore_index=True) if not df.empty else new_df
        return save_data(final, data_type)

def update_inventory(code, name, change, reason, user):
    df = load_data("inventory")
    # 형변환 안전장치
    if not df.empty and '현재고' in df.columns:
        df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)

    if code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    save_data(df, "inventory")
    
    hist = {
        "날짜": datetime.now().strftime("%Y-%m-%d"),
        "품목코드": code, "구분": "입고" if change > 0 else "출고",
        "수량": change, "비고": reason, "작성자": user, "입력시간": str(datetime.now())
    }
    append_data(hist, "inv_history")

# 유틸리티 함수
def save_all_items(df): return save_data(df, "items")
def delete_all_items(): return save_data(pd.DataFrame(columns=["품목코드","제품명"]), "items")
def save_all_records(df): return save_data(df, "records")
def get_user_id():
    # Streamlit Cloud에서는 user 정보가 없을 수 있음
    return "Admin" 

def read_uploaded_file(upl):
    try: return pd.read_excel(upl)
    except: pass
    upl.seek(0)
    try: return pd.read_csv(upl)
    except: pass
    upl.seek(0)
    try: return pd.read_csv(upl, encoding='cp949')
    except: raise ValueError("파일 형식 오류")

# ------------------------------------------------------------------
# 3. UI 구성 (사이드바 및 메뉴)
# ------------------------------------------------------------------
# 스타일
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    html, body, [class*="css"] { font-family: 'Noto Sans KR', sans-serif; }
    .header-box { background-color: white; padding: 1.25rem; border-radius: 0.5rem; border-left: 5px solid #4f46e5; margin-bottom: 1.5rem; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
    .header-title { font-size: 1.4rem; font-weight: 700; color: #111827; margin-bottom: 0.25rem; }
    .header-sub { color: #6b7280; font-size: 0.85rem; }
    </style>
""", unsafe_allow_html=True)

CATEGORIES = ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"]

with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown("<h2 style='text-align: center; color: #4f46e5;'>SMT 시스템</h2>", unsafe_allow_html=True)
    
    status_color = "green" if STORAGE_TYPE == "GOOGLE" else "orange"
    st.caption(f":{status_color}[●] {STORAGE_MSG}")
    if STORAGE_TYPE == "LOCAL":
        st.warning("⚠️ 주의: 로컬 모드입니다. 클라우드 배포 시 데이터가 사라질 수 있습니다. 구글 시트를 연결하세요.")
    
    st.markdown("---")
    menu = st.radio("MENU", ["📝 생산등록", "📦 SMT 반제품 현황", "📊 통합대시보드", "📑 보고서출력", "⚙️ 기준정보관리"])
    st.markdown("---")
    if st.button("🔄 새로고침"): st.rerun()

# --- 메뉴별 화면 로직 ---

if menu == "📝 생산등록":
    st.markdown('<div class="header-box"><div class="header-title">생산 실적 등록</div><div class="header-sub">오늘의 생산 실적을 입력합니다.</div></div>', unsafe_allow_html=True)
    
    item_df = load_data("items")
    item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
    
    c_in, c_view = st.columns([1, 2])
    with c_in:
        with st.container(border=True):
            date = st.date_input("일자", datetime.now())
            cat = st.selectbox("구분", CATEGORIES)
            
            # 품목코드 입력 시 자동완성 로직
            def on_code_change():
                c = st.session_state.code_in.upper().strip()
                if c in item_map: st.session_state.name_in = item_map[c]
            
            code = st.text_input("코드", key="code_in", on_change=on_code_change)
            name = st.text_input("제품명", key="name_in")
            qty = st.number_input("수량", min_value=1, value=100)
            
            auto_deduct = False
            if cat in ["후공정", "후공정 외주"]:
                auto_deduct = st.checkbox("반제품 재고 차감", value=True)
            
            if st.button("저장", type="primary", use_container_width=True):
                if name:
                    new_rec = {"날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, "수량":qty, "입력시간":str(datetime.now()), "작성자":get_user_id()}
                    append_data(new_rec, "records")
                    if auto_deduct:
                        update_inventory(code, name, -qty, f"생산출고({cat})", get_user_id())
                    st.success("저장 완료")
                    time.sleep(0.5); st.rerun()
                else: st.error("제품명 필수")

    with c_view:
        df = load_data("records")
        if not df.empty:
            df = df.sort_values("입력시간", ascending=False)
            edited = st.data_editor(df, use_container_width=True, num_rows="dynamic", hide_index=True, key="edit_rec")
            if st.button("수정사항 저장"):
                save_all_records(edited)
                st.success("저장됨"); st.rerun()

elif menu == "📦 SMT 반제품 현황":
    st.markdown('<div class="header-box"><div class="header-title">📦 재고 현황</div><div class="header-sub">현재 재고를 조회합니다.</div></div>', unsafe_allow_html=True)
    df = load_data("inventory")
    search = st.text_input("검색", placeholder="품목명/코드")
    if not df.empty:
        if search:
            mask = df['품목코드'].astype(str).str.contains(search, case=False) | df['제품명'].astype(str).str.contains(search, case=False)
            df = df[mask]
        
        # 0보다 큰 재고만 표시
        if '현재고' in df.columns:
            df = df[df['현재고'] > 0]
            
        st.dataframe(df, use_container_width=True, hide_index=True)
    else: st.info("재고 없음")

elif menu == "📊 통합대시보드":
    st.markdown('<div class="header-box"><div class="header-title">📊 대시보드</div></div>', unsafe_allow_html=True)
    df = load_data("records")
    if not df.empty:
        c1, c2 = st.columns(2)
        with c1: 
            dr = st.date_input("기간", (datetime.now().replace(day=1), datetime.now()))
        with c2:
            cats = st.multiselect("구분", CATEGORIES, default=CATEGORIES)
        
        if len(dr)==2:
            mask = (pd.to_datetime(df['날짜']).dt.date >= dr[0]) & (pd.to_datetime(df['날짜']).dt.date <= dr[1]) & (df['구분'].isin(cats))
            df = df[mask]
            
            col_a, col_b = st.columns(2)
            with col_a:
                top = df.groupby('제품명')['수량'].sum().reset_index().sort_values('수량', ascending=False).head(5)
                c = alt.Chart(top).mark_bar().encode(x='수량', y=alt.Y('제품명', sort='-x'))
                st.altair_chart(c, use_container_width=True)
            with col_b:
                st.dataframe(df, use_container_width=True, hide_index=True)

elif menu == "📑 보고서출력":
    st.markdown('<div class="header-box"><div class="header-title">📑 보고서</div></div>', unsafe_allow_html=True)
    # (이전 코드의 보고서 로직과 동일 - 생략 없이 사용 가능하지만 지면 관계상 핵심만)
    st.info("기간을 선택하여 보고서를 생성하세요.")
    c1, c2 = st.columns(2)
    start = c1.date_input("시작일")
    end = c2.date_input("종료일")
    if st.button("조회"):
        df = load_data("records")
        if not df.empty:
            mask = (pd.to_datetime(df['날짜']).dt.date >= start) & (pd.to_datetime(df['날짜']).dt.date <= end)
            st.dataframe(df[mask], use_container_width=True)

elif menu == "⚙️ 기준정보관리":
    st.markdown('<div class="header-box"><div class="header-title">⚙️ 관리</div></div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs(["품목관리", "데이터백업"])
    with tab1:
        st.write("품목 일괄 업로드")
        f = st.file_uploader("엑셀/CSV")
        if f and st.button("업로드"):
            try:
                new_df = read_uploaded_file(f)
                new_df.columns = ["품목코드", "제품명"] + list(new_df.columns[2:]) # 컬럼 강제 매핑
                save_all_items(new_df)
                st.success("완료")
            except: st.error("파일 형식 확인 필요")
    with tab2:
        if STORAGE_TYPE == "GOOGLE":
            st.info("구글 시트에 자동 저장되고 있습니다.")
            st.link_button("구글 시트 바로가기", "https://docs.google.com/spreadsheets")