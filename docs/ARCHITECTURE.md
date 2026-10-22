# 🚂 IRCTC Autonomous AI Booking Agent — System Architecture

An enterprise-grade, asynchronous Telegram AI bot engineered for automated seat sniping, quota management, and instant reservation execution across Indian Railways (IRCTC / CRIS).

---

## 🏗️ 1. Directory & Package Structure

```
Train/
├── docs/                             # System Documentation & Runbooks
│   ├── ARCHITECTURE.md               # End-to-end Architectural Specification
│   └── DEPLOYMENT.md                 # Cloud & VPS Deployment Manual
│
├── scripts/                          # Administration & Process Management
│   ├── start.ps1 / start_bot.bat     # Silent Background Process Launcher
│   ├── stop.ps1 / stop_bot.bat       # Process Stopper & Clean Shutdown
│   ├── info.ps1 / info_bot.bat       # Live PID & Resource Monitoring
│   └── push.ps1 / push_to_git.bat    # Automated Git Synchronization
│
├── src/                              # Core Application Logic
│   ├── __init__.py                   # Package Root
│   ├── bot.py                        # Telegram UI, State Machine & Menus
│   ├── config.py                     # Environment Configuration & Path Resolver
│   ├── irctc_live_engine.py          # Playwright Headless Scraping & Automation
│   ├── irctc_service.py              # PRS Business Logic, Tatkal & Charting Rules
│   ├── live_payment_service.py       # UPI Intent, QR Codes & Card Gateway
│   ├── scheduler.py                  # Background Watchdog & Task Scheduler
│   ├── security.py                   # AES-256 (Fernet) Encryption Layer
│   ├── storage.py                    # Multi-Tenant Persistence (Redis / JSON)
│   ├── ticket_generator.py           # Electronic Reservation Slip (ERS) PDF Engine
│   └── timezone_utils.py             # Indian Standard Time (IST / Asia/Kolkata)
│
├── tests/                            # Automated Verification Suites
│   ├── __init__.py
│   └── test_system.py                # 23 E2E Integration Tests (100% Pass)
│
├── .env                              # Active Environment Secrets (Git Ignored)
├── .env.example                      # Environment Configuration Template
├── .gitignore                        # Git Ignore Rules
├── Dockerfile                        # Container Specification
├── main.py                           # Application Server & Health Probe Entrypoint
├── Procfile                          # Cloud Process Manifest (Koyeb / Render)
├── README.md                         # Quickstart Guide
├── requirements.txt                  # Python Production Dependencies
├── secret.key                        # Master Fernet Encryption Key
├── start_bot.bat                     # Windows Root Launcher Shortcut
├── stop_bot.bat                      # Windows Root Stopper Shortcut
├── push_to_git.bat                   # Windows Root Git Sync Shortcut
└── test_system.py                    # Root Test Runner Shim
```

---

## ⚡ 2. Core Subsystems

```
                                      +-------------------------+
                                      |   Telegram User Chat    |
                                      +------------+------------+
                                                   |
                                                   v
                                      +-------------------------+
                                      |    src/bot.py (UI)      |
                                      +------------+------------+
                                                   |
                   +-------------------------------+-------------------------------+
                   |                               |                               |
                   v                               v                               v
        +--------------------+          +--------------------+          +--------------------+
        |  src/storage.py    |          | src/irctc_service  |          |  src/scheduler.py  |
        |  (AES-256 / Redis) |          | (PRS Rules Engine) |          | (Watchdog Worker)  |
        +--------------------+          +--------------------+          +----------+---------+
                                                                                   |
                                                                        Confirmed Berth Detected
                                                                                   |
                                                                                   v
                                                                        +--------------------+
                                                                        | irctc_live_engine  |
                                                                        | (Headless Browser) |
                                                                        +--------------------+
                                                                                   |
                                                                        Authentic CRIS PNR
                                                                                   |
                                                                                   v
                                                                        +--------------------+
                                                                        |  Delivery to User  |
                                                                        +--------------------+
```

### Subsystem Detail:
1. **Telegram Presentation Layer (`src/bot.py`)**:
   - Manages stateful conversation workflows (`python-telegram-bot`).
   - Dynamic date-picker inline keyboards, passenger manifest parsing, and balance verification actions.
2. **Indian Railways PRS Engine (`src/irctc_service.py`)**:
   - Accurately computes Indian Railways Chart 1 preparation times:
     - Trains departing $\ge 14:00$ IST $\to$ Prepared strictly 4 hours prior to origin station departure (`origin_dep - 4h`).
     - Morning trains departing $< 14:00$ IST $\to$ Prepared at 20:00 IST the previous evening.
   - Dynamic polling rate ramp-up engine ($900\text{s} \to 60\text{s} \to 30\text{s} \to 10\text{s}$).
3. **Autonomous Watchdog (`src/scheduler.py`)**:
   - Asynchronous worker polling live quotas across 3 pipeline stages: Live Check, Tatkal Strike (10/11 AM), and Chart 1 Watchdog.
   - Updates Telegram status messages in-place to avoid spam.
4. **IRCTC Live Scraper & Booking Engine (`src/irctc_live_engine.py`)**:
   - Playwright headless Chromium automation with anti-bot evasion and human-cadence input simulation.
   - Scrapes live e-Wallet balances directly from `https://www.irctc.co.in/nget/deposit-ewallet`.
   - Intercepts authentic 10-digit CRIS PNRs from the official booking confirmation screen.
   - Enforces a strict Zero-Fake Guarantee: NEVER fabricates random PNRs or synthetic PDF slips.
5. **Persistence & Security Layer (`src/storage.py` & `src/security.py`)**:
   - Multi-tenant cloud storage backed by Upstash Redis.
   - Encrypts user credentials, card records, and e-Wallet PINs with AES-256 (Fernet).
