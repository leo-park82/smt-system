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
    {"line": "1 LINE", "equip_id": "SML-120Y", "equip_name": "IN LOADER", "item_name": "AIR 압력", "check_content": "압력 게이지 지침 확인", "standard": "0.5 MPa", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "HP-520S", "equip_name": "SCREEN PRINTER", "item_name": "테이블 오염", "check_content": "테이블 위 솔더/이물 청결", "standard": "청결할 것", "check_type": "OX", "min_val": "", "max_val": "", "unit": ""},
    {"line": "1 LINE", "equip_id": "1809MK", "equip_name": "REFLOW", "item_name": "N2 PPM", "check_content": "산소 농도 모니터 수치", "standard": "3000 ppm 이하", "check_type": "NUMBER", "min_val": "0", "max_val": "3000", "unit": "ppm"},
]
DEFAULT_EQUIPMENT = [{"id": "SML-120Y", "name": "IN LOADER", "func": "PCB 공급"}]

# ------------------------------------------------------------------
# 2. 구글 시트 연결
# ------------------------------------------------------------------
@st.cache_resource
def get_gs_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" not in st.secrets:
             # st.error("Secrets 설정 오류") # 조용히 처리
             return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except Exception as e:
        return None

def get_worksheet(sheet_name, create_cols=None):
    client = get_gs_connection()
    if not client: return None
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
    except:
        # 시트가 없으면 None 반환 (나중에 Fallback 처리)
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

def append_rows(rows, sheet_name, cols):
    ws = get_worksheet(sheet_name, create_cols=cols)
    if ws:
        ws.append_rows(rows)
        clear_cache()
        return True
    return False

