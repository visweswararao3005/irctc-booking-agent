import asyncio
import sys
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from config import TELEGRAM_BOT_TOKEN
import bot
from scheduler import BackgroundBookingWorker

class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status": "healthy", "service": "irctc-booking-agent"}')

    def log_message(self, format, *args):
        pass  # Silence routine health check logs

def start_health_check_server():
    """Starts a background HTTP server on PORT (default 8000) for Cloud health probes (Koyeb, Render, Railway, etc.)."""
    port_str = os.getenv("PORT", "8000")
    try:
        port = int(port_str)
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print(f"🌐 Cloud HTTP health probe server listening on port {port}")
    except Exception as e:
        print(f"[WARN] Could not start health check server on port {port_str}: {e}")

async def run_bot():
    start_health_check_server()

    token = (os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN or "").strip()

    if not token:
        print("=" * 60)
        print("⚠️ [RENDER / CLOUD DEPLOYMENT NOTICE]")
        print("TELEGRAM_BOT_TOKEN is not set in Environment Variables!")
        print("Please go to your Render Dashboard -> Environment tab and add:")
        print("  Key  : TELEGRAM_BOT_TOKEN")
        print("  Value: 8646643318:AAHVFjcl4o0fc_PlSLD3HgWn5tcNSWBZgrE")
        print("=" * 60)
        print("🌐 Cloud HTTP health probe server is running so Render will NOT fail.")
        while not token:
            await asyncio.sleep(5)
            token = (os.getenv("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN or "").strip()

    print("🔧 Initializing Telegram Bot Application...")
    app = Application.builder().token(token).build()


    # Initialize and attach the background scheduler worker
    scheduler = BackgroundBookingWorker(app, bot.irctc_svc)
    bot.global_scheduler = scheduler

    # 1. Booking Conversation Handler
    booking_conv = ConversationHandler(
        entry_points=[
            CommandHandler("start", bot.start_booking),
            CommandHandler("book", bot.start_booking),
            MessageHandler(filters.Regex(r"^(?i)(hi|hello|start|book)$"), bot.start_booking)
        ],
        states={
            bot.STATE_ROUTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_route)],
            bot.STATE_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_date)],
            bot.STATE_TRAIN_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_train_select)],
            bot.STATE_CLASS_SELECT: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_class_select)],
            bot.STATE_PASSENGER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_passenger_name)],
            bot.STATE_PASSENGER_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_passenger_age)],
            bot.STATE_PASSENGER_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_passenger_gender)],
            bot.STATE_PASSENGER_BERTH: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_passenger_berth)],
            bot.STATE_IRCTC_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_inline_irctc_user)],
            bot.STATE_IRCTC_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_inline_irctc_pass)],
            bot.STATE_CARD_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_inline_card_num)],
            bot.STATE_CARD_EXP: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_inline_card_exp)],
            bot.STATE_CARD_CVV: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_inline_card_cvv)],
            bot.STATE_CARD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_inline_card_name)],
            bot.STATE_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_confirm)],
        },
        fallbacks=[CommandHandler("cancel", bot.cancel_booking)]
    )

    # 2. Account Setup/Change Conversation Handler
    account_conv = ConversationHandler(
        entry_points=[
            CommandHandler("change_account", bot.start_change_account),
            CommandHandler("set_account", bot.start_change_account),
        ],
        states={
            bot.STATE_SET_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_set_user)],
            bot.STATE_SET_PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_set_pass)],
        },
        fallbacks=[CommandHandler("cancel", bot.cancel_booking)]
    )

    # 3. Card Setup/Change Conversation Handler
    card_conv = ConversationHandler(
        entry_points=[
            CommandHandler("change_card", bot.start_change_card),
            CommandHandler("set_card", bot.start_change_card),
        ],
        states={
            bot.STATE_SET_CARD_NUM: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_set_card_num)],
            bot.STATE_SET_CARD_EXP: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_set_card_exp)],
            bot.STATE_SET_CARD_CVV: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_set_card_cvv)],
            bot.STATE_SET_CARD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_set_card_name)],
        },
        fallbacks=[CommandHandler("cancel", bot.cancel_booking)]
    )

    # Register handlers
    app.add_handler(booking_conv)
    app.add_handler(account_conv)
    app.add_handler(card_conv)
    app.add_handler(CommandHandler("account", bot.cmd_account))
    app.add_handler(CommandHandler("reset_account", bot.cmd_reset_account))
    app.add_handler(CommandHandler("card", bot.cmd_card))
    app.add_handler(CommandHandler("payment", bot.cmd_card))
    app.add_handler(CommandHandler("reset_card", bot.cmd_reset_card))
    app.add_handler(CallbackQueryHandler(bot.handle_callback_query))

    # Fallback message handler (used for OTP capture & general messages)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_potential_otp))


    # Start background polling worker in asyncio task
    asyncio.create_task(scheduler.start())

    print("🚀 Telegram IRCTC Booking Agent is now running and waiting for messages!")
    print("👉 Multi-user support active.")
    print("👉 Waiting List polling & Try Now buttons enabled.")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    # Keep alive
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        print("\n👋 Bot shut down cleanly.")
