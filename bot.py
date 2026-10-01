"""Multi-user Telegram Bot with FSM, Per-Chat IRCTC credentials, Live Pricing, and Try Now support."""
import re
import datetime
from typing import Dict, Any
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
    STATE_PASSENGER_NAME,
    STATE_PASSENGER_AGE,
    STATE_PASSENGER_GENDER,
    STATE_PASSENGER_BERTH,
    STATE_IRCTC_USER,
    STATE_IRCTC_PASS,
    STATE_CARD_NUM,
    STATE_CARD_EXP,
    STATE_CARD_CVV,
    STATE_CARD_NAME,
    STATE_CONFIRM
) = range(15)

# Conversation States for Account Setup/Change
STATE_SET_USER, STATE_SET_PASS = range(15, 17)

# Conversation States for Standalone Card Setup/Change
STATE_SET_CARD_NUM, STATE_SET_CARD_EXP, STATE_SET_CARD_CVV, STATE_SET_CARD_NAME = range(17, 21)


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

    welcome_msg = (
        f"🚆 *Welcome to the IRCTC AI Booking Agent, {tg_user.first_name}!*\n\n"
        "I will help you search real live trains, check coach availability with fares, "
        "and continuously monitor Waiting List tickets with auto-booking.\n\n"
        "📍 Please enter your journey route in format: `SOURCE-DESTINATION`\n"
        "*(Example: `KJM-MAS` or `MAS-NLR`)*"
    )
    await update.message.reply_text(
        welcome_msg,
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["❌ Cancel"]], resize_keyboard=True)
    )
    return STATE_ROUTE

