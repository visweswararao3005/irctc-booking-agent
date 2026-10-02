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
        """Starts the infinite background polling loop."""
        self.is_running = True
        print("[Scheduler] Started active train monitoring worker.")
        while self.is_running:
            try:
                await self.poll_all_active_tasks()
            except Exception as e:
                print(f"[Scheduler Loop Error] {e}")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)

    async def poll_all_active_tasks(self):
        """Checks availability for all active monitoring tasks."""
        active_tasks = await storage.get_active_tasks()
        for task in active_tasks:
            try:
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

        # Increment attempts count
        attempts = task.get("attempts_count", 0) + 1
        now_str = datetime.datetime.now().strftime("%H:%M:%S")

        # Query availability
        avail = await self.service.check_availability(train_no, date, coach_class, source, dest)
        await storage.update_task(task_id, {
            "attempts_count": attempts,
            "last_checked": now_str,
            "latest_status": avail["status"]
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
            status_text = (
                f"{mode_desc} at `{now_str}`\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"• *Train:* `{train_no}` - {task.get('train_name', 'EXP')} | *Class:* `{coach_class}`\n"
                f"• *Route:* {source} ➔ {dest} ({date})\n"
                f"{quota_line}"
                f"• *Current Status:* `{avail['status']}`\n"
                f"• *Target:* Confirmed / Current Available (CURR_AVBL)\n"
                f"• *Chart Prep Window:* ~4 hours before train departure\n"
                f"• *Total Checks:* `{attempts}` (Next check in {POLL_INTERVAL_SECONDS}s)\n\n"
                f"🛡️ _Sniper is holding fire. It will NEVER book Waiting List._\n"
                f"When unutilized berths hit the system at chart preparation or upon cancellation, the sniper will strike instantly!"
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
            except TelegramError:
                # If editing fails (e.g. message too old or text identical), send a fresh one
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
            await self.bot_app.bot.send_message(
                chat_id=chat_id,
                text="💼 *Executing instant payment via IRCTC e-Wallet balance...*",
                parse_mode="Markdown"
            )
            payment_res = await self.service.request_ewallet_payment(chat_id=chat_id, amount=amount)
            verif_str = "IRCTC eWallet Auto-Debit (Zero Latency)"

        elif pay_mode == "UPI / Instant Pay":
            upi_id = task.get("upi_id") or "Registered UPI App"
            async def upi_prompt_callback(chat_id, amount, timeout_sec):
                prompt_text = (
                    f"📱 *UPI PAYMENT COLLECT NOTIFICATION DISPATCHED*\n\n"
                    f"• *Destination UPI ID:* `{upi_id}`\n"
                    f"• *Amount:* `₹{amount + 17.70:.2f}` (incl. IRCTC fee)\n"
                    f"• *Apps:* Google Pay / PhonePe / Paytm / BHIM\n"
                    f"• *Time Limit:* `{timeout_sec}` seconds\n\n"
                    f"📲 *A payment collect push request has been dispatched to `{upi_id}`!*\n\n"
                    "👉 Open your UPI app and tap 'Approve', then click the confirmation button below:"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ I Have Approved in App", callback_data=f"approve_upi_{chat_id}")]
                ])
                await self.bot_app.bot.send_message(chat_id=chat_id, text=prompt_text, reply_markup=keyboard, parse_mode="Markdown")

            payment_res = await self.service.request_upi_payment_and_wait(
                chat_id=chat_id,
                amount=amount,
                prompt_callback=upi_prompt_callback
            )
            verif_str = f"UPI Collect Approved ({upi_id})"

        else:
            # Credit / Debit Card Flow
            async def otp_prompt_callback(chat_id, card_mask, amount, timeout_sec):
                prompt_text = (
                    f"🔐 *BANK 3D-SECURE OTP REQUIRED*\n\n"
                    f"• *Card:* `{card_mask}`\n"
                    f"• *Amount:* `₹{amount + 17.70:.2f}` (incl. IRCTC fee)\n"
                    f"• *Time Limit:* `{timeout_sec}` seconds\n\n"
                    f"📲 *Please enter the OTP sent to your registered mobile phone directly in this chat:* 👇"
                )
                await self.bot_app.bot.send_message(chat_id=chat_id, text=prompt_text, parse_mode="Markdown")

            card_data = await storage.get_decrypted_card(task.get("telegram_id"))
            payment_res = await self.service.request_card_payment_and_wait_for_otp(
                chat_id=chat_id,
                amount=amount,
                prompt_callback=otp_prompt_callback,
                card_info=card_data
            )
            verif_str = f"Bank 3D-Secure OTP `{payment_res.get('otp')}`"

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
