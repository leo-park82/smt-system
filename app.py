import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import time
import hashlib
import json
import os
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
# [핵심] SMT 일일점검표 HTML 코드 (날짜 버그 수정 버전 복구)
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
        input[type="date"] { position: relative; }
        input[type="date"]::-webkit-calendar-picker-indicator { position: absolute; top: 0; left: 0; right: 0; bottom: 0; width: 100%; height: 100%; color: transparent; background: transparent; cursor: pointer; }
        .ox-btn { transition: all 0.2s; }
        .ox-btn.active[data-ox="OK"] { background-color: #22c55e; color: white; border-color: #22c55e; }
        .ox-btn.active[data-ox="NG"] { background-color: #ef4444; color: white; border-color: #ef4444; }
        .ox-btn:not(.active) { background-color: white; color: #334155; border-color: #e2e8f0; }
        .num-input { transition: all 0.2s; }
        .num-input.error { background-color: #fef2f2; color: #dc2626; border-color: #fecaca; animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .5; } }
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

    <!-- Modals (Signature & Numpad) -->
    <div id="signature-modal" class="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 hidden flex items-center justify-center p-4">
        <div class="bg-white w-full max-w-lg rounded-2xl shadow-2xl overflow-hidden">
            <div class="bg-slate-900 px-6 py-4 flex justify-between items-center text-white"><h3 class="font-bold text-lg flex items-center gap-2"><i data-lucide="pen-tool" class="w-5 h-5"></i> 전자 서명</h3><button onclick="ui.closeSignatureModal()" class="text-slate-400 hover:text-white"><i data-lucide="x"></i></button></div>
            <div class="p-4 bg-slate-100"><canvas id="signature-pad" class="w-full h-48 rounded-xl shadow-inner border border-slate-300 touch-none bg-white"></canvas></div>
            <div class="p-4 bg-white flex gap-3 justify-end border-t border-slate-100"><button onclick="actions.clearSignature()" class="px-4 py-2 text-slate-500 hover:bg-slate-100 rounded-lg text-sm font-bold">지우기</button><button onclick="actions.saveSignature()" class="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-bold shadow-lg shadow-blue-500/30">서명 완료</button></div>
        </div>
    </div>
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
        const LAST_DATE_KEY = "SMT_DATA_LAST_DATE";
        const CONFIG_KEY = "SMT_CONFIG_V6.1_SYNTAX_FIXED";
        const defaultLineData = {
            "1 LINE": [
                { equip: "IN LOADER (SML-120Y)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "수/자동 전환", content: "MODE 전환 스위치 작동", standard: "정상 동작", type: "OX" }, { name: "각 구동부", content: "작동 이상음 및 소음 상태", standard: "정상 동작", type: "OX" }, { name: "매거진 상태", content: "Locking 마모, 휨, 흔들림", standard: "마모/휨 없을 것", type: "OX" }] },
                { equip: "VACUUM LOADER (SBSF-200)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "수/자동 전환", content: "MODE 전환 스위치 작동", standard: "정상 동작", type: "OX" }, { name: "각 구동부", content: "작동 이상음 및 소음 상태", standard: "정상 동작", type: "OX" }, { name: "PCB 흡착 패드", content: "패드 찢어짐 및 손상 확인", standard: "찢어짐 없을 것", type: "OX" }] },
                { equip: "MARKING (L5000)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "각 구동부", content: "작동 이상음 및 소음 상태", standard: "정상 동작", type: "OX" }, { name: "센서 작동", content: "입/출 감지 센서 작동 확인", standard: "정상 동작", type: "OX" }, { name: "컨베이어", content: "벨트 구동 및 소음 확인", standard: "이상 소음 없을 것", type: "OX" }] },
                { equip: "SCREEN PRINTER (HP-520S)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "테이블 오염", content: "테이블 위 솔더/이물 청결", standard: "청결할 것", type: "OX" }, { name: "스퀴지 점검", content: "날 끝 찌그러짐, 파손 확인", standard: "파손 및 변형 없을 것", type: "OX" }, { name: "백업 PIN", content: "PIN 휨 및 높이 상태", standard: "파손 및 변형 없을 것", type: "OX" }] },
                { equip: "SPI (TROL-7700EL)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "레이저 센서", content: "헤드부 센서 점등 상태", standard: "정상 동작", type: "OX" }, { name: "X, Y 테이블", content: "원점 복귀 및 이동 시 소음", standard: "정상 동작", type: "OX" }] },
                { equip: "CHIP MOUNTER (S2)", items: [{ name: "AIR 압력", content: "메인 공압 게이지 확인", standard: "5 Kg/cm² ± 0.5", type: "OX" }, { name: "필터 및 노즐", content: "Head Air 필터 및 노즐 오염", standard: "오염 및 변형 없을 것", type: "OX" }, { name: "인식 카메라", content: "카메라 렌즈부 이물/오염", standard: "이물 없을 것", type: "OX" }, { name: "피더 베이스", content: "피더 장착부 이물 확인", standard: "이물 없을 것", type: "OX" }] },
                { equip: "이형 MOUNTER (L2)", items: [{ name: "AIR 압력", content: "메인 공압 게이지 확인", standard: "5 Kg/cm² ± 0.5", type: "OX" }, { name: "필터 및 노즐", content: "Head Air 필터 및 노즐 오염", standard: "오염 및 변형 없을 것", type: "OX" }, { name: "인식 카메라", content: "카메라 렌즈부 이물/오염", standard: "이물 없을 것", type: "OX" }, { name: "피더 베이스", content: "피더 장착부 이물 확인", standard: "이물 없을 것", type: "OX" }, { name: "Tray Pallet", content: "Pallet 휨 및 변형 상태", standard: "휨 없을 것", type: "OX" }, { name: "Tray 구동부", content: "엘리베이터 작동 소음", standard: "정상 동작", type: "OX" }] },
                { equip: "REFLOW (1809MKⅢ)", items: [{ name: "N2 PPM", content: "산소 농도 모니터 수치", standard: "3000 ppm 이하", type: "NUMBER_AND_OX", unit: "ppm" }, { name: "배기관 OPEN", content: "배기 댐퍼 열림 위치", standard: "오픈 위치", type: "OX" }, { name: "CHAIN 작동", content: "체인 구동 시 진동/소음", standard: "정상 구동", type: "OX" }, { name: "폭 조정", content: "레일 폭 조절 스위치 작동", standard: "정상 조절", type: "OX" }] },
                { equip: "UN LOADER (SMU-120Y)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "수/자동 전환", content: "MODE 전환 스위치 작동", standard: "정상 동작", type: "OX" }, { name: "각 구동부", content: "Pusher/Lifter 작동 소음", standard: "정상 동작", type: "OX" }, { name: "매거진 상태", content: "Locking 마모, 휨, 흔들림", standard: "마모/휨 없을 것", type: "OX" }] }
            ],
            "2 LINE": [
                { equip: "IN LOADER (SML-120Y)", items: [{ name: "AIR 압력", content: "게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "수/자동 전환", content: "스위치 작동 확인", standard: "정상 동작", type: "OX" }, { name: "각 구동부", content: "작동 소음 확인", standard: "정상 동작", type: "OX" }, { name: "매거진 상태", content: "Locking 및 휨 확인", standard: "마모/휨 없을 것", type: "OX" }] },
                { equip: "VACUUM LOADER (SBSF-200Y)", items: [{ name: "AIR 압력", content: "게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "수/자동 전환", content: "스위치 작동 확인", standard: "정상 동작", type: "OX" }, { name: "각 구동부", content: "작동 소음 확인", standard: "정상 동작", type: "OX" }, { name: "PCB 흡착 패드", content: "패드 손상 여부", standard: "찢어짐 없을 것", type: "OX" }] },
                { equip: "MARKING (L5000)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "각 구동부", content: "작동 이상음 및 소음 상태", standard: "정상 동작", type: "OX" }, { name: "센서 작동", content: "입/출 감지 센서 작동 확인", standard: "정상 동작", type: "OX" }, { name: "컨베이어", content: "벨트 구동 및 소음 확인", standard: "이상 소음 없을 것", type: "OX" }] },
                { equip: "SCREEN PRINTER (HP-520S)", items: [{ name: "AIR 압력", content: "게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "테이블 오염", content: "이물 및 솔더 확인", standard: "청결할 것", type: "OX" }, { name: "스퀴지 점검", content: "날 끝 손상 확인", standard: "파손 및 변형 없을 것", type: "OX" }, { name: "백업 PIN", content: "PIN 상태 확인", standard: "파손 및 변형 없을 것", type: "OX" }] },
                { equip: "SPI (TROL-7700EL)", items: [{ name: "AIR 압력", content: "게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "레이저 센서", content: "점등 상태 확인", standard: "정상 동작", type: "OX" }, { name: "X, Y 테이블", content: "구동 소음 확인", standard: "정상 동작", type: "OX" }] },
                { equip: "CHIP MOUNTER (S2)", items: [{ name: "AIR 압력", content: "메인 공압 확인", standard: "5 Kg/cm² ± 0.5", type: "OX" }, { name: "필터 및 노즐", content: "오염 및 변형 확인", standard: "오염 및 변형 없을 것", type: "OX" }, { name: "인식 카메라", content: "렌즈부 청결 확인", standard: "이물 없을 것", type: "OX" }, { name: "피더 베이스", content: "장착부 이물 확인", standard: "이물 없을 것", type: "OX" }] },
                { equip: "이형 MOUNTER (L2)", items: [{ name: "AIR 압력", content: "메인 공압 확인", standard: "5 Kg/cm² ± 0.5", type: "OX" }, { name: "필터 및 노즐", content: "오염 및 변형 확인", standard: "오염 및 변형 없을 것", type: "OX" }, { name: "인식 카메라", content: "렌즈부 청결 확인", standard: "이물 없을 것", type: "OX" }, { name: "피더 베이스", content: "장착부 이물 확인", standard: "이물 없을 것", type: "OX" }, { name: "Tray Pallet", content: "휨/변형 확인", standard: "휨 없을 것", type: "OX" }, { name: "Tray 구동부", content: "작동 소음 확인", standard: "정상 동작", type: "OX" }] },
                { equip: "REFLOW (1809MKⅢ)", items: [{ name: "N2 PPM", content: "모니터 수치 확인", standard: "3000 ppm 이하", type: "NUMBER_AND_OX", unit: "ppm" }, { name: "배기관 OPEN", content: "댐퍼 위치 확인", standard: "오픈 위치", type: "OX" }, { name: "CHAIN 작동", content: "구동 상태 확인", standard: "정상 구동", type: "OX" }, { name: "폭 조정", content: "폭 조절 작동 확인", standard: "정상 조절", type: "OX" }] },
                { equip: "UN LOADER (SMU-120Y)", items: [{ name: "AIR 압력", content: "게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "수/자동 전환", content: "스위치 작동 확인", standard: "정상 동작", type: "OX" }, { name: "각 구동부", content: "작동 소음 확인", standard: "정상 동작", type: "OX" }, { name: "매거진 상태", content: "Locking 및 휨 확인", standard: "마모/휨 없을 것", type: "OX" }] }
            ],
            "AOI": [
                { equip: "AOI 검사 (ZENITH)", items: [{ name: "카메라 LED", content: "LED 조명 점등 상태 육안 검사", standard: "LED 점등 정상 동작", type: "OX" }, { name: "Y 테이블", content: "장비 원점 복귀 시 구동 상태", standard: "Y 구동 동작 정상동작", type: "OX" }, { name: "검사 상태", content: "마스터 샘플(양/불량) 검출 여부", standard: "정상 검사 완료", type: "OX" }] }
            ],
            "수삽 LINE": [
                { equip: "FLUX 도포기 (SAF-700)", items: [{ name: "플럭스 노즐", content: "PCB 투입하여 분사 상태 육안 확인", standard: "육안 확인", type: "OX" }, { name: "CHAIN 상태", content: "체인 구동 및 세척액 세척 상태", standard: "정상 구동", type: "OX" }, { name: "배기관 OPEN", content: "배기 댐퍼 열림 상태 목시 검사", standard: "오픈 위치", type: "OX" }] },
                { equip: "자동납땜기 (SAS-680L)", items: [{ name: "FINGER 상태", content: "FINGER 휨 및 이물 상태 목시 검사", standard: "이상 없을 것", type: "OX" }, { name: "CHAIN 작동", content: "체인 구동 상태 확인", standard: "정상 구동", type: "OX" }, { name: "납조 상태", content: "납조 찌꺼기 청결 상태 확인", standard: "납조 청결", type: "OX" }, { name: "배기관 OPEN", content: "배기 댐퍼 열림 상태 목시 검사", standard: "오픈 위치", type: "OX" }] }
            ],
            "MASK 세척기": [
                { equip: "METAL MASK 세척기 (JBMMC-3S/4S)", items: [{ name: "AIR 압력", content: "압력 게이지 지침 확인", standard: "0.5 MPa ± 0.1", type: "OX" }, { name: "자동 S/W", content: "자동 전환 스위치 작동 여부", standard: "자동 전환 정상동작", type: "OX" }, { name: "펌프 동작", content: "세척액 펌프 동작 소음 확인 (청각)", standard: "동작 상태 양호", type: "OX" }, { name: "세척액", content: "세척액 수위 게이지(눈금) 확인", standard: "LOW 레벨 이상", type: "OX" } ] }
            ],
            "SOLDER 보관온도": [
                { equip: "솔더크림 보관고", items: [{ name: "보관 온도", content: "온도계 지침 확인", standard: "0~10℃", type: "NUMBER_AND_OX", unit: "℃" }, { name: "유효기간", content: "선입선출 확인", standard: "기간 내", type: "OX" }] }
            ],
            "솔더 교반기": [
                { equip: "솔더 교반기", items: [{ name: "작동 시간", content: "Timer 설정 및 작동 확인", standard: "2분", type: "OX" }, { name: "진동/소음", content: "작동 중 이상 진동/소음 확인", standard: "이상 소음 없을 것", type: "OX" }, { name: "내/외부 청결", content: "솔더 페이스트 오염 여부", standard: "청결할 것", type: "OX" }, { name: "도어 센서", content: "도어 오픈 시 정지 확인", standard: "정상 동작", type: "OX" }] }
            ],
            "온,습도 CHECK": [
                { equip: "현장 온습도", items: [{ name: "실내 온도", content: "온도 관리 기준", standard: "24±5℃", type: "NUMBER_AND_OX", unit: "℃" }, { name: "실내 습도", content: "습도 관리 기준", standard: "40~60%", type: "NUMBER_AND_OX", unit: "%" }] }
            ],
            "인두기 CHECK": [
                { equip: "수동 인두기 1호기", items: [{ name: "팁 온도", content: "온도 측정기 확인", standard: "370±5℃", type: "NUMBER_AND_OX", unit: "℃" }, { name: "수분 상태", content: "스펀지 습윤 확인", standard: "양호", type: "OX" }] },
                { equip: "수동 인두기 2호기", items: [{ name: "팁 온도", content: "온도 측정기 확인", standard: "370±5℃", type: "NUMBER_AND_OX", unit: "℃" }, { name: "수분 상태", content: "스펀지 습윤 확인", standard: "양호", type: "OX" }] }
            ]
        };

        const state = {
            config: {}, results: {}, currentLine: "1 LINE", currentDate: "", signature: null,
            numpad: { targetId: null, value: "" }
        };

        function migrateOldResults(oldResults) {
            const migrated = {};
            Object.entries(oldResults || {}).forEach(([key, val]) => {
                if(key === 'signature') return;
                if (val && typeof val === 'object' && 'ox' in val) { migrated[key] = val; return; }
                if (val === 'OK' || val === 'NG') { migrated[key] = { ox: val, value: null }; }
                else if (typeof val === 'string' || typeof val === 'number') { if(!key.endsWith('_num')) migrated[key] = { ox: null, value: val }; }
            });
            return migrated;
        }

        const storage = {
            loadConfig() { try { const c = localStorage.getItem(CONFIG_KEY); return c ? JSON.parse(c) : JSON.parse(JSON.stringify(defaultLineData)); } catch { return JSON.parse(JSON.stringify(defaultLineData)); } },
            loadResults(date) { try { const raw = JSON.parse(localStorage.getItem(DATA_PREFIX + date)) || {}; const sig = raw.signature; const m = migrateOldResults(raw); m.signature = sig; return m; } catch { return {}; } },
            saveResults(date, data) { try { localStorage.setItem(DATA_PREFIX + date, JSON.stringify(data)); } catch (e) { console.error(e); } }
        };

        const dataMgr = {
            ensure(uid) { if (!state.results[uid] || typeof state.results[uid] !== 'object') state.results[uid] = { ox: null, value: null }; return state.results[uid]; },
            setOX(uid, ox) { this.ensure(uid).ox = ox; }, setValue(uid, val) { this.ensure(uid).value = val; },
            getOX(uid) { return state.results[uid]?.ox || null; }, getValue(uid) { return state.results[uid]?.value || null; }
        };

        const utils = {
            qs: (s) => document.querySelector(s), qsa: (s) => document.querySelectorAll(s),
            validateStandard(v, s) {
                if (!v) return true;
                const val = parseFloat(v.replace(/[^0-9.-]/g, ''));
                if (isNaN(val)) return true;
                if (s.includes('±')) { const p = s.split('±'); return val >= parseFloat(p[0]) - parseFloat(p[1]) && val <= parseFloat(p[0]) + parseFloat(p[1]); }
                if (s.includes('이하')) return val <= parseFloat(s);
                if (s.includes('이상')) return val >= parseFloat(s);
                if (s.includes('~')) { const p = s.split('~'); return val >= parseFloat(p[0]) && val <= parseFloat(p[1]); }
                return true;
            },
            isValueValid(uid, item) { const val = dataMgr.getValue(uid); if (val === null || val === "" || isNaN(parseFloat(val))) return false; return this.validateStandard(val, item.standard); },
            calculateSummary() {
                let total = 0, ok = 0, ng = 0;
                Object.keys(state.config).forEach(l => {
                    state.config[l].forEach(eq => { eq.items.forEach(it => { total++; const ox = dataMgr.getOX(`${l}-${state.config[l].indexOf(eq)}-${eq.items.indexOf(it)}`); if (ox === 'OK') ok++; if (ox === 'NG') ng++; }); });
                });
                return { total, ok, ng };
            }
        };

        const ui = {
            renderTabs() {
                const c = utils.qs('#lineTabs'); if(!c) return; c.innerHTML = '';
                Object.keys(state.config).forEach(l => {
                    const b = document.createElement('button');
                    b.className = `px-5 py-2 rounded-full text-sm font-bold whitespace-nowrap transition-all transform active:scale-95 ${l === state.currentLine ? 'tab-active' : 'tab-inactive'}`;
                    b.innerText = l;
                    b.onclick = () => { state.currentLine = l; ui.renderTabs(); ui.renderChecklist(); };
                    c.appendChild(b);
                });
            },
            renderChecklist() {
                const c = utils.qs('#checklistContainer'); c.innerHTML = '';
                const eqs = state.config[state.currentLine] || [];
                eqs.forEach((eq, ei) => {
                    const card = document.createElement('div');
                    card.className = "bg-white rounded-2xl shadow-sm border border-slate-100 mb-6 overflow-hidden animate-fade-in";
                    card.innerHTML = `<div class="bg-slate-50/50 px-6 py-4 border-b border-slate-100 flex justify-between items-center"><h3 class="font-bold text-lg text-slate-800">${eq.equip}</h3></div>`;
                    const list = document.createElement('div'); list.className = "divide-y divide-slate-50";
                    eq.items.forEach((it, ii) => {
                        const uid = `${state.currentLine}-${ei}-${ii}`;
                        const ox = dataMgr.getOX(uid);
                        const val = dataMgr.getValue(uid);
                        const activeClass = (t) => ox === t ? 'active' : '';
                        let control = '';
                        
                        if(it.type === 'OX') {
                            control = `<div class="flex gap-2"><button class="ox-btn px-4 py-2 rounded-lg font-bold text-xs border ${activeClass('OK')}" data-uid="${uid}" data-ox="OK">OK</button><button class="ox-btn px-4 py-2 rounded-lg font-bold text-xs border ${activeClass('NG')}" data-uid="${uid}" data-ox="NG">NG</button></div>`;
                        } else {
                            const isValid = utils.validateStandard(val, it.standard);
                            const inputClass = isValid ? 'bg-slate-50' : 'bg-red-50 text-red-600 error';
                            control = `<div class="flex items-center gap-2"><input type="text" readonly value="${val || ''}" class="num-input w-20 py-2 border rounded-lg text-center font-bold ${inputClass}" data-uid="${uid}"><div class="flex gap-2"><button class="ox-btn px-3 py-2 rounded-lg font-bold text-xs border ${activeClass('OK')}" data-uid="${uid}" data-ox="OK">O</button><button class="ox-btn px-3 py-2 rounded-lg font-bold text-xs border ${activeClass('NG')}" data-uid="${uid}" data-ox="NG">X</button></div></div>`;
                        }

                        const row = document.createElement('div'); row.className = "p-5 hover:bg-blue-50/30 transition-colors";
                        row.innerHTML = `<div class="flex justify-between items-center gap-4"><div class="flex-1"><div class="font-bold text-slate-700">${it.name} <span class="text-xs text-blue-500 bg-blue-50 px-1 rounded">${it.standard}</span></div><div class="text-sm text-slate-500">${it.content}</div></div>${control}</div>`;
                        list.appendChild(row);
                    });
                    card.appendChild(list); c.appendChild(card);
                });
                lucide.createIcons();
            },
            updateSummary() {
                const { total, ok, ng } = utils.calculateSummary();
                utils.qs('#count-total').innerText = total; utils.qs('#count-ok').innerText = ok; utils.qs('#count-ng').innerText = ng;
                const p = total === 0 ? 0 : Math.round(((ok + ng) / total) * 100);
                utils.qs('#progress-text').innerText = `${p}%`; utils.qs('#progress-circle').style.strokeDashoffset = 100 - p;
            },
            updateOXUI(uid) {
                const ox = dataMgr.getOX(uid);
                utils.qsa(`.ox-btn[data-uid="${uid}"]`).forEach(b => {
                    if (b.dataset.ox === ox) b.classList.add('active'); else b.classList.remove('active');
                });
            },
            updateNumUI(uid, val) {
                const inp = utils.qs(`.num-input[data-uid="${uid}"]`);
                if(inp) {
                    inp.value = val;
                    const [l, ei, ii] = uid.split('-');
                    const it = state.config[l][ei].items[ii];
                    if(utils.validateStandard(val, it.standard)) { inp.classList.remove('bg-red-50', 'text-red-600', 'error'); inp.classList.add('bg-slate-50'); }
                    else { inp.classList.remove('bg-slate-50'); inp.classList.add('bg-red-50', 'text-red-600', 'error'); }
                }
            },
            updateSignatureStatus() {
                const s = utils.qs('#sign-status'); const b = utils.qs('#btn-signature');
                if(state.signature) { s.innerText = "서명 완료"; s.className = "text-green-400 font-bold"; b.classList.add('border-green-500'); }
                else { s.innerText = "서명"; s.className = "text-slate-300"; b.classList.remove('border-green-500'); }
            },
            showToast(msg, type="normal") {
                const c = utils.qs('#toast-container'); const t = document.createElement('div');
                let bg="bg-slate-800", ic="info";
                if(type==="success"){ bg="bg-green-600"; ic="check-circle"; } if(type==="error"){ bg="bg-red-600"; ic="alert-circle"; }
                t.className = `${bg} text-white px-4 py-3 rounded-lg shadow-lg transform transition-all duration-300 translate-y-10 opacity-0 flex items-center gap-3 min-w-[200px]`;
                t.innerHTML = `<i data-lucide="${ic}" class="w-5 h-5"></i><span class="font-bold text-sm">${msg}</span>`;
                c.appendChild(t); lucide.createIcons();
                requestAnimationFrame(() => t.classList.remove('translate-y-10', 'opacity-0'));
                setTimeout(() => { t.classList.add('translate-y-10', 'opacity-0'); setTimeout(() => c.removeChild(t), 300); }, 3000);
            },
            openNumPad(uid) { state.numpad.targetId = uid; state.numpad.value = (dataMgr.getValue(uid) || "").toString(); utils.qs('#numpad-display').innerText = state.numpad.value; utils.qs('#numpad-modal').classList.remove('hidden'); setTimeout(() => utils.qs('#numpad-content').classList.remove('translate-y-full', 'scale-95'), 10); },
            closeNumPad() { utils.qs('#numpad-content').classList.add('translate-y-full', 'scale-95'); setTimeout(() => utils.qs('#numpad-modal').classList.add('hidden'), 200); },
            openSignatureModal() { utils.qs('#signature-modal').classList.remove('hidden'); actions.resizeCanvas(); },
            closeSignatureModal() { utils.qs('#signature-modal').classList.add('hidden'); }
        };

        const actions = {
            init() {
                const d = new Date();
                const today = `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
                const savedDate = localStorage.getItem(LAST_DATE_KEY);
                const initDate = savedDate || today;
                utils.qs('#inputDate').value = initDate;
                
                state.config = storage.loadConfig();
                actions.handleDateChange(initDate);
                ui.renderTabs(); actions.initSignaturePad(); actions.setupDelegation();
            },
            setupDelegation() {
                document.addEventListener('click', (e) => {
                    if (e.target.classList.contains('ox-btn')) {
                        const uid = e.target.dataset.uid; const ox = e.target.dataset.ox;
                        const [l, ei, ii] = uid.split('-');
                        const item = state.config[l][ei].items[ii];
                        if (item.type === 'NUMBER_AND_OX' && ox === 'OK' && !utils.isValueValid(uid, item)) { alert('수치를 정상적으로 입력해야 OK 체크가 가능합니다.'); return; }
                        dataMgr.setOX(uid, ox); ui.updateOXUI(uid); actions.saveOnly(); ui.updateSummary();
                    }
                    if (e.target.classList.contains('num-input')) ui.openNumPad(e.target.dataset.uid);
                });
            },
            handleDateChange(date) {
                if(utils.qs('#inputDate').value !== date) utils.qs('#inputDate').value = date;
                localStorage.setItem(LAST_DATE_KEY, date);
                state.currentDate = date; state.results = storage.loadResults(date); state.signature = state.results.signature || null;
                ui.updateSignatureStatus(); ui.renderChecklist(); ui.updateSummary();
            },
            checkAllGood() {
                const eqs = state.config[state.currentLine] || [];
                eqs.forEach((eq, ei) => {
                    eq.items.forEach((it, ii) => {
                        const uid = `${state.currentLine}-${ei}-${ii}`;
                        if (it.type === 'NUMBER_AND_OX' && !utils.isValueValid(uid, it)) return;
                        dataMgr.setOX(uid, 'OK'); ui.updateOXUI(uid);
                    });
                });
                actions.saveOnly(); ui.updateSummary(); ui.showToast("일괄 합격 처리되었습니다.", "success");
            },
            saveOnly() { if (state.signature) state.results.signature = state.signature; storage.saveResults(state.currentDate, state.results); },
            cvs: null, ctx: null, drawing: false,
            initSignaturePad() {
                this.cvs = document.getElementById('signature-pad'); this.ctx = this.cvs.getContext('2d'); this.resizeCanvas();
                const start = (e) => { e.preventDefault(); const r = this.cvs.getBoundingClientRect(); const x = e.touches ? e.touches[0].clientX : e.clientX; const y = e.touches ? e.touches[0].clientY : e.clientY; this.ctx.moveTo(x - r.left, y - r.top); this.ctx.beginPath(); this.drawing = true; };
                const move = (e) => { e.preventDefault(); if (!this.drawing) return; const r = this.cvs.getBoundingClientRect(); const x = e.touches ? e.touches[0].clientX : e.clientX; const y = e.touches ? e.touches[0].clientY : e.clientY; this.ctx.lineTo(x - r.left, y - r.top); this.ctx.stroke(); };
                const end = () => { this.drawing = false; };
                this.cvs.addEventListener('touchstart', start, {passive: false}); this.cvs.addEventListener('touchmove', move, {passive: false}); this.cvs.addEventListener('touchend', end);
                this.cvs.addEventListener('mousedown', start); this.cvs.addEventListener('mousemove', move); this.cvs.addEventListener('mouseup', end);
            },
            resizeCanvas() { if (this.cvs) { this.cvs.width = this.cvs.offsetWidth; this.cvs.height = this.cvs.offsetHeight; } },
            clearSignature() { this.ctx.clearRect(0, 0, this.cvs.width, this.cvs.height); },
            saveSignature() { state.signature = this.cvs.toDataURL(); actions.saveOnly(); ui.updateSignatureStatus(); ui.closeSignatureModal(); }
        };

        const numpad = {
            key(k) { if(k==='-') state.numpad.value = state.numpad.value.startsWith('-') ? state.numpad.value.substring(1) : '-'+state.numpad.value; else if(k!=='.' || !state.numpad.value.includes('.')) state.numpad.value += k; utils.qs('#numpad-display').innerText = state.numpad.value; },
            back() { state.numpad.value = state.numpad.value.slice(0, -1); utils.qs('#numpad-display').innerText = state.numpad.value; },
            clear() { state.numpad.value = ""; utils.qs('#numpad-display').innerText = state.numpad.value; },
            confirm() {
                const { targetId, value } = state.numpad; dataMgr.setValue(targetId, value);
                const [l, ei, ii] = targetId.split('-'); const it = state.config[l][ei].items[ii];
                if (utils.validateStandard(value, it.standard)) dataMgr.setOX(targetId, 'OK'); else { dataMgr.setOX(targetId, null); alert('기준 이탈'); }
                ui.updateOXUI(targetId); actions.saveOnly(); ui.updateNumUI(targetId, value); ui.closeNumPad(); ui.updateSummary();
            }
        };

        window.saveAndDownloadPDF = async function() {
            if (!state.signature) { alert('⚠️ 서명 필요'); return; }
            const d = utils.qs('#inputDate').value; const { jsPDF } = window.jspdf;
            const container = document.createElement('div'); Object.assign(container.style, { width: '794px', position: 'absolute', left: '-9999px', background: 'white' }); document.body.appendChild(container);
            try {
                // PDF 생성 로직 (단축)
                function createHeader(showTitle) { const h = document.createElement('div'); h.style.cssText = 'padding:20px; border-bottom:2px solid #333; margin-bottom:20px;'; if(showTitle) { const signImg = state.signature ? `<img src="${state.signature}" style="height:50px; width:auto;">` : ""; h.innerHTML = `<h1 class='text-3xl font-black'>SMT Daily Check</h1><div class='flex justify-between mt-4 items-end'><span class='font-bold'>Date: ${d}</span><div><span style="font-weight:bold;">Sign:</span>${signImg}</div></div>`; } return h; }
                const createCard = (l, e, ei) => {
                    const card = document.createElement('div'); card.className = "mb-4 border border-slate-200 rounded-lg overflow-hidden shadow-sm bg-white break-inside-avoid";
                    let h = `<div class="bg-slate-50 border-b border-slate-200 px-4 py-2 font-bold text-sm text-slate-800 flex justify-between"><span>${e.equip}</span><span class="text-xs text-slate-400 font-normal">${l}</span></div><table class="w-full text-xs text-left"><tr class="text-slate-500 border-b border-slate-100 bg-white"><th class="px-4 py-2 w-1/3">Item</th><th class="px-4 py-2 w-1/3">Standard</th><th class="px-4 py-2 text-right">Result</th></tr>`;
                    e.items.forEach((it, ii) => {
                        const uid = `${l}-${ei}-${ii}`; const ox = dataMgr.getOX(uid); const val = dataMgr.getValue(uid);
                        let r = `<span class="text-slate-300">-</span>`; const dv = val ? `<span class="mr-2 font-mono font-bold text-xs">${val} ${it.unit||''}</span>` : '';
                        if (ox === 'OK') r = `${dv}<span class="font-bold text-green-600">PASS</span>`; else if (ox === 'NG') r = `${dv}<span class="font-bold text-red-600">FAIL</span>`;
                        h += `<tr class="border-t border-slate-50"><td class="px-4 py-2"><div class="font-bold text-slate-700">${it.name}</div></td><td class="px-4 py-2 text-slate-500">${it.standard}</td><td class="px-4 py-2 text-right">${r}</td></tr>`;
                    });
                    h += `</table>`; card.innerHTML = h; return card;
                };

                let pageDiv = document.createElement('div'); Object.assign(pageDiv.style, { width: '794px', height: '1123px', padding: '40px', background: 'white', boxSizing: 'border-box', position: 'relative', marginBottom: '20px' });
                pageDiv.appendChild(createHeader(true)); container.appendChild(pageDiv);
                let currentH = 150; const PAGE_H = 1123, MARGIN = 40; let pageList = [pageDiv];

                Object.keys(state.config).forEach(line => {
                    state.config[line].forEach((equip, i) => {
                        const card = createCard(line, equip, i); pageDiv.appendChild(card); const cardH = card.offsetHeight + 16;
                        if (currentH + cardH > PAGE_H - MARGIN) {
                            pageDiv.removeChild(card); pageDiv = document.createElement('div');
                            Object.assign(pageDiv.style, { width: '794px', height: '1123px', padding: '40px', background: 'white', boxSizing: 'border-box', position: 'relative', marginBottom: '20px' });
                            pageDiv.appendChild(createHeader(false)); container.appendChild(pageDiv); pageDiv.appendChild(card); currentH = 100 + cardH; pageList.push(pageDiv);
                        } else { currentH += cardH; }
                    });
                });

                const pdf = new jsPDF('p', 'mm', 'a4'); const pdfW = pdf.internal.pageSize.getWidth(); const pdfH = pdf.internal.pageSize.getHeight();
                for(let i=0; i<pageList.length; i++) { if(i>0) pdf.addPage(); const canvas = await html2canvas(pageList[i], { scale: 2, useCORS: true, logging: false }); const imgData = canvas.toDataURL('image/jpeg', 0.95); pdf.addImage(imgData, 'JPEG', 0, 0, pdfW, pdfH); }
                pdf.save(`SMT_Checklist_${d}.pdf`); ui.showToast("PDF Saved", "success");
            } catch (e) { console.error(e); ui.showToast("PDF Error", "error"); } finally { document.body.removeChild(container); }
        };
        document.addEventListener('DOMContentLoaded', actions.init);
    </script>
</body>
</html>
"""

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
DEFAULT_EQUIPMENT = [{"id": "CIMON-SMT34", "name": "Loader (SLD-120Y)", "func": "메거진 로딩"}, {"id": "CIMON-SMT03", "name": "Screen Printer", "func": "솔더링 설비"}]

# ------------------------------------------------------------------
# 2. 데이터 핸들링 모듈
# ------------------------------------------------------------------
@st.cache_resource
def get_gs_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        if "gcp_service_account" not in st.secrets: st.error("Secrets 설정 오류"); return None
        return gspread.authorize(Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes))
    except Exception as e: st.error(f"연결 실패: {e}"); return None

@st.cache_resource
def get_spreadsheet_object(sheet_name):
    client = get_gs_connection()
    if not client: return None
    try: return client.open(sheet_name)
    except: st.error(f"시트 '{sheet_name}' 없음"); return None

def get_worksheet(sheet_name, worksheet_name, create_if_missing=False, columns=None):
    sh = get_spreadsheet_object(sheet_name)
    if not sh: return None
    try: return sh.worksheet(worksheet_name)
    except gspread.WorksheetNotFound:
        if create_if_missing: ws = sh.add_worksheet(title=worksheet_name, rows=100, cols=20); ws.append_row(columns); return ws
        else: return None

def init_sheets():
    sh = get_spreadsheet_object(GOOGLE_SHEET_NAME)
    if not sh: return
    existing = [ws.title for ws in sh.worksheets()]
    defaults = { SHEET_RECORDS: COLS_RECORDS, SHEET_ITEMS: COLS_ITEMS, SHEET_INVENTORY: COLS_INVENTORY, SHEET_INV_HISTORY: COLS_INV_HISTORY, SHEET_MAINTENANCE: COLS_MAINTENANCE, SHEET_EQUIPMENT: COLS_EQUIPMENT }
    for s, c in defaults.items():
        if s not in existing: ws = sh.add_worksheet(title=s, rows=100, cols=20); ws.append_row(c);
        if s == SHEET_EQUIPMENT and s not in existing: set_with_dataframe(ws, pd.DataFrame(DEFAULT_EQUIPMENT))

if 'sheets_initialized' not in st.session_state: init_sheets(); st.session_state.sheets_initialized = True

@st.cache_data(ttl=5)
def load_data(sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if not ws: return pd.DataFrame()
    try: df = get_as_dataframe(ws, evaluate_formulas=True); return df.dropna(how='all').dropna(axis=1, how='all')
    except: return pd.DataFrame()

def clear_cache(): load_data.clear()

def save_data(df, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws: ws.clear(); set_with_dataframe(ws, df); clear_cache(); return True
    return False

def append_data(data_dict, sheet_name):
    ws = get_worksheet(GOOGLE_SHEET_NAME, sheet_name)
    if ws:
        try: headers = ws.row_values(1)
        except: headers = list(data_dict.keys())
        ws.append_row([str(data_dict.get(h, "")) if not pd.isna(data_dict.get(h, "")) else "" for h in headers])
        clear_cache(); return True
    return False

def update_inventory(code, name, change, reason, user):
    df = load_data(SHEET_INVENTORY)
    if not df.empty and '현재고' in df.columns: df['현재고'] = pd.to_numeric(df['현재고'], errors='coerce').fillna(0).astype(int)
    else: df = pd.DataFrame(columns=COLS_INVENTORY)
    if not df.empty and code in df['품목코드'].values:
        idx = df[df['품목코드'] == code].index[0]
        df.at[idx, '현재고'] = df.at[idx, '현재고'] + change
    else:
        new_row = pd.DataFrame([{"품목코드": code, "제품명": name, "현재고": change}])
        df = pd.concat([df, new_row], ignore_index=True)
    save_data(df, SHEET_INVENTORY)
    append_data({"날짜": datetime.now().strftime("%Y-%m-%d"), "품목코드": code, "구분": "입고" if change > 0 else "출고", "수량": change, "비고": reason, "작성자": user, "입력시간": str(datetime.now())}, SHEET_INV_HISTORY)

# ------------------------------------------------------------------
# 3. 사용자 인증 (기존 로직 복구)
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
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.title("SMT 통합 시스템")
        with st.form("login_form"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign In", type="primary", use_container_width=True):
                if username in USERS and make_hash(password) == USERS[username]["password_hash"]:
                    st.session_state.logged_in = True
                    st.session_state.user_info = USERS[username]
                    st.session_state.user_info["id"] = username
                    st.rerun()
                else: st.error("아이디 또는 비밀번호 오류")
            if st.button("Guest (Viewer)", use_container_width=True):
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
# 4. 메인 UI 및 구조 (요청하신 메뉴 구조 적용)
# ------------------------------------------------------------------
with st.sidebar:
    st.title("Cloud SMT")
    u_info = st.session_state.user_info
    role_badge = "👑 Admin" if u_info["role"] == "admin" else "👤 User" if u_info["role"] == "editor" else "👀 Viewer"
    st.markdown(f"<div style='padding:10px; background:#f1f5f9; border-radius:10px; text-align:center;'><b>{u_info['name']}</b> ({role_badge})</div>", unsafe_allow_html=True)
    
    # [수정된 메뉴 구조]
    menu = st.radio("메뉴 이동", ["📊 대시보드", "🏭 생산관리", "🛠 설비보전관리", "✅ 일일점검관리", "⚙ 기준정보관리"])
    st.divider()
    if st.button("로그아웃"): st.session_state.logged_in = False; st.rerun()

st.markdown(f'<div class="dashboard-header"><h3>{menu}</h3></div>', unsafe_allow_html=True)

# ------------------------------------------------------------------
# 5. 각 메뉴별 기능 구현 (기존 코드 100% 이식)
# ------------------------------------------------------------------

if menu == "📊 대시보드":
    # 실제 데이터를 불러와서 대시보드 구성
    df_prod = load_data(SHEET_RECORDS)
    df_maint = load_data(SHEET_MAINTENANCE)
    
    prod_sum = 0
    maint_cost = 0
    today_prod = 0
    
    if not df_prod.empty:
        df_prod['수량'] = pd.to_numeric(df_prod['수량'], errors='coerce').fillna(0)
        prod_sum = df_prod['수량'].sum()
        df_prod['날짜'] = pd.to_datetime(df_prod['날짜'])
        today_prod = df_prod[df_prod['날짜'].dt.date == datetime.now().date()]['수량'].sum()
        
    if not df_maint.empty:
        df_maint['비용'] = pd.to_numeric(df_maint['비용'], errors='coerce').fillna(0)
        maint_cost = df_maint['비용'].sum()

    col1, col2, col3 = st.columns(3)
    col1.metric("총 누적 생산량", f"{prod_sum:,.0f} EA", f"오늘 {today_prod:,.0f} EA")
    col2.metric("총 정비 비용", f"{maint_cost:,.0f} 원")
    col3.metric("시스템 상태", "정상 가동 중")
    
    if not df_prod.empty and HAS_ALTAIR:
        st.markdown("##### 📈 주간 생산 추이")
        chart_data = df_prod.groupby('날짜')['수량'].sum().reset_index()
        c = alt.Chart(chart_data).mark_line(point=True).encode(x='날짜', y='수량').interactive()
        st.altair_chart(c, use_container_width=True)

elif menu == "🏭 생산관리":
    # 기존 '생산관리' 탭 내용 복원 (기준정보 제외)
    t1, t2, t3 = st.tabs(["📝 실적 등록", "📦 재고 현황", "📑 일일 보고서"])
    
    with t1:
        c1, c2 = st.columns([1, 1.5])
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
                    auto_deduct = st.checkbox("📦 반제품 재고 자동 차감", value=True) if cat in ["후공정", "후공정 외주"] else False
                    
                    def save_production():
                        cur_code = st.session_state.code_in; cur_name = st.session_state.name_in; cur_qty = st.session_state.prod_qty
                        if cur_name:
                            rec = {"날짜":str(date), "구분":cat, "품목코드":cur_code, "제품명":cur_name, "수량":cur_qty, "입력시간":str(datetime.now()), "작성자":get_user_id()}
                            if append_data(rec, SHEET_RECORDS):
                                if cat in ["후공정", "후공정 외주"]: 
                                    if auto_deduct: update_inventory(cur_code, cur_name, -cur_qty, f"생산출고({cat})", get_user_id())
                                else: update_inventory(cur_code, cur_name, cur_qty, f"생산입고({cat})", get_user_id())
                                st.session_state.code_in = ""; st.session_state.name_in = ""; st.session_state.prod_qty = 100
                                st.toast("저장 완료!", icon="✅")
                        else: st.toast("제품명을 입력해주세요.", icon="⚠️")
                    st.button("저장하기", type="primary", use_container_width=True, on_click=save_production)
            else: st.warning("🔒 뷰어 모드")

        with c2:
            st.markdown("#### 📋 최근 등록 내역")
            df = load_data(SHEET_RECORDS)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(50)
                if IS_ADMIN:
                    edited_df = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic", key="prod_editor")
                    if st.button("변경사항 저장", type="secondary"): save_data(edited_df, SHEET_RECORDS); st.rerun()
                else: st.dataframe(df, use_container_width=True, hide_index=True)

    with t2:
        df_inv = load_data(SHEET_INVENTORY)
        if not df_inv.empty:
            df_inv['현재고'] = pd.to_numeric(df_inv['현재고'], errors='coerce').fillna(0).astype(int)
            search = st.text_input("🔍 재고 검색", placeholder="품목명/코드")
            if search: df_inv = df_inv[df_inv['품목코드'].str.contains(search, case=False) | df_inv['제품명'].str.contains(search, case=False)]
            if IS_ADMIN:
                edited_inv = st.data_editor(df_inv, use_container_width=True, hide_index=True, num_rows="dynamic", key="inv_editor")
                if st.button("재고 저장"): save_data(edited_inv, SHEET_INVENTORY); st.rerun()
            else: st.dataframe(df_inv, use_container_width=True, hide_index=True)

    with t3:
        # PDF 리포트 기능 복구
        st.markdown("#### 📑 SMT 일일 생산현황 (PDF)")
        report_date = st.date_input("보고서 날짜 선택", datetime.now())
        df = load_data(SHEET_RECORDS)
        if not df.empty:
            mask_date = pd.to_datetime(df['날짜']).dt.date == report_date
            daily_df = df[mask_date].copy()
            daily_df = daily_df[~daily_df['구분'].astype(str).str.contains("외주")]
            if not daily_df.empty:
                st.dataframe(daily_df[['구분', '품목코드', '제품명', '수량']], use_container_width=True, hide_index=True)
                # HTML PDF 생성 로직 (단축)
                pdf_html = f"""
                <div id="pdf-content" style="display:none; font-family:'Noto Sans KR'; padding:20mm; width:210mm; background:white;">
                    <h1 style="text-align:center; border-bottom:2px solid #333;">SMT Daily Report</h1>
                    <p>Date: {report_date}</p>
                    <table style="width:100%; border-collapse:collapse; margin-top:20px; font-size:12px;">
                        <thead><tr style="background:#f2f2f2;"><th style="border:1px solid #ddd; padding:8px;">Cat</th><th style="border:1px solid #ddd;">Code</th><th style="border:1px solid #ddd;">Name</th><th style="border:1px solid #ddd;">Qty</th></tr></thead>
                        <tbody>{''.join([f"<tr><td style='border:1px solid #ddd; padding:8px;'>{r['구분']}</td><td style='border:1px solid #ddd;'>{r['품목코드']}</td><td style='border:1px solid #ddd;'>{r['제품명']}</td><td style='border:1px solid #ddd; text-align:right;'>{r['수량']:,}</td></tr>" for _, r in daily_df.iterrows()])}</tbody>
                    </table>
                </div>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
                <script>
                    async function generatePDF() {{
                        const {{ jsPDF }} = window.jspdf; const el = document.getElementById('pdf-content');
                        el.style.display = 'block'; el.style.position = 'absolute'; el.style.top = '-9999px';
                        const canvas = await html2canvas(el, {{ scale: 2 }});
                        const pdf = new jsPDF('p', 'mm', 'a4'); pdf.addImage(canvas.toDataURL('image/png'), 'PNG', 0, 0, 210, (canvas.height*210)/canvas.width);
                        pdf.save("Production_Report.pdf"); el.style.display = 'none';
                    }}
                </script>
                <button onclick="generatePDF()" style="background:#ef4444; color:white; padding:10px 20px; border:none; border-radius:5px; cursor:pointer;">📄 PDF 다운로드</button>
                """
                components.html(pdf_html, height=100)
            else: st.warning("데이터 없음")

elif menu == "🛠 설비보전관리":
    # 기존 '설비보전관리' 탭 내용 복원
    t1, t2, t3 = st.tabs(["📝 정비 이력 등록", "📋 이력 조회", "📊 분석 및 리포트"])
    
    with t1:
        c1, c2 = st.columns([1, 1.5])
        with c1:
            if IS_EDITOR:
                with st.container(border=True):
                    st.markdown("#### 🔧 정비 이력 등록")
                    eq_df = load_data(SHEET_EQUIPMENT)
                    eq_map = dict(zip(eq_df['id'], eq_df['name'])) if not eq_df.empty else {}
                    f_date = st.date_input("작업 날짜")
                    f_eq = st.selectbox("대상 설비", list(eq_map.keys()), format_func=lambda x: f"[{x}] {eq_map[x]}")
                    f_type = st.selectbox("작업 구분", ["PM (예방)", "BM (고장)", "CM (개선)"])
                    f_desc = st.text_area("작업 내용", height=80)
                    f_cost = st.number_input("소요 비용", step=1000)
                    f_down = st.number_input("비가동 시간(분)", step=10)
                    
                    if st.button("이력 저장", type="primary"):
                        rec = {"날짜":str(f_date), "설비ID":f_eq, "설비명":eq_map[f_eq], "작업구분":f_type, "작업내용":f_desc, "비용":f_cost, "비가동시간":f_down, "입력시간":str(datetime.now()), "작성자":get_user_id()}
                        if append_data(rec, SHEET_MAINTENANCE): st.success("저장 완료"); st.rerun()
            else: st.warning("권한 없음")

        with c2:
            st.markdown("#### 📋 최근 정비 내역")
            df = load_data(SHEET_MAINTENANCE)
            if not df.empty:
                df = df.sort_values("입력시간", ascending=False).head(50)
                if IS_ADMIN:
                    edited = st.data_editor(df, use_container_width=True, hide_index=True, num_rows="dynamic", key="maint_edit")
                    if st.button("변경사항 저장 (정비)"): save_data(edited, SHEET_MAINTENANCE); st.rerun()
                else: st.dataframe(df, use_container_width=True, hide_index=True)

    with t2:
        df_hist = load_data(SHEET_MAINTENANCE)
        st.dataframe(df_hist, use_container_width=True)

    with t3:
        st.markdown("#### 📊 설비 고장 분석")
        df = load_data(SHEET_MAINTENANCE)
        if not df.empty and '날짜' in df.columns:
            df['날짜'] = pd.to_datetime(df['날짜'])
            df['비용'] = pd.to_numeric(df['비용']).fillna(0)
            st.metric("총 정비 비용", f"{df['비용'].sum():,.0f} 원")
            if HAS_ALTAIR:
                c = alt.Chart(df).mark_bar().encode(x='작업구분', y='비용', color='작업구분').interactive()
                st.altair_chart(c, use_container_width=True)

elif menu == "✅ 일일점검관리":
    # [수정] 기존 태블릿용 HTML 화면을 이곳에 배치 (현장 입력용)
    tab1, tab2 = st.tabs(["📱 현장 점검 (Tablet)", "📊 점검 현황"])
    
    with tab1:
        st.caption("※ 태블릿 기기에서 전체 화면으로 사용하세요. (날짜 버그 수정됨)")
        # 복구된 HTML 코드 렌더링
        components.html(DAILY_CHECK_HTML, height=1000, scrolling=True)
    
    with tab2:
        st.info("점검 이력 데이터 연동 준비 중...")

elif menu == "⚙ 기준정보관리":
    # [이동] 생산관리/설비관리에서 분리된 기준정보 관리 기능을 이곳으로 통합
    t1, t2 = st.tabs(["📦 품목 관리", "🏭 설비 관리"])
    
    with t1:
        if IS_ADMIN:
            df_items = load_data(SHEET_ITEMS)
            edited = st.data_editor(df_items, num_rows="dynamic", use_container_width=True, key="item_master_edit")
            if st.button("품목 기준정보 저장", type="primary"): save_data(edited, SHEET_ITEMS); st.rerun()
        else: st.dataframe(load_data(SHEET_ITEMS))
        
    with t2:
        if IS_ADMIN:
            df_eq = load_data(SHEET_EQUIPMENT)
            edited = st.data_editor(df_eq, num_rows="dynamic", use_container_width=True, key="eq_master_edit")
            if st.button("설비 목록 저장", type="primary"): save_data(edited, SHEET_EQUIPMENT); st.rerun()
        else: st.dataframe(load_data(SHEET_EQUIPMENT))