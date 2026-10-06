"""Background Poller and Manual Try Engine with continuous Telegram try-feedback."""
import asyncio
import datetime
import random
from typing import Dict, Any, Optional
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from telegram.error import TelegramError
from config import POLL_INTERVAL_SECONDS
import storage
from security import mask_text
from ticket_generator import generate_ticket_pdf
from irctc_service import IRCTCService

def compute_dynamic_polling_interval(seconds_until_strike: float, seconds_until_watchdog_start: float = 0) -> tuple[int, str]:
    """
    Computes dynamic polling interval based on proximity to target opening/charting time:
    - If before watchdog start time (>0s): Scheduled Sleep (ZERO continuous 15-min loops!)
    - 60m to 30m away: 60s (1 min) high-alert polling (active loop starts!)
    - 30m to 10m away: 30s pre-strike ramp-up
    - 10m before to +15m after: 10s hyper-drive strike window (striking the spot)
    - Post-opening monitoring: 30s
    """
    if seconds_until_watchdog_start > 0:
        return int(seconds_until_watchdog_start), "💤 SCHEDULED SLEEP (Dormant until start point; zero spam)"

    s = seconds_until_strike
    if s > 7200:
        return 900, "💤 DORMANT STANDBY (Opens in >2 hrs)"
    elif s > 3600:
        return 300, "⏳ WARMUP PHASE (1h-2h to Opening)"
    elif s > 1800:
        return 60, "🟡 HIGH ALERT (T-60m Countdown | Polling every 60s)"
    elif s > 600:
        return 30, "🟠 PRE-STRIKE RAMP-UP (T-30m Countdown | Polling every 30s)"
    elif s > -900:
        return 10, "🔴 HYPER-DRIVE STRIKE ACTIVE (Hitting Chart Prep Spot | Polling every 10s)"
    else:
        return 30, "🎯 2ND CHART / CURRENT BOOKING WATCHDOG (Polling every 30s)"

