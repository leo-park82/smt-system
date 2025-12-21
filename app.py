import streamlit as st
import pandas as pd
from datetime import date

# -----------------------------
# 기본 설정
# -----------------------------
st.set_page_config(
    page_title="SMT 생산관리 시스템",
    layout="wide"
)

# -----------------------------
# 데이터 (실제론 DB / 엑셀 연동)
# -----------------------------
data = [
    {"구분": "PC", "제품명": "메인보드 A", "수량": 120, "라인": "L1"},
    {"구분": "PC", "제품명": "메인보드 B", "수량": 90, "라인": "L2"},
    {"구분": "CM1", "제품명": "컨트롤러 A", "수량": 80, "라인": "L1"},
    {"구분": "배전", "제품명": "전원모듈 A", "수량": 60, "라인": "L3"},
    {"구분": "후공정", "제품명": "완제품 A", "수량": 45, "라인": "L4"},
]

df = pd.DataFrame(data)

# -----------------------------
# 사이드바
# -----------------------------
st.sidebar.title("📌 생산관리 메뉴")
menu = st.sidebar.radio(
    "메뉴 선택",
    ["일일 생산현황", "일일 생산보고서"]
)

report_date = st.sidebar.date_input(
    "보고일자",
    value=date.today()
)

# -----------------------------
# 1️⃣ 일일 생산현황
# -----------------------------
if menu == "일일 생산현황":
    st.title("📊 SMT 일일 생산현황")

    st.dataframe(df, use_container_width=True)

    st.subheader("공정별 생산 합계")
    summary = df.groupby("구분")["수량"].sum().reset_index()
    st.table(summary)

# -----------------------------
# 2️⃣ 일일 생산보고서
# -----------------------------
if menu == "일일 생산보고서":
    st.title("📄 일일 생산보고서")

    total_qty = df["수량"].sum()

    st.markdown(f"""
    **보고일자** : {report_date.strftime("%Y-%m-%d")}  
    **총 생산수량** : {total_qty:,} EA
    """)

    st.dataframe(df, use_container_width=True)

    # -----------------------------
    # PDF 출력용 HTML
    # -----------------------------
    html = f"""
    <div id="pdf-area" style="width:100%; font-family:Arial;">
        <h2 style="text-align:center;">SMT 일일 생산 보고서</h2>
        <p style="text-align:center;">보고일자 : {report_date.strftime("%Y-%m-%d")}</p>

        <table border="1" cellpadding="6" cellspacing="0"
               style="width:100%; border-collapse:collapse; font-size:13px;">
            <thead>
                <tr style="background:#f2f2f2;">
                    <th>구분</th>
                    <th>라인</th>
                    <th>제품명</th>
                    <th>수량</th>
                </tr>
            </thead>
            <tbody>
    """

    for _, r in df.iterrows():
        html += f"""
        <tr>
            <td>{r['구분']}</td>
            <td>{r['라인']}</td>
            <td>{r['제품명']}</td>
            <td style="text-align:right;">{r['수량']}</td>
        </tr>
        """

    html += f"""
            </tbody>
        </table>

        <p style="margin-top:10px;">
            <strong>총 생산수량 :</strong> {total_qty:,} EA
        </p>
    </div>
    """

    st.markdown(html, unsafe_allow_html=True)

    # -----------------------------
    # PDF 다운로드 버튼 (JS)
    # -----------------------------
    pdf_js = f"""
    <script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js"></script>

    <button onclick="downloadPDF()" style="
        margin-top:20px;
        padding:10px 25px;
        font-size:16px;
        cursor:pointer;">
        📄 PDF 다운로드
    </button>

    <script>
    async function downloadPDF() {{
        const {{ jsPDF }} = window.jspdf;
        const pdf = new jsPDF('p', 'mm', 'a4');

        const element = document.getElementById("pdf-area");
        const canvas = await html2canvas(element, {{ scale: 2 }});
        const imgData = canvas.toDataURL("image/png");

        const imgWidth = 210;
        const imgHeight = canvas.height * imgWidth / canvas.width;

        pdf.addImage(imgData, 'PNG', 0, 10, imgWidth, imgHeight);
        pdf.save("SMT_일일생산보고서_{report_date}.pdf");
    }}
    </script>
    """

    st.components.v1.html(pdf_js, height=120)
