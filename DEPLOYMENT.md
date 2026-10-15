# 🌐 Server Deployment Guide - IRCTC Telegram AI Agent

This project is cloud-ready and can be deployed 24/7 on any cloud platform (**Koyeb**, **Render**, **Railway**, **Fly.io**) or any **Linux VPS** (Ubuntu/Debian, EC2, DigitalOcean).

---

## Option 1: Deploy to Koyeb / Render / Railway (Recommended, Same as `Post`)

Because `Dockerfile`, `Procfile`, and the background HTTP health probe (`PORT 8000`) are already included, you can deploy in minutes:

### 1. Push code to GitHub
Double-click `push_to_git.bat` in this folder to ensure your latest commits are on GitHub.

### 2. Connect to Cloud Platform
1. Log into **[Koyeb.com](https://app.koyeb.com)** or **[Render.com](https://dashboard.render.com)**.
2. Click **Create Service** / **New Web Service**.
3. Select **GitHub** and choose your repository: `visweswararao3005/irctc-booking-agent`.
4. The platform will automatically detect `Dockerfile` or `Procfile`.
5. Under **Environment Variables**, add:
   * `TELEGRAM_BOT_TOKEN`: `8646643318:AAHVFjcl4o0fc_PlSLD3HgWn5tcNSWBZgrE`
   * `CARD_NUMBER`: `4111222233334444`
   * `CARD_EXPIRY`: `12/28`
   * `CARD_CVV`: `123`
   * `CARD_HOLDER`: `BALAJI P`
   * `POLL_INTERVAL_SECONDS`: `60`
   * `REDIS_URL`: *(Recommended for permanent data persistence)* `rediss://default:xxxx@xxxx.upstash.io:6379`

### 3. Permanent Data Persistence across Redeployments (100% Free Forever)
Because Render web service containers have ephemeral filesystems, redeployments wipe temporary disk files (`data/*.json`). To preserve your linked credentials, passenger master lists, and active tasks permanently:
1. Go to **[Upstash.com](https://console.upstash.com)** (Sign in with Google/GitHub, no credit card required).
2. Click **Create Database** -> Choose **Redis** -> Pick region `ap-south-1 (Mumbai)` or `ap-southeast-1 (Singapore)`.
3. Under **Connect to your database**, copy the **`rediss://`** connection URL.
4. In Render.com -> Go to your bot service -> **Environment Variables** -> Add `REDIS_URL` = `<your rediss:// URL>`.
5. That's it! Every profile, password, and task is automatically encrypted with AES-256 and persisted in cloud Redis. Container restarts and git pushes will NEVER wipe your data again.

6. Click **Deploy**.
7. The cloud health probe on port 8000 will report healthy (`{"status": "healthy"}`) and keep your Telegram bot running 24/7!

---

## Option 2: Deploy to Linux VPS (Ubuntu / Debian / AWS EC2)

### 1. Clone & Setup
```bash
git clone https://github.com/visweswararao3005/irctc-booking-agent.git
cd irctc-booking-agent

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # Add your TELEGRAM_BOT_TOKEN and card details
```

### 2. Configure Systemd Service (Auto-Start on Reboot)
Create service file:
```bash
sudo nano /etc/systemd/system/irctc-bot.service
```

Paste:
```ini
[Unit]
Description=IRCTC Telegram Booking Agent
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/irctc-booking-agent
ExecStart=/home/ubuntu/irctc-booking-agent/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/irctc-booking-agent/.env

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable irctc-bot
sudo systemctl start irctc-bot
sudo systemctl status irctc-bot
```

---

## Option 3: Deploy using Docker

```bash
docker build -t irctc-bot .
docker run -d --name irctc-bot --restart always --env-file .env -p 8000:8000 irctc-bot
```
