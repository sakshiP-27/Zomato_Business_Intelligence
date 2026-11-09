"""Write the insights PDF and the 13-slide deck from the Week 4 numbers."""

from pathlib import Path

from fpdf import FPDF
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
MD = (ROOT / "reports" / "business_insights_report.md").read_text(encoding="utf-8")
PDF = ROOT / "reports" / "business_insights_report.pdf"
PPTX = ROOT / "reports" / "zomato_final_presentation.pptx"
FONT = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONTB = Path(r"C:\Windows\Fonts\segoeuib.ttf")


def write_pdf() -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    if FONT.exists():
        pdf.add_font("Segoe", "", str(FONT))
        pdf.add_font("Segoe", "B", str(FONTB if FONTB.exists() else FONT))
        family = "Segoe"
    else:
        family = "Helvetica"
    for raw in MD.splitlines():
        line = raw.rstrip()
        if line.startswith("# "):
            pdf.ln(2)
            pdf.set_x(pdf.l_margin)
            pdf.set_font(family, "B", 16)
            pdf.multi_cell(0, 8, line[2:])
        elif line.startswith("## "):
            pdf.ln(3)
            pdf.set_x(pdf.l_margin)
            pdf.set_font(family, "B", 13)
            pdf.multi_cell(0, 7, line[3:])
        elif line.startswith("**") and line.endswith("**"):
            pdf.set_x(pdf.l_margin)
            pdf.set_font(family, "B", 11)
            pdf.multi_cell(0, 6, line.strip("*"))
        elif not line:
            pdf.ln(2)
        else:
            pdf.set_x(pdf.l_margin)
            pdf.set_font(family, "", 11)
            pdf.multi_cell(0, 6, line.replace("**", ""))
    pdf.output(str(PDF))
    print(f"  {PDF.relative_to(ROOT)}")


