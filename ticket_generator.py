"""PDF e-Ticket Generator using fpdf2."""
from pathlib import Path
from fpdf import FPDF
from config import TICKETS_DIR

class IRCTCTicketPDF(FPDF):
    def header(self):
        self.set_fill_color(24, 76, 120)  # IRCTC Blue
        self.rect(0, 0, 210, 20, "F")
        self.set_text_color(255, 255, 255)
        self.set_font("Helvetica", "B", 14)
        self.cell(0, 10, "INDIAN RAILWAYS - ELECTRONIC RESERVATION SLIP (ERS)", ln=True, align="C")
        self.ln(6)

    def footer(self):
        self.set_y(-18)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(128, 128, 128)
        self.cell(0, 5, "This is an electronically generated receipt. Valid ID required during travel.", align="C", ln=True)
        self.cell(0, 5, f"Page {self.page_no()}", align="C")

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
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(40, 6, "PNR NUMBER:")
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(200, 30, 30)
    pdf.cell(50, 6, pnr)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(40, 6, "BOOKING STATUS:")
    pdf.set_font("Helvetica", "B", 11)
    pdf.set_text_color(34, 139, 34)  # Green
    pdf.cell(50, 6, "CONFIRMED (CNF)", ln=True)

    pdf.set_xy(15, 36)
    pdf.set_text_color(0, 0, 0)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "TRANSACTION ID:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(50, 6, f"TXN-{pnr[:6]}")
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 6, "QUOTA:")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(50, 6, "GENERAL (GN)", ln=True)

    # Journey Details Section
    pdf.ln(8)
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
    pdf.set_font("Helvetica", "I", 9)
    pdf.cell(190, 5, f"Payment Mode: Credit Card (Verified via 3D-Secure Bank OTP)", ln=True)

    # Save PDF
    out_file = TICKETS_DIR / f"ticket_{pnr}.pdf"
    pdf.output(str(out_file))
    return out_file
