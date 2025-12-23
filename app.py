import streamlit as st
import pandas as pd
from datetime import datetime
import json
import streamlit.components.v1 as components
from fpdf import FPDF

# 구글 시트 연동 라이브러리 (필요시 사용)
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import set_with_dataframe, get_as_dataframe

# ------------------------------------------------------------------
# 1. 기본 설정 및 데이터 정의 (Python에서 관리)
# ------------------------------------------------------------------
st.set_page_config(page_title="SMT 통합시스템", page_icon="🏭", layout="wide")

# 초기 데이터 (HTML에 있던 것을 Python으로 이동)
INITIAL_DATA = [
    {"line": "1 LINE", "equip": "IN LOADER (SML-120Y)", "name": "AIR 압력", "content": "압력 게이지 지침 확인", "standard": "0.5 MPa ± 0.1", "type": "OX", "unit": ""},
    {"line": "1 LINE", "equip": "IN LOADER (SML-120Y)", "name": "수/자동 전환", "content": "MODE 전환 스위치 작동", "standard": "정상 동작", "type": "OX", "unit": ""},
    {"line": "1 LINE", "equip": "IN LOADER (SML-120Y)", "name": "각 구동부", "content": "작동 이상음 및 소음 상태", "standard": "정상 동작", "type": "OX", "unit": ""},
    {"line": "1 LINE", "equip": "IN LOADER (SML-120Y)", "name": "매거진 상태", "content": "Locking 마모, 휨, 흔들림", "standard": "마모/휨 없을 것", "type": "OX", "unit": ""},
    
    {"line": "1 LINE", "equip": "REFLOW (1809MKⅢ)", "name": "N2 PPM", "content": "산소 농도 모니터 수치", "standard": "3000 ppm 이하", "type": "NUMBER_AND_OX", "unit": "ppm"},
    {"line": "1 LINE", "equip": "REFLOW (1809MKⅢ)", "name": "배기관 OPEN", "content": "배기 댐퍼 열림 위치", "standard": "오픈 위치", "type": "OX", "unit": ""},
    {"line": "1 LINE", "equip": "REFLOW (1809MKⅢ)", "name": "CHAIN 작동", "content": "체인 구동 시 진동/소음", "standard": "정상 구동", "type": "OX", "unit": ""},

    {"line": "2 LINE", "equip": "SCREEN PRINTER (HP-520S)", "name": "테이블 오염", "content": "이물 및 솔더 확인", "standard": "청결할 것", "type": "OX", "unit": ""},
    {"line": "2 LINE", "equip": "CHIP MOUNTER (S2)", "name": "AIR 압력", "content": "메인 공압 확인", "standard": "5 Kg/cm² ± 0.5", "type": "OX", "unit": ""},
    
    {"line": "온,습도 CHECK", "equip": "현장 온습도", "name": "실내 온도", "content": "온도 관리 기준", "standard": "24±5℃", "type": "NUMBER_AND_OX", "unit": "℃"},
    {"line": "온,습도 CHECK", "equip": "현장 온습도", "name": "실내 습도", "content": "습도 관리 기준", "standard": "40~60%", "type": "NUMBER_AND_OX", "unit": "%"},
    
    {"line": "인두기 CHECK", "equip": "수동 인두기 1호기", "name": "팁 온도", "content": "온도 측정기 확인", "standard": "370±5℃", "type": "NUMBER_AND_OX", "unit": "℃"},
    {"line": "인두기 CHECK", "equip": "수동 인두기 1호기", "name": "수분 상태", "content": "스펀지 습윤 확인", "standard": "양호", "type": "OX", "unit": ""}
]

