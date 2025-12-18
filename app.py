import streamlit as st
import pandas as pd
import altair as alt
from datetime import datetime, timedelta
import time
import os
import getpass

# ------------------------------------------------------------------
# 1. 기본 설정 및 스타일링
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT 생산/재고 통합 관리",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Tailwind 스타일의 커스텀 CSS 적용
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Noto Sans KR', sans-serif;
    }
    
    .stApp {
        background-color: #f3f4f6;
    }
    
    /* 헤더 스타일 */
    .header-box {
        background-color: white;
        padding: 1.25rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        border-left: 5px solid #4f46e5;
        margin-bottom: 1.5rem;
    }
    .header-title {
        color: #111827;
        font-size: 1.4rem;
        font-weight: 700;
        margin-bottom: 0.25rem;
    }
    .header-sub {
        color: #6b7280;
        font-size: 0.85rem;
    }

    /* 카드 스타일 */
    div[data-testid="metric-container"] {
        background-color: white;
        padding: 0.8rem;
        border-radius: 0.5rem;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
        border: 1px solid #e5e7eb;
    }
    
    /* 버튼 스타일 */
    .stButton > button {
        background-color: #4f46e5 !important;
        color: white !important;
        border-radius: 0.375rem !important;
        font-weight: 600 !important;
    }
    button[kind="secondary"] {
        background-color: white !important;
        color: #374151 !important;
        border: 1px solid #d1d5db !important;
    }
    
    /* 알림 메시지 */
    .success-msg { color: #059669; font-weight: bold; }
    .error-msg { color: #dc2626; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. 데이터 저장소 연결
# ------------------------------------------------------------------
try:
    import gspread
    from google.oauth2.service_account import Credentials
    HAS_GOOGLE_LIB = True
except ImportError:
    HAS_GOOGLE_LIB = False

if HAS_GOOGLE_LIB and os.path.exists("google_key.json"):
    STORAGE_TYPE = "GOOGLE"
    STORAGE_MSG = "구글 시트 연동됨"
else:
    STORAGE_TYPE = "LOCAL"
    STORAGE_MSG = "로컬 파일 모드"
    
FILE_RECORDS = "production_data.csv"
FILE_ITEMS = "item_codes.csv"
FILE_INVENTORY = "inventory_data.csv"      # 재고 데이터 (품목별 현재고)
FILE_INV_HISTORY = "inventory_history.csv" # 재고 변동 이력

# 작성자 식별 함수
def get_user_id():
    try:
        if hasattr(st, "user") and st.user.email: return st.user.email.split('@')[0]
    except: pass
    try: return getpass.getuser()
    except: return "guest"

def get_google_client():
    if STORAGE_TYPE != "GOOGLE": return None
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_file("google_key.json", scopes=SCOPES)
        return gspread.authorize(creds)
    except: return None

# --- 데이터 로드 함수 (통합) ---
def load_data(data_type="records"):
    """ data_type: 'records', 'items', 'inventory', 'inv_history' """
    if STORAGE_TYPE == "GOOGLE":
        client = get_google_client()
        if client:
            try:
                spreadsheet = client.open("production_data")
                sheet_map = {
                    "records": "Sheet1", # 기본 시트
                    "items": "item_codes",
                    "inventory": "inventory_data",
                    "inv_history": "inventory_history"
                }
                
                try:
                    ws = spreadsheet.worksheet(sheet_map.get(data_type, "Sheet1"))
                except gspread.WorksheetNotFound:
                    # 시트 없으면 생성
                    ws = spreadsheet.add_worksheet(title=sheet_map.get(data_type, "Sheet1"), rows=1000, cols=10)
                    # 헤더 추가
                    if data_type == "items": ws.append_row(["품목코드", "제품명"])
                    elif data_type == "inventory": ws.append_row(["품목코드", "제품명", "현재고"])
                    elif data_type == "inv_history": ws.append_row(["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"])
                
                data = ws.get_all_records()
                df = pd.DataFrame(data)
                
                # 데이터 전처리
                if data_type == "items" and not df.empty:
                    df.columns = [str(c).replace(" ", "") for c in df.columns]
                    if "품목코드" in df.columns: df['품목코드'] = df['품목코드'].astype(str).str.strip().str.upper()
                    if "제품명" in df.columns: df['제품명'] = df['제품명'].astype(str).str.strip()
                elif data_type == "records" and not df.empty:
                    if '날짜' in df.columns:
                        df = df[df['날짜'].astype(str).str.strip() != '']
                        df['날짜'] = pd.to_datetime(df['날짜']).dt.strftime('%Y-%m-%d')
                elif data_type == "inv_history" and not df.empty:
                     if '날짜' in df.columns:
                        df = df[df['날짜'].astype(str).str.strip() != '']
                        df['날짜'] = pd.to_datetime(df['날짜']).dt.strftime('%Y-%m-%d')
                
                return df
            except: return pd.DataFrame()
    else:
        # 로컬 파일 매핑
        file_map = {
            "records": FILE_RECORDS,
            "items": FILE_ITEMS,
            "inventory": FILE_INVENTORY,
            "inv_history": FILE_INV_HISTORY
        }
        filename = file_map.get(data_type, FILE_RECORDS)
        
        if os.path.exists(filename):
            try:
                df = pd.read_csv(filename, encoding='utf-8-sig')
                if data_type == "items" and not df.empty:
                    df['품목코드'] = df['품목코드'].astype(str).str.strip().str.upper()
                    df['제품명'] = df['제품명'].astype(str).str.strip()
                elif data_type == "records" and not df.empty:
                     if '날짜' in df.columns: 
                        df = df[df['날짜'].notna()]
                        df['날짜'] = pd.to_datetime(df['날짜']).dt.strftime('%Y-%m-%d')
                elif data_type == "inv_history" and not df.empty:
                     if '날짜' in df.columns: 
                        df = df[df['날짜'].notna()]
                        df['날짜'] = pd.to_datetime(df['날짜']).dt.strftime('%Y-%m-%d')
                return df
            except: pass
            
    # 기본 컬럼 정의
    if data_type == "records": cols = ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"]
    elif data_type == "items": cols = ["품목코드", "제품명"]
    elif data_type == "inventory": cols = ["품목코드", "제품명", "현재고"]
    elif data_type == "inv_history": cols = ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"]
    else: cols = []
    
    return pd.DataFrame(columns=cols)

# --- 데이터 저장 함수 (통합) ---
def save_data(df_new, data_type="records"):
    """ 전체 데이터 덮어쓰기 (수정/삭제용) """
    if STORAGE_TYPE == "GOOGLE":
        client = get_google_client()
        if client:
            spreadsheet = client.open("production_data")
            sheet_map = {
                "records": "Sheet1", "items": "item_codes",
                "inventory": "inventory_data", "inv_history": "inventory_history"
            }
            try: ws = spreadsheet.worksheet(sheet_map.get(data_type, "Sheet1"))
            except: ws = spreadsheet.add_worksheet(title=sheet_map.get(data_type, "Sheet1"), rows=1000, cols=10)
            
            ws.clear()
            # 데이터프레임을 리스트로 변환하여 업데이트 (헤더 포함)
            data_list = [df_new.columns.tolist()] + df_new.values.tolist()
            ws.update(data_list)
            return True
    else:
        file_map = {
            "records": FILE_RECORDS, "items": FILE_ITEMS,
            "inventory": FILE_INVENTORY, "inv_history": FILE_INV_HISTORY
        }
        filename = file_map.get(data_type, FILE_RECORDS)
        df_new.to_csv(filename, index=False, encoding='utf-8-sig')
        return True
    return False

def append_data(data_dict, data_type="records"):
    """ 데이터 한 줄 추가 (입력용) """
    if STORAGE_TYPE == "GOOGLE":
        client = get_google_client()
        if client:
            spreadsheet = client.open("production_data")
            sheet_map = {
                "records": "Sheet1", "items": "item_codes",
                "inventory": "inventory_data", "inv_history": "inventory_history"
            }
            try: ws = spreadsheet.worksheet(sheet_map.get(data_type, "Sheet1"))
            except: ws = spreadsheet.add_worksheet(title=sheet_map.get(data_type, "Sheet1"), rows=1000, cols=10)
            
            # 딕셔너리 값 순서 보장 (컬럼 정의 순서대로)
            if data_type == "records":
                row = [data_dict.get(c, "") for c in ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자"]]
            elif data_type == "inv_history":
                row = [data_dict.get(c, "") for c in ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"]]
            else:
                row = list(data_dict.values())
                
            ws.append_row(row)
            return True
    else:
        df = load_data(data_type)
        new_df = pd.DataFrame([data_dict])
        final_df = pd.concat([df, new_df], ignore_index=True) if not df.empty else new_df
        file_map = {
            "records": FILE_RECORDS, "items": FILE_ITEMS,
            "inventory": FILE_INVENTORY, "inv_history": FILE_INV_HISTORY
        }
        filename = file_map.get(data_type, FILE_RECORDS)
        final_df.to_csv(filename, index=False, encoding='utf-8-sig')
        return True
    return False

# --- 재고 업데이트 함수 (핵심 로직) ---
def update_inventory(item_code, item_name, change_qty, reason, user_id):
    """
    재고 수량을 변경하고 이력을 남깁니다.
    change_qty: 양수(입고) 또는 음수(출고)
    """
    # 1. 현재 재고 로드
    df_inv = load_data("inventory")
    
    # 2. 재고 수량 변경
    if item_code in df_inv['품목코드'].values:
        # 기존 품목 업데이트
        idx = df_inv[df_inv['품목코드'] == item_code].index[0]
        current_qty = int(df_inv.at[idx, '현재고'])
        df_inv.at[idx, '현재고'] = current_qty + change_qty
    else:
        # 신규 품목 추가
        new_row = pd.DataFrame([{"품목코드": item_code, "제품명": item_name, "현재고": change_qty}])
        df_inv = pd.concat([df_inv, new_row], ignore_index=True)
    
    # 3. 재고 데이터 저장
    save_data(df_inv, "inventory")
    
    # 4. 이력 남기기
    history_data = {
        "날짜": datetime.now().strftime("%Y-%m-%d"),
        "품목코드": item_code,
        "구분": "입고" if change_qty > 0 else "출고",
        "수량": change_qty,
        "비고": reason,
        "작성자": user_id,
        "입력시간": str(datetime.now())
    }
    append_data(history_data, "inv_history")
    return True

# --- [복구됨] 품목 코드 전체 저장 함수 ---
def save_all_items(df_items):
    # 중복 제거 (품목코드 기준)
    df_items = df_items.drop_duplicates(subset=['품목코드'], keep='last')
    return save_data(df_items, "items")

# --- [복구됨] 품목 코드 전체 삭제 함수 ---
def delete_all_items():
    empty_df = pd.DataFrame(columns=["품목코드", "제품명"])
    return save_data(empty_df, "items")

# --- [복구됨] 생산 기록 전체 저장 함수 ---
def save_all_records(df_new):
    return save_data(df_new, "records")

# --- [복구됨] 파일 읽기 함수 (엑셀/CSV) ---
def read_uploaded_file(uploaded_file):
    try:
        return pd.read_excel(uploaded_file)
    except: pass
    
    uploaded_file.seek(0)
    try: return pd.read_csv(uploaded_file)
    except: pass
        
    uploaded_file.seek(0)
    try: return pd.read_csv(uploaded_file, encoding='cp949')
    except: pass
        
    raise ValueError("파일 형식을 인식할 수 없습니다.")

CATEGORIES = ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"]

# ------------------------------------------------------------------
# 3. 사이드바
# ------------------------------------------------------------------
with st.sidebar:
    # [수정] 회사 로고 이미지 적용 (logo.png가 있으면 사용)
    if os.path.exists("logo.png"):
        st.image("logo.png", use_container_width=True)
    
    st.markdown(f"""
    <div style="text-align: center; padding: 10px;">
        <h2 style="color: #4f46e5; margin:0; font-size: 1.8rem; font-weight: 800; line-height: 1.4;">
            SMT 생산 현황
        </h2>
    </div>
    """, unsafe_allow_html=True)
    
    status_color = "green" if STORAGE_TYPE == "GOOGLE" else "orange"
    st.caption(f":{status_color}[●] {STORAGE_MSG}")
    
    st.markdown("---")
    menu = st.radio("MENU", [
        "📝 생산등록", 
        "📦 SMT 반제품 현황", 
        "📊 통합대시보드", 
        "📑 보고서출력", 
        "⚙️ 기준정보관리"
    ])
    
    st.markdown("---")
    st.caption(f"User: {get_user_id()}")
    if st.button("🔄 시스템 새로고침", use_container_width=True):
        st.rerun()

# ------------------------------------------------------------------
# 4. [메뉴 1] 생산등록
# ------------------------------------------------------------------
if menu == "📝 생산등록":
    
    st.markdown(f"""
    <div class="header-box">
        <div class="header-title">생산 실적 등록</div>
        <div class="header-sub">오늘의 생산 실적을 입력하고 관리하세요. ({datetime.now().strftime('%Y-%m-%d')})</div>
    </div>
    """, unsafe_allow_html=True)
    
    item_df = load_data("items")
    item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
    df_records = load_data("records")

    # 상단 요약
    today_str = datetime.now().strftime("%Y-%m-%d")
    today_qty = df_records[df_records['날짜'] == today_str]['수량'].sum() if not df_records.empty else 0
    c1, c2 = st.columns(2)
    c1.metric("오늘 생산량", f"{today_qty:,} EA")
    c2.metric("등록된 품목", f"{len(item_map):,} 개")
    st.markdown("<br>", unsafe_allow_html=True)

    col_input, col_view = st.columns([1, 2.5], gap="medium")

    # 입력 폼
    with col_input:
        with st.container(border=True):
            st.markdown('<div class="section-header">📝 실적 입력</div>', unsafe_allow_html=True)
            def update_product_name():
                code = st.session_state.code_key.upper().strip()
                found = item_map.get(code, "")
                if found: st.session_state.name_key = found

            input_date = st.date_input("작업 일자", datetime.now())
            category = st.selectbox("생산 구분", CATEGORIES)
            st.markdown("---")
            st.text_input("품목 코드", placeholder="코드 입력 (Enter)", key="code_key", on_change=update_product_name)
            product_name = st.text_input("제품명", placeholder="제품명", key="name_key")
            qty = st.number_input("생산 수량", min_value=1, step=1, value=100)
            
            # [수정] 반제품 차감 대상 설정 (후공정, 후공정 외주만)
            DEDUCT_TARGETS = ["후공정", "후공정 외주"]
            is_deduct_target = category in DEDUCT_TARGETS

            if is_deduct_target:
                auto_deduct = st.checkbox(f"반제품 재고 자동 차감 ({category})", value=True, help="체크 시 입력한 수량만큼 재고가 감소합니다.")
            else:
                auto_deduct = False
                st.caption(f"ℹ️ '{category}' 공정은 반제품 재고 차감 대상이 아닙니다.")

            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("실적 저장 (Save)", type="primary", use_container_width=True):
                code = st.session_state.code_key.upper().strip()
                name = st.session_state.name_key.strip()
                if not name:
                    st.error("제품명을 입력하세요.")
                else:
                    # 1. 실적 저장
                    new_data = {
                        "날짜": str(input_date), "구분": category, "품목코드": code,
                        "제품명": name, "수량": qty, "입력시간": str(datetime.now()),
                        "작성자": get_user_id()
                    }
                    if append_data(new_data, "records"):
                        msg = "실적 저장 완료!"
                        
                        # 2. 재고 자동 차감 (조건부)
                        if auto_deduct:
                            update_inventory(code, name, -qty, f"생산출고({category})", get_user_id())
                            msg += " (반제품 차감됨)"
                            
                        st.success(msg)
                        time.sleep(0.5)
                        st.rerun()
                    else: st.error("저장 실패")

    # 현황 리스트
    with col_view:
        with st.container(border=True):
            col_h1, col_h2 = st.columns([3, 1])
            with col_h1: st.markdown('<div class="section-header">📋 생산 이력 현황</div>', unsafe_allow_html=True)
            with col_h2: save_changes = st.button("💾 데이터 수정사항 저장", key="save_top", type="secondary", use_container_width=True)

            if not df_records.empty:
                edit_df = df_records.copy()
                if '입력시간' in edit_df.columns:
                    edit_df = edit_df.sort_values(by="입력시간", ascending=False)
                
                # 날짜 변환
                if '날짜' in edit_df.columns:
                    try: edit_df['날짜'] = pd.to_datetime(edit_df['날짜']).dt.date
                    except: pass
                
                # 작성자 처리
                if '작성자' not in edit_df.columns: edit_df['작성자'] = 'Unknown'

                column_cfg = {
                    "날짜": st.column_config.DateColumn("날짜", format="YYYY-MM-DD", width=100),
                    "구분": st.column_config.SelectboxColumn("구분", options=CATEGORIES, required=True, width=100),
                    "품목코드": st.column_config.TextColumn("품목코드", width=150),
                    "제품명": st.column_config.TextColumn("제품명", width="large"),
                    "수량": st.column_config.NumberColumn("수량", format="%d", width="small"),
                    "입력시간": st.column_config.TextColumn("입력시간", disabled=True, width="small"), 
                    "작성자": st.column_config.TextColumn("작성자", disabled=True, width="small")
                }

                edited_df = st.data_editor(
                    edit_df,
                    use_container_width=True,
                    num_rows="dynamic",
                    height=550,
                    hide_index=True,  
                    column_config=column_cfg,
                    key="editor"
                )
                
                if save_changes:
                    try:
                        if '날짜' in edited_df.columns:
                            edited_df['날짜'] = pd.to_datetime(edited_df['날짜']).dt.strftime('%Y-%m-%d')
                        if save_all_records(edited_df):
                            st.success("업데이트 완료")
                            time.sleep(1)
                            st.rerun()
                    except Exception as e: st.error(f"오류: {e}")
            else:
                st.info("데이터가 없습니다.")

# ------------------------------------------------------------------
# 5. SMT 반제품 현황
# ------------------------------------------------------------------
elif menu == "📦 SMT 반제품 현황":
    st.markdown(f"""
    <div class="header-box">
        <div class="header-title">📦 SMT 반제품 현황</div>
        <div class="header-sub">반제품 재고 현황을 확인합니다.</div>
    </div>
    """, unsafe_allow_html=True)
    
    df_inv = load_data("inventory")
    
    col_s1, col_s2 = st.columns([3, 1])
    with col_s1:
        search_inv = st.text_input("품목 검색 (코드 또는 제품명)", placeholder="검색어 입력...")
    with col_s2:
        st.metric("총 등록 품목", f"{len(df_inv):,} 종")
        
    if not df_inv.empty:
        # 검색 로직
        if search_inv:
            mask = df_inv['품목코드'].str.contains(search_inv, case=False) | df_inv['제품명'].str.contains(search_inv, case=False)
            display_inv = df_inv[mask]
        else:
            display_inv = df_inv
        
        # [수정] 0 초과인 재고만 필터링 (0 이하 숨김)
        display_inv = display_inv[display_inv['현재고'] > 0]
        
        def highlight_negative(val):
            color = '#ffcccc' if val < 0 else ''
            return f'background-color: {color}'
        
        st.write("▼ 현재 재고 목록")
        
        st.dataframe(
            display_inv.style.map(highlight_negative, subset=['현재고'])
                        .format({"현재고": "{:,} EA"}),
            use_container_width=True,
            hide_index=True,
            height=600  # 높이 확장
        )
        
        if display_inv.empty and not df_inv.empty:
            st.info("조건에 맞는 재고가 없습니다. (수량 0 이하는 숨김 처리됨)")
    else:
        st.info("재고 데이터가 없습니다.")

# ------------------------------------------------------------------
# 5. [메뉴 3] 통합대시보드
# ------------------------------------------------------------------
elif menu == "📊 통합대시보드":
    st.markdown(f"""
    <div class="header-box">
        <div class="header-title">📊 생산 통합 대시보드</div>
        <div class="header-sub">전체 생산 데이터를 시각적으로 분석합니다.</div>
    </div>
    """, unsafe_allow_html=True)

    df = load_data("records")
    
    if not df.empty:
        df['날짜'] = df['날짜'].astype(str)
        
        with st.container(border=True):
            # [수정] 기간 조회 및 구분 필터 추가
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("##### 📅 조회 기간")
                today = datetime.now()
                date_range = st.date_input("기간 선택", (today.replace(day=1), today), max_value=today, label_visibility="collapsed")
            with c2:
                st.markdown("##### 🏭 생산 구분")
                selected_cats = st.multiselect("구분 선택", CATEGORIES, default=CATEGORIES, label_visibility="collapsed")
        
        mask = pd.Series([True] * len(df))
        
        # 1. 날짜 필터 적용
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_d, end_d = date_range
            mask = mask & (pd.to_datetime(df['날짜']).dt.date >= start_d) & (pd.to_datetime(df['날짜']).dt.date <= end_d)
        
        # 2. 구분 필터 적용 (추가됨)
        if selected_cats:
            mask = mask & (df['구분'].isin(selected_cats))
        
        filtered_df = df.loc[mask]

        if not filtered_df.empty:
            st.markdown("<br>", unsafe_allow_html=True)
            col_chart1, col_chart2 = st.columns(2)
            
            with col_chart1:
                with st.container(border=True):
                    st.markdown("##### 🏆 제품별 생산량 Top 5")
                    top_prod = filtered_df.groupby('제품명')['수량'].sum().reset_index().sort_values('수량', ascending=False).head(5)
                    # 오류 해결: Altair 차트 직접 구현
                    chart = alt.Chart(top_prod).mark_bar().encode(
                        x=alt.X('수량', title='생산수량'),
                        y=alt.Y('제품명', sort='-x', title=''),
                        color=alt.Color('수량', legend=None),
                        tooltip=['제품명', '수량']
                    )
                    text = chart.mark_text(align='left', baseline='middle', dx=3).encode(text='수량')
                    st.altair_chart((chart + text), use_container_width=True)
            
            with col_chart2:
                with st.container(border=True):
                    st.markdown("##### 🍰 공정별 점유율")
                    cat_sum = filtered_df.groupby('구분')['수량'].sum().reset_index()
                    base = alt.Chart(cat_sum).encode(theta=alt.Theta("수량", stack=True))
                    pie = base.mark_arc(outerRadius=120, innerRadius=80).encode(
                        color=alt.Color("구분"), order=alt.Order("수량", sort="descending"), tooltip=["구분", "수량"]
                    )
                    text = base.mark_text(radius=140).encode(text=alt.Text("수량", format=","), order=alt.Order("수량", sort="descending"))
                    st.altair_chart(pie + text, use_container_width=True)

            # 상세 테이블 (심플하게)
            st.markdown("<br>", unsafe_allow_html=True)
            with st.expander("🔍 상세 데이터 검색 및 필터링", expanded=True):
                search_txt = st.text_input("제품명 검색", placeholder="제품명 입력...")
                display_df = filtered_df.copy()
                if search_txt:
                    display_df = display_df[display_df['제품명'].str.contains(search_txt, case=False)]
                
                st.dataframe(display_df[['날짜', '구분', '품목코드', '제품명', '수량', '작성자']], use_container_width=True, hide_index=True)
        else: st.warning("선택한 기간 또는 조건에 맞는 데이터가 없습니다.")
    else: st.info("데이터가 없습니다.")

# ------------------------------------------------------------------
# 6. [메뉴 4] 보고서 출력
# ------------------------------------------------------------------
elif menu == "📑 보고서출력":
    st.markdown(f"""
    <div class="header-box">
        <div class="header-title">📑 주간/월간 보고서</div>
        <div class="header-sub">기간별 실적을 집계하여 보고서를 생성합니다.</div>
    </div>
    """, unsafe_allow_html=True)
    
    with st.container(border=True):
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            today = datetime.now()
            start = st.date_input("시작일", today - timedelta(days=today.weekday()))
        with c2: end = st.date_input("종료일", today)
        with c3:
            # [기능 추가] 필터링 옵션
            hide_zero = st.checkbox("실적이 없는 품목 숨기기", value=True)
            
    plan = st.text_area("차주 계획 (선택)", height=100, placeholder="내용을 입력하세요")
    
    st.markdown("---")
    if st.button("보고서 생성 (Generate)", type="primary"):
        df = load_data("records")
        if df.empty:
            st.warning("데이터 없음")
        else:
            try:
                df['날짜'] = pd.to_datetime(df['날짜']).dt.date
                mask_w = (df['날짜'] >= start) & (df['날짜'] <= end)
                df_w = df.loc[mask_w]
                mask_m = (df['날짜'] >= end.replace(day=1)) & (df['날짜'] <= end)
                df_m = df.loc[mask_m]
                
                st.markdown(f"### 📅 {end.month}월 생산실적 보고")
                
                t1, t2 = st.tabs(["📝 텍스트 뷰", "📊 테이블 뷰"])
                
                with t1:
                    st.markdown("**1. 생산내용**")
                    txt = ""
                    if not df_w.empty:
                        target_cats = ["PC", "CM1", "CM3", "배전", "샘플"]
                        grp = df_w.groupby(['구분', '제품명'])['수량'].sum().reset_index()
                        for c in target_cats: 
                            sub = grp[grp['구분'] == c]
                            if not sub.empty:
                                txt += f"**▣ {c}**\n"
                                items = []
                                for _, r in sub.iterrows():
                                    if hide_zero and r['수량'] <= 0: continue
                                    items.append(f"{r['제품명']} {r['수량']:,}EA")
                                if items:
                                    txt += " - " + ", ".join(items) + "\n\n"
                        st.info(txt if txt else "해당 조건의 실적 없음")
                    else: st.warning("실적 없음")
                    st.markdown("**2. 차주 계획**")
                    st.text(f"▣ 차주계획\n - {plan}" if plan else "계획 없음")
                
                with t2:
                    res = []
                    tw, tm = 0, 0
                    for c in ["PC", "CM1", "CM3", "배전", "샘플"]: 
                        w = df_w[df_w['구분'] == c]['수량'].sum() if not df_w.empty else 0
                        m = df_m[df_m['구분'] == c]['수량'].sum() if not df_m.empty else 0
                        tw+=w; tm+=m
                        res.append({"구분": c, "금주": w, "월간": m})
                    res.append({"구분": "총합", "금주": tw, "월간": tm})
                    st.dataframe(pd.DataFrame(res).style.format("{:,}"), use_container_width=True)
            except: st.error("생성 오류")

# ------------------------------------------------------------------
# 7. [메뉴 5] 기준정보관리
# ------------------------------------------------------------------
elif menu == "⚙️ 기준정보관리":
    st.markdown(f"""
    <div class="header-box">
        <div class="header-title">⚙️ 기준정보 관리</div>
        <div class="header-sub">품목 코드 관리 및 데이터 백업/복구</div>
    </div>
    """, unsafe_allow_html=True)
    
    t_item, t_back = st.tabs(["📦 품목코드 관리", "💾 데이터 백업"])
    
    with t_item:
        current = load_data("items")
        col_kpi1, col_kpi2 = st.columns(2)
        col_kpi1.metric("등록된 품목 수", f"{len(current)}개")
        
        with st.container(border=True):
            st.markdown("##### 품목 목록")
            if not current.empty:
                st.dataframe(current, use_container_width=True, height=300)
            else: st.info("데이터 없음")
            
        st.write("---")
        c1, c2 = st.columns(2)
        with c1:
            st.write("**📤 품목 일괄 업로드**")
            upl = st.file_uploader("파일 (CSV/Excel)", type=['csv','xlsx','xls'])
            if upl:
                if st.button("업로드 (덮어쓰기)", type="primary", use_container_width=True):
                    try:
                        new_items = read_uploaded_file(upl)
                        if len(new_items.columns) >= 2:
                            new_items.columns = ["품목코드","제품명"]+list(new_items.columns[2:])
                            new_items['품목코드'] = new_items['품목코드'].astype(str).str.strip().str.upper()
                            new_items['제품명'] = new_items['제품명'].astype(str).str.strip()
                            if save_all_items(new_items): st.success("완료!"); time.sleep(1); st.rerun()
                        else: st.error("형식 오류: 최소 2개 열(품목코드, 제품명)이 필요합니다.")
                    except Exception as e: st.error(f"실패: {e}")
        with c2:
            st.write("**🗑️ 초기화**")
            if st.button("품목 전체 삭제", type="secondary", use_container_width=True):
                if delete_all_items(): st.success("삭제됨"); time.sleep(1); st.rerun()

    with t_back:
        with st.container(border=True):
            st.info("데이터는 자동으로 저장되지만, 정기적인 백업을 권장합니다.")
            if STORAGE_TYPE=="LOCAL":
                if os.path.exists(FILE_RECORDS):
                    with open(FILE_RECORDS,"rb") as f:
                        st.download_button("📥 생산기록 다운로드 (CSV)", f, "records_backup.csv", "text/csv")
                if os.path.exists(FILE_INVENTORY):
                    with open(FILE_INVENTORY,"rb") as f:
                        st.download_button("📥 재고데이터 다운로드 (CSV)", f, "inventory_backup.csv", "text/csv")