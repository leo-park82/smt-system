import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import json
import os
import tempfile
from fpdf import FPDF

# [선택] 그리기 서명 라이브러리 (Native Fallback용)
try:
    from streamlit_drawable_canvas import st_canvas
    HAS_CANVAS = True
except ImportError:
    HAS_CANVAS = False

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

# ------------------------------------------------------------------
# 2. 구글 시트 연결
# ------------------------------------------------------------------
@st.cache_resource
def get_gs_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" not in st.secrets: return None
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        return gspread.authorize(credentials)
    except: return None

def get_worksheet(sheet_name, create_cols=None):
    client = get_gs_connection()
    if not client: return None
    try:
        sh = client.open(GOOGLE_SHEET_NAME)
    except: return None
    try:
        return sh.worksheet(sheet_name)
    except gspread.WorksheetNotFound:
        if create_cols:
            ws = sh.add_worksheet(title=sheet_name, rows=100, cols=20)
            ws.append_row(create_cols)
            return ws
        return None

@st.cache_data(ttl=5)
def load_data(sheet_name, cols=None):
    ws = get_worksheet(sheet_name, create_cols=cols)
    if not ws: return pd.DataFrame(columns=cols) if cols else pd.DataFrame()
    try:
        df = get_as_dataframe(ws, evaluate_formulas=True)
        df = df.dropna(how='all').dropna(axis=1, how='all')
        df = df.fillna("") 
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
        df = df.fillna("")
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
        safe_rows = [[str(cell) if cell is not None else "" for cell in row] for row in rows]
        ws.append_rows(safe_rows)
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
    hist = {"날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, "작성자": user, "입력시간": str(datetime.now())}
    append_data(hist, SHEET_INV_HISTORY)

def safe_float(value, default_val=None):
    try:
        if value is None or value == "" or pd.isna(value): return default_val
        return float(value)
    except: return default_val

# ==============================================================================
# [MODULE] Daily Check Management (일일점검관리)
# ==============================================================================

class DailyCheckLogic:
    @staticmethod
    def get_master_json():
        df = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
        if df.empty: return "{}"
        
        # 정렬: 라인 -> 설비 -> 항목
        df = df.sort_values(by=['line', 'equip_name', 'item_name'])
        
        config = {}
        for line, g_line in df.groupby('line'):
            equip_list = []
            for equip, g_equip in g_line.groupby('equip_name', sort=False):
                items = []
                for _, row in g_equip.iterrows():
                    items.append({
                        "name": row['item_name'], "content": row['check_content'],
                        "type": row['check_type'], "min": row['min_val'], 
                        "max": row['max_val'], "unit": row['unit'],
                        "standard": row['standard'], "equip_id": row['equip_id']
                    })
                eid = g_equip.iloc[0]['equip_id']
                equip_list.append({"equip": equip, "id": eid, "items": items})
            config[line] = equip_list
        return json.dumps(config, ensure_ascii=False)

    @staticmethod
    def process_input_data(payload, user_id):
        try:
            meta = payload.get('meta', {})
            items = payload.get('items', [])
            signature = payload.get('signature', "")
            date_str = meta.get('date')
            
            # [규칙 3] 서명 필수 검사
            if not signature or len(signature) < 50:
                return False, 0, ["서명(Signature)이 누락되었습니다. 서명을 완료해주세요."]
            
            df_master = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)
            rows = []
            ng_list = []
            
            for item in items:
                line = item.get('line') 
                equip_id = item.get('equip_id')
                item_name = item.get('item_name')
                val = str(item.get('value'))
                
                # OK/NG 판정 (Python에서 수행)
                criteria = df_master[(df_master['line'] == line) & (df_master['equip_id'] == equip_id) & (df_master['item_name'] == item_name)]
                
                ox = "OK"
                if not criteria.empty:
                    crit = criteria.iloc[0]
                    if crit['check_type'] == 'NUMBER':
                        try:
                            if not val or val == '': ox = "NG" # 빈 값 NG
                            else:
                                num = float(val)
                                min_v = safe_float(crit['min_val'], -999999)
                                max_v = safe_float(crit['max_val'], 999999)
                                if not (min_v <= num <= max_v): ox = "NG"
                        except: ox = "NG"
                    else: # OX type
                        if val == 'NG' or val == 'X': ox = "NG"
                        elif not val: ox = "NG" # 미체크 NG
                
                if ox == "NG": ng_list.append(f"{line} > {item_name}")
                rows.append([date_str, line, equip_id, item_name, val, ox, user_id, str(datetime.now())])
            
            # 기존 데이터 삭제 (Overwrite)
            df_existing = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
            if not df_existing.empty:
                df_existing['date'] = df_existing['date'].astype(str)
                df_keep = df_existing[df_existing['date'] != str(date_str)]
                
                # 새 데이터와 병합
                df_new = pd.DataFrame(rows, columns=COLS_CHECK_RESULT)
                df_final = pd.concat([df_keep, df_new], ignore_index=True)
                save_data(df_final, SHEET_CHECK_RESULT)
            else:
                append_rows(rows, SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
            
            # 서명 저장 (Append)
            sig_row = [date_str, "ALL", user_id, signature[:100]+"...", str(datetime.now())]
            append_rows([sig_row], SHEET_CHECK_SIGNATURE, COLS_CHECK_SIGNATURE)
            
            return True, len(rows), ng_list
        except Exception as e:
            return False, 0, [f"System Error: {e}"]

class DailyCheckPDF:
    @staticmethod
    def generate(date_str):
        # [규칙 4] Result 기준 라인 출력 (점검한 라인만)
        df_r = load_data(SHEET_CHECK_RESULT, COLS_CHECK_RESULT)
        if df_r.empty: return None
        
        df_r['date'] = df_r['date'].astype(str)
        df_r = df_r[df_r['date'] == date_str]
        if df_r.empty: return None
        
        df_r = df_r.sort_values('timestamp').drop_duplicates(['line', 'equip_id', 'item_name'], keep='last')
        target_lines = df_r['line'].unique() # 점검된 라인만 추출

        df_m = load_data(SHEET_CHECK_MASTER, COLS_CHECK_MASTER)

        # 폰트 다운로드
        font_path = 'NanumGothic.ttf'
        if not os.path.exists(font_path):
            try:
                url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
                urllib.request.urlretrieve(url, font_path)
            except: pass

        pdf = FPDF()
        try: pdf.add_font('Korean', '', font_path, uni=True)
        except: pass
        font_name = 'Korean' if os.path.exists(font_path) else 'Arial'

        for line in target_lines:
            pdf.add_page()
            
            # Header Design
            pdf.set_fill_color(63, 81, 181)
            pdf.rect(0, 0, 210, 25, 'F')
            pdf.set_font(font_name, '', 20)
            pdf.set_text_color(255, 255, 255)
            pdf.set_xy(10, 8)
            pdf.cell(0, 10, f"Daily Check: {line}", 0, 0, 'L')
            pdf.set_font(font_name, '', 10)
            pdf.set_xy(10, 8)
            pdf.cell(0, 10, f"Date: {date_str}", 0, 0, 'R')
            pdf.ln(20)

            # Table Header
            pdf.set_text_color(0, 0, 0)
            pdf.set_fill_color(240, 240, 240)
            headers = ["Equip", "Item", "Standard", "Value", "Res", "User"]
            widths = [40, 60, 30, 20, 15, 20]
            for i, h in enumerate(headers):
                pdf.cell(widths[i], 8, h, 1, 0, 'C', 1)
            pdf.ln()

            # Data Merge
            line_master = df_m[df_m['line'] == line]
            # Result가 있는 항목만 필터링 된 df_r 사용
            df_merged = pd.merge(line_master, df_r, on=['line', 'equip_id', 'item_name'], how='left') # Master 기준이되, Result와 조인
            
            # Result에 없는 Master 항목은 제외하고 싶다면 inner join, 
            # 미점검 항목도 보여주고 싶다면 left join. 
            # 요청사항: "점검한 것만" -> Inner Join이 맞으나, 
            # 같은 라인 내에서 일부만 점검했을 때 누락 표시를 위해 Left Join 유지하되, 전체 라인 루프를 Result 기준으로 함.
            
            df_merged = df_merged.fillna({'value':'-', 'ox':'-', 'checker':''})

            for _, row in df_merged.iterrows():
                equip = str(row['equip_name'])[:15]
                item = str(row['item_name'])
                std = str(row['standard'])
                val = str(row['value'])
                ox = str(row['ox'])
                chk = str(row['checker'])
                
                pdf.cell(40, 8, equip, 1)
                pdf.cell(60, 8, item, 1)
                pdf.cell(30, 8, std, 1)
                pdf.cell(20, 8, val, 1, 0, 'C')
                
                if ox == 'NG': pdf.set_text_color(255, 0, 0)
                elif ox == 'OK': pdf.set_text_color(0, 128, 0)
                pdf.cell(15, 8, ox, 1, 0, 'C')
                pdf.set_text_color(0, 0, 0)
                
                pdf.cell(20, 8, chk, 1, 1, 'C')

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            pdf.output(tmp.name)
            with open(tmp.name, "rb") as f: bytes_data = f.read()
        os.unlink(tmp.name)
        return bytes_data

class DailyCheckUI:
    @staticmethod
    def render_input_html_string(master_json):
        return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Daily Check</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #f8fafc; padding-bottom: 100px; }}
        .tab-btn {{ padding: 10px 15px; border-radius: 20px; background: #fff; border: 1px solid #ddd; margin-right: 5px; font-weight: bold; cursor: pointer; white-space: nowrap; }}
        .tab-btn.active {{ background: #2563eb; color: #fff; border-color: #2563eb; }}
        .btn-ox {{ width: 45%; padding: 10px; border-radius: 8px; font-weight: bold; border: 1px solid #cbd5e1; background: #fff; }}
        .btn-ox.ok.selected {{ background: #22c55e; color: white; border-color: #22c55e; }}
        .btn-ox.ng.selected {{ background: #ef4444; color: white; border-color: #ef4444; }}
    </style>
</head>
<body>
    <div class="max-w-md mx-auto p-4">
        <div class="bg-white p-4 rounded-xl shadow-sm mb-4">
            <h2 class="text-xl font-bold mb-2">✅ 일일점검 입력 (HTML)</h2>
            <div class="flex gap-2 mb-2">
                <input type="date" id="checkDate" class="border p-2 rounded w-full">
            </div>
            <div id="tabs" class="flex overflow-x-auto pb-2"></div>
        </div>

        <div id="listContainer"></div>

        <div class="bg-white p-4 rounded-xl shadow-sm mt-4 border">
            <h3 class="font-bold mb-2">✍️ 서명 (Signature)</h3>
            <canvas id="sigCanvas" class="w-full h-32 border rounded bg-slate-50 touch-none"></canvas>
            <div class="flex justify-end mt-1"><button onclick="clearSig()" class="text-sm text-red-500 font-bold">Clear</button></div>
        </div>
        
        <div class="fixed bottom-0 left-0 w-full bg-white border-t p-4 shadow-lg flex gap-2 justify-center z-50">
            <button onclick="setBatchOK()" class="bg-green-100 text-green-700 px-4 py-3 rounded-xl font-bold flex-1">일괄 OK</button>
            <button onclick="exportData()" class="bg-blue-600 text-white px-6 py-3 rounded-xl font-bold flex-1">데이터 생성</button>
        </div>
    </div>

    <!-- Modal -->
    <div id="modal" class="fixed inset-0 bg-black/50 hidden flex items-center justify-center p-4 z-[99]">
        <div class="bg-white p-6 rounded-xl w-full max-w-sm">
            <h3 class="font-bold text-lg mb-2">데이터 준비 완료</h3>
            <p class="text-sm text-gray-500 mb-2">아래 텍스트를 복사하여 Streamlit에 붙여넣으세요.</p>
            <textarea id="out" class="w-full h-32 border p-2 text-xs mb-3 font-mono" readonly></textarea>
            <button onclick="copyAndClose()" class="w-full bg-blue-600 text-white py-3 rounded-lg font-bold">복사 및 닫기</button>
            <button onclick="document.getElementById('modal').classList.add('hidden')" class="w-full mt-2 text-gray-400 text-sm">닫기</button>
        </div>
    </div>

    <script>
        const MASTER = {master_json};
        const DATA = {{}};
        let curLine = Object.keys(MASTER)[0];
        let isSignatureEmpty = true;
        
        // Canvas Setup
        const canvas = document.getElementById('sigCanvas');
        const ctx = canvas.getContext('2d');
        let isDrawing = false;
        
        function resizeCanvas() {{
            const ratio = Math.max(window.devicePixelRatio || 1, 1);
            canvas.width = canvas.offsetWidth * ratio;
            canvas.height = canvas.offsetHeight * ratio;
            ctx.scale(ratio, ratio);
        }}
        window.addEventListener('resize', resizeCanvas);
        setTimeout(resizeCanvas, 500);

        function getPos(e) {{
            const r = canvas.getBoundingClientRect();
            const x = (e.touches ? e.touches[0].clientX : e.clientX) - r.left;
            const y = (e.touches ? e.touches[0].clientY : e.clientY) - r.top;
            return {{x, y}};
        }}
        
        ['mousedown', 'touchstart'].forEach(ev => canvas.addEventListener(ev, (e) => {{ e.preventDefault(); isDrawing = true; isSignatureEmpty = false; const p = getPos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); }}));
        ['mousemove', 'touchmove'].forEach(ev => canvas.addEventListener(ev, (e) => {{ if(!isDrawing) return; e.preventDefault(); const p = getPos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); }}));
        ['mouseup', 'touchend'].forEach(ev => canvas.addEventListener(ev, () => {{ isDrawing = false; }}));
        
        function clearSig() {{ ctx.clearRect(0, 0, canvas.width, canvas.height); isSignatureEmpty = true; }}

        document.getElementById('checkDate').value = new Date().toISOString().split('T')[0];
        renderTabs();
        renderList();

        function renderTabs() {{
            const con = document.getElementById('tabs');
            con.innerHTML = Object.keys(MASTER).map(line => 
                `<div class="tab-btn ${{line === curLine ? 'active' : ''}}" onclick="switchLine('${{line}}')">${{line}}</div>`
            ).join('');
        }}

        function switchLine(line) {{ curLine = line; renderTabs(); renderList(); }}

        function renderList() {{
            const con = document.getElementById('listContainer');
            con.innerHTML = '';
            const groups = MASTER[curLine] || [];
            
            groups.forEach(g => {{
                const card = document.createElement('div');
                card.className = "bg-white p-4 rounded-xl shadow-sm mb-3 border";
                let html = `<div class="font-bold text-lg mb-2 text-slate-700">🛠 ${{g.equip}}</div>`;
                
                g.items.forEach(it => {{
                    // Key with Line to avoid conflict
                    const uid = `${{curLine}}|${{g.id}}|${{it.name}}`;
                    const val = DATA[uid] || '';
                    
                    let input = '';
                    if(it.type === 'OX') {{
                        input = `
                            <div class="flex gap-2 mt-1 justify-center">
                                <button id="btn-ok-${{uid}}" onclick="setVal('${{uid}}', 'OK', 'OX')" class="btn-ox ok ${{val==='OK'?'selected':''}}">OK</button>
                                <button id="btn-ng-${{uid}}" onclick="setVal('${{uid}}', 'NG', 'OX')" class="btn-ox ng ${{val==='NG'?'selected':''}}">NG</button>
                            </div>`;
                    }} else {{
                        input = `<input id="input-${{uid}}" type="number" class="border p-3 rounded-lg w-full mt-1 text-center font-bold text-lg bg-slate-50" 
                            placeholder="${{it.min}} ~ ${{it.max}}" value="${{val}}" onchange="setVal('${{uid}}', this.value, 'NUMBER')">`;
                    }}
                    
                    html += `
                        <div class="py-3 border-t">
                            <div class="flex justify-between items-center mb-1">
                                <span class="font-bold text-slate-800">${{it.name}}</span>
                                <span class="text-xs text-blue-500 font-bold bg-blue-50 px-2 py-1 rounded">${{it.standard}}</span>
                            </div>
                            <div class="text-xs text-gray-400 mb-1">${{it.content}}</div>
                            ${{input}}
                        </div>`;
                }});
                card.innerHTML = html;
                con.appendChild(card);
            }});
        }}
        
        // [규칙 1] DOM Direct Manipulation
        window.setVal = (uid, val, type) => {{
            DATA[uid] = val;
            if(type === 'OX') {{
                const btnOk = document.getElementById('btn-ok-' + uid);
                const btnNg = document.getElementById('btn-ng-' + uid);
                if(btnOk && btnNg) {{
                    btnOk.classList.remove('selected');
                    btnNg.classList.remove('selected');
                    if(val === 'OK') btnOk.classList.add('selected');
                    if(val === 'NG') btnNg.classList.add('selected');
                }}
            }}
        }};
        
        window.setBatchOK = () => {{
            const groups = MASTER[curLine] || [];
            groups.forEach(g => {{
                g.items.forEach(it => {{
                    if(it.type === 'OX') {{
                        const uid = `${{curLine}}|${{g.id}}|${{it.name}}`;
                        if(!DATA[uid]) setVal(uid, 'OK', 'OX');
                    }}
                }});
            }});
        }};

        window.exportData = () => {{
            // [규칙 2] Check Missing Number
            const groups = MASTER[curLine] || [];
            let missingNum = false;
            groups.forEach(g => {{
                g.items.forEach(it => {{
                    if(it.type === 'NUMBER') {{
                        const uid = `${{curLine}}|${{g.id}}|${{it.name}}`;
                        if(!DATA[uid] || DATA[uid] === '') missingNum = true;
                    }}
                }});
            }});

            if(missingNum) {{
                alert('⚠️ 수치 입력 항목에 빈 값이 있습니다. 숫자를 입력해주세요.');
                return;
            }}

            const date = document.getElementById('checkDate').value;
            const items = Object.keys(DATA).map(key => {{
                const [line, equip_id, item_name] = key.split('|');
                return {{ line, equip_id, item_name, value: DATA[key] }};
            }});
            
            const payload = {{
                meta: {{ date: date }},
                items: items,
                signature: isSignatureEmpty ? "" : canvas.toDataURL()
            }};
            
            document.getElementById('out').value = JSON.stringify(payload);
            document.getElementById('modal').classList.remove('hidden');
        }};

        window.copyAndClose = () => {{
            const el = document.getElementById('out');
            el.select();
            document.execCommand('copy');
            document.getElementById('modal').classList.add('hidden');
        }};
        
        window.switchLine = switchLine;
    </script>
</body>
</html>
        """

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
# 5. 메인 UI (Streamlit)
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

if menu == "📊 대시보드":
    df_prod = load_data(SHEET_RECORDS, COLS_RECORDS)
    df_check = DailyCheckStorage.load_result()
    today = datetime.now().strftime("%Y-%m-%d")
    
    prod_today = 0
    if not df_prod.empty:
        df_prod['날짜'] = pd.to_datetime(df_prod['날짜'], errors='coerce')
        prod_today = df_prod[df_prod['날짜'].dt.strftime("%Y-%m-%d") == today]['수량'].sum()
    
    check_cnt = len(df_check[df_check['date'] == today]) if not df_check.empty else 0
    
    c1, c2 = st.columns(2)
    c1.metric("오늘 생산량", f"{prod_today:,.0f} EA")
    c2.metric("일일점검 건수", f"{check_cnt} 건")

elif menu == "🏭 생산관리":
    st.info("기존 생산관리 기능 (이전 코드 참조)")

elif menu == "🛠 설비보전관리":
    st.info("기존 설비보전관리 기능 (이전 코드 참조)")

elif menu == "✅ 일일점검관리":
    tab1, tab2, tab3 = st.tabs(["✍ 점검 입력 (HTML)", "📊 점검 현황", "📄 점검 이력 / PDF"])
    
    with tab1:
        # [HTML UI]
        master_json = DailyCheckLogic.get_master_json()
        html_code = DailyCheckUI.render_input_html_string(master_json)
        components.html(html_code, height=800, scrolling=True)
        
        st.divider()
        st.markdown("#### 📥 데이터 저장 (PC)")
        st.caption("위 화면에서 '데이터 생성' → 복사 후 아래에 붙여넣으세요.")
        json_input = st.text_area("JSON 데이터 붙여넣기", height=100)
        
        if st.button("💾 데이터 저장", type="primary"):
            if json_input:
                try:
                    payload = json.loads(json_input)
                    success, count, ng_list = DailyCheckLogic.process_input_data(payload, st.session_state.user_info['id'])
                    if success:
                        st.success(f"✅ {count}건 저장 완료")
                        if ng_list: st.error(f"NG 항목: {ng_list}")
                    else:
                        st.error("저장 실패 (서명 누락 등)")
                except Exception as e:
                    st.error(f"데이터 오류: {e}")

    with tab2:
        st.markdown("##### 📅 일별 점검 현황")
        df_res = DailyCheckStorage.load_result()
        if not df_res.empty:
            df_res['date'] = pd.to_datetime(df_res['date']).dt.date
            st.dataframe(df_res.sort_values('timestamp', ascending=False), use_container_width=True)
        else:
            st.info("데이터가 없습니다.")

    with tab3:
        c1, c2 = st.columns([1, 2])
        search_date = c1.date_input("조회 날짜", datetime.now())
        if st.button("📄 PDF 리포트 생성"):
            pdf_bytes = DailyCheckPDF.generate(str(search_date))
            if pdf_bytes:
                st.download_button("PDF 다운로드", pdf_bytes, file_name=f"Report_{search_date}.pdf", mime='application/pdf')
            else:
                st.warning("해당 날짜에 데이터가 없습니다.")

elif menu == "⚙ 기준정보관리":
    st.info("기준정보 관리 기능")