# ------------------------------------------------------------------
# 2. HTML 템플릿 (Config 주입식)
# ------------------------------------------------------------------
DAILY_CHECK_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>SMT Daily Check</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
    <script>
        tailwind.config = {
            safelist: ['text-red-500', 'text-blue-500', 'text-green-500', 'bg-red-50', 'border-red-500', 'ring-red-200', 'bg-green-500', 'bg-red-500', 'bg-white', 'border-green-500'],
            theme: { extend: { colors: { brand: { 50: '#eff6ff', 500: '#3b82f6', 600: '#2563eb', 900: '#1e3a8a' } }, fontFamily: { sans: ['Noto Sans KR', 'sans-serif'] } } }
        }
    </script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&display=swap');
        body { font-family: 'Noto Sans KR', sans-serif; background-color: #f3f4f6; -webkit-tap-highlight-color: transparent; }
        .no-scrollbar::-webkit-scrollbar { display: none; }
        .no-scrollbar { -ms-overflow-style: none; scrollbar-width: none; }
        .animate-fade-in { animation: fadeIn 0.3s ease-out forwards; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .tab-active { background: linear-gradient(135deg, #2563eb, #1d4ed8); color: white; box-shadow: 0 4px 6px -1px rgba(37, 99, 235, 0.3); }
        .tab-inactive { background: white; color: #64748b; border: 1px solid #e2e8f0; }
        .tab-inactive:hover { background: #f8fafc; color: #3b82f6; }
        #signature-pad { touch-action: none; background: #fff; cursor: crosshair; }
        #progress-circle { transition: stroke-dashoffset 0.5s ease-out, color 0.5s ease; }
        .ox-btn { transition: all 0.2s; }
        .ox-btn.active[data-ox="OK"] { background-color: #22c55e; color: white; border-color: #22c55e; }
        .ox-btn.active[data-ox="NG"] { background-color: #ef4444; color: white; border-color: #ef4444; }
        .ox-btn:not(.active) { background-color: white; color: #334155; border-color: #e2e8f0; }
        .num-input { transition: all 0.2s; }
        .num-input.error { background-color: #fef2f2; color: #dc2626; border-color: #fecaca; animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
        input[type="date"] { position: relative; }
        input[type="date"]::-webkit-calendar-picker-indicator { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; color: transparent; background: transparent; cursor: pointer; }
    </style>
</head>
<body class="h-screen flex flex-col text-slate-800 overflow-hidden">
    <header class="bg-white shadow-sm z-20 flex-shrink-0 relative">
        <div class="px-4 sm:px-6 py-3 flex justify-between items-center bg-slate-900 text-white">
            <div class="flex items-center gap-4">
                <span class="text-2xl font-black text-white tracking-tighter" style="font-family: 'Arial Black', sans-serif;">SMT Daily Check</span>
            </div>
            <div class="flex items-center gap-2">
                <button onclick="actions.checkAllGood()" class="flex items-center bg-green-600 hover:bg-green-500 text-white rounded-lg px-3 py-1.5 border border-green-500 transition-colors shadow-sm active:scale-95 mr-2">
                    <i data-lucide="check-check" class="w-4 h-4 mr-1"></i><span class="text-sm font-bold hidden sm:inline">일괄합격</span>
                </button>
                <div class="flex items-center bg-slate-800 rounded-lg px-3 py-1.5 border border-slate-700 hover:border-blue-500 transition-colors cursor-pointer group relative">
                    <input type="date" id="inputDate" class="bg-transparent border-none text-sm text-slate-200 focus:ring-0 p-0 cursor-pointer font-mono w-24 sm:w-auto font-bold z-10" onchange="actions.handleDateChange(this.value)">
                </div>
                <button onclick="ui.openSignatureModal()" class="flex items-center bg-slate-800 hover:bg-slate-700 rounded-lg px-3 py-1.5 border border-slate-700 transition-colors" id="btn-signature">
                    <i data-lucide="pen-tool" class="w-4 h-4 text-slate-400 mr-2"></i><span class="text-sm text-slate-300 font-bold hidden sm:inline" id="sign-status">서명</span>
                </button>
            </div>
        </div>
        <div class="px-4 sm:px-6 py-3 bg-slate-50/50 border-b border-slate-100 flex justify-between items-center">
            <div class="flex-1"></div>
            <div class="flex items-center gap-3">
                <div class="flex items-center gap-4 px-4 py-1.5 bg-white rounded-xl border border-slate-200 shadow-sm">
                    <div class="text-center"><div class="text-[8px] font-bold text-slate-400 uppercase tracking-wider">Total</div><div class="text-sm font-black text-slate-700 leading-none" id="count-total">0</div></div>
                    <div class="w-px h-6 bg-slate-100"></div>
                    <div class="text-center"><div class="text-[8px] font-bold text-green-500 uppercase tracking-wider">OK</div><div class="text-sm font-black text-green-600 leading-none" id="count-ok">0</div></div>
                    <div class="w-px h-6 bg-slate-100"></div>
                    <div class="text-center"><div class="text-[8px] font-bold text-red-500 uppercase tracking-wider">NG</div><div class="text-sm font-black text-red-600 leading-none" id="count-ng">0</div></div>
                </div>
                <div class="relative w-10 h-10 flex items-center justify-center">
                    <svg class="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
                        <path class="text-slate-200" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" stroke-width="3" />
                        <path id="progress-circle" class="text-red-500 transition-all duration-700 ease-out" stroke-dasharray="100, 100" stroke-dashoffset="100" d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
                    </svg>
                    <span class="absolute text-[9px] font-bold text-slate-700" id="progress-text">0%</span>
                </div>
                <button onclick="saveAndDownloadPDF()" class="bg-slate-900 hover:bg-slate-800 text-white px-3 py-2 rounded-lg font-bold text-xs shadow-md active:scale-95 flex items-center gap-2 transition-all"><i data-lucide="download" class="w-4 h-4"></i></button>
            </div>
        </div>
        <div class="bg-white border-b border-slate-200 shadow-sm"><nav class="flex overflow-x-auto gap-2 p-3 no-scrollbar whitespace-nowrap" id="lineTabs"></nav></div>
    </header>

    <main class="flex-1 overflow-y-auto p-4 sm:p-6 bg-slate-50 relative" id="main-scroll">
        <div class="max-w-5xl mx-auto" id="checklistContainer"></div>
        <div class="h-20"></div>
    </main>

    <!-- Signature Modal -->
    <div id="signature-modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden">
            <div class="bg-slate-900 px-6 py-4 flex justify-between items-center text-white"><h3 class="font-bold text-lg flex items-center gap-2"><i data-lucide="pen-tool" class="w-5 h-5"></i> 전자 서명</h3><button onclick="ui.closeSignatureModal()" class="text-slate-400 hover:text-white"><i data-lucide="x"></i></button></div>
            <div class="p-4 bg-slate-100"><canvas id="signature-pad" class="w-full h-48 rounded-xl shadow-inner border border-slate-300 touch-none bg-white"></canvas></div>
            <div class="p-4 bg-white flex gap-3 justify-end border-t border-slate-100"><button onclick="actions.clearSignature()" class="px-4 py-2 text-slate-500 hover:bg-slate-100 rounded-lg text-sm font-bold">지우기</button><button onclick="actions.saveSignature()" class="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold shadow-lg shadow-blue-500/30">서명 완료</button></div>
        </div>
    </div>

    <!-- NumPad Modal -->
    <div id="numpad-modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[70] hidden flex items-end sm:items-center justify-center transition-opacity duration-200">
        <div class="bg-white w-full sm:w-[320px] sm:rounded-2xl rounded-t-2xl shadow-2xl overflow-hidden transform transition-transform duration-300 translate-y-full sm:translate-y-0 scale-95" id="numpad-content">
            <div class="bg-slate-900 p-4 flex justify-between items-center text-white"><span class="font-bold text-lg flex items-center gap-2"><i data-lucide="calculator" width="20"></i> 값 입력</span><button onclick="ui.closeNumPad()" class="p-1 hover:bg-slate-700 rounded transition-colors"><i data-lucide="x"></i></button></div>
            <div class="p-4 bg-slate-50"><div class="bg-white border-2 border-blue-500 rounded-xl p-4 mb-4 text-right shadow-inner h-20 flex items-center justify-end"><span id="numpad-display" class="text-3xl font-mono font-black text-slate-800 tracking-wider"></span><span class="animate-pulse text-blue-500 ml-1 text-3xl font-light">|</span></div>
            <div class="grid grid-cols-4 gap-2">
                <button onclick="numpad.key('7')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">7</button><button onclick="numpad.key('8')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">8</button><button onclick="numpad.key('9')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">9</button><button onclick="numpad.back()" class="h-14 rounded-lg bg-slate-200 border border-slate-300 shadow-sm flex items-center justify-center"><i data-lucide="delete" width="24"></i></button>
                <button onclick="numpad.key('4')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">4</button><button onclick="numpad.key('5')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">5</button><button onclick="numpad.key('6')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">6</button><button onclick="numpad.clear()" class="h-14 rounded-lg bg-red-50 border border-red-200 shadow-sm text-lg font-bold text-red-500">C</button>
                <button onclick="numpad.key('1')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">1</button><button onclick="numpad.key('2')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">2</button><button onclick="numpad.key('3')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">3</button><button onclick="numpad.key('0')" class="row-span-2 h-full rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">0</button>
                <button onclick="numpad.key('.')" class="h-14 rounded-lg bg-slate-100 border border-slate-200 shadow-sm text-xl font-bold">.</button><button onclick="numpad.key('-')" class="h-14 rounded-lg bg-slate-100 border border-slate-200 shadow-sm text-xl font-bold">+/-</button><button onclick="numpad.confirm()" class="col-span-2 h-14 rounded-lg bg-blue-600 shadow-lg text-white text-lg font-bold flex items-center justify-center gap-2">완료 <i data-lucide="check" width="20"></i></button>
            </div></div>
        </div>
    </div>
    <div id="toast-container" class="fixed bottom-20 right-6 z-50 flex flex-col gap-2"></div>

    <script>
        const DATA_PREFIX = "SMT_DATA_V3_";
        // [중요] Python에서 주입된 설정 사용
        const appConfig = __CONFIG_JSON__;

        const state = {
            config: appConfig,
            results: {},
            currentLine: Object.keys(appConfig)[0] || "",
            currentDate: "",
            signature: null,
            numpad: { targetId: null, value: "" }
        };

        const storage = {
            loadResults(date) {
                try {
                    const raw = JSON.parse(localStorage.getItem(DATA_PREFIX + date)) || {};
                    const signature = raw.signature;
                    // 마이그레이션 및 데이터 로드
                    const migrated = {};
                    Object.entries(raw).forEach(([key, val]) => {
                        if(key === 'signature') return;
                        if (val && typeof val === 'object' && 'ox' in val) migrated[key] = val;
                        else if (val === 'OK' || val === 'NG') migrated[key] = { ox: val, value: null };
                        else if (typeof val === 'string' || typeof val === 'number') {
                            if(!key.endsWith('_num')) migrated[key] = { ox: null, value: val }; 
                        }
                    });
                    // _num 접미사 처리 (구 데이터 호환)
                    Object.entries(raw).forEach(([key, val]) => {
                        if (key.endsWith('_num')) {
                            const originalKey = key.replace('_num', '');
                            if (!migrated[originalKey]) migrated[originalKey] = { ox: null, value: null };
                            migrated[originalKey].value = val;
                        }
                    });
                    migrated.signature = signature;
                    return migrated;
                } catch { return {}; }
            },
            saveResults(date, data) {
                try { localStorage.setItem(DATA_PREFIX + date, JSON.stringify(data)); } catch(e) {}
            }
        };

        const dataMgr = {
            ensure(uid) {
                if (!state.results[uid] || typeof state.results[uid] !== 'object') state.results[uid] = { ox: null, value: null };
                return state.results[uid];
            },
            setOX(uid, ox) { this.ensure(uid).ox = ox; },
            setValue(uid, val) { this.ensure(uid).value = val; },
            getOX(uid) { return state.results[uid]?.ox || null; },
            getValue(uid) { return state.results[uid]?.value || null; }
        };

        const utils = {
            qs: (selector) => document.querySelector(selector),
            qsa: (selector) => document.querySelectorAll(selector),
            validateStandard(v, s) {
                if (!v) return true;
                const val = parseFloat(v.replace(/[^0-9.-]/g, ''));
                if (isNaN(val)) return true;
                if (s.includes('±')) {
                    const p = s.split('±');
                    return val >= parseFloat(p[0]) - parseFloat(p[1]) && val <= parseFloat(p[0]) + parseFloat(p[1]);
                }
                if (s.includes('이하')) return val <= parseFloat(s);
                if (s.includes('이상')) return val >= parseFloat(s);
                if (s.includes('~')) {
                    const p = s.split('~');
                    return val >= parseFloat(p[0]) && val <= parseFloat(p[1]);
                }
                return true;
            },
            isValueValid(uid, item) {
                const val = dataMgr.getValue(uid);
                if (val === null || val === "" || isNaN(parseFloat(val))) return false;
                return this.validateStandard(val, item.standard);
            },
            calculateSummary() {
                let total = 0, ok = 0, ng = 0;
                Object.keys(state.config).forEach(lineName => {
                    state.config[lineName].forEach((eq, ei) => {
                        eq.items.forEach((it, ii) => {
                            total++;
                            const uid = `${lineName}-${ei}-${ii}`;
                            const ox = dataMgr.getOX(uid);
                            if (ox === 'OK') ok++;
                            if (ox === 'NG') ng++;
                        });
                    });
                });
                return { total, ok, ng };
            }
        };

        const ui = {
            renderTabs() {
                const container = utils.qs('#lineTabs');
                if (!container) return;
                container.innerHTML = '';
                Object.keys(state.config).forEach(l => {
                    const b = document.createElement('button');
                    b.className = `px-5 py-2 rounded-full text-sm font-bold whitespace-nowrap transition-all transform active:scale-95 ${l === state.currentLine ? 'tab-active' : 'tab-inactive'}`;
                    b.innerText = l;
                    b.onclick = () => { state.currentLine = l; ui.renderTabs(); ui.renderChecklist(); };
                    container.appendChild(b);
                });
            },
            renderChecklist() {
                const container = utils.qs('#checklistContainer');
                container.innerHTML = '';
                const equipments = state.config[state.currentLine] || [];
                
                equipments.forEach((eq, ei) => {
                    const card = document.createElement('div');
                    card.className = "bg-white rounded-2xl shadow-sm border border-slate-100 mb-6 overflow-hidden animate-fade-in";
                    card.innerHTML = `<div class="bg-slate-50/50 px-6 py-4 border-b border-slate-100 flex justify-between items-center"><h3 class="font-bold text-lg text-slate-800">${eq.equip}</h3></div>`;
                    const list = document.createElement('div');
                    list.className = "divide-y divide-slate-50";
                    eq.items.forEach((it, ii) => {
                        const uid = `${state.currentLine}-${ei}-${ii}`;
                        const controlHtml = renderControl.render(it, uid);
                        const row = document.createElement('div');
                        row.className = "p-5 hover:bg-blue-50/30 transition-colors";
                        row.innerHTML = `<div class="flex justify-between items-center gap-4"><div class="flex-1"><div class="font-bold text-slate-700">${it.name} <span class="text-xs text-blue-500 bg-blue-50 px-1 rounded">${it.standard}</span></div><div class="text-sm text-slate-500">${it.content}</div></div>${controlHtml}</div>`;
                        list.appendChild(row);
                    });
                    card.appendChild(list); container.appendChild(card);
                });
                lucide.createIcons();
            },
            updateSummary() {
                const { total, ok, ng } = utils.calculateSummary();
                utils.qs('#count-total').innerText = total;
                utils.qs('#count-ok').innerText = ok;
                utils.qs('#count-ng').innerText = ng;
                const percent = total === 0 ? 0 : Math.round(((ok + ng) / total) * 100);
                utils.qs('#progress-text').innerText = `${percent}%`;
                utils.qs('#progress-circle').style.strokeDashoffset = 100 - percent;
            },
            updateOXUI(uid) {
                const ox = dataMgr.getOX(uid);
                utils.qsa(`.ox-btn[data-uid="${uid}"]`).forEach(btn => {
                    const isSelected = btn.dataset.ox === ox;
                    if (isSelected) btn.classList.add('active'); else btn.classList.remove('active');
                });
            },
            updateNumUI(uid, value) {
                const input = utils.qs(`.num-input[data-uid="${uid}"]`);
                if(input) {
                    input.value = value;
                    const [l, ei, ii] = uid.split('-');
                    const item = state.config[l][ei].items[ii];
                    const isValid = utils.validateStandard(value, item.standard);
                    if(isValid) { input.classList.remove('bg-red-50', 'text-red-600', 'error'); input.classList.add('bg-slate-50'); }
                    else { input.classList.remove('bg-slate-50'); input.classList.add('bg-red-50', 'text-red-600', 'error'); }
                }
            },
            updateSignatureStatus() {
                const btn = utils.qs('#btn-signature');
                const status = utils.qs('#sign-status');
                if (state.signature) {
                    status.innerText = "서명 완료"; status.className = "text-green-400 font-bold"; btn.classList.add('border-green-500');
                } else {
                    status.innerText = "서명"; status.className = "text-slate-300"; btn.classList.remove('border-green-500');
                }
            },
            showToast(message, type = "normal") {
                const container = utils.qs('#toast-container');
                const toast = document.createElement('div');
                let bgClass = "bg-slate-800", icon = "info";
                if (type === "success") { bgClass = "bg-green-600"; icon = "check-circle"; }
                if (type === "error") { bgClass = "bg-red-600"; icon = "alert-circle"; }
                toast.className = `${bgClass} text-white px-4 py-3 rounded-lg shadow-lg transform transition-all duration-300 translate-y-10 opacity-0 flex items-center gap-3 min-w-[200px]`;
                toast.innerHTML = `<i data-lucide="${icon}" class="w-5 h-5"></i><span class="font-bold text-sm">${message}</span>`;
                container.appendChild(toast);
                lucide.createIcons();
                requestAnimationFrame(() => toast.classList.remove('translate-y-10', 'opacity-0'));
                setTimeout(() => { toast.classList.add('translate-y-10', 'opacity-0'); setTimeout(() => container.removeChild(toast), 300); }, 3000);
            },
            openNumPad(targetId) {
                state.numpad.targetId = targetId;
                state.numpad.value = (dataMgr.getValue(targetId) || "").toString();
                utils.qs('#numpad-display').innerText = state.numpad.value;
                utils.qs('#numpad-modal').classList.remove('hidden');
                setTimeout(() => utils.qs('#numpad-content').classList.remove('translate-y-full', 'scale-95'), 10);
            },
            closeNumPad() {
                utils.qs('#numpad-content').classList.add('translate-y-full', 'scale-95');
                setTimeout(() => utils.qs('#numpad-modal').classList.add('hidden'), 200);
            },
            openSignatureModal() { utils.qs('#signature-modal').classList.remove('hidden'); actions.resizeCanvas(); },
            closeSignatureModal() { utils.qs('#signature-modal').classList.add('hidden'); }
        };

        const renderControl = {
            OX(uid) {
                const ox = dataMgr.getOX(uid);
                const activeClass = (type) => ox === type ? 'active' : '';
                return `<div class="flex gap-2"><button class="ox-btn px-4 py-2 rounded-lg font-bold text-xs border ${activeClass('OK')}" data-uid="${uid}" data-ox="OK">OK</button><button class="ox-btn px-4 py-2 rounded-lg font-bold text-xs border ${activeClass('NG')}" data-uid="${uid}" data-ox="NG">NG</button></div>`;
            },
            NUMBER_AND_OX(uid, item) {
                const val = dataMgr.getValue(uid);
                const ox = dataMgr.getOX(uid);
                const activeClass = (type) => ox === type ? 'active' : '';
                const isValid = utils.validateStandard(val, item.standard);
                const inputClass = isValid ? 'bg-slate-50' : 'bg-red-50 text-red-600 error';
                return `<div class="flex items-center gap-2"><input type="text" readonly value="${val || ''}" class="num-input w-20 py-2 border rounded-lg text-center font-bold ${inputClass}" data-uid="${uid}"><div class="flex gap-2"><button class="ox-btn px-3 py-2 rounded-lg font-bold text-xs border ${activeClass('OK')}" data-uid="${uid}" data-ox="OK">O</button><button class="ox-btn px-3 py-2 rounded-lg font-bold text-xs border ${activeClass('NG')}" data-uid="${uid}" data-ox="NG">X</button></div></div>`;
            },
            render(item, uid) {
                if (item.type === 'OX') return this.OX(uid);
                if (item.type === 'NUMBER_AND_OX') return this.NUMBER_AND_OX(uid, item);
                return '';
            }
        };

        const actions = {
            init() {
                const today = new Date().toISOString().split('T')[0];
                utils.qs('#inputDate').value = today;
                actions.handleDateChange(today);
                ui.renderTabs();
                actions.initSignaturePad();
                actions.setupDelegation();
            },
            setupDelegation() {
                document.addEventListener('click', (e) => {
                    if (e.target.classList.contains('ox-btn')) {
                        const uid = e.target.dataset.uid;
                        const ox = e.target.dataset.ox;
                        const [l, ei, ii] = uid.split('-');
                        const item = state.config[l][ei].items[ii];
                        if (item.type === 'NUMBER_AND_OX' && ox === 'OK') {
                            if (!utils.isValueValid(uid, item)) { alert('수치를 정상적으로 입력해야 OK 체크가 가능합니다.'); return; }
                        }
                        dataMgr.setOX(uid, ox);
                        ui.updateOXUI(uid);
                        actions.saveOnly();
                        ui.updateSummary();
                    }
                    if (e.target.classList.contains('num-input')) { ui.openNumPad(e.target.dataset.uid); }
                });
            },
            handleDateChange(date) {
                state.currentDate = date;
                state.results = storage.loadResults(date);
                state.signature = state.results.signature || null;
                ui.updateSignatureStatus();
                ui.renderChecklist();
                ui.updateSummary();
            },
            checkAllGood() {
                const line = state.currentLine;
                state.config[line].forEach((eq, ei) => {
                    eq.items.forEach((item, ii) => {
                        const uid = `${line}-${ei}-${ii}`;
                        if (item.type === 'NUMBER_AND_OX' && !utils.isValueValid(uid, item)) return;
                        dataMgr.setOX(uid, 'OK');
                        ui.updateOXUI(uid);
                    });
                });
                actions.saveOnly();
                ui.updateSummary();
                ui.showToast("일괄 합격 (미달 제외)", "success");
            },
            saveOnly() {
                if (state.signature) state.results.signature = state.signature;
                storage.saveResults(state.currentDate, state.results);
            },
            // Signature & Numpad same as before...
            cvs: null, ctx: null, drawing: false,
            initSignaturePad() {
                this.cvs = document.getElementById('signature-pad'); this.ctx = this.cvs.getContext('2d'); actions.resizeCanvas();
                const start = (e) => { e.preventDefault(); const r=this.cvs.getBoundingClientRect(); const x=e.touches?e.touches[0].clientX:e.clientX; const y=e.touches?e.touches[0].clientY:e.clientY; this.ctx.moveTo(x-r.left,y-r.top); this.ctx.beginPath(); this.drawing=true; };
                const move = (e) => { e.preventDefault(); if(!this.drawing)return; const r=this.cvs.getBoundingClientRect(); const x=e.touches?e.touches[0].clientX:e.clientX; const y=e.touches?e.touches[0].clientY:e.clientY; this.ctx.lineTo(x-r.left,y-r.top); this.ctx.stroke(); };
                const end = () => this.drawing=false;
                this.cvs.addEventListener('touchstart',start,{passive:false}); this.cvs.addEventListener('touchmove',move,{passive:false}); this.cvs.addEventListener('touchend',end);
                this.cvs.addEventListener('mousedown',start); this.cvs.addEventListener('mousemove',move); this.cvs.addEventListener('mouseup',end);
            },
            resizeCanvas() { this.cvs.width=this.cvs.offsetWidth; this.cvs.height=this.cvs.offsetHeight; },
            clearSignature() { this.ctx.clearRect(0,0,this.cvs.width,this.cvs.height); },
            saveSignature() { state.signature = this.cvs.toDataURL(); actions.saveOnly(); ui.updateSignatureStatus(); ui.closeSignatureModal(); }
        };

        const numpad = {
            key(k) {
                if(k==='-') state.numpad.value=state.numpad.value.startsWith('-')?state.numpad.value.substring(1):'-'+state.numpad.value;
                else if(k!=='.'||!state.numpad.value.includes('.')) state.numpad.value+=k;
                utils.qs('#numpad-display').innerText=state.numpad.value;
            },
            back() { state.numpad.value=state.numpad.value.slice(0,-1); utils.qs('#numpad-display').innerText=state.numpad.value; },
            clear() { state.numpad.value=""; utils.qs('#numpad-display').innerText=state.numpad.value; },
            confirm() {
                const { targetId, value } = state.numpad;
                dataMgr.setValue(targetId, value);
                const [l, ei, ii] = targetId.split('-');
                const item = state.config[l][ei].items[ii];
                if (utils.validateStandard(value, item.standard)) dataMgr.setOX(targetId, 'OK');
                else { dataMgr.setOX(targetId, null); alert('입력 수치가 기준을 벗어났습니다.'); }
                ui.updateOXUI(targetId);
                actions.saveOnly();
                ui.updateNumUI(targetId, value);
                ui.closeNumPad();
                ui.updateSummary();
            }
        };

        window.saveAndDownloadPDF = async function() {
            if (!state.signature) { alert('⚠️ 서명이 완료되지 않았습니다.'); return; }
            const d = utils.qs('#inputDate').value;
            const { jsPDF } = window.jspdf;
            const container = document.createElement('div');
            Object.assign(container.style, { width: '794px', position: 'absolute', left: '-9999px', background: 'white' });
            document.body.appendChild(container);
            try {
                // PDF Gen Logic Simplified for Brevity
                const page = document.createElement('div');
                Object.assign(page.style, { width:'794px', height:'1123px', padding:'40px', background:'white' });
                page.innerHTML = `<h1 style='border-bottom:2px solid #333; padding-bottom:10px; margin-bottom:20px; font-size:24px; font-weight:bold;'>SMT Daily Check (${d})</h1>`;
                
                Object.keys(state.config).forEach(line => {
                    state.config[line].forEach((eq, ei) => {
                        const card = document.createElement('div');
                        card.style.cssText = "border:1px solid #ccc; margin-bottom:15px; border-radius:8px; overflow:hidden;";
                        let html = `<div style='background:#f9fafb; padding:10px; font-weight:bold;'>${eq.equip}</div><table style='width:100%; border-collapse:collapse; font-size:12px;'>`;
                        eq.items.forEach((it, ii) => {
                            const uid = `${line}-${ei}-${ii}`;
                            const ox = dataMgr.getOX(uid) || '-';
                            const val = dataMgr.getValue(uid) || '';
                            const color = ox==='OK'?'green':ox==='NG'?'red':'gray';
                            html += `<tr style='border-top:1px solid #eee;'><td style='padding:8px;'>${it.name}</td><td style='padding:8px;'>${it.standard}</td><td style='padding:8px; text-align:right; font-weight:bold; color:${color};'>${val} ${ox}</td></tr>`;
                        });
                        html += "</table>";
                        card.innerHTML = html;
                        page.appendChild(card);
                    });
                });
                
                if(state.signature) page.innerHTML += `<div style='text-align:right; margin-top:20px;'><img src='${state.signature}' style='height:50px;'></div>`;
                container.appendChild(page);
                
                const canvas = await html2canvas(page, { scale: 2 });
                const pdf = new jsPDF('p', 'mm', 'a4');
                pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, 210, 297);
                pdf.save(`SMT_Check_${d}.pdf`);
                ui.showToast("PDF 완료", "success");
            } catch(e) { console.error(e); ui.showToast("오류", "error"); } 
            finally { document.body.removeChild(container); }
        };

        document.addEventListener('DOMContentLoaded', actions.init);
    </script>
</body>
</html>
"""

# ------------------------------------------------------------------
# 3. Helper Functions (DataFrame <-> JSON 변환)
# ------------------------------------------------------------------
def get_config_df():
    # 저장된 설정이 있으면 로드, 없으면 기본값 사용
    if "check_config_df" not in st.session_state:
        st.session_state.check_config_df = pd.DataFrame(INITIAL_DATA)
    return st.session_state.check_config_df

def convert_df_to_nested_json(df):
    """Pandas DataFrame을 HTML/JS에서 사용하는 중첩 JSON 구조로 변환"""
    nested_config = {}
    
    # 라인 순서 보장 및 그룹화
    lines = df['line'].unique()
    for line in lines:
        nested_config[line] = []
        line_data = df[df['line'] == line]
        
        # 설비별 그룹화
        equips = line_data['equip'].unique()
        for equip in equips:
            equip_items = line_data[line_data['equip'] == equip]
            items_list = []
            for _, row in equip_items.iterrows():
                items_list.append({
                    "name": row['name'],
                    "content": row['content'],
                    "standard": row['standard'],
                    "type": row['type'],
                    "unit": row['unit']
                })
            nested_config[line].append({
                "equip": equip,
                "items": items_list
            })
            
    return json.dumps(nested_config, ensure_ascii=False)

# 로그인 등 기존 로직 유지 (간소화를 위해 생략된 부분은 기존 코드 유지 필요)
# ... (check_password, init_sheets 등) ...
if 'logged_in' not in st.session_state: st.session_state.logged_in = True
if 'user_info' not in st.session_state: st.session_state.user_info = {"role": "admin", "name": "Manager"}
CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")

# ------------------------------------------------------------------
# 4. 메인 UI 및 메뉴
# ------------------------------------------------------------------
with st.sidebar:
    st.markdown("<h2 style='text-align:center;'>Cloud SMT</h2>", unsafe_allow_html=True)
    menu = st.radio("Navigation", ["🏭 생산관리", "🛠️ 설비보전관리", "📱 일일점검"])

# ... (생산관리, 설비보전관리 탭은 기존 코드 유지) ...

if menu == "📱 일일점검":
    st.markdown("##### 👆 태블릿 터치용 일일점검 시스템")
    
    # [관리자 전용] 설정 메뉴 승격
    if IS_ADMIN:
        with st.expander("🛠️ [관리자] 점검 항목 설정 (Excel 스타일 편집)", expanded=False):
            st.info("💡 여기서 항목을 수정하면 아래 점검표에 즉시 반영됩니다.")
            df_config = get_config_df()
            
            edited_df = st.data_editor(
                df_config,
                num_rows="dynamic",
                use_container_width=True,
                column_config={
                    "type": st.column_config.SelectboxColumn(
                        "입력 방식",
                        options=["OX", "NUMBER", "NUMBER_AND_OX"],
                        required=True
                    )
                }
            )
            
            if st.button("설정 저장 및 적용", type="primary"):
                st.session_state.check_config_df = edited_df
                st.success("설정이 저장되었습니다. 아래 점검표가 갱신됩니다.")
                time.sleep(0.5)
                st.rerun()
    
    # 설정 데이터를 JSON으로 변환하여 HTML에 주입
    config_df = get_config_df()
    config_json = convert_df_to_nested_json(config_df)
    
    # HTML 템플릿 내의 __CONFIG_JSON__ 치환
    final_html = DAILY_CHECK_HTML_TEMPLATE.replace('__CONFIG_JSON__', config_json)
    
    components.html(final_html, height=1200, scrolling=True)