async def handle_route(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = update.message.text.strip().upper()
    if is_cancel_command(text):
        return await cancel_booking(update, context)

    parts = text.split("-")
    if len(parts) != 2 or not parts[0].isalpha() or not parts[1].isalpha():
        await update.message.reply_text("❌ Please enter valid station codes as `SRC-DST` (e.g. `KJM-MAS` or `MAS-NLR`):")
        return STATE_ROUTE

    context.user_data["source"] = parts[0]
    context.user_data["dest"] = parts[1]

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    date_keyboard = [
        [today_str, tomorrow_str],
        ["⬅️ Back", "❌ Cancel"]
    ]
    await update.message.reply_text(
        f"✅ Route Selected: *{parts[0]}* ➔ *{parts[1]}*\n\n"
        "📅 Now enter your *Journey Date* in `YYYY-MM-DD` format\n"
        "*(or choose from quick options below)*:",
        reply_markup=ReplyKeyboardMarkup(date_keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
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

    # Normalize DD-MM-YYYY to YYYY-MM-DD if needed
    if re.match(r"^\d{2}-\d{2}-\d{4}$", raw_date):
        d, m, y = raw_date.split("-")
        date_str = f"{y}-{m}-{d}"
    elif re.match(r"^\d{4}-\d{2}-\d{2}$", raw_date):
        date_str = raw_date
    else:
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        await update.message.reply_text(
            "❌ Invalid format. Please enter date as `YYYY-MM-DD` (e.g. `2026-10-05`):",
            reply_markup=ReplyKeyboardMarkup([[today_str, tomorrow_str], ["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_DATE

    context.user_data["date"] = date_str
    src = context.user_data["source"]
    dst = context.user_data["dest"]

    await update.message.reply_text(f"🔍 *Fetching live trains for {src} ➔ {dst} on {date_str}...*", parse_mode="Markdown")

    trains = await irctc_svc.search_trains(src, dst, date_str)
    context.user_data["train_list"] = trains

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    if not trains:
        await update.message.reply_text(
            f"⚠️ No matching trains found running on `{date_str}` for `{src} ➔ {dst}`.\n"
            "Please choose or enter another journey date:",
            reply_markup=ReplyKeyboardMarkup([[today_str, tomorrow_str], ["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
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

    await update.message.reply_text(
        msg,
        reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
        parse_mode="Markdown"
    )
    return STATE_TRAIN_SELECT

async def handle_train_select(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    selected_text = update.message.text.strip()
    if is_cancel_command(selected_text):
        return await cancel_booking(update, context)

    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime("%Y-%m-%d")

    if is_back_command(selected_text):
        await update.message.reply_text(
            f"Route: *{context.user_data.get('source')}* ➔ *{context.user_data.get('dest')}*\n\n"
            "📅 Enter your *Journey Date* in `YYYY-MM-DD` format:",
            reply_markup=ReplyKeyboardMarkup([[today_str, tomorrow_str], ["⬅️ Back", "❌ Cancel"]], resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_DATE

    # Intelligent Auto-Detection: if user entered a date like 2026-10-04, switch date!
    if re.match(r"^\d{4}-\d{2}-\d{2}$", selected_text) or re.match(r"^\d{2}-\d{2}-\d{4}$", selected_text):
        return await handle_date(update, context)

    train_number = selected_text.split(" - ")[0].split()[0].strip()

    # Locate train details
    train_info = next((t for t in context.user_data.get("train_list", []) if t["number"] == train_number), None)
    if not train_info:
        await update.message.reply_text(
            "❌ Please tap one of the train options from the keyboard below, or click '⬅️ Back':"
        )
        return STATE_TRAIN_SELECT

    context.user_data["train_number"] = train_number
    context.user_data["train_name"] = train_info.get("name", "EXP")
    context.user_data["departure"] = train_info.get("departure", "00:00")
    context.user_data["arrival"] = train_info.get("arrival", "00:00")

    await update.message.reply_text(f"⏳ Checking live availability & fares for Train *{train_number}*...", parse_mode="Markdown")

    # Fetch classes WITH PRICES AND AVAILABILITY
    class_options = await irctc_svc.get_class_options_with_prices(
        train_number, context.user_data["source"], context.user_data["dest"], context.user_data["date"]
    )
    context.user_data["class_options"] = class_options

    msg = f"🎟️ *Select Coach Class for Train {train_number} ({train_info.get('name')}):*\n\n"
    keyboard = []
    for c in class_options:
        msg += f"• *{c['class_code']}:* `{c['status']}` — *₹{int(c['fare'])}*\n"
        keyboard.append([f"{c['class_code']} - {c['status']} (Rs. {int(c['fare'])})"])

    keyboard.append(["⬅️ Back", "❌ Cancel"])

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

    await update.message.reply_text(
        f"Selected Class: *{coach_code}* (Fare: ₹{int(context.user_data['fare'])})\n\n"
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
        # Re-display classes
        class_options = context.user_data.get("class_options", [])
        keyboard = [[f"{c['class_code']} - {c['status']} (Rs. {int(c['fare'])})"] for c in class_options]
        keyboard.append(["⬅️ Back", "❌ Cancel"])
        await update.message.reply_text(
            f"🎟️ *Select Coach Class for Train {context.user_data.get('train_number')}:*",
            reply_markup=ReplyKeyboardMarkup(keyboard, resize_keyboard=True),
            parse_mode="Markdown"
        )
        return STATE_CLASS_SELECT

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

    # Verify if this user has IRCTC credentials configured
    tg_id = update.effective_user.id
    username, password = await storage.get_decrypted_credentials(tg_id)

    if not username:
        # Ask for credentials now
        await update.message.reply_text(
            "⚠️ *IRCTC Account Required*\n\n"
            "You haven't linked your IRCTC ID to this Telegram chat yet.\n"
            "Please enter your *IRCTC Username* now:",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        return STATE_IRCTC_USER

    # Check payment card
    return await check_card_or_confirm(update, context)

async def check_card_or_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    tg_id = update.effective_user.id
    card = await storage.get_decrypted_card(tg_id)

    if not card or not card.get("card_number"):
        await update.message.reply_text(
            "💳 *Payment Card Required for Auto-Booking*\n\n"
            "You haven't linked a payment card to this chat yet.\n"
            "Please enter your *16-Digit Card Number* now:\n"
            "_(Encrypted with AES-256 for this chat only)_",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        return STATE_CARD_NUM

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
    card = await storage.get_decrypted_card(tg_id)
    c_num = card.get("card_number", "") if card else ""
    card_mask = f"**** **** **** {c_num[-4:]}" if len(c_num) >= 4 else "Linked Card"

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
        f"• *Payment Card:* `{card_mask}` (OTP in chat)\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "👉 Type `CONFIRM` to book, or tap `⬅️ Back` to edit:"
    )
    confirm_kb = [
        ["CONFIRM", "⬅️ Back"],
        ["❌ Cancel"]
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

    if is_cancel_command(ans) or ans != "CONFIRM":
        return await cancel_booking(update, context)


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
        "passengers": passengers,
        "created_at": datetime.datetime.now().isoformat()
    }

    task_id = await storage.add_task(task_data)

    if avail["is_available"]:
        await update.message.reply_text(
            "⚡ *Seats are Available!* Launching instant booking & payment checkout...",
            reply_markup=ReplyKeyboardRemove(),
            parse_mode="Markdown"
        )
        # Execute immediate booking through scheduler engine
        if global_scheduler:
            await global_scheduler.check_and_process_task(await storage.get_task(task_id), is_manual=False)
    else:
        # Waiting list -> continuous monitor
        initial_card = (
            f"⏳ *SEATS CURRENTLY IN WAITING LIST ({avail['status']})*\n\n"
            f"🔄 *Continuous Polling Monitor Activated:*\n"
            f"• *Task ID:* `{task_id}`\n"
            f"• *Train:* `{u['train_number']}` ({u['coach_class']})\n"
            f"• *Route:* {u['source']} ➔ {u['dest']}\n\n"
            f"The bot will check automatically every 60 seconds and report each try.\n"
            f"Click *'Try Now'* below to trigger an immediate check anytime! 👇"
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

# ----------------- Inline Button Callbacks ('Try Now' & 'Cancel') -----------------

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data.startswith("try_"):
        task_id = data.replace("try_", "")
        if global_scheduler:
            res = await global_scheduler.trigger_manual_check(task_id)
            if not res:
                await query.answer("Task is no longer active or already completed.", show_alert=True)
            else:
                await query.answer("Manual check completed!")
    elif data.startswith("cancel_"):
        task_id = data.replace("cancel_", "")
        deleted = await storage.delete_task(task_id)
        if deleted:
            await query.edit_message_text(
                f"🛑 *Monitoring for Task `{task_id}` has been cancelled.*",
                parse_mode="Markdown"
            )
        else:
            await query.answer("Task was already stopped.", show_alert=True)

# ----------------- Global OTP Interceptor -----------------

async def handle_potential_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Listens for messages that look like Bank OTPs when a payment checkout is in progress.
    """
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if irctc_svc.is_waiting_for_otp(chat_id):
        # User entered an OTP
        success = irctc_svc.provide_otp(chat_id, text)
        if success:
            await update.message.reply_text(f"🔐 Received OTP `{text}`. Submitting to 3D-Secure Bank Gateway...")
        return

    # Normal unrecognized message outside conversation
    await update.message.reply_text("👋 Hello! Send `hi` or `/start` to book a train ticket, or `/account` to manage credentials.")
