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

        if avail["is_available"]:
            # SEAT AVAILABLE! Initiate Booking Workflow
            status_text = (
                f"🎉 *SEATS ARE NOW AVAILABLE!*\n\n"
                f"{tag} at `{now_str}`\n"
                f"• *Train:* {train_no} ({coach_class})\n"
                f"• *Status:* {avail['status']}\n\n"
                f"⚡ *Proceeding to automated booking & Credit Card checkout...*"
            )
            await self._send_or_edit_status(chat_id, task_id, status_text, keyboard=None)
            await self._execute_booking_flow(task, avail)
            return {"status": "BOOKED", "details": avail}
        else:
            # Still in Waiting List -> Send update to user
            status_text = (
                f"{tag} at `{now_str}`\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"• *Train:* `{train_no}` | *Class:* `{coach_class}`\n"
                f"• *Route:* {source} ➔ {dest} ({date})\n"
                f"• *Current Status:* `{avail['status']}`\n"
                f"• *Total Attempts:* `{attempts}`\n"
                f"• *Next Auto-Try:* In {POLL_INTERVAL_SECONDS} seconds\n\n"
                f"💡 _You can click 'Try Now' anytime to force an instant re-check._"
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

        new_msg = await self.bot_app.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
        self.status_message_ids[task_id] = new_msg.message_id

    async def _execute_booking_flow(self, task: Dict[str, Any], avail: Dict[str, Any]):
        """Executes payment, waits for Bank OTP via Telegram, and sends ticket PDF."""
        task_id = task["task_id"]
        chat_id = task["telegram_chat_id"]
        amount = avail.get("fare", 240.0)

        # Callback function for OTP prompt
        async def otp_prompt_callback(chat_id, card_mask, amount, timeout_sec):
            prompt_text = (
                f"🔐 *BANK 3D-SECURE OTP REQUIRED*\n\n"
                f"• *Card:* `{card_mask}`\n"
                f"• *Amount:* `₹{amount + 17.70:.2f}` (incl. IRCTC fee)\n"
                f"• *Time Limit:* `{timeout_sec}` seconds\n\n"
                f"📲 *Please enter the OTP sent to your registered mobile phone directly in this chat:* 👇"
            )
            await self.bot_app.bot.send_message(chat_id=chat_id, text=prompt_text, parse_mode="Markdown")

        # Get this specific user's decrypted card
        card_data = await storage.get_decrypted_card(task.get("telegram_id"))

        # Request payment & wait for user OTP
        payment_res = await self.service.request_card_payment_and_wait_for_otp(
            chat_id=chat_id,
            amount=amount,
            prompt_callback=otp_prompt_callback,
            card_info=card_data
        )


        if not payment_res.get("success"):
            await self.bot_app.bot.send_message(
                chat_id=chat_id,
                text=f"❌ *Booking Failed:* {payment_res.get('error')}",
                parse_mode="Markdown"
            )
            # Re-queue task or keep monitoring
            return

        # Payment succeeded! Generate PNR and PDF ticket
        pnr = str(random.randint(4000000000, 4999999999))
        booking_data = {
            "pnr": pnr,
            "train_number": task["train_number"],
            "train_name": task.get("train_name", "SUPERFAST EXP"),
            "source": task["source_stn"],
            "dest": task["dest_stn"],
            "journey_date": task["journey_date"],
            "coach_class": task["coach_class"],
            "fare": amount,
            "passengers": task.get("passengers", []),
            "payment_method": f"Credit Card ({payment_res.get('card_mask')})"
        }

        pdf_path = generate_ticket_pdf(booking_data)

        # Notify user with full confirmation
        p_info = task.get("passengers", [{}])[0]
        success_msg = (
            f"🎉 *CONGRATULATIONS! TICKET BOOKED CONFIRMED!*\n\n"
            f"• *PNR Number:* `{pnr}`\n"
            f"• *Train:* {task['train_number']} ({task['coach_class']})\n"
            f"• *Route:* {task['source_stn']} ➔ {task['dest_stn']}\n"
            f"• *Journey Date:* {task['journey_date']}\n"
            f"• *Passenger:* {p_info.get('name', 'Passenger')} ({p_info.get('age', 25)} yrs, {p_info.get('gender', 'M')})\n"
            f"• *Berth Allocated:* S4, 34 (Lower Berth)\n"
            f"• *Payment Verified:* Bank OTP `{payment_res.get('otp')}`\n\n"
            f"📄 *Your official e-Ticket (PDF) is attached below:* 👇"
        )
        await self.bot_app.bot.send_message(chat_id=chat_id, text=success_msg, parse_mode="Markdown")

        # Send PDF file
        with open(pdf_path, "rb") as doc:
            await self.bot_app.bot.send_document(
                chat_id=chat_id,
                document=doc,
                filename=f"IRCTC_Ticket_{pnr}.pdf",
                caption=f"Electronic Reservation Slip (PNR: {pnr})"
            )

        # Auto-cleanup: remove task from JSON file so no unnecessary data remains
        await storage.delete_task(task_id)
        self.status_message_ids.pop(task_id, None)
        print(f"[Scheduler] Successfully booked and purged Task {task_id}.")
