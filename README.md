# 🚆 IRCTC AI Booking & Monitoring Telegram Agent

An intelligent, multi-user Telegram Bot that automates train search, live coach availability checking with prices, continuous Waiting List (WL) monitoring with live attempt feedback, on-demand "Try Now" re-checks, Credit Card 3D-Secure OTP payments, and electronic PDF ticket delivery.

---

## 🌟 Key Features

1. **Multi-User Isolation**:
   - Each Telegram chat manages its own independent IRCTC account (`/account`, `/change_account`, `/reset_account`).
   - All credentials stored in `data/users.json` are encrypted at rest using AES-256 (Fernet).
2. **Zero-Database JSON Storage**:
   - No SQL server (PostgreSQL/MySQL) setup required.
   - Built with thread-safe async locks and atomic writes.
   - **Auto-Purging**: Tasks are deleted from `data/active_tasks.json` once a ticket is booked or cancelled.
3. **Smart Search & Live Pricing**:
   - Displays all matching trains sorted chronologically by earliest departure time.
   - Shows live availability **and ticket fares** for every class (`SL`, `3A`, `2A`, `1A`, `2S`, `CC`).
4. **Continuous Waiting List (WL) Monitoring**:
   - If tickets are on Waiting List, the bot automatically monitors availability every 60 seconds.
   - **Continuous Progress Updates**: Sends status and timestamp for each attempt (`🔄 [Try #3 | 18:02]`).
   - **Interactive `[🔄 Try Now]` Button**: Click anytime to force an instant re-check on demand.
5. **Credit Card Payment & Telegram OTP Relay**:
   - Card details configured locally in `.env`.
   - When the bank 3D-Secure payment page requests an OTP, the bot sends a prompt directly to your Telegram chat, captures your response, submits the OTP, and completes booking.
6. **Electronic Reservation Slip (PDF)**:
   - Automatically generates a PDF e-ticket with PNR, coach, berth, and passenger details and delivers it to Telegram.

---

## 🚀 Quick Setup & Run

### 1. Configure `.env`
In `C:\Users\Balaji P\Desktop\project\Train`, create or edit `.env` (using `.env.example` as a template):

```ini
# Get this token from @BotFather on Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrSTUvwxyz

# Master Encryption Key (Leave blank to auto-generate)
ENCRYPTION_KEY=

# Credit Card Details for Checkout
CARD_NUMBER=4111222233334444
CARD_EXPIRY=12/28
CARD_CVV=123
CARD_HOLDER=BALAJI P

# Polling Interval in seconds (Default: 60)
POLL_INTERVAL_SECONDS=60
OTP_TIMEOUT_SECONDS=120
```

### 2. Run Verification Suite
```bash
python test_system.py
```

### 3. Start the Bot
```bash
python main.py
```

---

## 💬 Bot Commands & Interactions

| Command / Trigger | Action |
|---|---|
| `hi` / `hello` / `/start` / `/book` | Launches the conversational train booking assistant. |
| `/account` | Displays your currently linked IRCTC username (with password masked). |
| `/change_account` | Guides you to link or change your IRCTC username and password. |
| `/reset_account` | Clears and deletes your saved IRCTC credentials from storage. |
| `/card` / `/payment` | Displays your linked Credit/Debit card (masked: `**** **** **** 4444`). |
| `/change_card` | Guides you to link or update your payment card (Number, Expiry, CVV, Name). |
| `/reset_card` | Deletes and removes your saved payment card details from storage. |
| `/cancel` | Cancels the ongoing conversation or active form. |
| `[🔄 Try Now]` *(Inline Button)* | Forces an immediate availability check during monitoring. |
| `[❌ Cancel Monitoring]` *(Inline Button)* | Halts background monitoring and purges the task. |


---

## 📁 Project Architecture

```
Train/
├── .env                  # Secrets, bot token, and credit card info
├── .env.example          # Sample environment template
├── config.py             # Configuration and directory setup
├── security.py           # AES-256 encryption & masking
├── storage.py            # Thread-safe JSON storage & task lifecycle
├── irctc_service.py      # Train lookup, pricing, and Card+OTP engine
├── ticket_generator.py   # fpdf2 electronic ticket PDF generator
├── scheduler.py          # Background poller, live feedback, and Try Now handler
├── bot.py                # Telegram FSM ConversationHandler
├── test_system.py        # Automated verification test suite
└── main.py               # Unified application runner
```
