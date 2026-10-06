"""PDF e-Ticket Generator using fpdf2."""
from pathlib import Path
from fpdf import FPDF
from config import TICKETS_DIR

class IRCTCTicketPDF(FPDF):
    def header(self):
        self.set_fill_color(24, 76, 120)  # IRCTC Blue
        self.rect(0, 0, 210, 20, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 13)
        self.cell(0, 10, "INDIAN RAILWAYS - AGENT BOOKING CONFIRMATION RECEIPT", ln=True, align="C")
        self.ln(6)

    def footer(self):
        self.set_y(-20)
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(190, 40, 30)
        self.cell(0, 4, "NOT AUTHORIZED FOR BOARDING TRAINS. CARRY OFFICIAL GOVERNMENT ERS SLIP & VALID PHOTO ID.", align="C", ln=True)
        self.set_font("Helvetica", "I", 7.5)
        self.set_text_color(100, 100, 100)
        self.cell(0, 4, "Official IRCTC Portal: https://www.irctc.co.in | Gov PNR Enquiry: https://www.indianrail.gov.in", align="C", ln=True)
        self.cell(0, 4, f"Page {self.page_no()}", align="C")

def generate_ticket_pdf(booking_info: dict) -> Path:
    """
    Generates a professional IRCTC e-Ticket PDF.
    booking_info expected keys:
        - pnr: str
        - train_number: str
        - train_name: str
        - source: str
        - dest: str
        - journey_date: str
        - departure: str
        - arrival: str
        - coach_class: str
        - fare: float
        - passengers: list of dicts (name, age, gender, berth, status)
        - payment_method: str
    """
    pdf = IRCTCTicketPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    pnr = booking_info.get("pnr", "8492049182")
    pdf.set_text_color(0, 0, 0)

    # PNR and Transaction Info Box
    pdf.set_fill_color(245, 247, 250)
    pdf.rect(10, 25, 190, 20, "F")
    pdf.set_xy(15, 28)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(42, 6, "OFFICIAL CRIS PNR:")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(200, 30, 30)
    pdf.cell(48, 6, pnr)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "SEAT STATUS:")
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(34, 139, 34)  # Green
    pdf.cell(50, 6, "CONFIRMED RESERVATION", ln=True)

    pdf.set_xy(15, 36)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "TRANSACTION ID:")
    pdf.set_font("Helvetica", "", 10)
    txn_str = booking_info.get("txn_id") or f"IRCTC-CRIS-{pnr[:6]}"
    pdf.cell(50, 6, txn_str)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "QUOTA:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(50, 6, "GENERAL (GN)", ln=True)

    # Statutory Compliance Notice Box (Not Authorized for Boarding)
    pdf.ln(3)
    notice_x = 10
    notice_y = pdf.get_y()
    pdf.set_fill_color(255, 243, 230)  # Light warm amber warning background
    pdf.set_draw_color(217, 83, 79)    # Crimson warning border
    pdf.set_line_width(0.35)
    pdf.rect(notice_x, notice_y, 190, 21, "FD")
    pdf.set_xy(notice_x + 3, notice_y + 2)

    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(190, 30, 20)
    pdf.cell(184, 4.5, "[!] IMPORTANT ADVISORY: THIS PDF IS NOT AN AUTHORIZED TRAVEL TICKET (ERS)", ln=True)

    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(50, 50, 50)
    pdf.set_x(notice_x + 3)
    pdf.cell(184, 4, "This document is an agent booking acknowledgment receipt only. Indian Railways mandates an authorized", ln=True)
    pdf.set_x(notice_x + 3)
    pdf.cell(184, 4, "government Electronic Reservation Slip (ERS) for boarding. Please download the official ticket using the link below:", ln=True)

    pdf.set_font("Helvetica", "B", 8)
    pdf.set_text_color(16, 92, 180)  # Blue clickable link
    pdf.set_x(notice_x + 3)
    pdf.cell(
        184, 4.5,
        ">> Click here to download Official Government IRCTC Ticket (www.irctc.co.in/nget)",
        ln=True,
        link="https://www.irctc.co.in/nget/train-search"
    )

    pdf.set_draw_color(0, 0, 0)
    pdf.set_line_width(0.2)
    pdf.set_text_color(0, 0, 0)

    # Journey Details Section
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(220, 230, 242)
    pdf.cell(190, 7, "  JOURNEY DETAILS", ln=True, fill=True)
    pdf.ln(2)

    col_w = 47.5
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "Train No. & Name:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, f"{booking_info.get('train_number', '')} / {booking_info.get('train_name', '')}")
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "Class:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, booking_info.get("coach_class", ""), ln=True)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "From Station:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, booking_info.get("source", ""))
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "To Station:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, booking_info.get("dest", ""), ln=True)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "Departure Time:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, booking_info.get("departure", "14:10"))
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "Arrival Time:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, booking_info.get("arrival", "16:40"), ln=True)

    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "Date of Journey:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, booking_info.get("journey_date", ""))
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(col_w, 6, "Distance:")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(col_w, 6, "175 KM", ln=True)

    # Passenger Details Section
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(220, 230, 242)
    pdf.cell(190, 7, "  PASSENGER DETAILS", ln=True, fill=True)
    pdf.ln(2)

    # Table Header
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Helvetica", "B", 9)
    pdf.cell(15, 6, "#", border=1, fill=True, align="C")
    pdf.cell(65, 6, "Passenger Name", border=1, fill=True)
    pdf.cell(20, 6, "Age", border=1, fill=True, align="C")
    pdf.cell(25, 6, "Gender", border=1, fill=True, align="C")
    pdf.cell(30, 6, "Booking Status", border=1, fill=True, align="C")
    pdf.cell(35, 6, "Coach / Berth", border=1, fill=True, align="C")
    pdf.ln(6)

    pdf.set_font("Helvetica", "", 9)
    passengers = booking_info.get("passengers", [])
    if not passengers:
        passengers = [{"name": "Balaji P", "age": 28, "gender": "M", "berth": "LB", "status": "CNF"}]

    for idx, p in enumerate(passengers, start=1):
        pdf.cell(15, 6, str(idx), border=1, align="C")
        pdf.cell(65, 6, f" {p.get('name', 'Passenger')}", border=1)
        pdf.cell(20, 6, str(p.get("age", 25)), border=1, align="C")
        pdf.cell(25, 6, str(p.get("gender", "M")), border=1, align="C")
        pdf.cell(30, 6, "CNF", border=1, align="C")
        pdf.cell(35, 6, f"S4 / {p.get('berth', '34 (LB)')}", border=1, align="C")
        pdf.ln(6)

    # Payment Summary
    pdf.ln(6)
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_fill_color(220, 230, 242)
    pdf.cell(190, 7, "  PAYMENT & FARE BREAKUP", ln=True, fill=True)
    pdf.ln(2)

    fare = booking_info.get("fare", 265.0)
    conv_fee = 17.70
    total = fare + conv_fee

    pdf.set_font("Helvetica", "", 9)
    pdf.cell(95, 5, "Ticket Fare:")
    pdf.cell(95, 5, f"INR {fare:.2f}", ln=True, align="R")
    pdf.cell(95, 5, "Convenience Fee (incl. GST):")
    pdf.cell(95, 5, f"INR {conv_fee:.2f}", ln=True, align="R")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(95, 6, "Total Amount Paid:")
    pdf.cell(95, 6, f"INR {total:.2f}", ln=True, align="R")
    pay_m = str(booking_info.get("payment_method", "Official IRCTC eWallet")).replace("₹", "Rs. ")
    pdf.cell(190, 5, f"Payment Mode: {pay_m}", ln=True)

    # Official Government Links & Verification Box
    pdf.ln(3)
    links_y = pdf.get_y()
    pdf.set_fill_color(245, 248, 252)
    pdf.set_draw_color(180, 200, 220)
    pdf.set_line_width(0.3)
    pdf.rect(10, links_y, 190, 15, "FD")
    pdf.set_xy(13, links_y + 1.5)
    pdf.set_font("Helvetica", "B", 7.5)
    pdf.set_text_color(40, 40, 40)
    pdf.cell(184, 3.8, "OFFICIAL GOVERNMENT PORTALS FOR AUTHORIZED ERS DOWNLOAD & PNR TRACKING:", ln=True)
    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_text_color(16, 92, 180)
    pdf.set_x(13)
    pdf.cell(90, 4, "- Download ERS: https://www.irctc.co.in/nget", link="https://www.irctc.co.in/nget/train-search")
    pdf.cell(94, 4, "- PNR Status: https://www.indianrail.gov.in", ln=True, link="https://www.indianrail.gov.in/enquiry/PNR/PnrEnquiry.html")
    pdf.set_x(13)
    pdf.set_font("Helvetica", "I", 6.5)
    pdf.set_text_color(110, 110, 110)
    pdf.cell(184, 3.5, "Indian Railways rules mandate carrying the official government ERS and original government photo identity proof during travel.", ln=True)

    # Save PDF
    out_file = TICKETS_DIR / f"ticket_{pnr}.pdf"
    try:
        pdf.output(str(out_file))
    except (PermissionError, OSError):
        import time
        out_file = TICKETS_DIR / f"ticket_{pnr}_{int(time.time())}.pdf"
        pdf.output(str(out_file))
    return out_file
