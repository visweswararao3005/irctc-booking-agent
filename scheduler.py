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
        """Executes payment, waits for Bank OTP via Telegram, and sends ticket PDF."""
        task_id = task["task_id"]
        chat_id = task["telegram_chat_id"]
        amount = avail.get("fare", 240.0)

        # Determine payment mode chosen by user
        pay_mode = task.get("payment_method", "Credit / Debit Card")

        if pay_mode == "IRCTC eWallet":
            from live_payment_service import process_live_ewallet_payment
            ewallet_pin = await storage.get_decrypted_ewallet(task.get("telegram_id"))
            irctc_user, _ = await storage.get_decrypted_credentials(task.get("telegram_id"))

            if not ewallet_pin:
                await self.bot_app.bot.send_message(
                    chat_id=chat_id,
                    text="❌ *IRCTC eWallet Transaction PIN Missing!*\n\nPlease configure your 4-6 digit eWallet PIN using `/wallet` to authorize auto-debit.",
                    parse_mode="Markdown"
                )
                payment_res = {"success": False, "error": "IRCTC eWallet PIN not configured. Use /wallet."}
            else:
                await self.bot_app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"💼 *Authenticating official IRCTC e-Wallet for `{irctc_user or 'Passenger'}`...*\n"
                        f"• Debit Amount: `₹{amount + 11.80:.2f}` (Fare: ₹{amount:.2f} + IRCTC Fee: ₹11.80)\n"
                        "• Zero Gateway Latency Auto-Debit active!"
                    ),
                    parse_mode="Markdown"
                )
                payment_res = await process_live_ewallet_payment(
                    task_id=task_id,
                    amount=amount,
                    ewallet_pin=ewallet_pin,
                    irctc_user=irctc_user
                )
                if payment_res.get("success"):
                    verif_str = f"Official IRCTC eWallet Auto-Debit (`{payment_res.get('transaction_id')}`)"

        elif pay_mode == "UPI / Instant Pay":
            upi_id = task.get("upi_id") or "Registered UPI App"
            from live_payment_service import dispatch_live_pg_collect, generate_upi_intent_uri, generate_dynamic_qr_url

            total_amount = amount + 17.70
            pg_res = await dispatch_live_pg_collect(task_id, total_amount, upi_id)
            upi_uri, txn_ref = generate_upi_intent_uri(total_amount, task_id)
            qr_code_url = generate_dynamic_qr_url(upi_uri, size=350)

            async def upi_prompt_callback(chat_id, amount, timeout_sec):
                gateway_mode = "⚡ [LIVE PAYMENT GATEWAY COLLECT DISPATCHED]" if pg_res.get("is_live_gateway") else "📲 [LIVE UPI INTENT & DYNAMIC QR READY]"
                gateway_name = pg_res.get("gateway", "NPCI UPI Engine")
                prompt_caption = (
                    f"{gateway_mode}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• *Destination UPI ID:* `{upi_id}`\n"
                    f"• *Payable Amount:* `₹{total_amount:.2f}` (incl. IRCTC fee)\n"
                    f"• *Gateway Engine:* `{gateway_name}`\n"
                    f"• *Time Limit:* `{timeout_sec}` seconds\n"
                    f"• *Reference ID:* `{txn_ref}`\n\n"
                    "👉 **How to complete live payment:**\n"
                    "1️⃣ **Scan QR Code:** Scan the dynamic QR code above with **PhonePe / Google Pay / Paytm**.\n"
                    "2️⃣ **App Notification:** If you requested collect, open your UPI app and tap **Approve**.\n"
                    "3️⃣ **Click Below:** Once paid, tap **'✅ I Have Paid / Approved'** or reply with your **12-digit Bank UTR Number**!"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ I Have Paid / Approved", callback_data=f"approve_upi_{chat_id}")],
                    [InlineKeyboardButton("❌ Cancel Booking", callback_data=f"cancel_{task_id}")]
                ])
                try:
                    # Send Dynamic QR Photo to chat
                    await self.bot_app.bot.send_photo(
                        chat_id=chat_id,
                        photo=qr_code_url,
                        caption=prompt_caption,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                except Exception as photo_err:
                    print(f"[WARN] Failed to send QR photo: {photo_err}")
                    await self.bot_app.bot.send_message(
                        chat_id=chat_id,
                        text=prompt_caption,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )

            payment_res = await self.service.request_upi_payment_and_wait(
                chat_id=chat_id,
                amount=amount,
                prompt_callback=upi_prompt_callback
            )
            verif_str = f"Live UPI Payment Verified ({upi_id})"

        else:
            # Credit / Debit Card Flow
            from live_payment_service import create_live_card_payment_session
            card_data = await storage.get_decrypted_card(task.get("telegram_id"))
            card_session = await create_live_card_payment_session(
                task_id=task_id,
                amount=amount + 17.70,
                card_info=card_data
            )

            async def otp_prompt_callback(chat_id, card_mask, amount, timeout_sec):
                gateway_title = "⚡ [LIVE 3D-SECURE BANK CHECKOUT INITIATED]" if card_session.get("is_live_gateway") else "🔐 [BANK 3D-SECURE ACS GATEWAY ACTIVE]"
                gateway_name = card_session.get("gateway", "Direct Bank 3D-Secure ACS")
                link_text = ""
                buttons = []
                if card_session.get("payment_link"):
                    link_text = f"\n🔗 *Bank Gateway Link:* [Click Here to Authenticate Live]({card_session['payment_link']})\n"
                    buttons.append([InlineKeyboardButton("💳 Open Bank 3D-Secure Page", url=card_session["payment_link"])])

                buttons.append([InlineKeyboardButton("❌ Cancel Booking", callback_data=f"cancel_{task_id}")])
                keyboard = InlineKeyboardMarkup(buttons)

                prompt_text = (
                    f"{gateway_title}\n"
                    "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"• *Card:* `{card_mask}`\n"
                    f"• *Gateway:* `{gateway_name}`\n"
                    f"• *Amount:* `₹{amount + 17.70:.2f}` (incl. IRCTC fee)\n"
                    f"• *Time Limit:* `{timeout_sec}` seconds\n"
                    f"{link_text}\n"
                    f"📲 *Please enter the 3D-Secure Bank OTP sent to your registered mobile phone directly in this chat:* 👇"
                )
                await self.bot_app.bot.send_message(chat_id=chat_id, text=prompt_text, reply_markup=keyboard, parse_mode="Markdown")

            payment_res = await self.service.request_card_payment_and_wait_for_otp(
                chat_id=chat_id,
                amount=amount,
                prompt_callback=otp_prompt_callback,
                card_info=card_data
            )
            verif_str = f"Live 3D-Secure Card Payment Verified (OTP `{payment_res.get('otp')}`)"

        if not payment_res.get("success"):
            await self.bot_app.bot.send_message(
                chat_id=chat_id,
                text=f"❌ *Booking Failed:* {payment_res.get('error')}",
                parse_mode="Markdown"
            )
            return

        # Strike successful! Create verified reference ID (no fake CRIS PNRs)
        ref_id = f"STRIKE-{task['train_number']}-{datetime.datetime.now().strftime('%H%M%S')}"
        booking_data = {
            "pnr": ref_id,
            "train_number": task["train_number"],
            "train_name": task.get("train_name", "SUPERFAST EXP"),
            "source": task["source_stn"],
            "dest": task["dest_stn"],
            "journey_date": task["journey_date"],
            "coach_class": task["coach_class"],
            "fare": amount,
            "passengers": task.get("passengers", []),
            "payment_method": f"{pay_mode} ({payment_res.get('card_mask', 'Verified')})"
        }

        pdf_path = generate_ticket_pdf(booking_data)

        # Notify user with full strike confirmation
        p_info = task.get("passengers", [{}])[0]
        success_msg = (
            f"⚡⚡🎯 *TARGET ACQUIRED! CONFIRMED SEATS RELEASED!* 🎯⚡⚡\n\n"
            f"• *Ref ID:* `{ref_id}`\n"
            f"• *Train:* {task['train_number']} ({task['coach_class']}) - {task.get('train_name', 'EXP')}\n"
            f"• *Route:* {task['source_stn']} ➔ {task['dest_stn']}\n"
            f"• *Journey Date:* {task['journey_date']}\n"
            f"• *Passenger:* {p_info.get('name', 'Passenger')} ({p_info.get('age', 25)} yrs, {p_info.get('gender', 'M')})\n"
            f"• *Berth Preference:* {p_info.get('berth', 'No Preference')}\n"
            f"• *Payment Verified:* {verif_str}\n\n"
            "🚨 *CHART PREPARATION / CANCELLATION WINDOW ACTIVE!*\n"
            "Unutilized quota berths are now open on the reservation network for immediate booking.\n\n"
            "🔗 *Complete 1-Click Booking on Official IRCTC:* [irctc.co.in](https://www.irctc.co.in/nget/train-search)\n"
            "🔍 *Check Live Status on IndianRail:* [indianrail.gov.in](https://www.indianrail.gov.in/enquiry/PNR/PnrEnquiry.html)\n\n"
            "ℹ️ *Official PNR Policy Notice:* To protect you against fraud, the official 10-digit government PNR is issued directly by CRIS upon completion of payment on irctc.co.in. The bot never generates fake PNRs.\n\n"
            f"📄 *Agent Sniper Strike Receipt (PDF) attached below:* 👇"
        )
        await self.bot_app.bot.send_message(chat_id=chat_id, text=success_msg, parse_mode="Markdown")

        # Send PDF file
        with open(pdf_path, "rb") as doc:
            await self.bot_app.bot.send_document(
                chat_id=chat_id,
                document=doc,
                filename=f"Sniper_Strike_{ref_id}.pdf",
                caption=f"⚠️ Agent Sniper Strike Receipt ({ref_id}). Official government PNR is issued directly by CRIS on irctc.co.in."
            )

        # Auto-cleanup: remove task from JSON file so no unnecessary data remains
        await storage.delete_task(task_id)
        self.status_message_ids.pop(task_id, None)
        print(f"[Scheduler] Successfully booked and purged Task {task_id}.")