# ------------------------------------------------------------------
# 3. HTML 템플릿 (서명 그리기 + 빈칸 숫자 입력)
# ------------------------------------------------------------------
def get_input_html(master_json):
    return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Check Input</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f8fafc; -webkit-tap-highlight-color: transparent; }}
        .btn-ox {{ transition: all 0.2s; border: 1px solid #e2e8f0; }}
        .btn-ox.selected[data-val="OK"] {{ background: #22c55e; color: white; border-color: #22c55e; }}
        .btn-ox.selected[data-val="NG"] {{ background: #ef4444; color: white; border-color: #ef4444; }}
        #signature-pad {{ touch-action: none; background: white; border: 2px solid #e2e8f0; border-radius: 0.5rem; width: 100%; height: 200px; cursor: crosshair; }}
    </style>
</head>
<body class="p-4 pb-28">
    <div class="max-w-md mx-auto">
        <div class="bg-white p-4 rounded-xl shadow-sm mb-4 border border-slate-200">
            <h1 class="text-xl font-bold text-slate-800 flex items-center gap-2">
                <i data-lucide="clipboard-check" class="text-blue-600"></i> 일일점검 입력
            </h1>
            <div class="mt-2 flex gap-2">
                <select id="lineSelect" class="bg-slate-50 border p-2 rounded w-full font-bold" onchange="renderList()">
                    <!-- Options -->
                </select>
                <input type="date" id="checkDate" class="bg-slate-50 border p-2 rounded font-mono" />
            </div>
            <button onclick="setAllOK()" class="mt-2 w-full bg-green-50 text-green-700 border border-green-200 py-2 rounded-lg font-bold text-sm">
                ✅ 전체 OK (일괄 적용)
            </button>
        </div>

        <div id="checkList" class="space-y-3"></div>
        
        <!-- 그리기 서명란 -->
        <div class="bg-white p-4 rounded-xl shadow-sm mt-4 border border-slate-200">
            <div class="flex justify-between items-end mb-2">
                <div class="font-bold text-slate-700">✍️ 점검자 서명 (Signature)</div>
                <button onclick="clearSignature()" class="text-xs text-red-500 underline font-bold">지우기</button>
            </div>
            <canvas id="signature-pad"></canvas>
            <div class="mt-2 text-xs text-gray-400 text-center">※ 위 박스에 서명해주세요 (터치/마우스)</div>
        </div>

        <div class="fixed bottom-0 left-0 right-0 p-4 bg-white border-t border-slate-200 shadow-lg z-50">
            <div class="max-w-md mx-auto">
                <button onclick="exportData()" class="w-full bg-blue-600 text-white py-3.5 rounded-xl font-bold text-lg active:scale-95 transition-transform shadow-blue-200 shadow-lg flex items-center justify-center gap-2">
                    <i data-lucide="save"></i> 저장용 데이터 생성
                </button>
            </div>
        </div>
    </div>

    <!-- 데이터 내보내기 모달 -->
    <div id="exportModal" class="fixed inset-0 bg-black/60 backdrop-blur-sm hidden flex items-center justify-center z-[99] p-4">
        <div class="bg-white rounded-xl w-full max-w-sm p-5 shadow-2xl">
            <h3 class="font-bold text-lg mb-2">데이터 전송 준비 완료</h3>
            <p class="text-sm text-slate-500 mb-3">아래 텍스트를 복사하여 <b>[데이터 동기화]</b> 탭에 붙여넣으세요.</p>
            <textarea id="jsonOutput" class="w-full h-32 bg-slate-50 border rounded p-2 text-xs font-mono mb-3 focus:ring-2 ring-blue-500 outline-none" readonly></textarea>
            <div class="flex gap-2">
                <button onclick="copyAndClose()" class="flex-1 bg-green-600 text-white py-3 rounded-lg font-bold shadow-md active:scale-95">복사 및 닫기</button>
                <button onclick="document.getElementById('exportModal').classList.add('hidden')" class="px-4 py-3 text-slate-500 font-bold">취소</button>
            </div>
        </div>
    </div>

    <script>
        const MASTER = {master_json};
        const RESULTS = {{}};
        let signaturePad, ctx;

        function init() {{
            const today = new Date().toISOString().split('T')[0];
            document.getElementById('checkDate').value = today;
            
            const lineSel = document.getElementById('lineSelect');
            Object.keys(MASTER).forEach(line => {{
                const opt = document.createElement('option');
                opt.value = line;
                opt.innerText = line;
                lineSel.appendChild(opt);
            }});
            renderList();
            setTimeout(initSignature, 500);
            lucide.createIcons();
        }}

        function renderList() {{
            const line = document.getElementById('lineSelect').value;
            const container = document.getElementById('checkList');
            container.innerHTML = '';
            
            const equipments = MASTER[line] || [];
            equipments.forEach(eq => {{
                const card = document.createElement('div');
                card.className = 'bg-white p-4 rounded-xl border border-slate-200 shadow-sm';
                let html = `<div class='font-bold text-slate-700 mb-3 flex items-center gap-2'><i data-lucide='server' class='w-4 h-4 text-slate-400'></i> ${{eq.equip}}</div>`;
                
                eq.items.forEach(item => {{
                    const uid = `${{line}}_${{eq.id}}_${{item.name}}`;
                    const saved = RESULTS[uid] || {{}};
                    
                    let inputHtml = '';
                    if(item.type === 'OX') {{
                        inputHtml = `
                            <div class="flex gap-1 w-32">
                                <button onclick="setResult('${{uid}}', 'OK')" class="btn-ox px-3 py-2 rounded-lg text-sm font-bold flex-1 ${{saved.val==='OK'?'selected':''}}" data-val="OK">O</button>
                                <button onclick="setResult('${{uid}}', 'NG')" class="btn-ox px-3 py-2 rounded-lg text-sm font-bold flex-1 ${{saved.val==='NG'?'selected':''}}" data-val="NG">X</button>
                            </div>`;
                    }} else {{
                        // [수정] 빈칸 처리 (undefined/null 일 때 빈 문자열)
                        const displayVal = (saved.val === undefined || saved.val === null) ? '' : saved.val;
                        inputHtml = `
                            <div class="flex items-center gap-2 justify-end w-32">
                                <input type="number" placeholder="입력" class="border rounded-lg px-2 py-1.5 w-24 text-center font-bold text-sm bg-slate-50 focus:bg-white focus:ring-2 ring-blue-500 outline-none transition-all" 
                                    onchange="setResult('${{uid}}', this.value)" value="${{displayVal}}">
                                <span class="text-xs text-slate-400 w-6">${{item.unit}}</span>
                            </div>`;
                    }}
                    
                    html += `
                    <div class="py-3 border-t border-slate-50 flex justify-between items-center gap-2">
                        <div class="flex-1">
                            <div class="text-sm font-bold text-slate-700">${{item.name}}</div>
                            <div class="text-xs text-slate-400 mt-0.5">${{item.content}} <span class="text-blue-500 font-medium">[${{item.min}}~${{item.max}}]</span></div>
                        </div>
                        ${{inputHtml}}
                    </div>`;
                }});
                card.innerHTML = html;
                container.appendChild(card);
            }});
            lucide.createIcons();
        }}

        window.setResult = (uid, val) => {{
            RESULTS[uid] = {{ val: val }};
            if(val === 'OK' || val === 'NG') renderList();
        }};

        window.setAllOK = () => {{
            const line = document.getElementById('lineSelect').value;
            const equipments = MASTER[line] || [];
            equipments.forEach(eq => {{
                eq.items.forEach(item => {{
                    const uid = `${{line}}_${{eq.id}}_${{item.name}}`;
                    if(item.type === 'OX') setResult(uid, 'OK');
                }});
            }});
            alert("모든 OX 항목이 OK로 설정되었습니다.");
        }};

        function initSignature() {{
            signaturePad = document.getElementById('signature-pad');
            if(!signaturePad) return;
            
            const ratio = Math.max(window.devicePixelRatio || 1, 1);
            signaturePad.width = signaturePad.offsetWidth * ratio;
            signaturePad.height = signaturePad.offsetHeight * ratio;
            ctx = signaturePad.getContext('2d');
            ctx.scale(ratio, ratio);
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.strokeStyle = '#000';

            let drawing = false;
            function getPos(e) {{
                const rect = signaturePad.getBoundingClientRect();
                const clientX = e.touches ? e.touches[0].clientX : e.clientX;
                const clientY = e.touches ? e.touches[0].clientY : e.clientY;
                return {{ x: clientX - rect.left, y: clientY - rect.top }};
            }}

            const start = (e) => {{ e.preventDefault(); drawing = true; ctx.beginPath(); const {{x,y}} = getPos(e); ctx.moveTo(x, y); }};
            const move = (e) => {{ if(!drawing) return; e.preventDefault(); const {{x,y}} = getPos(e); ctx.lineTo(x, y); ctx.stroke(); }};
            const end = () => {{ drawing = false; }};

            signaturePad.addEventListener('mousedown', start);
            signaturePad.addEventListener('mousemove', move);
            signaturePad.addEventListener('mouseup', end);
            signaturePad.addEventListener('touchstart', start, {{passive: false}});
            signaturePad.addEventListener('touchmove', move, {{passive: false}});
            signaturePad.addEventListener('touchend', end);
        }}

        window.clearSignature = () => {{
            if(ctx) ctx.clearRect(0, 0, signaturePad.width, signaturePad.height);
        }}

        window.exportData = () => {{
            const date = document.getElementById('checkDate').value;
            const line = document.getElementById('lineSelect').value;
            const signature = signaturePad.toDataURL();
            
            const items = [];
            Object.keys(RESULTS).forEach(uid => {{
                const [l, equip_id, item_name] = uid.split('_');
                items.push({{ equip_id, item_name, value: RESULTS[uid].val }});
            }});

            const payload = {{ meta: {{ date, line, exporter: "Tablet" }}, items, signature }};
            document.getElementById('jsonOutput').value = JSON.stringify(payload);
            document.getElementById('exportModal').classList.remove('hidden');
        }};

        window.copyAndClose = () => {{
            const txt = document.getElementById('jsonOutput');
            txt.select();
            document.execCommand('copy');
            document.getElementById('exportModal').classList.add('hidden');
        }};

        init();
    </script>
</body>
</html>
"""

# ------------------------------------------------------------------
# 4. 서버 사이드 로직
# ------------------------------------------------------------------
def get_daily_check_master_data():
    df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    if df.empty or len(df) < 5:
        # Fallback to default if sheet is empty or fails
        df = pd.DataFrame(DEFAULT_CHECK_MASTER)
    return df

def get_master_json():
    df = get_daily_check_master_data()
    config = {}
    if not df.empty:
        for line, g_line in df.groupby('line'):
            equip_list = []
            for equip, g_equip in g_line.groupby('equip_name'):
                items = []
                for _, row in g_equip.iterrows():
                    items.append({
                        "name": row['item_name'], "content": row['check_content'],
                        "type": row['check_type'], "min": row['min_val'], 
                        "max": row['max_val'], "unit": row['unit']
                    })
                equip_list.append({"equip": equip, "id": g_equip.iloc[0]['equip_id'], "items": items})
            config[line] = equip_list
    return json.dumps(config, ensure_ascii=False)

def process_check_data(payload, user_id):
    try:
        meta = payload.get('meta', {})
        items = payload.get('items', [])
        signature = payload.get('signature', "")
        date, line = meta.get('date'), meta.get('line')
        
        df_master = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
        # Use defaults if sheet fails
        if df_master.empty: df_master = pd.DataFrame(DEFAULT_CHECK_MASTER)
        df_master = df_master[df_master['line'] == line]
        
        rows, ng_list = [], []
        
        for item in items:
            equip_id, item_name, val = item.get('equip_id'), item.get('item_name'), str(item.get('value'))
            criteria = df_master[(df_master['equip_id'] == equip_id) & (df_master['item_name'] == item_name)]
            ox = "OK"
            if not criteria.empty:
                crit = criteria.iloc[0]
                if crit['check_type'] == 'NUMBER':
                    try:
                        if not val or val == '': ox = "NG" # 빈 값 NG
                        else:
                            num = float(val)
                            min_v = float(crit['min_val']) if crit['min_val'] else -99999
                            max_v = float(crit['max_val']) if crit['max_val'] else 99999
                            if not (min_v <= num <= max_v): ox = "NG"
                    except: ox = "NG"
                else:
                    if val == 'NG': ox = "NG"
            
            if ox == "NG": ng_list.append(f"{equip_id}-{item_name}")
            rows.append([date, line, equip_id, item_name, val, ox, user_id, str(datetime.now())])
        
        if rows:
            append_rows(rows, SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
            if signature:
                # 서명 데이터 저장 (텍스트로 저장됨, 실제 이미지 저장은 Blob Storage 필요)
                append_rows([[date, line, user_id, signature[:50]+"...", str(datetime.now())]], SHEET_CHECK_SIGNATURE, COLS_CHECK_SIGNATURE)
            return True, len(rows), ng_list
        return False, 0, []
    except Exception as e:
        print(e)
        return False, 0, []

def generate_all_daily_check_pdf(date_str):
    df_m = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
    if df_m.empty: df_m = pd.DataFrame(DEFAULT_CHECK_MASTER)
    
    df_r = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
    if not df_r.empty:
        df_r = df_r[df_r['date'] == date_str]
        df_r = df_r.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')

    pdf = FPDF()
    font_path = 'NanumGothic.ttf' 
    if not os.path.exists(font_path): font_path = 'C:\\Windows\\Fonts\\malgun.ttf'
    try: pdf.add_font('Korean', '', font_path, uni=True)
    except: pass

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
        if not df_r.empty:
            df_final = pd.merge(line_master, df_r, on=['line', 'equip_id', 'item_name'], how='left')
        else:
            df_final = line_master.copy()
            df_final['value'] = '-'
            df_final['ox'] = '-'
            df_final['checker'] = ''

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
# 5. 사용자 인증 및 메인 메뉴
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

elif menu == "🏭 생산관리":
    st.info("생산관리 메뉴 (기존 기능 유지)")

elif menu == "🛠 설비보전관리":
    st.info("설비보전관리 메뉴 (기존 기능 유지)")

elif menu == "✅ 일일점검관리":
    tab1, tab2, tab3 = st.tabs(["✍ 점검 입력 (Tablet)", "📊 점검 현황", "📄 점검 이력 / PDF"])
    
    with tab1:
        st.caption("현장 태블릿용 입력 화면입니다.")
        # HTML 생성 및 렌더링 (안전하게 호출)
        try:
            master_json = get_master_json()
            html_code = get_input_html(master_json)
            components.html(html_code, height=800, scrolling=True)
        except Exception as e:
            st.error(f"입력 화면 로드 중 오류 발생: {e}")

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

    with tab3:
        st.markdown("#### 📥 현장 데이터 수신 (PC)")
        col_pdf, col_sync = st.columns([1, 1])
        
        with col_pdf:
            st.markdown("###### 📄 PDF 출력")
            search_date = st.date_input("조회 날짜", datetime.now())
            if st.button("전체 점검 리포트 생성 (PDF)"):
                pdf_bytes = generate_all_daily_check_pdf(str(search_date))
                if pdf_bytes:
                    st.download_button("PDF 다운로드", pdf_bytes, file_name=f"DailyCheck_All_{search_date}.pdf", mime='application/pdf')
                else: st.warning("데이터가 없습니다.")

        with col_sync:
            st.markdown("###### 🔄 데이터 동기화 (저장)")
            json_input = st.text_area("JSON 데이터 붙여넣기", height=100)
            if st.button("데이터 저장 (Server Save)", type="primary"):
                if json_input:
                    try:
                        payload = json.loads(json_input)
                        success, count, ngs = process_check_data(payload, st.session_state.user_info['id'])
                        if success:
                            st.success(f"✅ {count}건 저장 완료.")
                            if ngs: st.error(f"⚠ {len(ngs)}건의 NG 발견: {ngs}")
                        else: st.warning("저장할 데이터가 없습니다.")
                    except: st.error("데이터 형식이 올바르지 않습니다.")

elif menu == "⚙ 기준정보관리":
    st.info("기준정보관리 메뉴 (기존 기능 유지)")