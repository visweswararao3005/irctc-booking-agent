"""JSON File Storage manager with thread-safe file operations and task auto-cleanup."""
import json
import os
import uuid
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import DATA_DIR
from security import encrypt_text, decrypt_text

USERS_FILE = DATA_DIR / "users.json"
TASKS_FILE = DATA_DIR / "active_tasks.json"

_lock = asyncio.Lock()

def _read_json_sync(file_path: Path) -> Dict[str, Any]:
    if not file_path.exists():
        return {}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

def _write_json_sync(file_path: Path, data: Dict[str, Any]) -> None:
    """Atomic write to JSON file using a temp file."""
    temp_dir = file_path.parent
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=temp_dir, delete=False, encoding="utf-8") as tf:
        json.dump(data, tf, indent=2, ensure_ascii=False)
        temp_name = tf.name
    os.replace(temp_name, file_path)

# ----------------- User Management (Per-Chat Credentials) -----------------

async def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve user profile by Telegram chat ID."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        return users.get(str(telegram_id))

async def save_user_credentials(telegram_id: int, irctc_user: str, irctc_pass: str) -> None:
    """Save encrypted IRCTC credentials for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}
        
        users[user_key]["encrypted_irctc_user"] = encrypt_text(irctc_user)
        users[user_key]["encrypted_irctc_pass"] = encrypt_text(irctc_pass)
        _write_json_sync(USERS_FILE, users)

async def get_decrypted_credentials(telegram_id: int) -> tuple[Optional[str], Optional[str]]:
    """Return decrypted (irctc_user, irctc_pass) for a specific Telegram chat."""
    user = await get_user(telegram_id)
    if not user:
        return None, None
    enc_user = user.get("encrypted_irctc_user", "")
    enc_pass = user.get("encrypted_irctc_pass", "")
    return decrypt_text(enc_user), decrypt_text(enc_pass)

async def reset_user_credentials(telegram_id: int) -> bool:
    """Reset and delete IRCTC credentials for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key in users:
            users[user_key].pop("encrypted_irctc_user", None)
            users[user_key].pop("encrypted_irctc_pass", None)
            _write_json_sync(USERS_FILE, users)
            return True
        return False

# ----------------- Active Tasks & Polling Lifecycle -----------------

async def add_task(task_data: Dict[str, Any]) -> str:
    """Create a new monitoring/booking task."""
    task_id = str(uuid.uuid4())[:8]
    task_data["task_id"] = task_id
    task_data["status"] = task_data.get("status", "MONITORING")
    task_data["attempts_count"] = 0
    task_data["last_checked"] = None
    task_data["created_at"] = str(task_data.get("created_at", ""))

    async with _lock:
        tasks = _read_json_sync(TASKS_FILE)
        tasks[task_id] = task_data
        _write_json_sync(TASKS_FILE, tasks)
    return task_id

async def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a specific task by task_id."""
    async with _lock:
        tasks = _read_json_sync(TASKS_FILE)
        return tasks.get(task_id)

async def get_active_tasks() -> List[Dict[str, Any]]:
    """Get all tasks currently in MONITORING status."""
    async with _lock:
        tasks = _read_json_sync(TASKS_FILE)
        return [t for t in tasks.values() if t.get("status") == "MONITORING"]

async def get_user_active_tasks(telegram_id: int) -> List[Dict[str, Any]]:
    """Get all active tasks for a specific Telegram user."""
    async with _lock:
        tasks = _read_json_sync(TASKS_FILE)
        return [
            t for t in tasks.values()
            if t.get("telegram_id") == telegram_id and t.get("status") == "MONITORING"
        ]

async def update_task(task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update specific fields of an active task."""
    async with _lock:
        tasks = _read_json_sync(TASKS_FILE)
        if task_id in tasks:
            tasks[task_id].update(updates)
            _write_json_sync(TASKS_FILE, tasks)
            return tasks[task_id]
        return None

async def delete_task(task_id: str) -> bool:
    """
    Purge task from JSON storage once completed, booked, expired, or cancelled.
    Keeps files lean and zero-footprint.
    """
    async with _lock:
        tasks = _read_json_sync(TASKS_FILE)
        if task_id in tasks:
            del tasks[task_id]
            _write_json_sync(TASKS_FILE, tasks)
            return True
        return False
