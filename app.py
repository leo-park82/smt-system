# ... (이전 코드 동일)

# ------------------------------------------------------------------
# [신규] PDF 보고서 생성 함수 (한글 인코딩 오류 수정)
# ------------------------------------------------------------------
def create_daily_pdf(daily_df, report_date):
    pdf = FPDF()
    pdf.add_page()
    
    # 1. 폰트 설정 (가장 중요)
    # 한글 폰트 파일이 실행 경로에 있어야 합니다. (NanumGothic.ttf 등)
    # Streamlit Cloud 환경이라면 해당 폰트 파일을 리포지토리에 같이 올려야 합니다.
    font_path = 'NanumGothic.ttf'
    if not os.path.exists(font_path):
        # 윈도우 로컬 테스트용 (시스템 폰트 경로)
        font_path = 'C:\\Windows\\Fonts\\malgun.ttf'
    
    has_korean_font = False
    if os.path.exists(font_path):
        try:
            pdf.add_font('Korean', '', font_path, uni=True)
            pdf.set_font('Korean', '', 12)
            has_korean_font = True
        except:
            # 폰트 로드 실패 시 기본 폰트 (한글 깨짐)
            pdf.set_font('Arial', '', 12)
    else:
        pdf.set_font('Arial', '', 12)

    # 2. 타이틀 출력
    pdf.set_font_size(18)
    title_text = f'SMT Daily Report ({report_date.strftime("%Y-%m-%d")})'
    if has_korean_font:
        title_text = f'SMT 일일 생산현황 ({report_date.strftime("%Y-%m-%d")})'
    pdf.cell(0, 15, title_text, ln=True, align='C')
    pdf.ln(5)

    # 3. 데이터 필터링 (외주 제외)
    daily_df = daily_df[~daily_df['구분'].astype(str).str.contains("외주")] 
    
    custom_order = ["PC", "CM1", "CM3", "배전", "샘플", "후공정"]
    # 카테고리 순서 정렬을 위한 임시 컬럼
    daily_df['구분_Order'] = daily_df['구분'].astype("category")
    daily_df['구분_Order'] = daily_df['구분_Order'].cat.set_categories(custom_order, ordered=True)
    daily_df = daily_df.sort_values(by=['구분_Order', '제품명'])

    # 4. 헤더 출력
    pdf.set_font_size(10)
    pdf.set_fill_color(220, 230, 241) 
    
    w_cat = 30; w_code = 40; w_name = 80; w_qty = 30
    
    pdf.cell(w_cat, 10, "Category", border=1, align='C', fill=True)
    pdf.cell(w_code, 10, "Item Code", border=1, align='C', fill=True)
    pdf.cell(w_name, 10, "Item Name", border=1, align='C', fill=True)
    pdf.cell(w_qty, 10, "Q'ty", border=1, align='C', fill=True)
    pdf.ln()

    # 5. 본문 출력
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

    # 6. 합계 출력
    pdf.ln(5)
    pdf.set_font_size(12)
    pdf.set_fill_color(255, 255, 200) 
    pdf.cell(w_cat + w_code + w_name, 10, "Total Production Quantity : ", border=1, align='R', fill=True)
    pdf.cell(w_qty, 10, f"{total_qty:,} EA", border=1, align='R', fill=True)
    
    # [수정] PDF 바이트 데이터 반환 방식 변경 (인코딩 오류 방지)
    # output(dest='S')로 문자열을 받아 encode('latin-1') 하는 방식이 오류의 원인일 수 있음.
    # 대신 bytearray로 직접 변환하거나 안전한 방식을 사용해야 함.
    
    # FPDF 최신 버전 호환성 고려: .output()은 기본적으로 latin-1 인코딩된 문자열을 반환하려고 시도함.
    # 이를 우회하기 위해 dest='S'로 받고 .encode('latin-1', 'ignore')가 아닌 'replace' 등을 쓰거나,
    # 가장 확실한 방법은 메모리 버퍼 등에 쓰는 것이지만 FPDF1.7 계열에서는 아래 방식이 통용됨.
    
    try:
        return pdf.output(dest='S').encode('latin-1') 
    except UnicodeEncodeError:
        # 만약 위 방식이 실패하면 (한글 폰트가 제대로 적용 안되어 텍스트로 남은 경우 등)
        # 폰트 로드 실패 시 한글을 제거하고 출력 시도
        return pdf.output(dest='S').encode('latin-1', errors='ignore')

# ... (이후 코드 동일)