"""Multi-user Telegram Bot with FSM, Per-Chat IRCTC credentials, Live Pricing, and Try Now support."""
import re
import datetime
import calendar
from typing import Dict, Any, Optional, Tuple
from telegram import (
    Update, ReplyKeyboardMarkup, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, ContextTypes, filters
)

import storage
from security import mask_text
from irctc_service import IRCTCService

# Global service instance
irctc_svc = IRCTCService()
global_scheduler = None  # Injected in main.py

# Conversation States for Booking Flow
(
    STATE_ROUTE,
    STATE_DATE,
    STATE_TRAIN_SELECT,
    STATE_CLASS_SELECT,
    STATE_PAYMENT_SELECT,
    STATE_PASSENGER_CHOICE,
    STATE_PASSENGER_NAME,
    STATE_PASSENGER_AGE,
    STATE_PASSENGER_GENDER,
    STATE_PASSENGER_BERTH,
    STATE_IRCTC_USER,
    STATE_IRCTC_PASS,
    STATE_UPI_ID,
    STATE_CARD_NUM,
    STATE_CARD_EXP,
    STATE_CARD_CVV,
    STATE_CARD_NAME,
    STATE_CONFIRM
) = range(18)

# Conversation States for Account Setup/Change
STATE_SET_USER, STATE_SET_PASS = range(18, 20)

# Conversation States for Standalone Card Setup/Change
STATE_SET_CARD_NUM, STATE_SET_CARD_EXP, STATE_SET_CARD_CVV, STATE_SET_CARD_NAME = range(20, 24)


# ----------------- Account Management Handlers -----------------

async def cmd_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View stored IRCTC credentials for this specific chat."""
    tg_id = update.effective_user.id
    username, password = await storage.get_decrypted_credentials(tg_id)

    if not username:
        await update.message.reply_text(
            "ℹ️ *No IRCTC Account Configured*\n\n"
            "You haven't linked your IRCTC ID yet.\n"
            "Use `/change_account` to link your IRCTC username & password.",
            parse_mode="Markdown"
        )
        return

    masked_u = mask_text(username, 3)
    masked_p = "•" * 8
    await update.message.reply_text(
        f"🔐 *Your Configured IRCTC Account:*\n\n"
        f"• *IRCTC Username:* `{masked_u}`\n"
        f"• *Password:* `{masked_p}`\n"
        f"• *Status:* Encrypted & Active (AES-256)\n\n"
        "Commands:\n"
        "• `/change_account` - Update your ID/Password\n"
        "• `/reset_account` - Remove your credentials from storage",
        parse_mode="Markdown"
    )

async def cmd_reset_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes stored credentials for this chat."""
    tg_id = update.effective_user.id
    success = await storage.reset_user_credentials(tg_id)
    if success:
        await update.message.reply_text("🗑️ *IRCTC account credentials have been completely reset and deleted.*", parse_mode="Markdown")
    else:
        await update.message.reply_text("ℹ️ No active IRCTC account was saved for this chat.")

