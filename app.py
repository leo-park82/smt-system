import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import requests
import json

st.set_page_config(
    page_title="SMT 생산관리 시스템",
    layout="wide"
)

# ===============================
# 전역 세션 상태
# ===============================
if "login" not in st.session_state:
    st.session_state.login = True  # 기존 코드 기준: 로그인 이미 통과 상태

if "prod_df" not in st.session_state:
    st.session_state.prod_df = pd.DataFrame(columns=[
        "일자", "공정", "라인", "모델", "품명",
        "LOT", "수량", "작업자", "비고"
    ])

if "inspect_html_loaded" not in st.session_state:
    st.session_state.inspect_html_loaded = False
# ===============================
# 사이드바 메뉴
# ===============================
st.sidebar.title("📌 SMT 통합 관리")

menu = st.sidebar.radio(
    "메뉴 선택",
    [
        "대시보드",
        "일일 생산 입력",
        "일일 생산현황",
        "일일 생산보고서",
        "설비보전관리",
        "일일점검"
    ]
)

base_date = st.sidebar.date_input(
    "기준일자",
    value=date.today()
)
if menu == "대시보드":
    st.title("📊 SMT 생산 대시보드")

    df = st.session_state.prod_df
    day_df = df[df["일자"] == base_date]

    c1, c2, c3 = st.columns(3)

    c1.metric("금일 생산 LOT", len(day_df))
    c2.metric("금일 총 생산수량", f"{day_df['수량'].sum():,} EA")
    c3.metric("누적 생산 LOT", len(df))

    if not day_df.empty:
        st.subheader("공정별 생산량")
        st.bar_chart(day_df.groupby("공정")["수량"].sum())
if menu == "일일 생산 입력":
    st.title("✏️ 일일 생산 입력")

    with st.form("prod_form"):
        c1, c2, c3 = st.columns(3)

        with c1:
            공정 = st.selectbox("공정", ["PC", "CM1", "CM2", "배전", "후공정"])
            라인 = st.text_input("라인")
            작업자 = st.text_input("작업자")

        with c2:
            모델 = st.text_input("모델")
            품명 = st.text_input("품명")
            LOT = st.text_input("LOT")

        with c3:
            수량 = st.number_input("수량", min_value=0, step=1)
            비고 = st.text_input("비고")

        save = st.form_submit_button("저장")

        if save:
            new_row = {
                "일자": base_date,
                "공정": 공정,
                "라인": 라인,
                "모델": 모델,
                "품명": 품명,
                "LOT": LOT,
                "수량": 수량,
                "작업자": 작업자,
                "비고": 비고
            }
            st.session_state.prod_df = pd.concat(
                [st.session_state.prod_df, pd.DataFrame([new_row])],
                ignore_index=True
            )
            st.success("저장 완료")
if menu == "일일 생산현황":
    st.title("📊 일일 생산현황")

    df = st.session_state.prod_df
    day_df = df[df["일자"] == base_date]

    if day_df.empty:
        st.warning("데이터 없음")
    else:
        st.dataframe(day_df, use_container_width=True)

        c1, c2 = st.columns(2)
        c1.table(day_df.groupby("공정")["수량"].sum().reset_index())
        c2.table(day_df.groupby("라인")["수량"].sum().reset_index())


if menu == "일일 생산보고서":
    st.title("📄 일일 생산보고서")

    df = st.session_state.prod_df
    rpt = df[df["일자"] == base_date]

    if rpt.empty:
        st.warning("보고서 데이터 없음")
    else:
        st.dataframe(rpt, use_container_width=True)

        html = f"""
        <div id="pdf-area">
        <h2 style="text-align:center;">SMT 일일 생산보고서</h2>
        <p style="text-align:center;">{base_date}</p>
        {rpt.to_html(index=False)}
        </div>
        """
        st.markdown(html, unsafe_allow_html=True)
st.components.v1.html("""
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>
<button onclick="makePDF()">PDF 다운로드</button>
<script>
async function makePDF(){
  const { jsPDF } = window.jspdf;
  const el = document.getElementById("pdf-area");
  const canvas = await html2canvas(el, {scale:2});
  const img = canvas.toDataURL("image/png");
  const pdf = new jsPDF("p","mm","a4");
  const w = pdf.internal.pageSize.getWidth();
  const h = canvas.height * w / canvas.width;
  pdf.addImage(img,"PNG",0,0,w,h);
  pdf.save("SMT_Daily_Report.pdf");
}
</script>
""", height=120)

if menu == "설비보전관리":
    st.title("🛠 설비보전관리")
    st.info("기존 설비보전 관리 로직 유지 영역")

if menu == "일일점검":
    st.title("📝 일일점검")
    st.markdown("<!-- 기존 대형 HTML 점검표 유지 -->", unsafe_allow_html=True)
