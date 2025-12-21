import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import base64
import os
from fpdf import FPDF
import streamlit.components.v1 as components

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
# [핵심] SMT 일일점검표 HTML 코드 (그대로 내장)
# ------------------------------------------------------------------
DAILY_CHECK_HTML = """
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
            safelist: ['text-red-500', 'text-blue-500', 'text-green-500', 'bg-red-50', 'border-red-500', 'ring-red-200'],
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
        .tab-ng { background: linear-gradient(135deg, #ef4444, #b91c1c); color: white; box-shadow: 0 4px 6px -1px rgba(239, 68, 68, 0.3); }
        #signature-pad { touch-action: none; background: #fff; cursor: crosshair; }
        #progress-circle { transition: stroke-dashoffset 0.5s ease-out, color 0.5s ease; }
        input[type="date"] { position: relative; }
        input[type="date"]::-webkit-calendar-picker-indicator { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; color: transparent; background: transparent; cursor: pointer; }
        .calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; }
        .calendar-day { aspect-ratio: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; border-radius: 8px; font-size: 0.8rem; font-weight: bold; position: relative; border: 1px solid transparent; }
        .calendar-day:hover { background-color: #f1f5f9; }
        .calendar-day.today { border-color: #3b82f6; color: #3b82f6; }
        .calendar-day.active { background-color: #eff6ff; color: #1d4ed8; }
        .dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 4px; }
        .dot-green { background-color: #22c55e; }
        .dot-red { background-color: #ef4444; }
        .dot-gray { background-color: #cbd5e1; }
    </style>
</head>
<body class="h-screen flex flex-col text-slate-800 overflow-hidden bg-white">
    <!-- Header -->
    <header class="bg-white shadow-sm z-20 flex-shrink-0 relative">
        <div class="px-4 sm:px-6 py-3 flex justify-between items-center bg-slate-900 text-white">
            <div class="flex items-center gap-4">
                <span class="text-xl font-black text-white tracking-tighter" style="font-family: 'Arial Black', sans-serif;">CIMON</span>
                <div class="h-6 w-px bg-slate-700 hidden sm:block"></div>
                <h1 class="font-bold text-base tracking-tight hidden sm:block">SMT Daily Check</h1>
            </div>
            <div class="flex items-center gap-2">
                <div class="flex items-center bg-slate-800 rounded-lg px-3 py-1.5 border border-slate-700 hover:border-blue-500 transition-colors cursor-pointer group relative">
                    <button onclick="openCalendarModal()" class="mr-2 text-blue-400 hover:text-white transition-colors"><i data-lucide="calendar-days" class="w-5 h-5"></i></button>
                    <input type="date" id="inputDate" class="bg-transparent border-none text-sm text-slate-200 focus:ring-0 p-0 cursor-pointer font-mono w-24 sm:w-auto font-bold z-10" onclick="this.showPicker()">
                </div>
                <button onclick="openSignatureModal()" class="flex items-center bg-slate-800 hover:bg-slate-700 rounded-lg px-3 py-1.5 border border-slate-700 transition-colors" id="btn-signature">
                    <i data-lucide="pen-tool" class="w-4 h-4 text-slate-400 mr-2"></i><span class="text-sm text-slate-300 font-bold hidden sm:inline" id="sign-status">서명</span>
                </button>
                <button onclick="openSettings()" class="p-2 hover:bg-slate-700 rounded-full transition-colors text-slate-300 hover:text-white"><i data-lucide="settings" class="w-5 h-5"></i></button>
            </div>
        </div>
        <div class="px-4 sm:px-6 py-3 bg-slate-50/50 border-b border-slate-100 flex justify-between items-center">
             <div id="edit-mode-indicator" class="hidden px-3 py-1 bg-amber-100 text-amber-700 text-xs font-bold rounded-full border border-amber-200 animate-pulse flex items-center gap-1"><i data-lucide="wrench" size="12"></i> 편집 모드 ON</div>
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
    <div class="fixed bottom-6 right-6 z-30" id="fab-container">
        <button onclick="checkAllGood()" class="group bg-green-500 hover:bg-green-600 text-white p-4 rounded-full shadow-xl shadow-green-500/30 flex items-center justify-center transition-all hover:scale-110 active:scale-90">
            <i data-lucide="check-check" class="w-6 h-6"></i>
        </button>
    </div>
    <input type="file" id="cameraInput" accept="image/*" capture="environment" class="hidden" onchange="processImageUpload(this)">
    <div id="calendar-modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden transform transition-all scale-95 opacity-0" id="calendar-content">
            <div class="bg-slate-900 px-6 py-4 flex justify-between items-center text-white"><h3 class="font-bold text-lg flex items-center gap-2"><i data-lucide="calendar-days" class="w-5 h-5"></i> 월간 현황</h3><button onclick="closeCalendarModal()" class="text-slate-400 hover:text-white"><i data-lucide="x"></i></button></div>
            <div class="p-6 bg-white"><div class="flex justify-between items-center mb-6"><button onclick="changeMonth(-1)" class="p-2 hover:bg-slate-100 rounded-full"><i data-lucide="chevron-left" class="w-5 h-5"></i></button><span class="text-lg font-bold text-slate-800" id="calendar-title">2023년 10월</span><button onclick="changeMonth(1)" class="p-2 hover:bg-slate-100 rounded-full"><i data-lucide="chevron-right" class="w-5 h-5"></i></button></div><div class="grid grid-cols-7 gap-1 mb-2 text-center text-xs font-bold text-slate-400"><div>일</div><div>월</div><div>화</div><div>수</div><div>목</div><div>금</div><div>토</div></div><div id="calendar-grid" class="calendar-grid"></div></div>
        </div>
    </div>
    <div id="settings-modal" class="fixed inset-0 bg-black/50 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white w-full max-w-md rounded-2xl shadow-2xl overflow-hidden transform transition-all scale-95 opacity-0" id="settings-content">
            <div class="bg-slate-900 px-6 py-4 flex justify-between items-center text-white"><h3 class="font-bold text-lg flex items-center gap-2"><i data-lucide="settings" class="w-5 h-5"></i> 설정</h3><button onclick="closeSettings()" class="hover:text-slate-300"><i data-lucide="x" class="w-5 h-5"></i></button></div>
            <div class="p-6 space-y-6"><div class="flex justify-between items-center p-4 bg-amber-50 border border-amber-200 rounded-xl"><div><div class="font-bold text-amber-900">점검 항목 편집 모드</div></div><label class="relative inline-flex items-center cursor-pointer"><input type="checkbox" id="toggleEditMode" class="sr-only peer" onchange="toggleEditMode(this.checked)"><div class="w-11 h-6 bg-gray-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div></label></div><button onclick="resetCurrentData()" class="w-full py-3 border border-red-200 text-red-600 hover:bg-red-50 rounded-xl text-sm font-bold flex items-center justify-center gap-2"><i data-lucide="trash-2" class="w-4 h-4"></i> 데이터 초기화</button></div>
        </div>
    </div>
    <div id="signature-modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden">
            <div class="bg-slate-900 px-6 py-4 flex justify-between items-center text-white"><h3 class="font-bold text-lg flex items-center gap-2"><i data-lucide="pen-tool" class="w-5 h-5"></i> 전자 서명</h3><button onclick="closeSignatureModal()" class="text-slate-400 hover:text-white"><i data-lucide="x"></i></button></div>
            <div class="p-4 bg-slate-100"><canvas id="signature-pad" class="w-full h-48 rounded-xl shadow-inner border border-slate-300 touch-none bg-white"></canvas></div>
            <div class="p-4 bg-white flex gap-3 justify-end border-t border-slate-100"><button onclick="clearSignature()" class="px-4 py-2 text-slate-500 hover:bg-slate-100 rounded-lg text-sm font-bold">지우기</button><button onclick="saveSignature()" class="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold shadow-lg shadow-blue-500/30">서명 완료</button></div>
        </div>
    </div>
    <div id="numpad-modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-[70] hidden flex items-end sm:items-center justify-center transition-opacity duration-200">
        <div class="bg-white w-full sm:w-[320px] sm:rounded-2xl rounded-t-2xl shadow-2xl overflow-hidden transform transition-transform duration-300 translate-y-full sm:translate-y-0 scale-95" id="numpad-content">
            <div class="bg-slate-900 p-4 flex justify-between items-center text-white"><span class="font-bold text-lg flex items-center gap-2"><i data-lucide="calculator" width="20"></i> 값 입력</span><button onclick="closeNumPad()" class="p-1 hover:bg-slate-700 rounded transition-colors"><i data-lucide="x"></i></button></div>
            <div class="p-4 bg-slate-50"><div class="bg-white border-2 border-blue-500 rounded-xl p-4 mb-4 text-right shadow-inner h-20 flex items-center justify-end"><span id="numpad-display" class="text-3xl font-mono font-black text-slate-800 tracking-wider"></span><span class="animate-pulse text-blue-500 ml-1 text-3xl font-light">|</span></div><div class="grid grid-cols-4 gap-2"><button onclick="npKey('7')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">7</button><button onclick="npKey('8')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">8</button><button onclick="npKey('9')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">9</button><button onclick="npBack()" class="h-14 rounded-lg bg-slate-200 border border-slate-300 shadow-sm flex items-center justify-center"><i data-lucide="delete" width="24"></i></button><button onclick="npKey('4')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">4</button><button onclick="npKey('5')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">5</button><button onclick="npKey('6')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">6</button><button onclick="npClear()" class="h-14 rounded-lg bg-red-50 border border-red-200 shadow-sm text-lg font-bold text-red-500">C</button><button onclick="npKey('1')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">1</button><button onclick="npKey('2')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">2</button><button onclick="npKey('3')" class="h-14 rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">3</button><button onclick="npKey('0')" class="row-span-2 h-full rounded-lg bg-white border border-slate-200 shadow-sm text-xl font-bold">0</button><button onclick="npKey('.')" class="h-14 rounded-lg bg-slate-100 border border-slate-200 shadow-sm text-xl font-bold">.</button><button onclick="npKey('-')" class="h-14 rounded-lg bg-slate-100 border border-slate-200 shadow-sm text-xl font-bold">+/-</button><button onclick="npConfirm()" class="col-span-2 h-14 rounded-lg bg-blue-600 shadow-lg text-white text-lg font-bold flex items-center justify-center gap-2">완료 <i data-lucide="check" width="20"></i></button></div></div>
        </div>
    </div>
    <div id="toast-container" class="fixed bottom-20 right-6 z-50 flex flex-col gap-2"></div>
    <script>
        const DATA_PREFIX="SMT_DATA_V3_",CONFIG_KEY="SMT_CONFIG_V6.1_SYNTAX_FIXED";
        const defaultLineData={"1 LINE":[{"equip":"IN LOADER (SML-120Y)","items":[{"name":"AIR 압력","content":"압력 게이지 지침 확인","standard":"0.5 MPa ± 0.1","type":"OX"}]},{"equip":"SCREEN PRINTER (HP-520S)","items":[{"name":"AIR 압력","content":"압력 게이지 지침 확인","standard":"0.5 MPa ± 0.1","type":"OX"}]},{"equip":"CHIP MOUNTER (S2)","items":[{"name":"AIR 압력","content":"메인 공압 게이지 확인","standard":"5 Kg/cm² ± 0.5","type":"OX"}]},{"equip":"REFLOW (1809MKⅢ)","items":[{"name":"N2 PPM","content":"산소 농도 모니터 수치","standard":"3000 ppm 이하","type":"NUMBER_AND_OX","unit":"ppm"}]}],"2 LINE":[{"equip":"IN LOADER (SML-120Y)","items":[{"name":"AIR 압력","content":"게이지 지침 확인","standard":"0.5 MPa ± 0.1","type":"OX"}]}]};
        let appConfig={},checkResults={},currentLine="1 LINE",isEditMode=false,signatureData=null,currentDate="",currentMonth=new Date(),activePhotoId=null;
        document.addEventListener('DOMContentLoaded',()=>{initApp()});
        function initApp(){
            const t=new Date().toISOString().split('T')[0];document.getElementById('inputDate').value=t;
            try{const c=localStorage.getItem(CONFIG_KEY);appConfig=c?JSON.parse(c):JSON.parse(JSON.stringify(defaultLineData));}catch(e){appConfig=JSON.parse(JSON.stringify(defaultLineData));}
            handleDateChange(t);document.getElementById('inputDate').addEventListener('change',e=>handleDateChange(e.target.value));
            if(typeof lucide!=='undefined')lucide.createIcons();renderTabs();initSignaturePad();
        }
        function handleDateChange(d){currentDate=d;const k=DATA_PREFIX+d;let s=null;try{s=localStorage.getItem(k)}catch(e){}if(s){try{checkResults=JSON.parse(s);signatureData=checkResults.signature||null}catch(e){checkResults={};signatureData=null}}else{checkResults={};signatureData=null}updateSignatureStatus();renderChecklist();updateSummary();}
        function saveData(){if(signatureData)checkResults.signature=signatureData;try{localStorage.setItem(DATA_PREFIX+currentDate,JSON.stringify(checkResults))}catch(e){}updateSummary();}
        function renderTabs(){const n=document.getElementById('lineTabs');if(!n)return;n.innerHTML='';Object.keys(appConfig).forEach(l=>{const b=document.createElement('button');b.className=`px-5 py-2 rounded-full text-sm font-bold whitespace-nowrap transition-all transform active:scale-95 ${l===currentLine?'tab-active':'tab-inactive'}`;b.innerText=l;b.onclick=()=>{currentLine=l;renderTabs();renderChecklist();};n.appendChild(b);});}
        function validateStandard(v,s){if(!v)return true;const val=parseFloat(v.replace(/[^0-9.-]/g,''));if(isNaN(val))return true;if(s.includes('±')){const p=s.split('±');return val>=parseFloat(p[0])-parseFloat(p[1])&&val<=parseFloat(p[0])+parseFloat(p[1]);}if(s.includes('이하'))return val<=parseFloat(s);if(s.includes('이상'))return val>=parseFloat(s);return true;}
        function getIconForEquip(n){return `<i data-lucide="monitor" size="20"></i>`;}
        let npTargetId=null,npType=null,npValue="";
        function openNumPad(i,t){npTargetId=i;npType=t;npValue=(checkResults[t==='num_suffix'?i+'_num':i]||"").toString();document.getElementById('numpad-display').innerText=npValue;document.getElementById('numpad-modal').classList.remove('hidden');setTimeout(()=>document.getElementById('numpad-content').classList.remove('translate-y-full','scale-95'),10);}
        function closeNumPad(){document.getElementById('numpad-content').classList.add('translate-y-full','scale-95');setTimeout(()=>document.getElementById('numpad-modal').classList.add('hidden'),200);}
        function npKey(k){if(k==='-'){npValue=npValue.startsWith('-')?npValue.substring(1):'-'+npValue}else if(k!=='.'||!npValue.includes('.'))npValue+=k;document.getElementById('numpad-display').innerText=npValue;}
        function npBack(){npValue=npValue.slice(0,-1);document.getElementById('numpad-display').innerText=npValue;}
        function npClear(){npValue="";document.getElementById('numpad-display').innerText=npValue;}
        function npConfirm(){if(npType==='num_suffix')checkResults[npTargetId+'_num']=npValue;else checkResults[npTargetId]=npValue;saveData();updateSummary();renderChecklist();closeNumPad();}
        function renderChecklist(){
            const c=document.getElementById('checklistContainer');c.innerHTML='';const eqs=appConfig[currentLine]||[];
            eqs.forEach((eq,ei)=>{
                const card=document.createElement('div');card.className="bg-white rounded-2xl shadow-sm border border-slate-100 mb-6 overflow-hidden animate-fade-in";
                card.innerHTML=`<div class="bg-slate-50/50 px-6 py-4 border-b border-slate-100 flex justify-between items-center"><h3 class="font-bold text-lg text-slate-800">${eq.equip}</h3></div>`;
                const list=document.createElement('div');list.className="divide-y divide-slate-50";
                eq.items.forEach((it,ii)=>{
                    const uid=`${currentLine}-${ei}-${ii}`,v=checkResults[uid],nv=checkResults[uid+'_num'];
                    let ctrl='';
                    if(it.type==='OX')ctrl=`<div class="flex gap-2"><button onclick="setBtnResult('${uid}','OK')" class="px-4 py-2 rounded-lg font-bold text-xs border ${v==='OK'?'bg-green-500 text-white':'bg-white'}">OK</button><button onclick="setBtnResult('${uid}','NG')" class="px-4 py-2 rounded-lg font-bold text-xs border ${v==='NG'?'bg-red-500 text-white':'bg-white'}">NG</button></div>`;
                    else if(it.type==='NUMBER_AND_OX')ctrl=`<div class="flex items-center gap-2"><input type="text" readonly value="${nv||''}" onclick="openNumPad('${uid}','num_suffix')" class="w-20 py-2 border rounded-lg text-center font-bold ${validateStandard(nv,it.standard)?'bg-slate-50':'bg-red-50 text-red-600 animate-pulse'}"><div class="flex gap-2"><button onclick="setBtnResult('${uid}','OK')" class="px-3 py-2 rounded-lg font-bold text-xs border ${v==='OK'?'bg-green-500 text-white':'bg-white'}">O</button><button onclick="setBtnResult('${uid}','NG')" class="px-3 py-2 rounded-lg font-bold text-xs border ${v==='NG'?'bg-red-500 text-white':'bg-white'}">X</button></div></div>`;
                    const row=document.createElement('div');row.className="p-5 hover:bg-blue-50/30 transition-colors";
                    row.innerHTML=`<div class="flex justify-between items-center gap-4"><div class="flex-1"><div class="font-bold text-slate-700">${it.name} <span class="text-xs text-blue-500 bg-blue-50 px-1 rounded">${it.standard}</span></div><div class="text-sm text-slate-500">${it.content}</div></div>${ctrl}</div>`;
                    list.appendChild(row);
                });
                card.appendChild(list);c.appendChild(card);
            });
            lucide.createIcons();
        }
        function setBtnResult(i,v){checkResults[i]=v;saveData();renderChecklist();}
        function updateSummary(){
            let t=0,o=0,n=0;Object.keys(appConfig).forEach(l=>appConfig[l].forEach((e,ei)=>e.items.forEach((it,ii)=>{t++;const v=checkResults[`${l}-${ei}-${ii}`];if(v==='OK')o++;if(v==='NG')n++})));
            document.getElementById('count-total').innerText=t;document.getElementById('count-ok').innerText=o;document.getElementById('count-ng').innerText=n;
            const p=t===0?0:Math.round(((o+n)/t)*100);document.getElementById('progress-text').innerText=`${p}%`;
            document.getElementById('progress-circle').style.strokeDashoffset=100-p;
        }
        let cvs,ctx,drw=false;
        function initSignaturePad(){cvs=document.getElementById('signature-pad');ctx=cvs.getContext('2d');cvs.width=cvs.offsetWidth;cvs.height=cvs.offsetHeight;
            cvs.addEventListener('touchstart',e=>{e.preventDefault();const r=cvs.getBoundingClientRect();ctx.moveTo(e.touches[0].clientX-r.left,e.touches[0].clientY-r.top);ctx.beginPath();drw=true},{passive:false});
            cvs.addEventListener('touchmove',e=>{e.preventDefault();if(!drw)return;const r=cvs.getBoundingClientRect();ctx.lineTo(e.touches[0].clientX-r.left,e.touches[0].clientY-r.top);ctx.stroke()},{passive:false});
            cvs.addEventListener('touchend',()=>drw=false);
            cvs.addEventListener('mousedown',e=>{const r=cvs.getBoundingClientRect();ctx.moveTo(e.clientX-r.left,e.clientY-r.top);ctx.beginPath();drw=true});
            cvs.addEventListener('mousemove',e=>{if(!drw)return;const r=cvs.getBoundingClientRect();ctx.lineTo(e.clientX-r.left,e.clientY-r.top);ctx.stroke()});
            cvs.addEventListener('mouseup',()=>drw=false);
        }
        function openSignatureModal(){document.getElementById('signature-modal').classList.remove('hidden');cvs.width=cvs.offsetWidth;cvs.height=cvs.offsetHeight;}
        function closeSignatureModal(){document.getElementById('signature-modal').classList.add('hidden');}
        function clearSignature(){ctx.clearRect(0,0,cvs.width,cvs.height);}
        function saveSignature(){signatureData=cvs.toDataURL();saveData();updateSignatureStatus();closeSignatureModal();}
        function updateSignatureStatus(){const b=document.getElementById('btn-signature'),s=document.getElementById('sign-status');if(signatureData){s.innerText="서명 완료";s.className="text-green-400 font-bold";b.classList.add('border-green-500')}else{s.innerText="서명";s.className="text-slate-300";b.classList.remove('border-green-500')}}
        window.saveAndDownloadPDF=async function(){
            const d=document.getElementById('inputDate').value;const {jsPDF}=window.jspdf;const doc=new jsPDF('p','mm','a4');
            // Simple PDF generation logic placeholder (Full logic in original file)
            doc.text(`SMT Daily Check - ${d}`,10,10);doc.save(`SMT_${d}.pdf`);
        }
    </script>
</body>
</html>
"""

