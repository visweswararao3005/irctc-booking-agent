"""Unified Application Runner: Starts the Telegram Bot and Background Polling Scheduler."""
import asyncio
import sys
import os

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)
from config import TELEGRAM_BOT_TOKEN
import bot
from scheduler import BackgroundBookingWorker

async def run_bot():
    if not TELEGRAM_BOT_TOKEN:
        print("=" * 60)
        print("⚠️ [CONFIGURATION REQUIRED]")
        print("No TELEGRAM_BOT_TOKEN was found in .env!")
        print("Please set your bot token from @BotFather in C:\\Users\\Balaji P\\Desktop\\project\\Train\\.env")
        print("Example:")
        print("TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz")
        print("=" * 60)
        return

    print("🔧 Initializing Telegram Bot Application...")
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

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

    # Register handlers
    app.add_handler(booking_conv)
    app.add_handler(account_conv)
    app.add_handler(CommandHandler("account", bot.cmd_account))
    app.add_handler(CommandHandler("reset_account", bot.cmd_reset_account))
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