INK = RGBColor(0x26, 0x46, 0x53)
RED = RGBColor(0xE2, 0x37, 0x44)
TEAL = RGBColor(0x2A, 0x9D, 0x8F)
GOLD = RGBColor(0xC4, 0x8A, 0x1A)
CREAM = RGBColor(0xF7, 0xF2, 0xF2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
MUTED = RGBColor(0x6B, 0x5E, 0x5E)
CARD = RGBColor(0xFF, 0xFB, 0xFB)
SLATE = RGBColor(0x3D, 0x5A, 0x66)

W = Inches(13.333)
H = Inches(7.5)


def _anchor(tf, anchor):
    tf._txBody.bodyPr.set("anchor", anchor)


def rect(slide, l, t, w, h, fill):
    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, l, t, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    shape.shadow.inherit = False
    return shape


def card(slide, l, t, w, h, fill=WHITE):
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, l, t, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    shape.line.fill.background()
    shape.shadow.inherit = False
    try:
        shape.adjustments[0] = 0.08
    except Exception:
        pass
    return shape


def write(slide, l, t, w, h, lines, align=PP_ALIGN.LEFT, anchor="t"):
    box = slide.shapes.add_textbox(l, t, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    tf.margin_left = Emu(0)
    tf.margin_right = Emu(0)
    tf.margin_top = Emu(0)
    tf.margin_bottom = Emu(0)
    _anchor(tf, anchor)
    for i, line in enumerate(lines):
        text, size, color, bold = line
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.space_before = Pt(0)
        p.space_after = Pt(0)
        run = p.add_run()
        run.text = text
        run.font.name = "Segoe UI"
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
    return box


def blank(prs):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    rect(slide, 0, 0, W, H, CREAM)
    return slide


def chrome(slide, kicker, title, number, notes):
    rect(slide, 0, 0, W, Inches(0.08), RED)
    write(slide, Inches(0.55), Inches(0.28), Inches(10), Inches(0.28), [(kicker, 12, RED, True)])
    write(slide, Inches(0.55), Inches(0.54), Inches(12.2), Inches(0.85), [(title, 28, INK, True)])
    write(slide, Inches(0.55), Inches(7.12), Inches(8), Inches(0.24), [("Zomato Business Intelligence  ·  Sakshi", 11, MUTED, False)])
    write(slide, Inches(11.4), Inches(7.12), Inches(1.4), Inches(0.24), [(f"{number}  /  13", 11, MUTED, False)], PP_ALIGN.RIGHT)
    slide.notes_slide.notes_text_frame.text = notes


def stat(slide, l, t, w, h, value, label, accent=RED):
    card(slide, l, t, w, h)
    rect(slide, l, t, Inches(0.08), h, accent)
    write(slide, l + Inches(0.28), t + Inches(0.28), w - Inches(0.45), Inches(0.85), [(value, 32, INK, True)])
    write(slide, l + Inches(0.28), t + Inches(1.2), w - Inches(0.45), Inches(0.85), [(label, 15, MUTED, False)])


def write_pptx() -> None:
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    s = prs.slides.add_slide(prs.slide_layouts[6])
    rect(s, 0, 0, W, H, INK)
    rect(s, 0, 0, Inches(0.18), H, RED)
    write(s, Inches(0.7), Inches(1.45), Inches(8), Inches(0.3), [("FINAL READOUT  ·  9 NOVEMBER 2026", 14, GOLD, True)])
    write(s, Inches(0.7), Inches(1.95), Inches(11.5), Inches(1.8), [("A delivery dataset\nwith no delivery signal", 44, WHITE, True)])
    write(s, Inches(0.7), Inches(4.15), Inches(10), Inches(0.4), [("Sakshi   ·   Zomato Business Intelligence", 18, RGBColor(0xF7, 0xF2, 0xF2), False)])
    write(s, Inches(0.7), Inches(6.35), Inches(11), Inches(0.35), [("20,475 orders    ·    25 cities    ·    reference date 31 Dec 2024", 14, RGBColor(0xE9, 0xC4, 0x6A), False)])
    s.notes_slide.notes_text_frame.text = "Open with the conclusion, not the pipeline. Every number is the Week 1 definition, checked against SQL and Python."

    s = blank(prs)
    chrome(s, "THE BUSINESS PROBLEM", "Late orders are common. This data cannot say why.", 2,
           "KPI definitions are in documentation/kpi_definitions.md. Reference date is 31 Dec 2024.")
    stat(s, Inches(0.55), Inches(1.85), Inches(3.9), Inches(2.35), "22.3%", "of all orders are cancelled. There is no reason column.")
    stat(s, Inches(4.7), Inches(1.85), Inches(3.9), Inches(2.35), "24.9%", "of completed orders take longer than 45 minutes.", TEAL)
    stat(s, Inches(8.85), Inches(1.85), Inches(3.9), Inches(2.35), "40.1", "minutes is the average. The 90th percentile is 61.", GOLD)
    write(s, Inches(0.55), Inches(4.55), Inches(12.2), Inches(1.8), [
        ("City, rain, traffic, and hour were tested. None of them separates late orders in a way you can staff against.", 20, INK, False),
    ])

    s = blank(prs)
    chrome(s, "HOW THE WORK IS BUILT", "One pipeline. Three places that must agree.", 3,
           "Order city is the restaurant city. Customer city stays on the customer. DAX only aggregates.")
    steps = [
        ("01", "PostgreSQL", "Raw orders land in the warehouse. SQL owns the restaurant score."),
        ("02", "Python", "Cleaning, features, and both models are computed once and exported."),
        ("03", "Power BI", "Six pages read those exports. They do not invent a second late rule."),
    ]
    for i, (num, name, body) in enumerate(steps):
        left = Inches(0.55 + i * 4.2)
        card(s, left, Inches(2.05), Inches(3.9), Inches(3.7))
        write(s, left + Inches(0.3), Inches(2.3), Inches(3.3), Inches(0.55), [(num, 28, RED, True)])
        write(s, left + Inches(0.3), Inches(3.05), Inches(3.3), Inches(0.5), [(name, 22, INK, True)])
        write(s, left + Inches(0.3), Inches(3.7), Inches(3.3), Inches(1.5), [(body, 16, MUTED, False)])

    s = blank(prs)
    chrome(s, "DATA QUALITY", "Every logged quality issue was fixed.", 4,
           "Ambiguous slash dates and the unusable distance feature are documented, not hidden.")
    card(s, Inches(0.55), Inches(1.9), Inches(5.3), Inches(4.4), INK)
    write(s, Inches(0.9), Inches(2.3), Inches(4.6), Inches(1.5), [("100%", 60, WHITE, True)])
    write(s, Inches(0.9), Inches(4.0), Inches(4.6), Inches(1.6), [("of logged data-quality issues resolved before any model or page was built.", 20, RGBColor(0xF7, 0xF2, 0xF2), False)])
    stat(s, Inches(6.15), Inches(1.9), Inches(6.6), Inches(2.0), "20,475", "orders. Python and SQL count the same rows.", TEAL)
    stat(s, Inches(6.15), Inches(4.15), Inches(6.6), Inches(2.15), "To the paisa", "Delivered revenue matches across SQL and Python.", GOLD)

    s = blank(prs)
    chrome(s, "REVENUE", "Revenue is flat. Kolkata leads a wide field.", 5,
           "Completed revenue, Delivered plus Delivered Late, is ₹52.36 lakh across 13,351 orders. Delivered-only is ₹44.06 lakh.")
    card(s, Inches(0.55), Inches(1.85), Inches(6.3), Inches(4.5), INK)
    write(s, Inches(0.9), Inches(2.2), Inches(5.6), Inches(0.4), [("COMPLETED REVENUE", 13, GOLD, True)])
    write(s, Inches(0.9), Inches(2.7), Inches(5.6), Inches(1.2), [("₹52.36L", 54, WHITE, True)])
    write(s, Inches(0.9), Inches(4.15), Inches(5.6), Inches(1.5), [("Delivered and Delivered Late, positive amount. About ₹392 an order.", 18, RGBColor(0xF7, 0xF2, 0xF2), False)])
    stat(s, Inches(7.15), Inches(1.85), Inches(5.6), Inches(1.35), "+0.4%", "2024 versus 2023. Monthly totals stay between ₹1.60L and ₹2.06L.", TEAL)
    stat(s, Inches(7.15), Inches(3.4), Inches(5.6), Inches(1.35), "₹2.02L", "Kolkata, the largest city. Same figure in SQL and Python.", RED)
    stat(s, Inches(7.15), Inches(4.95), Inches(5.6), Inches(1.4), "₹3.07L", "South Indian, the largest cuisine. 34% above the tenth.", GOLD)

    s = blank(prs)
    chrome(s, "DELIVERY OPERATIONS", "Hour 19 is busy. It is not slower.", 6,
           "Traffic matched only 5.1% of valid deliveries. Do not staff extra partners from this chart.")
    stat(s, Inches(0.55), Inches(1.85), Inches(4.0), Inches(2.3), "22.2%", "of orders fall in 19:00–22:00.", RED)
    stat(s, Inches(4.75), Inches(1.85), Inches(4.0), Inches(2.3), "12.3%", "late at that peak, on the EDA delivered subset.", TEAL)
    stat(s, Inches(8.95), Inches(1.85), Inches(3.85), Inches(2.3), "12.1%", "late off-peak. The gap is not a staffing plan.", GOLD)
    card(s, Inches(0.55), Inches(4.4), Inches(12.25), Inches(2.3))
    write(s, Inches(0.9), Inches(4.7), Inches(11.6), Inches(1.7), [
        ("City, rain, and traffic tests are not significant.", 22, INK, True),
        ("Do not add riders for rain or for 7 pm on this evidence.", 18, MUTED, False),
    ])

    s = blank(prs)
    chrome(s, "DELIVERY MODEL", "The model does not beat predicting the average.", 7,
           "Random Forest won a fair comparison and still missed both targets. Feedback and the broken distance feature stayed out.")
    headers = [(Inches(0.55), "WHAT WE GOT"), (Inches(4.7), "TARGET"), (Inches(8.85), "VERDICT")]
    for left, label in headers:
        write(s, left, Inches(1.75), Inches(3.8), Inches(0.35), [(label, 13, MUTED, True)])
    rows = [
        ("R²  −0.0022", "At least 0.75", "Miss"),
        ("RMSE  9.8 min", "At most 6 min", "Miss"),
    ]
    for i, (got, target, verdict) in enumerate(rows):
        top = Inches(2.25 + i * 2.15)
        card(s, Inches(0.55), top, Inches(3.9), Inches(1.9))
        write(s, Inches(0.8), top + Inches(0.5), Inches(3.4), Inches(0.9), [(got, 26, INK, True)], anchor="ctr")
        card(s, Inches(4.7), top, Inches(3.9), Inches(1.9))
        write(s, Inches(4.95), top + Inches(0.5), Inches(3.4), Inches(0.9), [(target, 26, INK, True)], anchor="ctr")
        card(s, Inches(8.85), top, Inches(3.9), Inches(1.9), RED)
        write(s, Inches(9.1), top + Inches(0.5), Inches(3.4), Inches(0.9), [(verdict, 26, WHITE, True)], align=PP_ALIGN.CENTER, anchor="ctr")

    s = blank(prs)
    chrome(s, "WHAT DRIVES LATENESS", "No feature moves delivery time.", 8,
           "Say association, not cause. Permutation importance sits inside the noise. There was no association.")
    points = [
        ("01", "Importance is noise", "Shuffling any feature changes RMSE by a few thousandths of a minute."),
        ("02", "Prep time is flat", "Preparation time and delivery time move together by about zero."),
        ("03", "Do not staff rain", "A rain chart with equal bars is not a roster."),
    ]
    for i, (num, title, body) in enumerate(points):
        top = Inches(1.85 + i * 1.65)
        card(s, Inches(0.55), top, Inches(12.25), Inches(1.5))
        write(s, Inches(0.85), top + Inches(0.4), Inches(1.1), Inches(0.7), [(num, 22, RED, True)], anchor="ctr")
        write(s, Inches(2.1), top + Inches(0.22), Inches(10), Inches(0.45), [(title, 20, INK, True)])
        write(s, Inches(2.1), top + Inches(0.72), Inches(10), Inches(0.5), [(body, 16, MUTED, False)])

    s = blank(prs)
    chrome(s, "CHURN MODEL", "The F1 looks strong. It means nothing.", 9,
           "Features stop at 1 Nov 2024. The label is the next 60 days. No leakage by construction.")
    stat(s, Inches(0.55), Inches(1.9), Inches(4.0), Inches(3.6), "87.4%", "of customers place no order in the 60 days after 1 Nov 2024.")
    stat(s, Inches(4.75), Inches(1.9), Inches(4.0), Inches(3.6), "0.933", "test F1. The same score as predicting that everyone churns.", TEAL)
    stat(s, Inches(8.95), Inches(1.9), Inches(3.85), Inches(3.6), "0.514", "ROC-AUC. A coin flip is 0.50.", GOLD)

    s = blank(prs)
    chrome(s, "WHO THE MODEL FLAGS", "Risk bands do not separate anyone.", 10,
           "Dashboard At-risk is 30 days of silence. The model label is 60 days. Do not mail the High band.")
    bands = [("Low", 0.875, "87.5%"), ("Medium", 0.859, "85.9%"), ("High", 0.891, "89.1%")]
    for i, (name, share, label) in enumerate(bands):
        top = Inches(1.95 + i * 1.55)
        write(s, Inches(0.55), top + Inches(0.25), Inches(1.8), Inches(0.5), [(name, 18, INK, True)])
        card(s, Inches(2.5), top + Inches(0.15), Inches(8.3), Inches(0.7), RGBColor(0xF0, 0xE4, 0xE4))
        rect(s, Inches(2.5), top + Inches(0.15), Inches(8.3 * share), Inches(0.7), RED if name == "High" else TEAL)
        write(s, Inches(11.0), top + Inches(0.25), Inches(1.7), Inches(0.5), [(label, 18, INK, True)])
    write(s, Inches(0.55), Inches(6.5), Inches(12), Inches(0.4), [("Share of each test band that actually churned. The bars are the finding.", 16, MUTED, False)])

    s = blank(prs)
    chrome(s, "THE DASHBOARD", "Six pages. One set of definitions.", 11,
           "Screenshots are in images/powerbi_01_executive.png through powerbi_06_ml.png. Revenue on the cards is Delivered plus Delivered Late.")
    defs = [
        ("Revenue", "Delivered and Delivered Late, amount above zero. ₹52.36 lakh."),
        ("Late", "is_late is blank when the time is missing or not positive. The card is 20.7%."),
        ("Score", "The restaurant score comes from the SQL view, ranked inside each city."),
    ]
    for i, (title, body) in enumerate(defs):
        left = Inches(0.55 + i * 4.2)
        card(s, left, Inches(2.0), Inches(3.95), Inches(3.9))
        rect(s, left, Inches(2.0), Inches(3.95), Inches(0.12), RED if i == 0 else TEAL if i == 1 else GOLD)
        write(s, left + Inches(0.3), Inches(2.45), Inches(3.35), Inches(0.6), [(title, 24, INK, True)])
        write(s, left + Inches(0.3), Inches(3.3), Inches(3.35), Inches(2.1), [(body, 18, MUTED, False)])

    s = blank(prs)
    chrome(s, "WHAT TO DO", "Two actions. Two things to refuse.", 12,
           "Success is a later month where the metric moves for a reason you can name.")
    actions = [
        (TEAL, "DO", "Review the bottom restaurants", "Start with cancellation, city by city. Do not delist anyone on the score alone."),
        (TEAL, "DO", "Treat 22% cancellation as the problem", "The rate is real. The file has no reason code, so the next question is operational."),
        (RED, "DON'T", "Staff rain or the 7 pm peak", "Busy is not the same as late. The tests do not support extra riders."),
        (RED, "DON'T", "Mail the High churn band", "Low, Medium, and High all churn at 86–89%. F1 matches 'flag everyone'."),
    ]
    for i, (accent, tag, title, body) in enumerate(actions):
        col, row = i % 2, i // 2
        left = Inches(0.55 + col * 6.4)
        top = Inches(1.85 + row * 2.45)
        card(s, left, top, Inches(6.15), Inches(2.25))
        rect(s, left, top, Inches(0.1), Inches(2.25), accent)
        write(s, left + Inches(0.35), top + Inches(0.22), Inches(1.5), Inches(0.35), [(tag, 13, accent, True)])
        write(s, left + Inches(0.35), top + Inches(0.58), Inches(5.5), Inches(0.5), [(title, 18, INK, True)])
        write(s, left + Inches(0.35), top + Inches(1.15), Inches(5.5), Inches(0.85), [(body, 14, MUTED, False)])

    s = blank(prs)
    chrome(s, "LIMITS", "What this cannot tell you.", 13,
           "Threshold is the 75th percentile, 45 minutes. Leakage is prevented by the 1 Nov 2024 cutoff. Dashboard numbers trace to SQL.")
    limits = [
        ("No reason for a cancel", "22% is the problem you can see. The column that would explain it was never collected."),
        ("No real distance", "Restaurant coordinates sit about 950 km from their own city centre. Distance stayed out of the model."),
        ("No signal in either model", "Delivery does not beat the mean. Churn does not beat 'everyone'. Both need data that contains a difference."),
    ]
    for i, (title, body) in enumerate(limits):
        top = Inches(1.85 + i * 1.6)
        card(s, Inches(0.55), top, Inches(12.25), Inches(1.45))
        write(s, Inches(0.9), top + Inches(0.22), Inches(11.5), Inches(0.4), [(title, 20, INK, True)])
        write(s, Inches(0.9), top + Inches(0.7), Inches(11.5), Inches(0.5), [(body, 16, MUTED, False)])

    prs.save(str(PPTX))
    print(f"  {PPTX.relative_to(ROOT)}  (13 slides)")


if __name__ == "__main__":
    write_pdf()
    write_pptx()