async def start_change_account(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begins the credential update conversation."""
    await update.message.reply_text(
        "🔑 *IRCTC Account Setup*\n\n"
        "Please enter your *IRCTC Username*:\n"
        "_(This is securely encrypted at rest for this chat)_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return STATE_SET_USER

async def handle_set_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_irctc_user"] = update.message.text.strip()
    await update.message.reply_text("Now enter your *IRCTC Password*:", parse_mode="Markdown")
    return STATE_SET_PASS

async def handle_set_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    irctc_pass = update.message.text.strip()
    irctc_user = context.user_data.get("new_irctc_user", "")
    tg_id = update.effective_user.id

    await storage.save_user_credentials(tg_id, irctc_user, irctc_pass)
    await update.message.reply_text(
        f"✅ *IRCTC Account Successfully Saved!*\n\n"
        f"• Username: `{mask_text(irctc_user, 3)}`\n"
        f"• Password: `••••••••`\n\n"
        "You can now book tickets anytime using `/start` or `hi`.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ----------------- Payment Card Management Handlers -----------------

async def cmd_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View stored payment card details for this specific chat."""
    tg_id = update.effective_user.id
    card = await storage.get_decrypted_card(tg_id)

    if not card or not card.get("card_number"):
        await update.message.reply_text(
            "ℹ️ *No Payment Card Configured*\n\n"
            "You haven't linked a credit/debit card yet.\n"
            "Use `/change_card` to link your card for auto-booking.",
            parse_mode="Markdown"
        )
        return

    num = card.get("card_number", "")
    card_mask = f"**** **** **** {num[-4:]}" if len(num) >= 4 else "****"
    await update.message.reply_text(
        f"💳 *Your Linked Payment Card:*\n\n"
        f"• *Card Number:* `{card_mask}`\n"
        f"• *Expiry:* `{card.get('card_expiry', 'MM/YY')}`\n"
        f"• *CVV:* `•••`\n"
        f"• *Holder Name:* `{card.get('card_holder', 'Cardholder')}`\n"
        f"• *Status:* Encrypted & Active (AES-256)\n\n"
        "Commands:\n"
        "• `/change_card` - Update your card details\n"
        "• `/reset_card` - Remove your card from storage",
        parse_mode="Markdown"
    )

async def cmd_reset_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes stored payment card for this chat."""
    tg_id = update.effective_user.id
    success = await storage.reset_user_card(tg_id)
    if success:
        await update.message.reply_text("🗑️ *Payment card details have been completely removed.*", parse_mode="Markdown")
    else:
        await update.message.reply_text("ℹ️ No active payment card was saved for this chat.")

async def start_change_card(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begins the card update conversation."""
    await update.message.reply_text(
        "💳 *Payment Card Setup*\n\n"
        "Please enter your *16-Digit Card Number*:\n"
        "_(This is securely encrypted at rest for this chat using AES-256)_",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return STATE_SET_CARD_NUM

async def handle_set_card_num(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    num = update.message.text.strip().replace(" ", "").replace("-", "")
    if not num.isdigit() or len(num) < 12:
        await update.message.reply_text("❌ Please enter a valid 12-19 digit card number:")
        return STATE_SET_CARD_NUM
    context.user_data["new_card_num"] = num
    await update.message.reply_text("Enter *Card Expiry* in `MM/YY` format (e.g. `12/28`):", parse_mode="Markdown")
    return STATE_SET_CARD_EXP

async def handle_set_card_exp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    exp = update.message.text.strip()
    if not re.match(r"^\d{2}/\d{2}$", exp):
        await update.message.reply_text("❌ Please enter valid expiry as `MM/YY` (e.g. `12/28`):")
        return STATE_SET_CARD_EXP
    context.user_data["new_card_exp"] = exp
    await update.message.reply_text("Enter *CVV* (3 or 4 digits):", parse_mode="Markdown")
    return STATE_SET_CARD_CVV

async def handle_set_card_cvv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cvv = update.message.text.strip()
    if not cvv.isdigit() or len(cvv) not in [3, 4]:
        await update.message.reply_text("❌ Please enter a valid 3 or 4 digit CVV:")
        return STATE_SET_CARD_CVV
    context.user_data["new_card_cvv"] = cvv
    await update.message.reply_text("Enter *Cardholder Name* as printed on card:", parse_mode="Markdown")
    return STATE_SET_CARD_NAME

async def handle_set_card_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    tg_id = update.effective_user.id
    u_data = context.user_data

    await storage.save_user_card(
        telegram_id=tg_id,
        card_number=u_data["new_card_num"],
        card_expiry=u_data["new_card_exp"],
        card_cvv=u_data["new_card_cvv"],
        card_holder=name
    )

    masked_num = f"**** **** **** {u_data['new_card_num'][-4:]}"
    await update.message.reply_text(
        f"✅ *Payment Card Saved Successfully!*\n\n"
        f"• *Card:* `{masked_num}`\n"
        f"• *Expiry:* `{u_data['new_card_exp']}`\n"
        f"• *Holder:* `{name}`\n\n"
        "Your card is securely encrypted with AES-256 and ready for auto-booking.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ----------------- UPI Validation & Management Handlers -----------------

def validate_and_normalize_upi(raw_input: str) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Validates and normalizes UPI IDs and 10-digit mobile numbers.
    Returns: (is_valid, normalized_upi, detected_app, error_msg)
    """
    cleaned = raw_input.strip()
    if not cleaned:
        return False, None, None, "Input cannot be empty."

    # App map for popular Indian PSP handles
    KNOWN_HANDLES = {
        "paytm": "Paytm",
        "ybl": "PhonePe (Yes Bank)",
        "ibl": "PhonePe (ICICI Bank)",
        "axl": "PhonePe (Axis Bank)",
        "okaxis": "Google Pay (Axis Bank)",
        "okhdfcbank": "Google Pay (HDFC Bank)",
        "okicici": "Google Pay (ICICI Bank)",
        "oksbi": "Google Pay (SBI)",
        "apl": "Amazon Pay",
        "upi": "BHIM / Central NPCI",
        "barodampay": "Bank of Baroda",
        "cred": "CRED UPI",
        "postbank": "India Post Payments Bank (IPPB)",
        "kotak": "Kotak Mahindra Bank",
        "indus": "IndusInd Bank",
        "idbi": "IDBI Bank",
        "federal": "Federal Bank",
        "waaxis": "WhatsApp Pay",
        "waicici": "WhatsApp Pay",
        "wahdfcbank": "WhatsApp Pay",
        "wasbi": "WhatsApp Pay"
    }

    # Case 1: Standard UPI VPA format (contains '@')
    if "@" in cleaned:
        parts = cleaned.split("@")
        if len(parts) != 2:
            return False, None, None, "A valid UPI ID must have exactly one '@' symbol (e.g. `username@paytm`)."

        handle, psp = parts[0].strip().lower(), parts[1].strip().lower()

        # Handle validation: 2-64 chars, alphanumeric with dots, hyphens, underscores
        if not re.match(r"^[a-zA-Z0-9.\-_]{2,64}$", handle):
            return False, None, None, "Invalid username part before '@'. Must contain 2 to 64 letters, numbers, or dots/underscores."

        # PSP validation: 2-32 chars, letters/numbers
        if not re.match(r"^[a-zA-Z0-9.\-_]{2,32}$", psp):
            return False, None, None, "Invalid bank/app handle after '@' (e.g. `paytm`, `ybl`, `okaxis`)."

        detected_app = KNOWN_HANDLES.get(psp, f"{psp.upper()} Bank Gateway")
        normalized = f"{handle}@{psp}"
        return True, normalized, detected_app, None

    # Case 2: Phone number format (without '@')
    # Strip spaces, hyphens, plus signs, dots
    phone_clean = re.sub(r"[\s\-\+\.]", "", cleaned)

    # Strip country code +91 or 91 if present and total length is 12
    if phone_clean.startswith("91") and len(phone_clean) == 12:
        phone_clean = phone_clean[2:]
    elif phone_clean.startswith("0") and len(phone_clean) == 11:
        phone_clean = phone_clean[1:]

    # Check 10-digit Indian mobile number
    if len(phone_clean) == 10 and phone_clean.isdigit():
        if phone_clean[0] not in ["6", "7", "8", "9"]:
            return False, None, None, "Invalid Indian mobile number: Standard Indian mobile numbers must start with 6, 7, 8, or 9 (e.g. `9876543210`)."

        normalized = f"{phone_clean}@upi"
        return True, normalized, "Central NPCI UPI Number Mapper (BHIM / PhonePe / GPay / Paytm)", None

    # Invalid input with digits
    if phone_clean.isdigit():
        return False, None, None, f"Mobile number has {len(phone_clean)} digits. Indian mobile numbers must be exactly 10 digits."

    return False, None, None, "Invalid format. Enter a 10-digit mobile number (e.g. `9876543210`) or a UPI ID (e.g. `name@paytm`, `name@ybl`, `name@okaxis`)."

async def cmd_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View stored UPI ID for this specific chat."""
    tg_id = update.effective_user.id
    upi_id = await storage.get_decrypted_upi(tg_id)

    if not upi_id:
        await update.message.reply_text(
            "ℹ️ *No UPI ID Configured*\n\n"
            "You haven't linked a UPI ID yet.\n"
            "When booking a ticket, select *UPI / Instant Pay* to link your UPI address.",
            parse_mode="Markdown"
        )
        return

    is_valid, normalized_upi, detected_app, _ = validate_and_normalize_upi(upi_id)
    app_info = f" ({detected_app})" if detected_app else ""
    await update.message.reply_text(
        f"📱 *Your Configured UPI Address:*\n\n"
        f"• *UPI ID:* `{upi_id}`{app_info}\n"
        f"• *Status:* Verified & Active (AES-256 Encrypted)\n\n"
        "Commands:\n"
        "• `/reset_upi` - Remove your saved UPI ID",
        parse_mode="Markdown"
    )

async def cmd_reset_upi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Wipes stored UPI ID for this chat."""
    tg_id = update.effective_user.id
    success = await storage.reset_user_upi(tg_id)
    if success:
        await update.message.reply_text("🗑️ *Saved UPI address has been deleted from storage.*", parse_mode="Markdown")
    else:
        await update.message.reply_text("ℹ️ No active UPI ID was saved for this chat.")

# ----------------- /info and /tasks Command Handlers -----------------

async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Explains how the IRCTC AI Booking Agent & Seat Sniper works end-to-end with full details."""
    info_text = (
        "🤖 *IRCTC AI BOOKING AGENT — END-TO-END SYSTEM GUIDE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 *How This Bot Works (Step-by-Step):*\n\n"
        "1️⃣ *Live Train Discovery & Departure Sorting:*\n"
        "• Send `/start`, `/book`, or your route like `KJM-MAS`.\n"
        "• The agent queries live Indian Railways network feeds directly.\n"
        "• Trains running on your selected travel date are sorted chronologically by earliest departure time.\n\n"
        "2️⃣ *Official Railway Quotas & Live Fares:*\n"
        "• For each train, the bot parses official reserved coach quotas (Field 62) allocated by Indian Railways (e.g. `SL: Quota 134 Berths`, `3A: Quota 300 Berths`).\n"
        "• Live fares (Field 41) are fetched directly with zero synthetic pricing.\n\n"
        "3️⃣ *Seat Availability Sniper (Chart Watchdog):*\n"
        "• *Why regular Waiting List (WL) is skipped:* Indian Railways rules prohibit boarding with unconfirmed WL e-tickets.\n"
        "• *The Charting Window:* CRIS prepares the 1st reservation chart ~4 hours before train departure.\n"
        "• *Berth Release:* Unutilized quotas (defense, foreign tourist, VIP/HO, leftover Tatkal) release into the public pool as Current Availability (`CURR_AVBL`).\n"
        "• *The Sniper Strike:* The bot maintains a 24/7 Watchdog on your train. The second unutilized berths hit the system, you get an immediate strike alert to secure the seat in 1 click!\n\n"
        "4️⃣ *100% Truth & Zero Fake Info Guarantee:*\n"
        "• Official 10-digit government PNRs are cryptographically managed and issued only by CRIS/IRCTC upon payment.\n"
        "• The agent never generates fake PNRs or simulated WL numbers.\n\n"
        "5️⃣ *Bank-Grade Security (AES-256):*\n"
        "• All sensitive credentials, payment cards, and UPI IDs are encrypted with AES-256 Fernet for your chat only.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *All Available Commands:*\n"
        "• `/start` or `/book` — Search trains & start booking\n"
        "• `/tasks` (or `/task`) — View all open monitoring tasks in progress\n"
        "• `/info` — View this end-to-end operational guide\n"
        "• `/account` — Check or update your linked IRCTC ID\n"
        "• `/upi` — Check or update your linked UPI address\n"
        "• `/card` — Check or update your encrypted payment card\n"
        "• `/cancel` — Cancel any active booking conversation"
    )
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚆 Search Trains Now", callback_data="info_start_booking"),
            InlineKeyboardButton("📋 View Active Tasks", callback_data="info_view_tasks")
        ]
    ])
    effective_msg = update.effective_message
    if effective_msg:
        await effective_msg.reply_text(info_text, reply_markup=keyboard, parse_mode="Markdown")

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays all open seat monitoring / sniper tasks currently in progress for this user."""
    tg_id = update.effective_user.id
    active_tasks = await storage.get_user_active_tasks(tg_id)
    effective_msg = update.effective_message

    if not effective_msg:
        return

    if not active_tasks:
        no_tasks_msg = (
            "📋 *ACTIVE SEAT SNIPER TASKS*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "ℹ️ You currently have *no active monitoring tasks* in progress.\n\n"
            "When you search for a train and select *🎯 ACTIVATE SEAT SNIPER*, "
            "the 24/7 Watchdog will continuously monitor the train and appear here!\n\n"
            "👉 Send `/start` or `/book` to search trains and activate a sniper."
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚆 Start New Booking", callback_data="info_start_booking")]
        ])
        await effective_msg.reply_text(no_tasks_msg, reply_markup=keyboard, parse_mode="Markdown")
        return

    header_msg = (
        f"📋 *ACTIVE SEAT SNIPER TASKS ({len(active_tasks)} in progress)*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "The Watchdog is actively monitoring the trains below.\n"
        "When seats release at chart preparation, you will be notified immediately!"
    )
    await effective_msg.reply_text(header_msg, parse_mode="Markdown")

    for task in active_tasks:
        task_id = task["task_id"]
        t_num = task["train_number"]
        t_name = task.get("train_name", "EXP")
        c_class = task["coach_class"]
        src = task["source_stn"]
        dst = task["dest_stn"]
        date = task["journey_date"]
        attempts = task.get("attempts_count", 0)
        last_chk = task.get("last_checked") or "Pending first check"
        latest_stat = task.get("latest_status") or "WL / Awaiting Chart Release"
        pay_mode = task.get("payment_method", "Instant Pay")
        p_info = task.get("passengers", [{}])[0]
        p_name = p_info.get("name", "Passenger")

        phase_line = f"• *Monitoring Phase:* {task.get('phase_desc')}\n" if task.get("phase_desc") else ""
        poll_line = f"• *Dynamic Polling Rate:* Every {task.get('polling_interval', 60)}s (Auto-accelerates at opening)\n" if task.get("polling_interval") else ""
        chart_line = f"• *Estimated Chart Prep:* `{task.get('target_strike_time')} IST`\n" if task.get("target_strike_time") else ""

        task_card = (
            f"🎯 *Task ID:* `{task_id}`\n"
            f"• *Train:* `{t_num}` - {t_name} (*{c_class}*)\n"
            f"• *Route:* {src} ➔ {dst} ({date})\n"
            f"• *Passenger:* {p_name} ({p_info.get('berth', 'No Pref')})\n"
            f"• *Current Status:* `{latest_stat}`\n"
            f"• *Target:* Confirmed / Current Available (`CURR_AVBL`)\n"
            f"{chart_line}"
            f"{phase_line}"
            f"{poll_line}"
            f"• *Payment Mode:* {pay_mode}\n"
            f"• *Checks Performed:* `{attempts}` (Last: `{last_chk}`)\n\n"
            "👉 Tap below to trigger a live check or cancel monitoring:"
        )
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Try Now", callback_data=f"try_{task_id}"),
                InlineKeyboardButton("❌ Cancel Monitoring", callback_data=f"cancel_{task_id}")
            ]
        ])
        await effective_msg.reply_text(task_card, reply_markup=kb, parse_mode="Markdown")

# Helper command checkers
def is_back_command(text: str) -> bool:
    t = text.strip().lower()
    return t in ["⬅️ back", "back", "prev", "previous", "< back", "go back"]

def is_cancel_command(text: str) -> bool:
    t = text.strip().lower()
    return t in ["❌ cancel", "cancel", "stop", "exit", "quit"]

# ----------------- Booking Conversation Handlers -----------------

async def start_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point for /start, /book, or greetings."""
    tg_user = update.effective_user
    context.user_data.clear()

    # Sanitize user name to prevent Markdown parsing crash
    raw_name = tg_user.first_name if (tg_user and tg_user.first_name) else "Traveler"
    safe_name = re.sub(r"[*_`\[\]]", "", raw_name).strip() or "Traveler"

    welcome_msg = (
        f"🚆 *Welcome to the IRCTC AI Booking Agent, {safe_name}!*\n\n"
        "I will help you search real live trains, check coach availability with fares, "
        "and continuously monitor Waiting List tickets with auto-booking.\n\n"
        "💡 *Quick Commands:*\n"
        "• `/info` — Detailed guide on how this agent & sniper works\n"
        "• `/tasks` — View and manage open seat sniper tasks in progress\n\n"
        "📍 Please enter your journey route in format: `SOURCE-DESTINATION`\n"
        "*(Example: `KJM-MAS` or `MAS-NLR`)*"
    )
    kb = ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
    try:
        await update.message.reply_text(
            welcome_msg,
            parse_mode="Markdown",
            reply_markup=kb
        )
    except Exception:
        await update.message.reply_text(
            welcome_msg.replace("*", "").replace("`", ""),
            reply_markup=kb
        )
    return STATE_ROUTE

def adjust_date(curr: datetime.date, delta_y: int = 0, delta_m: int = 0, delta_d: int = 0) -> datetime.date:
    """Adjust date safely across months and years with month-length clamping and 120-day limit."""
    new_y = curr.year + delta_y
    new_m = curr.month + delta_m
    while new_m > 12:
        new_m -= 12
        new_y += 1
    while new_m < 1:
        new_m += 12
        new_y -= 1

    max_days = calendar.monthrange(new_y, new_m)[1]
    new_d = min(curr.day, max_days)
    target = datetime.date(new_y, new_m, new_d)

    if delta_d != 0:
        target = target + datetime.timedelta(days=delta_d)

    today = datetime.date.today()
    max_advance = today + datetime.timedelta(days=120)

    if target < today:
        target = today
    elif target > max_advance:
        target = max_advance

    return target


def build_date_picker_inline_keyboard(selected_date: datetime.date) -> InlineKeyboardMarkup:
    """
    Builds an interactive Date Picker widget with individual steppers for Year, Month, and Day,
    plus quick stepper buttons and a clear Confirm button.
    Only allows current date or future dates within 120 days.
    """
    today = datetime.date.today()
    max_advance = today + datetime.timedelta(days=120)

    if selected_date < today:
        selected_date = today
    elif selected_date > max_advance:
        selected_date = max_advance

    y = selected_date.year
    m = selected_date.month
    d = selected_date.day

    month_name = calendar.month_abbr[m]
    date_str = selected_date.strftime("%Y-%m-%d")
    disp_date = selected_date.strftime("%d-%b-%Y")
    day_name = selected_date.strftime("%A")

    keyboard = [
        # Year scroll row: ◀️ Year: 2026 ▶️
        [
            InlineKeyboardButton("◀️", callback_data=f"cal_prev_y_{date_str}"),
            InlineKeyboardButton(f"📅 Year: {y}", callback_data="cal_noop_y"),
            InlineKeyboardButton("▶️", callback_data=f"cal_next_y_{date_str}"),
        ],
        # Month scroll row: ◀️ Month: Oct (10) ▶️
        [
            InlineKeyboardButton("◀️", callback_data=f"cal_prev_m_{date_str}"),
            InlineKeyboardButton(f"🗓️ Month: {month_name} ({m:02d})", callback_data="cal_noop_m"),
            InlineKeyboardButton("▶️", callback_data=f"cal_next_m_{date_str}"),
        ],
        # Day scroll row: ◀️ Day: 05 (Mon) ▶️
        [
            InlineKeyboardButton("◀️", callback_data=f"cal_prev_d_{date_str}"),
            InlineKeyboardButton(f"📆 Day: {d:02d} ({day_name[:3]})", callback_data="cal_noop_d"),
            InlineKeyboardButton("▶️", callback_data=f"cal_next_d_{date_str}"),
        ],
        # Quick jump steppers: -5 Days | Today | +5 Days
        [
            InlineKeyboardButton("⏪ -5 Days", callback_data=f"cal_minus5_{date_str}"),
            InlineKeyboardButton("🔄 Today", callback_data=f"cal_today_{date_str}"),
            InlineKeyboardButton("+5 Days ⏩", callback_data=f"cal_plus5_{date_str}"),
        ],
        # Confirmation button
        [
            InlineKeyboardButton(f"✅ CONFIRM: {disp_date} ({day_name[:3]})", callback_data=f"cal_confirm_{date_str}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def format_date_picker_text(src: str, dst: str, dt: datetime.date) -> str:
    """Generates the prompt message displaying selected date and relative offset."""
    today = datetime.date.today()
    diff = (dt - today).days
    day_rel = "Today" if diff == 0 else ("Tomorrow" if diff == 1 else f"in {diff} days")
    return (
        f"📍 Route: *{src}* ➔ *{dst}*\n"
        f"📅 Selected Date: *{dt.strftime('%d-%b-%Y (%A)')}* ({day_rel})\n\n"
        "👉 *Scroll & select your Date | Month | Year below:*\n"
        "• Tap `◀️` / `▶️` on any row to scroll Day, Month, or Year\n"
        "• Once selected, tap `[ ✅ CONFIRM ]` to view all trains on that day!"
    )


def get_date_keyboard():
    today = datetime.date.today()
    tomorrow = today + datetime.timedelta(days=1)
    day_after = today + datetime.timedelta(days=2)

    return ReplyKeyboardMarkup(
        [
            [f"📅 Today ({today.strftime('%Y-%m-%d')})", f"📅 Tomorrow ({tomorrow.strftime('%Y-%m-%d')})"],
            [f"📅 Day After ({day_after.strftime('%Y-%m-%d')})", "📅 Choose Custom Date"],
            ["⬅️ Back", "❌ Cancel"]
        ],
        resize_keyboard=True
    )


async def handle_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    # Clean separators: support ' - ', '-', ' TO ', '->', '➔', '/', or spaces
    cleaned = re.sub(r"\s*(->|➔|TO|-|–|/)\s*", "-", text, flags=re.IGNORECASE).strip()
    if "-" not in cleaned and " " in cleaned:
        cleaned = re.sub(r"\s+", "-", cleaned).strip()

    parts = [p.strip().upper() for p in cleaned.split("-") if p.strip()]
    if len(parts) != 2 or not parts[0].isalpha() or not parts[1].isalpha() or len(parts[0]) > 6 or len(parts[1]) > 6:
        await update.message.reply_text("❌ Please enter valid station codes as `SRC-DST` (e.g. `KJM-MAS` or `MAS-NLR`):")
        return STATE_ROUTE

    context.user_data["source"] = parts[0]
    context.user_data["dest"] = parts[1]

    # Persist session to JSON so redeploys don't lose the route
    tg_id = update.effective_user.id
    await storage.save_user_session(tg_id, context.user_data)

    today = datetime.date.today()
    today_disp = today.strftime("%d-%b-%Y (%A)")

    # 1. Quick options keyboard
    await update.message.reply_text(
        f"✅ Route Selected: *{parts[0]}* ➔ *{parts[1]}*\n"
        f"📅 Today's Date: `{today_disp}`\n\n"
        "👉 *Choose your Journey Date below*:\n"
        "_(Only today or future dates within 120 days are valid)_",
        reply_markup=get_date_keyboard(),
        parse_mode="Markdown"
    )

    # 2. Interactive Date Picker Widget (Date | Month | Year Steppers)
    await update.message.reply_text(
        format_date_picker_text(parts[0], parts[1], today),
        reply_markup=build_date_picker_inline_keyboard(today),
        parse_mode="Markdown"
    )
    return STATE_DATE


async def proceed_to_train_search(update: Update, context: ContextTypes.DEFAULT_TYPE, date_obj: datetime.date) -> int:
    """Executes live train search and displays sorted train list for a validated date."""
    today = datetime.date.today()
    max_advance = today + datetime.timedelta(days=120)
    effective_msg = update.effective_message

    if date_obj < today:
        await effective_msg.reply_text(
            f"❌ *Past Date Not Allowed!*\n\n"
            f"You selected `{date_obj.strftime('%Y-%m-%d')}`, which is in the past.\n"
            f"Indian Railways reservations permit only *Today ({today.strftime('%Y-%m-%d')})* or a *Future Date*.\n\n"
            "Please select a valid date from the options below:",
            reply_markup=get_date_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_DATE

    if date_obj > max_advance:
        await effective_msg.reply_text(
            f"❌ *Date Beyond 120-Day Advance Booking Window!*\n\n"
            f"Indian Railways advance bookings are open up to 120 days in advance (until `{max_advance.strftime('%Y-%m-%d')}`).\n"
            "Please choose a date within the booking window:",
            reply_markup=get_date_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_DATE

    date_str = date_obj.strftime("%Y-%m-%d")
    context.user_data["date"] = date_str
    src = context.user_data.get("source", "KJM")
    dst = context.user_data.get("dest", "MAS")

    tg_id = update.effective_user.id
    await storage.save_user_session(tg_id, context.user_data)

    await effective_msg.reply_text(f"🔍 *Fetching live trains for {src} ➔ {dst} on {date_str}...*", parse_mode="Markdown")

    trains = await irctc_svc.search_trains(src, dst, date_str)
    context.user_data["train_list"] = trains
    await storage.save_user_session(tg_id, context.user_data)

    if not trains:
        await effective_msg.reply_text(
            f"⚠️ *No Live Trains Found from Indian Railways*\n\n"
            f"Could not find any trains running on `{date_str}` for `{src} ➔ {dst}`.\n"
            "• Please ensure station codes are valid (e.g. `KJM`, `MAS`, `SBC`, `NDLS`)\n"
            "• Or Indian Railways servers may be temporarily experiencing heavy load.\n\n"
            "👉 Please enter another date or send `hi` to start fresh.",
            reply_markup=get_date_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_DATE

    msg = f"🚆 *Available Trains on {date_str} (Earliest First):*\n\n"
    keyboard = []
    for t in trains:
        c_str = ", ".join(t.get("classes", []))
        msg += f"• `{t['number']}` - *{t['name']}*\n  🕒 Departs: `{t['departure']}` ➔ Arrives: `{t['arrival']}` ({t['duration']})\n  🎫 Classes: `{c_str}`\n\n"
        keyboard.append([f"{t['number']} - {t['name']} ({t['departure']})"])

    keyboard.append(["⬅️ Back", "❌ Cancel"])

    await effective_msg.reply_text(
        msg,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_TRAIN_SELECT


async def handle_date_calendar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    data = query.data or ""

    if data.startswith("cal_noop_"):
        await query.answer("Tap ◀️ or ▶️ to adjust Year, Month, or Day.")
        return STATE_DATE

    parts = data.split("_")
    action = parts[1]
    curr_date_str = parts[-1]

    try:
        curr_date = datetime.datetime.strptime(curr_date_str, "%Y-%m-%d").date()
    except Exception:
        curr_date = datetime.date.today()

    today = datetime.date.today()

    if action == "confirm":
        await query.answer("Journey date selected!")
        return await proceed_to_train_search(update, context, curr_date)

    # Compute updated date based on stepper
    new_date = curr_date
    if action == "prev" and len(parts) >= 4:
        unit = parts[2]
        if unit == "y":
            new_date = adjust_date(curr_date, delta_y=-1)
        elif unit == "m":
            new_date = adjust_date(curr_date, delta_m=-1)
        elif unit == "d":
            new_date = adjust_date(curr_date, delta_d=-1)
    elif action == "next" and len(parts) >= 4:
        unit = parts[2]
        if unit == "y":
            new_date = adjust_date(curr_date, delta_y=1)
        elif unit == "m":
            new_date = adjust_date(curr_date, delta_m=1)
        elif unit == "d":
            new_date = adjust_date(curr_date, delta_d=1)
    elif action == "minus5":
        new_date = adjust_date(curr_date, delta_d=-5)
    elif action == "plus5":
        new_date = adjust_date(curr_date, delta_d=5)
    elif action == "today":
        new_date = today

    if new_date == curr_date:
        if action.startswith("prev") or action == "minus5":
            await query.answer("⚠️ Cannot select past date. Today is the earliest date allowed.", show_alert=False)
        elif action.startswith("next") or action == "plus5":
            await query.answer("⚠️ Advance reservations open up to 120 days only.", show_alert=False)
        else:
            await query.answer()
        return STATE_DATE

    await query.answer()
    src = context.user_data.get("source", "KJM")
    dst = context.user_data.get("dest", "MAS")
    new_text = format_date_picker_text(src, dst, new_date)
    new_markup = build_date_picker_inline_keyboard(new_date)
    await query.edit_message_text(new_text, reply_markup=new_markup, parse_mode="Markdown")
    return STATE_DATE


async def handle_date(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_date = update.message.text.strip()
    if is_cancel_command(raw_date):
        return await cancel_booking(update, context)

    if is_back_command(raw_date):
        await update.message.reply_text(
            "📍 Please enter your journey route in format: `SOURCE-DESTINATION` (e.g. `KJM-MAS`):",
            reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_ROUTE

    if "custom date" in raw_date.lower():
        today = datetime.date.today()
        src = context.user_data.get("source", "KJM")
        dst = context.user_data.get("dest", "MAS")
        await update.message.reply_text(
            format_date_picker_text(src, dst, today),
            reply_markup=build_date_picker_inline_keyboard(today),
            parse_mode="Markdown"
        )
        return STATE_DATE

    # Extract date if clicked from quick button e.g. "📅 Today (2026-10-01)"
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw_date)
    if m:
        clean_input = m.group(1)
    elif raw_date.lower() == "today":
        clean_input = datetime.date.today().strftime("%Y-%m-%d")
    elif raw_date.lower() == "tomorrow":
        clean_input = (datetime.date.today() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        clean_input = raw_date

    # Parse date across standard formats
    date_obj = None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            date_obj = datetime.datetime.strptime(clean_input, fmt).date()
            break
        except ValueError:
            pass

    if not date_obj:
        await update.message.reply_text(
            "❌ Invalid date format. Please enter date as `YYYY-MM-DD` (e.g. `2026-10-05`)\n"
            "or use the interactive date scroller / quick options below:",
            reply_markup=get_date_keyboard(),
            parse_mode="Markdown"
        )
        return STATE_DATE

    return await proceed_to_train_search(update, context, date_obj)


async def handle_out_of_state_train_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """
    Intelligently handles train buttons clicked after server restart, timeout, or outside active flow.
    Recovers stored route/date if available, or clearly explains the issue and prompts to continue.
    """
    text = update.message.text.strip()
    tg_id = update.effective_user.id
    m = re.match(r"^(\d{5})\s*-\s*(.+?)(?:\s*\(\d{2}:\d{2}\))?$", text)
    train_num = m.group(1) if m else text.split()[0]
    train_name = m.group(2) if m else "TRAIN"

    saved = await storage.get_user_session(tg_id)
    if saved and saved.get("source") and saved.get("dest") and saved.get("date"):
        # Session recovered!
        context.user_data.update(saved)
        context.user_data["train_number"] = train_num
        await update.message.reply_text(
            f"🔄 *Restoring Session:* Train *{train_num} - {train_name}* for *{saved.get('source')}* ➔ *{saved.get('dest')}* on *{saved.get('date')}*...\n"
            "Checking live coach classes and fares...",
            parse_mode="Markdown"
        )
        return await handle_train_select(update, context)

    # Session lost due to server reboot / redeploy -> clearly explain the proper issue
    context.user_data.clear()
    context.user_data["preselected_train"] = train_num
    await update.message.reply_text(
        f"⚠️ *Booking Session Interrupted / Server Updated*\n\n"
        f"You tapped *{train_num} - {train_name}*, but the previous booking session was interrupted by an automated server deployment.\n\n"
        "📍 Please enter your journey route to resume:\n"
        "*(Example: `KJM-MAS` or `MAS-NLR`)*\n\n"
        "_(Or send `hi` to start fresh)_",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_ROUTE


async def handle_train_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_text = update.message.text.strip()
    if is_cancel_command(selected_text):
        return await cancel_booking(update, context)

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    if is_back_command(selected_text):
        today = datetime.date.today()
        src = context.user_data.get("source", "KJM")
        dst = context.user_data.get("dest", "MAS")
        await update.message.reply_text(
            f"Route: *{src}* ➔ *{dst}*\n\n"
            "📅 *Choose your Journey Date*:",
            reply_markup=get_date_keyboard(),
            parse_mode="Markdown"
        )
        await update.message.reply_text(
            format_date_picker_text(src, dst, today),
            reply_markup=build_date_picker_inline_keyboard(today),
            parse_mode="Markdown"
        )
        return STATE_DATE

    # Intelligent Auto-Detection: if user entered a date like 2026-10-04, switch date!
    if re.match(r"^\d{4}-\d{2}-\d{2}$", selected_text) or re.match(r"^\d{2}-\d{2}-\d{4}$", selected_text):
        return await handle_date(update, context)

    train_number = selected_text.split(" - ")[0].split()[0].strip()

    # Locate train details
    train_info = next((t for t in context.user_data.get("train_list", []) if t["number"] == train_number), None)
    if not train_info and train_number.isdigit():
        # Fetch live trains if train_list was cleared
        src = context.user_data.get("source", "KJM")
        dst = context.user_data.get("dest", "MAS")
        dt = context.user_data.get("date", datetime.date.today().strftime("%Y-%m-%d"))
        fresh_trains = await irctc_svc.search_trains(src, dst, dt)
        context.user_data["train_list"] = fresh_trains
        train_info = next((t for t in fresh_trains if t["number"] == train_number), {
            "number": train_number,
            "name": selected_text.split(" - ")[1].split("(")[0].strip() if " - " in selected_text else "SUPERFAST EXP",
            "departure": "00:15",
            "arrival": "06:45"
        })

    if not train_info:
        await update.message.reply_text(
            "❌ Please tap one of the train options from the keyboard below, or click '⬅️ Back':"
        )
        return STATE_TRAIN_SELECT

    context.user_data["train_number"] = train_number
    context.user_data["train_name"] = train_info.get("name", "EXP")
    context.user_data["departure"] = train_info.get("departure", "00:00")
    context.user_data["arrival"] = train_info.get("arrival", "00:00")
    tg_id = update.effective_user.id
    await storage.save_user_session(tg_id, context.user_data)

    await update.message.reply_text(f"⏳ Checking live availability & fares for Train *{train_number}*...", parse_mode="Markdown")

    # Fetch classes WITH PRICES AND AVAILABILITY
    class_options = await irctc_svc.get_class_options_with_prices(
        train_number, context.user_data["source"], context.user_data["dest"], context.user_data["date"]
    )
    context.user_data["class_options"] = class_options

    msg = f"🎟️ *Select Coach Class for Train {train_number} ({train_info.get('name')}):*\n\n"
    keyboard = []
    for c in class_options:
        curr_stat = c.get("status", "WL")
        quota_txt = f"Quota: *{c['quota']} Berths* | " if c.get("quota") else ""
        msg += f"• *{c['class_code']}:* `{curr_stat}` | {quota_txt}Live Fare: *₹{int(c['fare'])}*\n"
        keyboard.append([f"{c['class_code']} (Rs. {int(c['fare'])})"])

    keyboard.append(["⬅️ Back", "❌ Cancel"])

    msg += (
        "\nℹ️ *Live Capacity & Waiting List Advisory:*\n"
        "• Quota numbers show total reserved capacity allocated to this train by CRIS.\n"
        "• Dynamic Waiting List status updates continuously. Verify real-time WL on official portal:\n"
        "🔗 [Check Dynamic WL on Official IRCTC](https://www.irctc.co.in/nget/train-search)\n"
        "• The *Seat Sniper* will monitor this train 24/7 and strike when confirmed berths release at chart preparation!"
    )

    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_CLASS_SELECT

async def handle_class_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    if is_back_command(text):
        # Re-display trains list
        trains = context.user_data.get("train_list", [])
        keyboard = [[f"{t['number']} - {t['name']} ({t['departure']})"] for t in trains]
        keyboard.append(["⬅️ Back", "❌ Cancel"])
        await update.message.reply_text(
            f"🚆 *Select a Train ({context.user_data.get('source')} ➔ {context.user_data.get('dest')} on {context.user_data.get('date')}):*",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_TRAIN_SELECT

    coach_code = text.split(" - ")[0].split()[0].upper()
    context.user_data["coach_class"] = coach_code

    # Find fare
    opts = context.user_data.get("class_options", [])
    matching = next((o for o in opts if o["class_code"] == coach_code), None)
    if not matching:
        await update.message.reply_text("❌ Please select one of the coach classes from the keyboard options above:")
        return STATE_CLASS_SELECT

    context.user_data["fare"] = matching["fare"]
    context.user_data["class_status"] = matching["status"]

    payment_keyboard = [
        ["💼 IRCTC eWallet", "💳 Credit / Debit Card"],
        ["📱 UPI / Instant Pay"],
        ["⬅️ Back", "❌ Cancel"]
    ]

    await update.message.reply_text(
        f"Selected Class: *{coach_code}* (Fare: ₹{int(context.user_data['fare'])})\n\n"
        "💳 *Choose Payment Mode:*\n\n"
        "• *💼 IRCTC eWallet* — Instant wallet deduction (zero gateway delay)\n"
        "• *💳 Credit / Debit Card* — Card on file (3D-Secure mobile notification)\n"
        "• *📱 UPI / Instant Pay* — Push collect notification to your mobile UPI app\n\n"
        "👉 Tap an option below to proceed:",
        reply_markup=ReplyKeyboardMarkup(payment_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_PAYMENT_SELECT

async def handle_payment_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    if is_back_command(text):
        # Re-display classes
        class_options = context.user_data.get("class_options", [])
        keyboard = [[f"{c['class_code']} (Rs. {int(c['fare'])})"] for c in class_options]
        keyboard.append(["⬅️ Back", "❌ Cancel"])
        await update.message.reply_text(
            f"🎟️ *Select Coach Class for Train {context.user_data.get('train_number')}:*",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_CLASS_SELECT

    t_lower = text.lower()
    fare = int(context.user_data.get("fare", 240))

    if "ewallet" in t_lower or "wallet" in t_lower:
        context.user_data["payment_method"] = "IRCTC eWallet"
        info_banner = (
            "💼 *Payment Mode: IRCTC eWallet*\n\n"
            f"⚠️ *Wallet Balance Advisory:* Please maintain sufficient funds (minimum *₹{fare + 18}* including fees) "
            "in your IRCTC e-Wallet prior to booking.\n"
            "Funds will be deducted instantly with zero gateway latency when seats become available!"
        )
    elif "card" in t_lower:
        context.user_data["payment_method"] = "Credit / Debit Card"
        info_banner = (
            "💳 *Payment Mode: Credit / Debit Card*\n\n"
            "📲 *Payment Notification Advisory:* When seats become available, an automated checkout will trigger. "
            "A 3D-Secure Bank OTP or mobile transaction notification will be sent directly to your registered mobile phone. "
            "Please keep your mobile handy to authenticate!"
        )
    elif "upi" in t_lower:
        context.user_data["payment_method"] = "UPI / Instant Pay"
        info_banner = (
            "📱 *Payment Mode: UPI / Instant Pay*\n\n"
            "📲 *UPI Collect Notification Advisory:* When seats open, a payment collect push notification "
            "will be sent to your mobile UPI app (GPay / PhonePe / Paytm / BHIM). "
            "Please approve the notification on your phone within the timeout window to confirm your ticket!"
        )
    else:
        await update.message.reply_text(
            "❌ Please select one of the payment options from the keyboard below, or tap '⬅️ Back':"
        )
        return STATE_PAYMENT_SELECT

    tg_id = update.effective_user.id
    saved = await storage.get_passenger_profile(tg_id)
    if saved and saved.get("name"):
        context.user_data["saved_profile"] = saved
        choice_kb = [
            [f"✅ Use Saved: {saved['name']} ({saved['age']}, {saved['gender']})"],
            ["➕ Enter New Passenger Details"],
            ["⬅️ Back", "❌ Cancel"]
        ]
        await update.message.reply_text(
            f"{info_banner}\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "👤 *Saved Passenger Profile Found:*\n\n"
            f"• *Name:* {saved['name']}\n"
            f"• *Age:* {saved['age']} yrs | *Gender:* {saved['gender']}\n"
            f"• *Berth Preference:* {saved.get('berth', 'No Preference')}\n\n"
            "👉 Tap below to use this saved passenger in 1-click or enter new details:",
            reply_markup=ReplyKeyboardMarkup(choice_kb, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_PASSENGER_CHOICE

    await update.message.reply_text(
        f"{info_banner}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "👤 Please enter the *Passenger Full Name*:",
        reply_markup=ReplyKeyboardMarkup([["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_PASSENGER_NAME

async def handle_passenger_choice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    if is_back_command(text):
        payment_keyboard = [
            ["💼 IRCTC eWallet", "💳 Credit / Debit Card"],
            ["📱 UPI / Instant Pay"],
            ["⬅️ Back", "❌ Cancel"]
        ]
        await update.message.reply_text(
            "💳 *Choose Payment Mode:*\n\nPlease choose a payment option:",
            reply_markup=ReplyKeyboardMarkup(payment_keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_PAYMENT_SELECT

    if "Use Saved" in text or "✅" in text:
        saved = context.user_data.get("saved_profile") or await storage.get_passenger_profile(update.effective_user.id)
        if saved:
            context.user_data["p_name"] = saved["name"]
            context.user_data["p_age"] = saved["age"]
            context.user_data["p_gender"] = saved["gender"]
            context.user_data["p_berth"] = saved.get("berth", "No Preference")
            await update.message.reply_text(
                f"✅ Selected Saved Passenger: *{saved['name']}* ({saved['age']} yrs, {saved['gender']}, {saved.get('berth', 'No Preference')})",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
            return await check_credentials_and_next(update, context)

    # User chose "➕ Enter New Passenger Details"
    await update.message.reply_text(
        "👤 Please enter the *Passenger Full Name*:",
        reply_markup=ReplyKeyboardMarkup([["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_PASSENGER_NAME

async def handle_passenger_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    if is_back_command(text):
        payment_keyboard = [
            ["💼 IRCTC eWallet", "💳 Credit / Debit Card"],
            ["📱 UPI / Instant Pay"],
            ["⬅️ Back", "❌ Cancel"]
        ]
        await update.message.reply_text(
            "💳 *Choose Payment Mode:*\n\n"
            "Please choose a payment option:",
            reply_markup=ReplyKeyboardMarkup(payment_keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_PAYMENT_SELECT

    context.user_data["p_name"] = text
    await update.message.reply_text(
        "Enter passenger *Age*:",
        reply_markup=ReplyKeyboardMarkup([["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_PASSENGER_AGE

async def handle_passenger_age(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    if is_back_command(text):
        await update.message.reply_text(
            "👤 Please enter the *Passenger Full Name*:",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_PASSENGER_NAME

    try:
        age = int(text)
        if age < 1 or age > 120:
            raise ValueError
        context.user_data["p_age"] = age
    except ValueError:
        await update.message.reply_text(
            "❌ Please enter a valid age (1-120):",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Back", "❌ Cancel"]], resize_keyboard=True)
        )
        return STATE_PASSENGER_AGE

    gender_keyboard = [
        ["Male", "Female", "Transgender"],
        ["⬅️ Back", "❌ Cancel"]
    ]
    await update.message.reply_text(
        "Select passenger *Gender*:",
        reply_markup=ReplyKeyboardMarkup(gender_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_PASSENGER_GENDER

async def handle_passenger_gender(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    if is_back_command(text):
        await update.message.reply_text(
            "Enter passenger *Age*:",
            reply_markup=ReplyKeyboardMarkup([["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_PASSENGER_AGE

    context.user_data["p_gender"] = text[0].upper()

    berth_keyboard = [
        ["Lower Berth (LB)", "Middle Berth (MB)"],
        ["Upper Berth (UB)", "Side Lower (SL)"],
        ["Side Upper (SU)", "No Preference"],
        ["⬅️ Back", "❌ Cancel"]
    ]
    await update.message.reply_text(
        "Select *Berth Preference*:",
        reply_markup=ReplyKeyboardMarkup(berth_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_PASSENGER_BERTH

async def handle_passenger_berth(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    if is_back_command(text):
        gender_keyboard = [
            ["Male", "Female", "Transgender"],
            ["⬅️ Back", "❌ Cancel"]
        ]
        await update.message.reply_text(
            "Select passenger *Gender*:",
            reply_markup=ReplyKeyboardMarkup(gender_keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_PASSENGER_GENDER

    context.user_data["p_berth"] = text
    tg_id = update.effective_user.id

    # Auto-save passenger profile for future 1-click bookings!
    await storage.save_passenger_profile(
        tg_id,
        context.user_data.get("p_name", "Passenger"),
        context.user_data.get("p_age", 25),
        context.user_data.get("p_gender", "M"),
        context.user_data.get("p_berth", "No Preference")
    )

    return await check_credentials_and_next(update, context)

async def check_credentials_and_next(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    username, password = await storage.get_decrypted_credentials(tg_id)

    if not username:
        await update.message.reply_text(
            "⚠️ *IRCTC Account Required*\n\n"
            "You haven't linked your IRCTC ID to this Telegram chat yet.\n"
            "Please enter your *IRCTC Username* now:\n"
            "_(Encrypted with AES-256 for future 1-click bookings)_",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        return STATE_IRCTC_USER

    # User already has IRCTC account saved!
    context.user_data["irctc_user"] = username
    return await check_card_or_confirm(update, context)

async def check_card_or_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    pay_mode = context.user_data.get("payment_method", "Credit / Debit Card")

    # 1. Credit / Debit Card Verification
    if pay_mode == "Credit / Debit Card":
        card = await storage.get_decrypted_card(tg_id)
        if not card or not card.get("card_number"):
            await update.message.reply_text(
                "💳 *Payment Card Required for Card Checkout*\n\n"
                "You haven't linked a payment card to this chat yet.\n"
                "Please enter your *16-Digit Card Number* now:\n"
                "_(Encrypted with AES-256 for this chat only)_",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
            return STATE_CARD_NUM
        else:
            context.user_data["card_on_file"] = True

    # 2. UPI / Instant Pay Verification
    elif pay_mode == "UPI / Instant Pay":
        upi = await storage.get_decrypted_upi(tg_id)
        if not upi:
            await update.message.reply_text(
                "📱 *UPI ID / Mobile Number Required*\n\n"
                "Please enter your **UPI ID / VPA** or registered 10-digit mobile number:\n"
                "*(Examples: `9876543210@paytm`, `username@oksbi`, `name@ybl`)*\n\n"
                "When seats open, payment collect push notifications will be dispatched to this UPI address.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
            return STATE_UPI_ID
        else:
            context.user_data["upi_id"] = upi

    return await render_confirmation(update, context)


async def handle_inline_upi_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    upi_text = update.message.text.strip()
    if is_cancel_command(upi_text):
        return await cancel_booking(update, context)

    is_valid, normalized_upi, detected_app, err_msg = validate_and_normalize_upi(upi_text)
    if not is_valid:
        await update.message.reply_text(
            f"❌ *Invalid UPI / Mobile Number!*\n\n"
            f"• *Issue Detected:* {err_msg}\n\n"
            "👉 Please enter a valid 10-digit Indian mobile number (e.g. `9876543210`) or your full UPI ID (e.g. `name@paytm`, `name@ybl`, `name@okaxis`):",
            parse_mode="Markdown"
        )
        return STATE_UPI_ID

    tg_id = update.effective_user.id
    context.user_data["upi_id"] = normalized_upi
    await storage.save_user_upi(tg_id, normalized_upi)
    await update.message.reply_text(
        f"✅ *UPI Address Successfully Verified & Saved!*\n\n"
        f"• *Linked UPI ID:* `{normalized_upi}`\n"
        f"• *Detected App Gateway:* `{detected_app}`\n"
        f"• *Security Status:* Encrypted with AES-256 for this chat\n\n"
        "📲 *Payment Push Dispatch Notice:*\n"
        f"When seats open at chart preparation, an instant payment collect push request will be dispatched to `{normalized_upi}` on `{detected_app}` so you can approve it with 1 tap!",
        parse_mode="Markdown"
    )
    return await render_confirmation(update, context)

async def handle_inline_irctc_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["temp_irctc_user"] = update.message.text.strip()
    await update.message.reply_text("Now enter your *IRCTC Password*:", parse_mode="Markdown")
    return STATE_IRCTC_PASS

async def handle_inline_irctc_pass(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    irctc_pass = update.message.text.strip()
    irctc_user = context.user_data.get("temp_irctc_user", "")
    tg_id = update.effective_user.id

    await storage.save_user_credentials(tg_id, irctc_user, irctc_pass)
    await update.message.reply_text("🔐 IRCTC credentials encrypted and saved for this chat!")
    return await check_card_or_confirm(update, context)

async def handle_inline_card_num(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    num = update.message.text.strip().replace(" ", "").replace("-", "")
    if not num.isdigit() or len(num) < 12:
        await update.message.reply_text("❌ Please enter a valid 12-19 digit card number:")
        return STATE_CARD_NUM
    context.user_data["temp_card_num"] = num
    await update.message.reply_text("Enter *Card Expiry* in `MM/YY` format (e.g. `12/28`):", parse_mode="Markdown")
    return STATE_CARD_EXP

async def handle_inline_card_exp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    exp = update.message.text.strip()
    if not re.match(r"^\d{2}/\d{2}$", exp):
        await update.message.reply_text("❌ Please enter valid expiry as `MM/YY` (e.g. `12/28`):")
        return STATE_CARD_EXP
    context.user_data["temp_card_exp"] = exp
    await update.message.reply_text("Enter *CVV* (3 or 4 digits):", parse_mode="Markdown")
    return STATE_CARD_CVV

async def handle_inline_card_cvv(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    cvv = update.message.text.strip()
    if not cvv.isdigit() or len(cvv) not in [3, 4]:
        await update.message.reply_text("❌ Please enter a valid 3 or 4 digit CVV:")
        return STATE_CARD_CVV
    context.user_data["temp_card_cvv"] = cvv
    await update.message.reply_text("Enter *Cardholder Name* as printed on card:", parse_mode="Markdown")
    return STATE_CARD_NAME

async def handle_inline_card_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    name = update.message.text.strip()
    tg_id = update.effective_user.id
    u_data = context.user_data

    await storage.save_user_card(
        telegram_id=tg_id,
        card_number=u_data["temp_card_num"],
        card_expiry=u_data["temp_card_exp"],
        card_cvv=u_data["temp_card_cvv"],
        card_holder=name
    )
    await update.message.reply_text("💳 Card details encrypted and saved successfully!")
    return await render_confirmation(update, context)

async def render_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    u = context.user_data
    tg_id = update.effective_user.id
    pay_mode = u.get("payment_method", "Credit / Debit Card")

    card = await storage.get_decrypted_card(tg_id)
    c_num = card.get("card_number", "") if card else ""
    card_mask = f"**** **** **** {c_num[-4:]}" if len(c_num) >= 4 else "Linked Card"

    if pay_mode == "Credit / Debit Card":
        payment_line = f"• *Payment Mode:* `Credit / Debit Card` ({card_mask} - 3D Secure OTP to mobile)"
    elif pay_mode == "IRCTC eWallet":
        payment_line = "• *Payment Mode:* `IRCTC eWallet` (Direct auto-deduction; zero gateway latency)"
    else:
        upi_val = u.get("upi_id") or await storage.get_decrypted_upi(tg_id) or "Linked UPI"
        payment_line = f"• *Payment Mode:* `UPI / Instant Pay` (`{upi_val}`)"

    open_est = irctc_svc.estimate_ticket_opening(u['train_number'], u.get('departure', '00:15'), u['date'], u['coach_class'])

    summary = (
        "📋 *JOURNEY BOOKING SUMMARY:*\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• *Train:* `{u['train_number']}` - {u.get('train_name', 'EXP')}\n"
        f"• *Route:* `{u['source']}` ➔ `{u['dest']}`\n"
        f"• *Date:* `{u['date']}`\n"
        f"• *Class:* `{u['coach_class']}` ({u.get('class_status')})\n"
        f"• *Fare:* `₹{int(u['fare'])}` (+ IRCTC fee)\n"
        f"• *Passenger:* {u['p_name']}, Age {u['p_age']} ({u['p_gender']})\n"
        f"• *Berth:* {u['p_berth']}\n"
        f"{payment_line}\n"
        f"• *Estimated Chart Prep:* `{open_est['target_strike_time']} IST`\n"
        f"  _({open_est['chart_rule_note']})_\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 *CHOOSE EXECUTION MODE:*\n\n"
        "1️⃣ *🎯 SEAT AVAILABILITY SNIPER* (Recommended)\n"
        "   _Never books Waiting List! Continually monitors the train 24/7._\n"
        "   _When charting occurs and unutilized quotas release confirmed berths (or someone cancels), the agent strikes and books the confirmed seat instantly!_\n\n"
        "2️⃣ *⚡ BOOK NOW*\n"
        "   _Attempts immediate live booking right away._\n\n"
        "👉 Tap an option below:"
    )
    confirm_kb = [
        ["🎯 ACTIVATE SEAT SNIPER (Confirmed Berths Only)"],
        ["⚡ BOOK NOW (Instant Checkout)"],
        ["⬅️ Back", "❌ Cancel"]
    ]
    await update.message.reply_text(
        summary,
        reply_markup=ReplyKeyboardMarkup(confirm_kb, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_CONFIRM

async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    ans = update.message.text.strip().upper()

    if is_back_command(ans):
        berth_keyboard = [
            ["Lower Berth (LB)", "Middle Berth (MB)"],
            ["Upper Berth (UB)", "Side Lower (SL)"],
            ["Side Upper (SU)", "No Preference"],
            ["⬅️ Back", "❌ Cancel"]
        ]
        await update.message.reply_text(
            "Select *Berth Preference*:",
            reply_markup=ReplyKeyboardMarkup(berth_keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_PASSENGER_BERTH

    if is_cancel_command(ans):
        return await cancel_booking(update, context)

    # Determine execution mode: default to SNIPER unless user explicitly requested INSTANT
    if "BOOK NOW" in ans or "INSTANT" in ans:
        booking_mode = "INSTANT"
    else:
        booking_mode = "SNIPER"

    u = context.user_data
    tg_id = update.effective_user.id
    chat_id = update.effective_chat.id

    passengers = [{
        "name": u["p_name"],
        "age": u["p_age"],
        "gender": u["p_gender"],
        "berth": u["p_berth"],
        "status": "WL"
    }]

    # Check live seat status
    avail = await irctc_svc.check_availability(u["train_number"], u["date"], u["coach_class"], u["source"], u["dest"])

    task_data = {
        "telegram_id": tg_id,
        "telegram_chat_id": chat_id,
        "source_stn": u["source"],
        "dest_stn": u["dest"],
        "journey_date": u["date"],
        "train_number": u["train_number"],
        "train_name": u.get("train_name", "EXP"),
        "coach_class": u["coach_class"],
        "departure_time": u.get("departure", "00:15"),
        "payment_method": u.get("payment_method", "Credit / Debit Card"),
        "upi_id": u.get("upi_id") or await storage.get_decrypted_upi(tg_id),
        "booking_mode": booking_mode,
        "passengers": passengers,
        "created_at": datetime.datetime.now().isoformat()
    }

    task_id = await storage.add_task(task_data)

    if booking_mode == "INSTANT" and avail["is_available"]:
        await update.message.reply_text(
            "⚡ *Launching Instant Booking & Payment Checkout...*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        # Execute immediate booking through scheduler engine
        if global_scheduler:
            await global_scheduler.check_and_process_task(await storage.get_task(task_id), is_manual=False)
    else:
        # Sniper Mode Activated
        # 1. First remove the custom reply keyboard cleanly from the user's screen
        await update.message.reply_text(
            "🎯 *Seat Sniper activated! Initializing live reservation watchdog...*",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )

        open_est = irctc_svc.estimate_ticket_opening(u['train_number'], u.get('departure', '00:15'), u['date'], u['coach_class'])
        upi_display = f" (`{u.get('upi_id')}`)" if u.get("upi_id") else ""
        initial_card = (
            f"🎯 *SEAT AVAILABILITY SNIPER ACTIVATED!*\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• *Task ID:* `{task_id}`\n"
            f"• *Train:* `{u['train_number']}` - {u.get('train_name', 'EXP')} ({u['coach_class']})\n"
            f"• *Route:* {u['source']} ➔ {u['dest']} ({u['date']})\n"
            f"• *Current Status:* `{avail['status']}`\n"
            f"• *Payment:* `{u.get('payment_method')}`{upi_display}\n"
            f"• *Target:* Confirmed / Current Available Berths (CNF / CURR_AVBL)\n"
            f"• *Estimated Chart Prep:* `{open_est['target_strike_time']} IST`\n"
            f"  _({open_est['chart_rule_note']})_\n\n"
            f"🛡️ *Dynamic Charting Watchdog Active:*\n"
            f"• The agent will **NEVER** book a Waiting List (WL) ticket.\n"
            f"• Polling schedule automatically accelerates: Standby ➔ **60s** at T-60m ➔ **30s** at T-30m ➔ **10s** at T-10m.\n"
            f"• The sniper will strike and alert you the exact moment confirmed berths open!\n\n"
            f"👉 Click *'Try Now'* below to test a live check anytime! 👇"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Try Now", callback_data=f"try_{task_id}"),
                InlineKeyboardButton("❌ Cancel Monitoring", callback_data=f"cancel_{task_id}")
            ]
        ])
        sent_msg = await update.message.reply_text(
            initial_card,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        if global_scheduler:
            global_scheduler.status_message_ids[task_id] = sent_msg.message_id

    return ConversationHandler.END

async def cancel_booking(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Operation cancelled. Type `hi` or `/start` to begin anytime.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ----------------- Inline Button Callbacks ('Try Now', 'Approve UPI' & 'Cancel') -----------------

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data or ""

    if data.startswith("cal_"):
        return await handle_date_calendar_callback(update, context)

    if data.startswith("try_"):
        task_id = data.replace("try_", "")
        try:
            await query.answer("🔄 Checking live IRCTC reservation status...")
        except Exception:
            pass

        if global_scheduler:
            res = await global_scheduler.trigger_manual_check(task_id)
            if not res:
                try:
                    await query.edit_message_text(
                        f"ℹ️ *Task `{task_id}` is no longer active or already completed.*",
                        parse_mode="Markdown"
                    )
                except Exception:
                    pass

    elif data.startswith("cancel_"):
        task_id = data.replace("cancel_", "")
        deleted = await storage.delete_task(task_id)
        try:
            await query.answer("Monitoring cancelled.")
        except Exception:
            pass
        if deleted:
            try:
                await query.edit_message_text(
                    f"🛑 *Monitoring for Task `{task_id}` has been cancelled.*",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        else:
            try:
                await query.edit_message_text(
                    f"ℹ️ *Task `{task_id}` was already stopped.*",
                    parse_mode="Markdown"
                )
            except Exception:
                pass

    elif data.startswith("approve_upi_"):
        chat_id_str = data.replace("approve_upi_", "")
        c_id = int(chat_id_str) if chat_id_str.isdigit() else update.effective_chat.id
        irctc_svc.provide_otp(c_id, "UPI_APPROVED_BY_USER")
        try:
            await query.answer("Payment approval received!", show_alert=True)
        except Exception:
            pass
        try:
            await query.edit_message_text("✅ *Payment Approval Confirmed!* Generating government PNR and ticket PDF...", parse_mode="Markdown")
        except Exception:
            pass

    elif data == "info_start_booking":
        try:
            await query.answer()
        except Exception:
            pass
        await query.message.reply_text(
            "📍 Please enter your journey route in format: `SOURCE-DESTINATION`\n*(Example: `KJM-MAS` or `MAS-NLR`)*",
            parse_mode="Markdown"
        )

    elif data == "info_view_tasks":
        try:
            await query.answer()
        except Exception:
            pass
        return await cmd_tasks(update, context)

    else:
        try:
            await query.answer()
        except Exception:
            pass

# ----------------- Global Message & Leftover Button Interceptor -----------------

async def handle_potential_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Listens for messages that look like Bank OTPs when a payment checkout is in progress,
    leftover confirmation keyboard presses, or recovers active sessions.
    """
    chat_id = update.effective_chat.id
    tg_id = update.effective_user.id
    text = update.message.text.strip()

    if irctc_svc.is_waiting_for_otp(chat_id):
        # User entered an OTP
        success = irctc_svc.provide_otp(chat_id, text)
        if success:
            await update.message.reply_text(f"🔐 Received OTP `{text}`. Submitting to 3D-Secure Bank Gateway...")
        return

    # 1. Check if user clicked a leftover keyboard button from confirmation
    if any(k in text.upper() for k in ["ACTIVATE SEAT SNIPER", "BOOK NOW", "CONFIRM", "BACK"]):
        active_tasks = await storage.get_active_tasks_for_user(tg_id)
        if active_tasks:
            t = active_tasks[-1]
            await update.message.reply_text(
                f"🎯 *Seat Sniper is already active for Task* `{t['task_id']}`!\n\n"
                f"• *Train:* `{t.get('train_number')}` ({t.get('coach_class')}) - {t.get('train_name', 'EXP')}\n"
                f"• *Route:* {t.get('source_stn')} ➔ {t.get('dest_stn')} ({t.get('journey_date')})\n"
                f"• *Status:* `{t.get('latest_status', 'MONITORING')}`\n\n"
                f"💡 Type `/tasks` to view active monitoring or `hi` to start a new search.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "ℹ️ No booking in progress. Send `hi` or `/start` to start a new booking.",
                reply_markup=ReplyKeyboardRemove(),
                parse_mode="Markdown"
            )
        return

    # 2. Check if user tapped a train option like "16022 - KAVERI EXPRESS (00:15)"
    train_match = re.match(r"^(\d{5})\s*-\s*(.+?)(?:\s*\(\d{2}:\d{2}\))?$", text)
    if train_match:
        return await handle_out_of_state_train_selection(update, context)

    # 3. Check if user typed a route like "KJM - MAS" or "KJM-MAS"
    cleaned = re.sub(r"\s*(->|➔|TO|-|–|/)\s*", "-", text, flags=re.IGNORECASE).strip()
    if "-" not in cleaned and " " in cleaned:
        cleaned = re.sub(r"\s+", "-", cleaned).strip()
    parts = [p.strip().upper() for p in cleaned.split("-") if p.strip()]
    if len(parts) == 2 and parts[0].isalpha() and parts[1].isalpha() and len(parts[0]) <= 6 and len(parts[1]) <= 6:
        context.user_data.clear()
        return await handle_route(update, context)

    # Normal unrecognized message outside conversation
    await update.message.reply_text(
        "👋 Hello! Send `hi` or a route like `KJM-MAS` to book a train ticket, `/tasks` for active monitoring, or `/info` for a complete guide.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode="Markdown"
    )