# ------------------------------------------------------------------
# 1. 기본 설정 및 디자인
# ------------------------------------------------------------------
st.set_page_config(
    page_title="SMT 통합시스템", 
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="auto" 
)

st.markdown("""
    <style>
    @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
    html, body, [class*="css"] { font-family: 'Pretendard', sans-serif !important; color: #1e293b; }
    .stApp { background-color: #f8fafc; }
    [data-testid="stHeader"] { background: rgba(0,0,0,0); }
    .smart-card {
        background: #ffffff; border-radius: 16px; padding: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05); border: 1px solid #f1f5f9; height: 100%;
    }
    .dashboard-header {
        background: linear-gradient(135deg, #4f46e5 0%, #3b82f6 100%);
        padding: 30px 40px; border-radius: 20px; color: white; margin-bottom: 30px;
        display: flex; justify-content: space-between; align-items: center;
    }
    .kpi-title { font-size: 0.85rem; font-weight: 600; color: #64748b; text-transform: uppercase; margin-bottom: 8px; }
    .kpi-value { font-size: 2.2rem; font-weight: 800; color: #0f172a; margin-bottom: 4px; }
    </style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 2. Google Sheets 연결 설정 (캐싱 최적화)
# ------------------------------------------------------------------
GOOGLE_SHEET_NAME = "SMT_Database" 

SHEET_RECORDS = "production_data"
SHEET_ITEMS = "item_codes"
SHEET_INVENTORY = "inventory_data"
SHEET_INV_HISTORY = "inventory_history"
SHEET_MAINTENANCE = "maintenance_data"
SHEET_EQUIPMENT = "equipment_list"

# 기본 컬럼 정의
COLS_RECORDS = ["날짜", "구분", "품목코드", "제품명", "수량", "입력시간", "작성자", "수정자", "수정시간"]
COLS_ITEMS = ["품목코드", "제품명"]
COLS_INVENTORY = ["품목코드", "제품명", "현재고"]
COLS_INV_HISTORY = ["날짜", "품목코드", "구분", "수량", "비고", "작성자", "입력시간"]
COLS_MAINTENANCE = ["날짜", "설비ID", "설비명", "작업구분", "작업내용", "교체부품", "비용", "작업자", "비가동시간", "입력시간", "작성자", "수정자", "수정시간"]
COLS_EQUIPMENT = ["id", "name", "func"]

DEFAULT_EQUIPMENT = [
    {"id": "CIMON-SMT34", "name": "Loader (SLD-120Y)", "func": "메거진 로딩"},
    {"id": "CIMON-SMT03", "name": "Screen Printer", "func": "솔더링 설비"},
    {"id": "CIMON-SMT08", "name": "REFLOW(1809MKⅢ)", "func": "리플로우 오븐"},
    {"id": "CIMON-SMT29", "name": "AOI검사(ZENITH)", "func": "비젼 검사"}
]

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

@st.cache_resource
def get_spreadsheet_object(sheet_name):
    client = get_gs_connection()
    if not client: return None
    try:
        return client.open(sheet_name)
    except gspread.SpreadsheetNotFound:
        st.error(f"구글 시트 '{sheet_name}'를 찾을 수 없습니다.")
        return None
    except Exception as e:
        st.error(f"시트 열기 오류: {e}")
        return None

def get_worksheet(sheet_name, worksheet_name, create_if_missing=False, columns=None):
    sh = get_spreadsheet_object(sheet_name)
    if not sh: return None
    try:
        ws = sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        if create_if_missing:
            ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20)
            if columns: ws.append_row(columns)
        else: return None
    return ws

def init_sheets():
    sh = get_spreadsheet_object(GOOGLE_SHEET_NAME)
    if not sh: return
    existing_titles = [ws.title for ws in sh.worksheets()]
    defaults = {
        SHEET_RECORDS: COLS_RECORDS, SHEET_ITEMS: COLS_ITEMS,
        SHEET_INVENTORY: COLS_INVENTORY, SHEET_INV_HISTORY: COLS_INV_HISTORY,
        SHEET_MAINTENANCE: COLS_MAINTENANCE, SHEET_EQUIPMENT: COLS_EQUIPMENT
    }
    for s_name, cols in defaults.items():
        if s_name not in existing_titles:
            ws = sh.add_worksheet(title=s_name, rows=100, cols=20)
            ws.append_row(cols)
            if s_name == SHEET_EQUIPMENT:
                 set_with_dataframe(ws, pd.DataFrame(DEFAULT_EQUIPMENT))

if 'sheets_initialized' not in st.session_state:
    init_sheets()
    st.session_state.sheets_initialized = True

@st.cache_data(ttl=5)
def load_data(sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if not ws: return pd.DataFrame()
    try:
        df = get_as_dataframe(ws, evaluate_formulas=True)
        return df.dropna(how='all').dropna(axis=1, how='all')
    except: return pd.DataFrame()

def clear_cache():
    load_data.clear()

def save_data(df, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        ws.clear() 
        set_with_dataframe(ws, df) 
        clear_cache()
        return True
    return False

def append_data(data_dict, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        try: headers = ws.row_values(1)
        except: headers = list(data_dict.keys())
        row_to_add = [str(data_dict.get(h, "")) if not pd.isna(data_dict.get(h, "")) else "" for h in headers]
        ws.append_row(row_to_add)
        clear_cache()
        return True
    return False

def update_inventory(code, name, change, reason, user):
    df = load_data(SHEET_INVENTORY)
    if not df.empty and '현재고' in df.columns:
        df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
    else:
        df = pd.DataFrame(columns=COLS_INVENTORY)

    if not df.empty and code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    
    save_data(df, SHEET_INVENTORY)
    
    hist = {
        "날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, 
        "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, 
        "작성자": user, "입력시간": str(datetime.now())
    }
    append_data(hist, SHEET_INV_HISTORY)

def get_user_id():
    return st.session_state.user_info["name"]

# ------------------------------------------------------------------
# [신규] PDF 보고서 생성 함수
# ------------------------------------------------------------------
def create_daily_pdf(daily_df, report_date):
    pdf = FPDF()
    pdf.add_page()
    
    font_path = 'NanumGothic.ttf'
    if not os.path.exists(font_path):
        font_path = 'C:\\Windows\\Fonts\\malgun.ttf'
    
    has_korean_font = False
    if os.path.exists(font_path):
        try:
            pdf.add_font('Korean', '', font_path, uni=True)
            pdf.set_font('Korean', '', 12)
            has_korean_font = True
        except:
            pdf.set_font('Arial', '', 12)
    else:
        pdf.set_font('Arial', '', 12)

    pdf.set_font_size(18)
    title_text = f'SMT Daily Report ({report_date.strftime("%Y-%m-%d")})'
    if has_korean_font:
        title_text = f'SMT 일일 생산현황 ({report_date.strftime("%Y-%m-%d")})'
    pdf.cell(0, 15, title_text, ln=True, align='C')
    pdf.ln(5)

    daily_df = daily_df[~daily_df['구분'].astype(str).str.contains("외주")] # 외주 제외
    
    custom_order = ["PC", "CM1", "CM3", "배전", "샘플", "후공정"]
    daily_df['구분'] = pd.Categorical(daily_df['구분'], categories=custom_order, ordered=True)
    daily_df = daily_df.sort_values(by=['구분', '제품명'])

    pdf.set_font_size(10)
    pdf.set_fill_color(220, 230, 241) 
    
    w_cat = 30; w_code = 40; w_name = 80; w_qty = 30
    
    pdf.cell(w_cat, 10, "Category", border=1, align='C', fill=True)
    pdf.cell(w_code, 10, "Item Code", border=1, align='C', fill=True)
    pdf.cell(w_name, 10, "Item Name", border=1, align='C', fill=True)
    pdf.cell(w_qty, 10, "Q'ty", border=1, align='C', fill=True)
    pdf.ln()

    total_qty = 0
    for _, row in daily_df.iterrows():
        pdf.cell(w_cat, 8, str(row['구분']), border=1, align='C')
        pdf.cell(w_code, 8, str(row['품목코드']), border=1, align='C')
        p_name = str(row['제품명'])
        if len(p_name) > 30: p_name = p_name[:28] + ".."
        pdf.cell(w_name, 8, p_name, border=1, align='L')
        pdf.cell(w_qty, 8, f"{row['수량']:,}", border=1, align='R')
        pdf.ln()
        total_qty += row['수량']

    pdf.ln(5)
    pdf.set_font_size(12)
    pdf.set_fill_color(255, 255, 200) 
    pdf.cell(w_cat + w_code + w_name, 10, "Total Production Quantity : ", border=1, align='R', fill=True)
    pdf.cell(w_qty, 10, f"{total_qty:,} EA", border=1, align='R', fill=True)
    return bytes(pdf.output())

# ------------------------------------------------------------------
# 3. 로그인 및 사용자 관리
# ------------------------------------------------------------------
def make_hash(password): return hashlib.sha256(str.encode(password)).hexdigest()

USERS = {
    "park": {"name": "Park", "password_hash": make_hash("1083"), "role": "admin", "desc": "System Administrator"},
    "suk": {"name": "Suk", "password_hash": make_hash("1734"), "role": "editor", "desc": "Production Manager"},
    "kim": {"name": "Kim", "password_hash": make_hash("8943"), "role": "editor", "desc": "Equipment Engineer"}
}

def check_password():
    if "logged_in" not in st.session_state: st.session_state.logged_in = False
    if st.session_state.logged_in: return True

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True) 
        st.markdown("<h1 style='text-align:center;'>SMT 통합시스템</h1>", unsafe_allow_html=True)
        with st.container(border=True):
            with st.form(key="login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                    if username in USERS and make_hash(password) == USERS[username]["password_hash"]:
                        st.session_state.logged_in = True
                        st.session_state.user_info = USERS[username]
                        st.session_state.user_info["id"] = username
                        st.rerun()
                    else: st.error("아이디 또는 비밀번호가 잘못되었습니다.")
            
            if st.button("Guest Access (Viewer)", use_container_width=True):
                st.session_state.logged_in = True
                st.session_state.user_info = {"id": "viewer", "name": "Guest", "role": "viewer", "desc": "Viewer Mode"}
                st.rerun()
    return False

if not check_password(): st.stop()
CURRENT_USER = st.session_state.user_info
IS_ADMIN = (CURRENT_USER["role"] == "admin")
IS_EDITOR = (CURRENT_USER["role"] in ["admin", "editor"])
def get_user_id(): return st.session_state.user_info["name"]

# ------------------------------------------------------------------
# 4. 메인 UI 및 메뉴
# ------------------------------------------------------------------
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    st.markdown("<h2 style='text-align:center;'>Cloud SMT</h2>", unsafe_allow_html=True)
    if st.session_state.logged_in:
        u_info = st.session_state.user_info
        role_badge = "👑 Admin" if u_info["role"] == "admin" else "👤 User" if u_info["role"] == "editor" else "👀 Viewer"
        role_style = "background:#dcfce7; color:#15803d;" if u_info["role"] == "admin" else "background:#dbeafe; color:#1d4ed8;"
        st.markdown(f"""
            <div class="smart-card" style="padding:15px; margin-bottom:20px; text-align:center;">
                <div style="font-weight:bold; font-size:1.1rem;">{u_info['name']}</div>
                <div style="font-size:0.8rem; color:#64748b; margin-bottom:5px;">{u_info['desc']}</div>
                <span style="font-size:0.75rem; padding:4px 10px; border-radius:12px; font-weight:bold; {role_style}">{role_badge}</span>
            </div>
        """, unsafe_allow_html=True)
    
    # [수정] 메뉴 분리: '일일점검'을 독립 메뉴로 생성
    menu = st.radio("Navigation", ["🏭 생산관리", "🛠️ 설비보전관리", "📱 일일점검 (Tablet)"])
    st.markdown("---")
    if st.button("로그아웃", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()

st.markdown(f"""<div class="dashboard-header"><div><h2 style="margin:0;">{menu}</h2><div style="opacity:0.8; margin-top:5px;">Real-time Management System</div></div></div>""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# 5. [메뉴 1] 생산관리
# ------------------------------------------------------------------
if menu == "🏭 생산관리":
    t1, t2, t3, t4, t5 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📊 대시보드", "⚙️ 기준정보", "📑 일일 보고서"])
    
    with t1:
        c1, c2 = st.columns([1, 1.5], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### ✏️ 신규 생산 등록")
                    date = st.date_input("작업 일자")
                    cat = st.selectbox("공정 구분", ["PC", "CM1", "CM3", "배전", "샘플", "후공정", "후공정 외주"])
                    
                    item_df = load_data(SHEET_ITEMS)
                    item_map = dict(zip(item_df['품목코드'], item_df['제품명'])) if not item_df.empty else {}
                    
                    def on_code():
                        c = st.session_state.code_in.upper().strip()
                        if c in item_map: st.session_state.name_in = item_map[c]
                    
                    code = st.text_input("품목 코드", key="code_in", on_change=on_code)
                    name = st.text_input("제품명", key="name_in")
                    qty = st.number_input("생산 수량", min_value=1, value=100, key="prod_qty")
                    
                    auto_deduct = False
                    if cat in ["후공정", "후공정 외주"]:
                        st.divider()
                        auto_deduct = st.checkbox("📦 반제품 재고 자동 차감 (체크 시 감소)", value=True)
                    else:
                        st.divider()
                        st.info("ℹ️ 생산 등록 시 재고가 자동으로 증가합니다.")

                    if st.button("저장하기", type="primary", use_container_width=True):
                        if name:
                            rec = {
                                "날짜":str(date), "구분":cat, "품목코드":code, "제품명":name, 
                                "수량":qty, "입력시간":str(datetime.now()), 
                                "작성자":get_user_id(), "수정자":"", "수정시간":""
                            }
                            with st.spinner("저장 중..."):
                                if append_data(rec, SHEET_RECORDS):
                                    if cat in ["후공정", "후공정 외주"]:
                                        if auto_deduct: update_inventory(code, name, -qty, f"생산출고({cat})", get_user_id())
                                    else:
                                        update_inventory(code, name, qty, f"생산입고({cat})", get_user_id())
                                    
                                    st.success("저장 완료!")
                                    st.session_state.code_in = ""
                                    st.session_state.name_in = ""
                                    st.session_state.prod_qty = 100
                                    time.sleep(0.5); st.rerun()
                                else: st.error("저장 실패")
                        else: st.error("제품명을 입력해주세요.")
            else: st.warning("🔒 뷰어 모드입니다.")

        with c2:
            st.markdown("#### 📋 최근 등록 내역 (삭제 가능)")
            df = load_data(SHEET_RECORDS)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(50)
                if IS_EDITOR:
                    st.caption("💡 행을 선택하고 Del 키를 누르면 삭제됩니다.")
                    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic", key="prod_editor")
                    if st.button("변경사항 저장 (삭제 반영)", type="secondary"):
                        save_data(edited_df, SHEET_RECORDS) 
                        st.success("반영되었습니다.")
                        time.sleep(1); st.rerun()
                else: st.dataframe(df, use_container_width=True, hide_index=True)
            else: st.info("데이터가 없습니다.")

    with t2:
        df_inv = load_data(SHEET_INVENTORY)
        if not df_inv.empty:
            df_inv['현재고'] = pd.to_numeric(df_inv['현재고'], errors='coerce').fillna(0).astype(int)
            c_s, _ = st.columns([1, 2])
            search = c_s.text_input("🔍 재고 검색", placeholder="품목명/코드")
            if search:
                mask = df_inv['품목코드'].astype(str).str.contains(search, case=False) | df_inv['제품명'].astype(str).str.contains(search, case=False)
                df_inv = df_inv[mask]
            
            if IS_EDITOR:
                st.caption("💡 수량 수정 및 Del 키로 삭제 가능")
                edited_inv = st.data_editor(df_inv, use_container_width=True, hide_index=True, num_rows="dynamic", key="inv_editor")
                if st.button("재고 현황 저장", type="primary"):
                    save_data(edited_inv, SHEET_INVENTORY)
                    st.success("재고가 업데이트되었습니다.")
                    time.sleep(1); st.rerun()
            else: st.dataframe(df_inv, use_container_width=True, hide_index=True)
        else: st.info("재고 데이터가 없습니다.")

    with t3:
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            df['수량'] = pd.to_numeric(df['수량'], errors='coerce').fillna(0)
            df['날짜'] = pd.to_datetime(df['날짜'])
            k1, k2 = st.columns(2)
            k1.metric("총 누적 생산량", f"{df['수량'].sum():,} EA")
            k2.metric("최근 생산일", df['날짜'].max().strftime('%Y-%m-%d'))
            st.divider()
            if HAS_ALTAIR:
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown("##### 📉 일별 생산 추이")
                    chart_data = df.groupby('날짜')['수량'].sum().reset_index()
                    c = alt.Chart(chart_data).mark_bar(color='#818cf8').encode(
                        x=alt.X('날짜', axis=alt.Axis(format='%m-%d', labelAngle=0, title='날짜')), 
                        y=alt.Y('수량', axis=alt.Axis(labelAngle=0, titleAngle=0, title='수량')),
                        tooltip=['날짜', '수량']
                    ).interactive()
                    st.altair_chart(c, use_container_width=True)
                with c2:
                    st.markdown("##### 🍰 공정별 비중")
                    pie_data = df.groupby('구분')['수량'].sum().reset_index()
                    pie = alt.Chart(pie_data).mark_arc(innerRadius=50).encode(theta=alt.Theta("수량", stack=True), color=alt.Color("구분"), tooltip=["구분", "수량"])
                    st.altair_chart(pie, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    with t4:
        if IS_ADMIN:
            st.warning("⚠️ 구글 시트에 즉시 반영됩니다.")
            t_item, t_raw = st.tabs(["품목 관리", "데이터 원본(Admin)"])
            with t_item:
                df_items = load_data(SHEET_ITEMS)
                edited = st.data_editor(df_items, num_rows="dynamic", use_container_width=True)
                if st.button("품목 기준정보 저장", type="primary"):
                    save_data(edited, SHEET_ITEMS); st.success("저장 완료"); time.sleep(1); st.rerun()
            with t_raw: st.markdown("전체 데이터 직접 편집 모드")
        else: st.warning("관리자 권한 필요")

    with t5:
        st.markdown("#### 📑 SMT 일일 생산현황 (PDF)")
        st.markdown("PC, CM1, CM3, 배전, 샘플, 후공정 작업 내용만 출력됩니다. (외주 제외)")
        
        c1, c2 = st.columns([1, 3])
        with c1:
            report_date = st.date_input("보고서 날짜 선택", datetime.now())
        
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            mask_date = pd.to_datetime(df['날짜']).dt.date == report_date
            daily_df = df[mask_date].copy()
            daily_df = daily_df[~daily_df['구분'].astype(str).str.contains("외주")]
            
            if not daily_df.empty:
                st.info(f"{report_date} : 총 {len(daily_df)}건의 생산 실적 (외주 제외)")
                st.dataframe(daily_df[['구분', '품목코드', '제품명', '수량']], use_container_width=True, hide_index=True)
                
                if st.button("📄 PDF 보고서 생성", type="primary"):
                    try:
                        pdf_bytes = create_daily_pdf(daily_df, report_date)
                        st.download_button(label="📥 PDF 다운로드", data=pdf_bytes, file_name=f"SMT_Daily_Report_{report_date}.pdf", mime="application/pdf")
                    except Exception as e: st.error(f"오류: {e}")
            else: st.warning(f"해당 날짜({report_date})에 '외주'를 제외한 생산 실적이 없습니다.")
        else: st.info("데이터가 없습니다.")

# ------------------------------------------------------------------
# 6. [메뉴 2] 설비보전관리
# ------------------------------------------------------------------
elif menu == "🛠️ 설비보전관리":
    # [수정] 탭 원래대로 복구 (4개 탭)
    t1, t2, t3, t4 = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "📊 분석 및 리포트", "⚙️ 설비 목록"])
    
    # 6-1. 정비 이력 등록
    with t1:
        c1, c2 = st.columns([1, 1.5], gap="large")
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### 🔧 정비 이력 등록")
                    eq_df = load_data(SHEET_EQUIPMENT)
                    eq_map = dict(zip(eq_df['id'], eq_df['name'])) if not eq_df.empty else {}
                    eq_list = list(eq_map.keys())
                    
                    f_date = st.date_input("작업 날짜", key="m_date")
                    f_eq = st.selectbox("대상 설비", eq_list, format_func=lambda x: f"[{x}] {eq_map[x]}" if x in eq_map else x, key="m_eq")
                    f_type = st.selectbox("작업 구분", ["PM (예방)", "BM (고장)", "CM (개선)"], key="m_type")
                    f_desc = st.text_area("작업 내용", height=80, key="m_desc")
                    
                    st.markdown("---")
                    st.caption("🔩 교체 부품 / 상세 비용 추가")
                    
                    if 'parts_buffer' not in st.session_state: st.session_state.parts_buffer = []
                    col_p1, col_p2, col_p3 = st.columns([2, 1, 0.8])
                    p_name = col_p1.text_input("내역/부품명", key="p_name_in")
                    p_cost = col_p2.number_input("비용(원)", step=1000, key="p_cost_in")
                    
                    if col_p3.button("추가", use_container_width=True):
                        if p_name: st.session_state.parts_buffer.append({"내역": p_name, "비용": int(p_cost)})
                        else: st.toast("내역을 입력하세요.")
                    
                    total_p_cost = 0
                    if st.session_state.parts_buffer:
                        p_df = pd.DataFrame(st.session_state.parts_buffer)
                        st.dataframe(p_df, use_container_width=True, hide_index=True)
                        total_p_cost = p_df['비용'].sum()
                        if st.button("목록 초기화"):
                            st.session_state.parts_buffer = []
                            st.rerun()

                    st.markdown("---")
                    f_cost = st.number_input("💰 총 소요 비용 (원)", value=total_p_cost, step=1000, key="m_cost")
                    f_down = st.number_input("⏱️ 비가동 시간 (분)", step=10, key="m_down")
                    
                    if st.button("이력 저장", type="primary", use_container_width=True):
                        eq_name = eq_map.get(f_eq, "")
                        parts_str = ", ".join([f"{p['내역']}({p['비용']:,})" for p in st.session_state.parts_buffer]) if st.session_state.parts_buffer else ""
                        rec = {
                            "날짜": str(f_date), "설비ID": f_eq, "설비명": eq_name,
                            "작업구분": f_type.split()[0], "작업내용": f_desc, 
                            "교체부품": parts_str, "비용": f_cost, "작업자": get_user_id(), 
                            "비가동시간": f_down, "입력시간": str(datetime.now()), "작성자": get_user_id()
                        }
                        with st.spinner("저장 중..."):
                            append_data(rec, SHEET_MAINTENANCE)
                            st.session_state.parts_buffer = [] 
                            st.session_state.m_desc = ""
                            st.session_state.m_cost = 0
                            st.session_state.m_down = 0
                            st.success("저장 완료")
                            time.sleep(0.5); st.rerun()
            else: st.warning("권한이 없습니다.")

        with c2:
            st.markdown("#### 📋 최근 정비 내역 (삭제 가능)")
            df_maint = load_data(SHEET_MAINTENANCE)
            if not df_maint.empty:
                df_maint = df_maint.sort_values("입력시간", ascending=False).head(50)
                if IS_EDITOR:
                    st.caption("💡 행을 선택하고 Del 키를 누르면 삭제됩니다.")
                    edited_maint = st.data_editor(df_maint, use_container_width=True, hide_index=True, num_rows="dynamic", key="maint_editor_recent")
                    if st.button("변경사항 저장 (정비내역)", type="secondary"):
                        save_data(edited_maint, SHEET_MAINTENANCE)
                        st.success("반영되었습니다.")
                        time.sleep(1); st.rerun()
                else: st.dataframe(df_maint, use_container_width=True, hide_index=True)
            else: st.info("이력이 없습니다.")

    # 6-2. 이력 조회
    with t2:
        df_hist = load_data(SHEET_MAINTENANCE)
        if not df_hist.empty: 
            if IS_EDITOR:
                st.caption("💡 전체 이력 수정 및 삭제 모드")
                df_hist_sorted = df_hist.sort_values("날짜", ascending=False)
                edited_hist = st.data_editor(df_hist_sorted, use_container_width=True, num_rows="dynamic", key="hist_editor_full")
                if st.button("이력 수정 저장", type="primary"):
                    save_data(edited_hist, SHEET_MAINTENANCE)
                    st.success("이력이 전체 업데이트되었습니다.")
                    time.sleep(1); st.rerun()
            else: st.dataframe(df_hist, use_container_width=True)
        else: st.info("데이터가 없습니다.")

    # 6-3. 분석 및 리포트
    with t3:
        st.markdown("#### 📊 설비 고장 및 정비 분석")
        df = load_data(SHEET_MAINTENANCE)
        if not df.empty and '날짜' in df.columns:
            df['날짜'] = pd.to_datetime(df['날짜'], errors='coerce')
            df['비용'] = pd.to_numeric(df['비용'], errors='coerce').fillna(0)
            df['비가동시간'] = pd.to_numeric(df['비가동시간'], errors='coerce').fillna(0)
            df['Year'] = df['날짜'].dt.year
            df['Month'] = df['날짜'].dt.month
            
            avail_years = sorted(df['Year'].dropna().unique().astype(int), reverse=True)
            if not avail_years: avail_years = [datetime.now().year]
            sel_year = st.selectbox("조회 연도", avail_years)
            df_year = df[df['Year'] == sel_year]
            
            if not df_year.empty:
                k1, k2, k3 = st.columns(3)
                k1.metric("💰 연간 정비비용", f"{df_year['비용'].sum():,.0f} 원")
                k2.metric("⏱️ 연간 비가동", f"{df_year['비가동시간'].sum():,} 분")
                k3.metric("🔥 고장(BM) 발생", f"{len(df_year[df_year['작업구분'].astype(str).str.contains('BM', na=False)])} 건")
                st.divider()
                if HAS_ALTAIR:
                    c1, c2 = st.columns([2, 1])
                    with c1:
                        st.markdown("##### 📉 월별 비용 추이")
                        chart = alt.Chart(df_year.groupby('Month')['비용'].sum().reset_index()).mark_bar().encode(
                            x=alt.X('Month:O', title='월', axis=alt.Axis(labelAngle=0)), 
                            y=alt.Y('비용', title='비용', axis=alt.Axis(labelAngle=0, titleAngle=0))
                        )
                        st.altair_chart(chart, use_container_width=True)
                    with c2:
                        st.markdown("##### 🥧 유형별 비율")
                        pie = alt.Chart(df_year.groupby('작업구분')['비용'].sum().reset_index()).mark_arc(innerRadius=40).encode(theta=alt.Theta("비용", stack=True), color="작업구분")
                        st.altair_chart(pie, use_container_width=True)
            else: st.info(f"{sel_year}년 데이터가 없습니다.")
        else: st.info("데이터가 없습니다.")

    # 6-4. 설비 목록
    with t4:
        if IS_ADMIN:
            st.markdown("#### 설비 리스트 관리")
            df_eq = load_data(SHEET_EQUIPMENT)
            edited_eq = st.data_editor(df_eq, num_rows="dynamic", use_container_width=True)
            if st.button("설비 목록 저장", type="primary"):
                save_data(edited_eq, SHEET_EQUIPMENT); st.success("갱신 완료"); time.sleep(1); st.rerun()
        else: st.dataframe(load_data(SHEET_EQUIPMENT))

# ------------------------------------------------------------------
# 7. [메뉴 3] 일일점검 (Tablet) - 독립 메뉴
# ------------------------------------------------------------------
elif menu == "📱 일일점검 (Tablet)":
    st.markdown("##### 👆 태블릿 터치용 일일점검 시스템")
    st.caption("※ 이 화면의 데이터는 태블릿 기기 내부에 자동 저장됩니다.")
    # HTML 삽입 (높이 충분히 확보)
    components.html(DAILY_CHECK_HTML, height=1200, scrolling=True)