class BackgroundBookingWorker:
    def __init__(self, bot_app, irctc_service: IRCTCService):
        self.bot_app = bot_app
        self.service = irctc_service
        self.is_running = False
        # Store message_id of the active monitoring status card per task_id: {task_id: message_id}
        self.status_message_ids: Dict[str, int] = {}

    def get_monitoring_keyboard(self, task_id: str) -> InlineKeyboardMarkup:
        """Inline buttons allowing user to trigger manual check or cancel monitoring."""
        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🔄 Try Now", callback_data=f"try_{task_id}"),
                InlineKeyboardButton("❌ Cancel Monitoring", callback_data=f"cancel_{task_id}")
            ]
        ])

    async def start(self):
        """Starts the active background polling loop with dynamic interval scheduling."""
        self.is_running = True
        print("[Scheduler] Started active train monitoring worker with dynamic countdown engine.")
        while self.is_running:
            try:
                await self.poll_all_active_tasks()
            except Exception as e:
                print(f"[Scheduler Loop Error] {e}")
            await asyncio.sleep(5)

    async def poll_all_active_tasks(self):
        """Checks availability for all active monitoring tasks based on dynamic intervals."""
        active_tasks = await storage.get_active_tasks()
        now_ts = datetime.datetime.now().timestamp()
        for task in active_tasks:
            try:
                # Point-of-time check: If current time is before watchdog start time, DO NOT LOOP!
                watchdog_start_ts = task.get("watchdog_start_timestamp", 0)
                if watchdog_start_ts and now_ts < watchdog_start_ts:
                    # If already checked at least once on creation, sleep silently until start point
                    if task.get("attempts_count", 0) > 0:
                        continue

                last_ts = task.get("last_checked_timestamp", 0)
                interval = task.get("polling_interval", POLL_INTERVAL_SECONDS)
                if now_ts - last_ts >= interval:
                    await self.check_and_process_task(task, is_manual=False)
            except Exception as err:
                print(f"[Scheduler Error on Task {task.get('task_id')}] {err}")

    async def trigger_manual_check(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Invoked when user clicks the '🔄 Try Now' button in Telegram."""
        task = await storage.get_task(task_id)
        if not task or task.get("status") != "MONITORING":
            return None
        return await self.check_and_process_task(task, is_manual=True)

    async def check_and_process_task(self, task: Dict[str, Any], is_manual: bool = False) -> Dict[str, Any]:
        task_id = task["task_id"]
        chat_id = task["telegram_chat_id"]
        train_no = task["train_number"]
        coach_class = task["coach_class"]
        date = task["journey_date"]
        source = task["source_stn"]
        dest = task["dest_stn"]

        # Calculate opening estimation and dynamic countdown
        open_est = self.service.estimate_ticket_opening(
            train_no,
            task.get("departure_time", "00:15"),
            date,
            coach_class
        )
        diff_sec = open_est.get("seconds_until_strike", 3600)
        sec_to_start = open_est.get("seconds_until_watchdog_start", 0)
        is_active = open_est.get("is_watchdog_active", True)
        interval_sec, phase_desc = compute_dynamic_polling_interval(diff_sec, sec_to_start if not is_manual else 0)

        # Increment attempts count
        attempts = task.get("attempts_count", 0) + 1
        now_dt = datetime.datetime.now()
        now_str = now_dt.strftime("%H:%M:%S")

        # Query availability
        avail = await self.service.check_availability(train_no, date, coach_class, source, dest)
        await storage.update_task(task_id, {
            "attempts_count": attempts,
            "last_checked": now_str,
            "last_checked_timestamp": now_dt.timestamp(),
            "latest_status": avail["status"],
            "polling_interval": interval_sec,
            "phase_desc": phase_desc,
            "target_strike_time": open_est["target_strike_time"],
            "target_strike_timestamp": open_est["target_strike_timestamp"],
            "target_label": open_est["target_label"],
            "watchdog_start_time": open_est["watchdog_start_time"],
            "watchdog_start_timestamp": open_est["watchdog_start_timestamp"],
            "is_watchdog_active": is_active,
            "chart_rule_note": open_est["chart_rule_note"]
        })

        tag = "⚡ [MANUAL TRY NOW]" if is_manual else f"🔄 [AUTOMATIC TRY #{attempts}]"

        # Sniper Mode Check: ONLY book if seat is Confirmed / Current Available, NEVER Waiting List
        is_sniper = task.get("booking_mode") == "SNIPER"
        status_upper = avail.get("status", "").upper()
        is_wl = any(x in status_upper for x in ["WL", "WAITING", "RAC", "REGRET", "PENDING"])
        can_book = avail["is_available"] and (not is_sniper or not is_wl)

        if can_book:
            # SEAT AVAILABLE & CONFIRMED! Initiate Booking Workflow
            status_text = (
                f"⚡⚡🎯 *TARGET ACQUIRED! CONFIRMED SEATS RELEASED!* 🎯⚡⚡\n\n"
                f"{tag} at `{now_str}`\n"
                f"• *Train:* {train_no} ({coach_class})\n"
                f"• *Status:* {avail['status']}\n"
                f"• *Seats Open:* {avail.get('seats', 1)} Berths\n\n"
                f"⚡ *Sniper Triggered! Firing instant booking strike...*"
            )
            await self._send_or_edit_status(chat_id, task_id, status_text, keyboard=None)
            await self._execute_booking_flow(task, avail)
            return {"status": "BOOKED", "details": avail}
        else:
            # Still in Waiting List / Charting Pending -> Send update to user
            mode_desc = "🎯 [SEAT SNIPER WATCHDOG ACTIVE]" if is_sniper else tag
            quota_line = f"• *Class Quota:* `{avail.get('quota')} Berths`\n" if avail.get("quota") else ""
            chart_line = (
                f"• *Estimated Chart Prep:* `{open_est['target_strike_time']} IST`\n"
                f"  • *Chart Rule:* {open_est['chart_rule_note']}\n"
            )

            if not is_active:
                watchdog_mode_line = (
                    f"• *Watchdog Start Time:* `{open_est['watchdog_start_time']} IST`\n"
                    f"• *Monitoring Mode:* 💤 `SCHEDULED SLEEP`\n"
                    f"  • *Schedule Note:* Dormant sleep; zero 15-min spam. Active polling loop starts 1 hr before chart prep.\n"
                )
            else:
                watchdog_mode_line = (
                    f"• *Monitoring Phase:* {phase_desc}\n"
                    f"• *Dynamic Polling Rate:* `Every {interval_sec}s` (Auto-decreasing at opening)\n"
                )

            status_text = (
                f"{mode_desc} at `{now_str}`\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"• *Train:* `{train_no}` - {task.get('train_name', 'EXP')} | *Class:* `{coach_class}`\n"
                f"• *Route:* {source} ➔ {dest} ({date})\n"
                f"{quota_line}"
                f"• *Current Status:* `{avail['status']}`\n"
                f"• *Target:* Confirmed / Current Available (`CURR_AVBL`)\n"
                f"{chart_line}"
                f"{watchdog_mode_line}"
                f"• *Total Checks:* `{attempts}`\n\n"
                f"🛡️ *Sniper is holding fire. It will NEVER book Waiting List.*\n"
                f"As chart preparation approaches (T-60m ➔ T-30m ➔ T-10m), the retry rate automatically accelerates to hit the exact spot when unutilized berths drop into the reservation pool!"
            )
            keyboard = self.get_monitoring_keyboard(task_id)
            await self._send_or_edit_status(chat_id, task_id, status_text, keyboard=keyboard)
            return {"status": "STILL_WAITING", "details": avail}

    async def _send_or_edit_status(self, chat_id: int, task_id: str, text: str, keyboard=None):
        """Sends status message or updates previous message in-place to avoid spam."""
        msg_id = self.status_message_ids.get(task_id)
        if msg_id:
            try:
                await self.bot_app.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
                return
            except TelegramError as te:
                err_str = str(te).lower()
                if "can't parse entities" in err_str:
                    try:
                        clean = text.replace("*", "").replace("`", "").replace("_", "")
                        await self.bot_app.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=clean,
                            reply_markup=keyboard,
                            parse_mode=None
                        )
                        return
                    except Exception:
                        pass
                # If editing fails for other reasons (e.g. message too old), fall through to send fresh
                pass

        try:
            new_msg = await self.bot_app.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            self.status_message_ids[task_id] = new_msg.message_id
        except Exception:
            clean_text = text.replace("*", "").replace("`", "").replace("_", "")
            try:
                new_msg = await self.bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=clean_text,
                    reply_markup=keyboard,
                    parse_mode=None
                )
                self.status_message_ids[task_id] = new_msg.message_id
            except Exception:
                pass

    async def _execute_booking_flow(self, task: Dict[str, Any], avail: Dict[str, Any]):
        """
        Dispatches authentic IRCTC Payment Action Notification to the user.
        Strict Financial Safety Policy:
        - NEVER assumes or simulates payment deduction.
        - Uses user's linked IRCTC account credentials.
        - Prompts user to complete authentic payment on IRCTC / UPI app.
        - Enforces mandatory verification with official 10-digit CRIS PNR.
        """
        task_id = task["task_id"]
        chat_id = task["telegram_chat_id"]
        tg_id = task.get("telegram_id")
        amount = avail.get("fare", 240.0)
        pay_mode = task.get("payment_method", "UPI / Instant Pay")
        p_info = task.get("passengers", [{}])[0]

        irctc_user, _ = await storage.get_decrypted_credentials(tg_id)
        user_display = irctc_user or "Linked IRCTC Account"

        # Update task status to awaiting payment
        task["latest_status"] = "AWAITING_IRCTC_PAYMENT_AND_PNR"
        task["payable_fare"] = amount
        await storage.save_task(task)

        buttons = [
            [InlineKeyboardButton("✅ I Have Paid on IRCTC — Verify Booking", callback_data=f"verify_booking_{task_id}")],
            [InlineKeyboardButton("🔗 Open Official IRCTC Portal", url="https://www.irctc.co.in/nget/train-search")],
            [InlineKeyboardButton("❌ Cancel Booking", callback_data=f"cancel_{task_id}")]
        ]
        keyboard = InlineKeyboardMarkup(buttons)

        if pay_mode == "IRCTC eWallet":
            ewallet_pin = await storage.get_decrypted_ewallet(tg_id)
            pin_note = "PIN On File (Encrypted)" if ewallet_pin else "PIN Needed on IRCTC"
            total_ewallet_amount = amount + 11.80
            prompt_text = (
                "🚨 <b>CONFIRMED SEATS OPEN ON IRCTC — PAYMENT ACTION REQUIRED</b> 🚨\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"• <b>Train:</b> <code>{task['train_number']}</code> ({task['coach_class']}) - {task.get('train_name', 'EXP')}\n"
                f"• <b>Route:</b> {task['source_stn']} ➔ {task['dest_stn']} | <b>Date:</b> {task['journey_date']}\n"
                f"• <b>Passenger:</b> {p_info.get('name', 'Passenger')} ({p_info.get('age', 25)} yrs, {p_info.get('gender', 'M')})\n"
                f"• <b>Berth Preference:</b> {p_info.get('berth', 'No Preference')}\n"
                f"• <b>IRCTC Account:</b> <code>{user_display}</code>\n"
                f"• <b>Payable Amount:</b> <code>₹{total_ewallet_amount:.2f}</code> (Fare: ₹{amount:.2f} + IRCTC Fee: ₹11.80)\n"
                f"• <b>Payment Rail:</b> <code>Official IRCTC eWallet</code> ({pin_note})\n\n"
                "💼 <b>HOW TO COMPLETE YOUR PAYMENT:</b>\n"
                f"1️⃣ Login to your official IRCTC account <code>{user_display}</code> on <a href='https://www.irctc.co.in/nget/train-search'>irctc.co.in</a>.\n"
                f"2️⃣ Confirm payment of <b>₹{total_ewallet_amount:.2f}</b> from your eWallet deposit balance.\n\n"
                "⚠️ <b>STRICT FINANCIAL SAFETY NOTICE:</b>\n"
                "Because real money is involved, this bot <b>NEVER assumes or fakes payment success</b>.\n"
                "Once completed, tap <b>'✅ I Have Paid on IRCTC — Verify Booking'</b> below and provide your <b>10-digit CRIS PNR</b> to verify with Indian Railways!"
            )
            await self.bot_app.bot.send_message(chat_id=chat_id, text=prompt_text, reply_markup=keyboard, parse_mode="HTML")

        elif pay_mode == "Credit / Debit Card":
            card_data = await storage.get_decrypted_card(tg_id)
            c_num = card_data.get("card_number", "") if card_data else ""
            card_mask = f"**** **** **** {c_num[-4:]}" if len(c_num) >= 4 else "Saved Bank Card"
            total_card_amount = amount + 17.70
            prompt_text = (
                "🚨 <b>CONFIRMED SEATS OPEN ON IRCTC — PAYMENT ACTION REQUIRED</b> 🚨\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"• <b>Train:</b> <code>{task['train_number']}</code> ({task['coach_class']}) - {task.get('train_name', 'EXP')}\n"
                f"• <b>Route:</b> {task['source_stn']} ➔ {task['dest_stn']} | <b>Date:</b> {task['journey_date']}\n"
                f"• <b>Passenger:</b> {p_info.get('name', 'Passenger')} ({p_info.get('age', 25)} yrs, {p_info.get('gender', 'M')})\n"
                f"• <b>Berth Preference:</b> {p_info.get('berth', 'No Preference')}\n"
                f"• <b>IRCTC Account:</b> <code>{user_display}</code>\n"
                f"• <b>Payable Amount:</b> <code>₹{total_card_amount:.2f}</code> (incl. IRCTC fee)\n"
                f"• <b>Card Rail:</b> <code>{card_mask}</code>\n\n"
                "💳 <b>HOW TO COMPLETE YOUR PAYMENT:</b>\n"
                f"1️⃣ Open official <a href='https://www.irctc.co.in/nget/train-search'>irctc.co.in</a> under account <code>{user_display}</code>.\n"
                "2️⃣ Complete payment on the official IRCTC card payment gateway using bank 3D-Secure OTP.\n\n"
                "⚠️ <b>STRICT FINANCIAL SAFETY NOTICE:</b>\n"
                "Because real money is involved, this bot <b>NEVER assumes or fakes payment success</b>.\n"
                "Once approved, tap <b>'✅ I Have Paid on IRCTC — Verify Booking'</b> below and provide your <b>10-digit CRIS PNR</b> to verify with Indian Railways!"
            )
            await self.bot_app.bot.send_message(chat_id=chat_id, text=prompt_text, reply_markup=keyboard, parse_mode="HTML")

        else:
            # UPI / Instant Pay Mode
            upi_id = task.get("upi_id") or "Your Registered UPI App"
            from live_payment_service import generate_upi_intent_uri, generate_dynamic_qr_url
            total_upi_amount = amount + 17.70
            upi_uri, txn_ref = generate_upi_intent_uri(total_upi_amount, task_id)
            qr_code_url = generate_dynamic_qr_url(upi_uri, size=350)

            prompt_text = (
                "🚨 <b>CONFIRMED SEATS OPEN ON IRCTC — PAYMENT ACTION REQUIRED</b> 🚨\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"• <b>Train:</b> <code>{task['train_number']}</code> ({task['coach_class']}) - {task.get('train_name', 'EXP')}\n"
                f"• <b>Route:</b> {task['source_stn']} ➔ {task['dest_stn']} | <b>Date:</b> {task['journey_date']}\n"
                f"• <b>Passenger:</b> {p_info.get('name', 'Passenger')} ({p_info.get('age', 25)} yrs, {p_info.get('gender', 'M')})\n"
                f"• <b>Berth Preference:</b> {p_info.get('berth', 'No Preference')}\n"
                f"• <b>IRCTC Account:</b> <code>{user_display}</code>\n"
                f"• <b>Payable Amount:</b> <code>₹{total_upi_amount:.2f}</code> (Official IRCTC Fare + fee)\n"
                f"• <b>Destination UPI VPA:</b> <code>{upi_id}</code>\n\n"
                "📲 <b>HOW TO COMPLETE YOUR PAYMENT:</b>\n"
                f"1️⃣ <b>Check Your UPI App:</b> Open PhonePe, Google Pay, Paytm, or BHIM linked to <code>{upi_id}</code>.\n"
                f"2️⃣ <b>Approve IRCTC Request:</b> Check for the payment request from <b>IRCTC</b> (or scan QR code) for <b>₹{total_upi_amount:.2f}</b> and authorize with your UPI PIN.\n"
                "3️⃣ <b>Direct IRCTC Checkout:</b> You can also complete it on <a href='https://www.irctc.co.in/nget/train-search'>irctc.co.in</a>.\n\n"
                "⚠️ <b>STRICT FINANCIAL SAFETY NOTICE:</b>\n"
                "Because real money is involved, this bot <b>NEVER assumes or fakes payment success</b>.\n"
                "After paying, tap <b>'✅ I Have Paid on IRCTC — Verify Booking'</b> below and enter your <b>10-digit CRIS PNR Number</b> from your IRCTC SMS to verify!"
            )
            try:
                await self.bot_app.bot.send_photo(
                    chat_id=chat_id,
                    photo=qr_code_url,
                    caption=prompt_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
            except Exception as e:
                print(f"[WARN] Failed to send photo: {e}")
                await self.bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=prompt_text,
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
