import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import json
import streamlit.components.v1 as components
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
# 1. 시스템 설정 및 데이터 스키마 정의 (STEP 1)
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT 통합 관리 시스템", 
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded" 
)

# CSS 스타일 적용
st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; color: #1e293b; }
    .stApp { background-color: #f8fafc; }
    .dashboard-header {
        background: linear-gradient(135deg, #3b82f6 0%, #1e3a8a 100%);
        padding: 20px 30px; border-radius: 12px; color: white; margin-bottom: 20px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }
    .metric-card {
        background: white; border: 1px solid #e2e8f0; border-radius: 12px; padding: 20px;
        box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# 구글 시트 설정
GOOGLE_SHEET_NAME = "SMT_Database" 

# 시트 이름 상수
SHEET_RECORDS = "production_data"       # 생산 실적
SHEET_INVENTORY = "inventory_data"      # 재고 현황
SHEET_MAINTENANCE = "maintenance_data"  # 보전 이력
SHEET_EQUIPMENT = "equipment_master"    # 설비 기준 (Line 포함)
SHEET_CHECK_MASTER = "daily_check_master" # [NEW] 일일점검 기준
SHEET_CHECK_RESULT = "daily_check_result" # [NEW] 일일점검 결과

# 컬럼 정의
COLS_CHECK_MASTER = ["line", "equip_id", "equip_name", "item_name", "check_content", "standard", "check_type", "unit", "min_val", "max_val"]
COLS_CHECK_RESULT = ["date", "line", "equip_id", "item_name", "value", "ox", "checker", "timestamp"]

# 기본 설비/점검 데이터 (초기화용 더미 데이터)
DEFAULT_CHECK_MASTER = [
    {"line": "1 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "AIR 압력", "check_content": "게이지 확인", "standard": "0.5 MPa", "check_type": "OX", "unit": "", "min_val": "", "max_val": ""},
    {"line": "1 LINE", "equip_id": "HP-520S", "equip_name": "PRINTER", "item_name": "온도", "check_content": "온도계 확인", "standard": "24±5", "check_type": "NUMBER_AND_OX", "unit": "℃", "min_val": "19", "max_val": "29"},
]

# ------------------------------------------------------------------
# 2. 데이터 핸들링 모듈 (Google Sheets)
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

def get_worksheet(sheet_name, worksheet_name, create_cols=None):
    client = get_gs_connection()
    if not client: return None
    try:
        sh = client.open(sheet_name)
    except:
        st.error(f"시트 '{sheet_name}'를 찾을 수 없습니다.")
        return None

    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        if create_cols:
            ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)
            ws.append_row(create_cols)
        else: return None
    return ws

@st.cache_data(ttl=10)
def load_data(sheet_name, cols=None):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name, create_cols=cols)
    if not ws: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()
    try:
        df = get_as_dataframe(ws, evaluate_formulas=True)
        # 빈 컬럼/행 제거
        df = df.dropna(how='all').dropna(axis=1, how='all')
        # 필수 컬럼 보장
        if cols:
            for col in cols:
                if col not in df.columns: df[col] = ""
        return df
    except: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()

def save_data(df, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        ws.clear()
        set_with_dataframe(ws, df)
        load_data.clear()
        return True
    return False

def append_row(data_dict, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        # 헤더 순서대로 정렬
        try: headers = ws.row_values(1)
        except: headers = list(data_dict.keys())
        
        row = [str(data_dict.get(h, "")) for h in headers]
        ws.append_row(row)
        load_data.clear()
        return True
    return False

# ------------------------------------------------------------------
# 3. 비즈니스 로직 (STEP 2: Python -> HTML 데이터 변환)
# ------------------------------------------------------------------
def get_daily_check_config():
    """
    Google Sheet의 'daily_check_master' 데이터를 읽어서
    HTML(JS)에서 사용할 수 있는 JSON 구조로 변환합니다.
    """
    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    
    if df.empty:
        # 데이터가 없으면 초기 데이터 생성
        df = pd.DataFrame(DEFAULT_CHECK_MASTER)
        save_data(df, SHEET_CHECK_MASTER)
    
    # JSON 구조 변환: { "LineName": [ { "equip": "...", "items": [...] } ] }
    config = {}
    
    # 라인별 그룹화
    for line_name, line_group in df.groupby("line"):
        equip_list = []
        # 설비별 그룹화
        for equip_name, equip_group in line_group.groupby("equip_name"):
            items = []
            for _, row in equip_group.iterrows():
                items.append({
                    "name": row["item_name"],
                    "content": row["check_content"],
                    "standard": row["standard"],
                    "type": row["check_type"],
                    "unit": row["unit"] if pd.notna(row["unit"]) else "",
                    "min": row["min_val"] if pd.notna(row["min_val"]) else "",
                    "max": row["max_val"] if pd.notna(row["max_val"]) else ""
                })
            equip_list.append({
                "equip": f"{equip_name} ({equip_group.iloc[0]['equip_id']})", # ID 병기
                "items": items
            })
        config[line_name] = equip_list
        
    return json.dumps(config, ensure_ascii=False)

# ------------------------------------------------------------------
# 4. 일일점검 HTML 템플릿 (동적 데이터 주입 가능하도록 수정됨)
# ------------------------------------------------------------------
def get_html_content(config_json):
    # 기존 HTML 코드의 구조를 유지하되, defaultLineData 부분을 Python 변수로 치환
    return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>SMT Daily Check Field</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;700&display=swap');
        body {{ font-family: 'Noto Sans KR', sans-serif; background-color: #f1f5f9; -webkit-tap-highlight-color: transparent; }}
        .ox-btn.active[data-ox="OK"] {{ background-color: #22c55e; color: white; border-color: #22c55e; }}
        .ox-btn.active[data-ox="NG"] {{ background-color: #ef4444; color: white; border-color: #ef4444; }}
        .ox-btn {{ background-color: white; border: 1px solid #cbd5e1; }}
        .tab-active {{ background: #2563eb; color: white; }}
        .tab-inactive {{ background: white; color: #64748b; }}
    </style>
</head>
<body class="h-screen flex flex-col overflow-hidden">
    <!-- 상단 헤더 -->
    <header class="bg-slate-900 text-white p-4 flex justify-between items-center shrink-0">
        <div class="font-bold text-xl">SMT Daily Check</div>
        <div class="flex gap-2">
            <input type="date" id="inputDate" class="bg-slate-800 border-none rounded px-2 py-1 text-sm font-mono">
            <button onclick="app.saveLocal()" class="bg-blue-600 px-3 py-1 rounded text-sm font-bold">임시저장</button>
        </div>
    </header>

    <!-- 탭 메뉴 -->
    <div class="bg-white border-b p-2 overflow-x-auto whitespace-nowrap" id="lineTabs"></div>

    <!-- 메인 리스트 -->
    <main class="flex-1 overflow-y-auto p-4" id="checklistContainer"></main>

    <!-- 하단 액션바 (NG 발생 시 보전 요청 연계 가능) -->
    <div class="bg-white border-t p-4 flex justify-between items-center shrink-0">
        <div id="status-text" class="text-sm font-bold text-slate-500">진행률: 0%</div>
        <button onclick="app.exportData()" class="bg-green-600 text-white px-6 py-3 rounded-xl font-bold shadow-lg active:scale-95 transition-transform">
            데이터 내보내기 (서버전송)
        </button>
    </div>

    <!-- 데이터 전송용 모달 (임시) -->
    <div id="export-modal" class="fixed inset-0 bg-black/50 hidden flex items-center justify-center z-50">
        <div class="bg-white p-6 rounded-xl w-[90%] max-w-md">
            <h3 class="font-bold text-lg mb-2">데이터 내보내기</h3>
            <p class="text-sm text-slate-500 mb-4">아래 데이터를 복사하여 시스템의 [데이터 동기화] 탭에 붙여넣으세요.</p>
            <textarea id="export-area" class="w-full h-32 border p-2 rounded text-xs font-mono mb-4" readonly></textarea>
            <div class="flex justify-end gap-2">
                <button onclick="document.getElementById('export-modal').classList.add('hidden')" class="px-4 py-2 bg-slate-200 rounded">닫기</button>
                <button onclick="app.copyToClipboard()" class="px-4 py-2 bg-blue-600 text-white rounded">복사하기</button>
            </div>
        </div>
    </div>

    <script>
        // Python에서 주입된 데이터
        const MASTER_DATA = {config_json}; 
        const DATA_KEY_PREFIX = "SMT_CHECK_RESULT_";

        const app = {{
            state: {{ currentLine: Object.keys(MASTER_DATA)[0], date: "", results: {{}} }},
            
            init() {{
                const today = new Date().toISOString().split('T')[0];
                this.state.date = today;
                document.getElementById('inputDate').value = today;
                this.loadLocal(today);
                this.renderTabs();
                this.renderList();
                lucide.createIcons();
            }},

            loadLocal(date) {{
                const saved = localStorage.getItem(DATA_KEY_PREFIX + date);
                if (saved) this.state.results = JSON.parse(saved);
                else this.state.results = {{}};
            }},

            saveLocal() {{
                localStorage.setItem(DATA_KEY_PREFIX + this.state.date, JSON.stringify(this.state.results));
                // Toast 메시지 대신 간단 알림
                const btn = document.querySelector('button[onclick="app.saveLocal()"]');
                const org = btn.innerText;
                btn.innerText = "저장됨!";
                setTimeout(() => btn.innerText = org, 1000);
            }},

            setResult(uid, type, val) {{
                if(!this.state.results[uid]) this.state.results[uid] = {{}};
                this.state.results[uid][type] = val;
                this.saveLocal();
                this.updateUI(uid);
                this.updateSummary();
            }},

            renderTabs() {{
                const con = document.getElementById('lineTabs');
                con.innerHTML = Object.keys(MASTER_DATA).map(line => 
                    `<button onclick="app.switchLine('${{line}}')" 
                        class="px-4 py-2 rounded-full text-sm font-bold mr-2 transition-colors ${{line === this.state.currentLine ? 'tab-active' : 'tab-inactive'}}">
                        ${{line}}
                    </button>`
                ).join('');
            }},

            switchLine(line) {{
                this.state.currentLine = line;
                this.renderTabs();
                this.renderList();
                lucide.createIcons();
            }},

            renderList() {{
                const con = document.getElementById('checklistContainer');
                const equipments = MASTER_DATA[this.state.currentLine] || [];
                
                con.innerHTML = equipments.map((eq, ei) => `
                    <div class="bg-white rounded-xl shadow-sm border border-slate-200 mb-4 overflow-hidden">
                        <div class="bg-slate-50 px-4 py-2 border-b font-bold text-slate-700 flex justify-between items-center">
                            <span>${{eq.equip}}</span>
                        </div>
                        <div class="divide-y divide-slate-100">
                            ${{eq.items.map((item, ii) => {{
                                const uid = `${{this.state.currentLine}}_${{eq.equip}}_${{item.name}}`; // Unique ID
                                const res = this.state.results[uid] || {{}};
                                const ox = res.ox || null;
                                
                                let controls = '';
                                if(item.type === 'OX') {{
                                    controls = `
                                        <div class="flex gap-1">
                                            <button class="ox-btn px-3 py-2 rounded font-bold text-xs ${{ox==='OK'?'active':''}}" 
                                                onclick="app.setResult('${{uid}}', 'ox', 'OK')" data-ox="OK">OK</button>
                                            <button class="ox-btn px-3 py-2 rounded font-bold text-xs ${{ox==='NG'?'active':''}}" 
                                                onclick="app.setResult('${{uid}}', 'ox', 'NG')" data-ox="NG">NG</button>
                                        </div>`;
                                }} else {{
                                    controls = `
                                        <div class="flex items-center gap-2">
                                            <input type="number" class="border rounded w-16 p-1 text-center text-sm font-bold" 
                                                value="${{res.val || ''}}" placeholder="${{item.standard}}"
                                                onchange="app.setResult('${{uid}}', 'val', this.value)">
                                            <div class="flex gap-1">
                                                <button class="ox-btn px-2 py-2 rounded font-bold text-xs ${{ox==='OK'?'active':''}}" 
                                                    onclick="app.setResult('${{uid}}', 'ox', 'OK')" data-ox="OK">O</button>
                                                <button class="ox-btn px-2 py-2 rounded font-bold text-xs ${{ox==='NG'?'active':''}}" 
                                                    onclick="app.setResult('${{uid}}', 'ox', 'NG')" data-ox="NG">X</button>
                                            </div>
                                        </div>`;
                                }}

                                return `
                                <div class="p-4 flex justify-between items-center">
                                    <div class="flex-1 pr-2">
                                        <div class="font-bold text-sm text-slate-800">${{item.name}}</div>
                                        <div class="text-xs text-slate-500">${{item.content}} <span class="text-blue-500">[${{item.standard}}]</span></div>
                                    </div>
                                    ${{controls}}
                                </div>`;
                            }}).join('')}}
                        </div>
                    </div>
                `).join('');
            }},

            updateUI(uid) {{
                this.renderList(); // 간단하게 전체 리렌더링 (최적화 가능)
            }},

            updateSummary() {{
                // 진행률 계산 로직 등
            }},

            exportData() {{
                const exportJson = JSON.stringify({{
                    date: this.state.date,
                    results: this.state.results,
                    timestamp: new Date().toISOString()
                }}, null, 2);
                
                document.getElementById('export-area').value = exportJson;
                document.getElementById('export-modal').classList.remove('hidden');
            }},

            copyToClipboard() {{
                const copyText = document.getElementById("export-area");
                copyText.select();
                document.execCommand("copy");
                alert("복사되었습니다. 시스템의 '데이터 동기화' 탭에 붙여넣으세요.");
            }}
        }};

        document.addEventListener('DOMContentLoaded', () => app.init());
    </script>
</body>
</html>
    """

# ------------------------------------------------------------------
# 5. 사용자 인증 (기존 유지)
# ------------------------------------------------------------------
def check_password():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: return True
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("SMT 통합 관리 시스템")
        with st.form("login"):
            id = st.text_input("ID")
            pw = st.text_input("PW", type="password")
            if st.form_submit_button("로그인", use_container_width=True):
                # 간단한 하드코딩 인증 (실제론 DB 연동)
                if id in ["admin", "user"] and pw: # 비밀번호 체크 로직 생략
                    st.session_state.logged_in = True
                    st.session_state.user_id = id
                    st.session_state.role = "admin" if id == "admin" else "user"
                    st.rerun()
                else:
                    st.error("로그인 실패")
    return False

if not check_password(): st.stop()

# ------------------------------------------------------------------
# 6. 메인 UI (STEP 3: 메뉴 구조 개편)
# ------------------------------------------------------------------
with st.sidebar:
    st.title("Cloud SMT")
    st.caption(f"접속자: {st.session_state.user_id} ({st.session_state.role})")
    
    # [설계 목표] 메뉴 구조 통일
    menu = st.radio("메뉴 이동", 
        ["📊 대시보드", "📦 생산관리", "🛠 설비보전관리", "✅ 일일점검관리", "⚙ 기준정보관리"]
    )
    st.divider()
    if st.button("로그아웃"):
        st.session_state.logged_in = False
        st.rerun()

# 헤더 표시
st.markdown(f'<div class="dashboard-header"><h3>{menu}</h3></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------
# 7. 메뉴별 기능 구현
# ------------------------------------------------------------------

if menu == "📊 대시보드":
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("오늘 생산량", "12,500 EA", "+5%")
    col2.metric("가동률", "92.4%", "-1.2%")
    col3.metric("일일점검 완료율", "85%", "미완료 2건")
    col4.metric("보전 요청", "1 건", "신규")
    
    st.markdown("#### 📅 주간 생산/불량 추이")
    st.info("데이터 시각화 영역 (Altair 차트)")

elif menu == "📦 생산관리":
    tab1, tab2 = st.tabs(["생산 실적 등록", "생산 이력 조회"])
    with tab1:
        st.write("기존 생산 관리 기능 이식")
        # 기존 app.py의 생산관리 로직을 여기에 배치

elif menu == "🛠 설비보전관리":
    tab1, tab2 = st.tabs(["보전 요청/처리", "보전 이력"])
    with tab1:
        st.markdown("#### 🚨 긴급 보전 요청 (NG 연동)")
        # 일일점검에서 NG난 항목이 있다면 여기서 자동으로 불러와서 리스트업
        st.info("일일점검 NG 항목이 발생하면 자동으로 이곳에 요청이 생성됩니다.")
        
        with st.expander("수동 요청 등록"):
            st.selectbox("설비 선택", ["SML-120Y", "HP-520S"])
            st.text_area("요청 내용")
            st.button("요청 등록")

elif menu == "✅ 일일점검관리":
    # [설계 목표] 점검 현황 / 입력 / 이력 분리
    tab_dash, tab_input, tab_sync, tab_hist = st.tabs(["📊 점검 현황", "📱 현장 입력 (Tablet)", "🔄 데이터 동기화", "📋 이력 조회"])
    
    with tab_dash:
        st.markdown("#### 오늘의 점검 현황")
        # daily_check_result 시트에서 오늘 날짜 데이터를 조회하여 표시
        df_res = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        today = datetime.now().strftime("%Y-%m-%d")
        if not df_res.empty:
            df_today = df_res[df_res['date'] == today]
            st.metric("오늘 점검 항목 수", len(df_today))
        else:
            st.info("오늘 등록된 점검 데이터가 없습니다.")

    with tab_input:
        st.markdown("##### 📱 태블릿용 점검 화면")
        st.caption("아래 화면은 현장 태블릿에서 전체화면으로 사용됩니다.")
        
        # [STEP 2] Python 기준정보 -> HTML 주입
        config_json = get_daily_check_config()
        html_code = get_html_content(config_json)
        
        # HTML 렌더링
        components.html(html_code, height=800, scrolling=True)

    with tab_sync:
        st.markdown("#### 📥 현장 데이터 서버 저장")
        st.caption("태블릿(HTML)에서 '데이터 내보내기'한 JSON을 여기에 붙여넣어 저장합니다.")
        
        json_input = st.text_area("JSON 데이터 붙여넣기", height=150)
        if st.button("데이터 저장 및 분석", type="primary"):
            try:
                data = json.loads(json_input)
                results = data.get("results", {})
                date = data.get("date")
                
                rows_to_add = []
                for uid, res in results.items():
                    # uid format: LINE_EQUIP_ITEM (예: 1 LINE_IN LOADER_AIR 압력)
                    parts = uid.split('_')
                    if len(parts) >= 3:
                        line = parts[0]
                        equip = parts[1]
                        item = "_".join(parts[2:])
                        
                        rows_to_add.append({
                            "date": date,
                            "line": line,
                            "equip_id": equip, # 여기서는 이름이 ID로 쓰임 (매핑 필요 시 수정)
                            "item_name": item,
                            "value": res.get("val", ""),
                            "ox": res.get("ox", ""),
                            "checker": st.session_state.user_id,
                            "timestamp": str(datetime.now())
                        })
                        
                if rows_to_add:
                    df_new = pd.DataFrame(rows_to_add)
                    # 기존 데이터에 추가 (append_data 함수 개선 필요하거나 gspread append_rows 사용)
                    # 여기서는 단순화를 위해 개별 추가 루프 (실제론 bulk update 권장)
                    ws = get_worksheet(GOOGLE_SHEET_NAME, SHEET_CHECK_RESULT, create_cols=COLS_CHECK_RESULT)
                    ws.append_rows(df_new.values.tolist())
                    st.success(f"{len(rows_to_add)}건의 점검 데이터가 저장되었습니다.")
                    
                    # [STEP 4] NG 항목 자동 감지
                    ng_items = [r for r in rows_to_add if r['ox'] == 'NG']
                    if ng_items:
                        st.error(f"🚨 {len(ng_items)}건의 NG 항목이 발견되었습니다! 설비보전 요청을 검토하세요.")
                        st.dataframe(pd.DataFrame(ng_items))
                
            except Exception as e:
                st.error(f"데이터 처리 중 오류: {e}")

    with tab_hist:
        st.markdown("#### 📋 과거 점검 이력")
        df_hist = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        st.dataframe(df_hist, use_container_width=True)

elif menu == "⚙ 기준정보관리":
    tab1, tab2 = st.tabs(["설비 기준정보", "일일점검 기준정보"])
    
    with tab1:
        st.markdown("#### 🏭 라인 및 설비 관리")
        df_eq = load_data(SHEET_EQUIPMENT, ["id", "name", "line", "func"])
        edited_eq = st.data_editor(df_eq, num_rows="dynamic", use_container_width=True)
        if st.button("설비 정보 저장"):
            save_data(edited_eq, SHEET_EQUIPMENT)
            st.success("저장 완료")

    with tab2:
        st.markdown("#### ✅ 일일점검 항목 관리")
        st.caption("여기서 항목을 추가하면 '현장 입력(HTML)' 화면에 자동으로 반영됩니다.")
        
        df_check = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
        edited_check = st.data_editor(df_check, num_rows="dynamic", use_container_width=True)
        
        if st.button("점검 기준 저장"):
            save_data(edited_check, SHEET_CHECK_MASTER)
            st.success("기준 정보가 업데이트되었습니다. '일일점검관리' 메뉴에서 확인하세요.")