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
SESSIONS_FILE = DATA_DIR / "sessions.json"
BOOKINGS_FILE = DATA_DIR / "bookings.json"

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

# ----------------- Per-Chat Credit Card Management -----------------

async def save_user_card(
    telegram_id: int, card_number: str, card_expiry: str, card_cvv: str, card_holder: str
) -> None:
    """Save encrypted credit/debit card details for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}

        clean_number = card_number.replace(" ", "").replace("-", "").strip()
        users[user_key]["card_number"] = encrypt_text(clean_number)
        users[user_key]["card_expiry"] = encrypt_text(card_expiry.strip())
        users[user_key]["card_cvv"] = encrypt_text(card_cvv.strip())
        users[user_key]["card_holder"] = encrypt_text(card_holder.strip())
        _write_json_sync(USERS_FILE, users)

async def get_decrypted_card(telegram_id: int) -> Optional[Dict[str, str]]:
    """Return decrypted card details dict for a specific Telegram chat."""
    user = await get_user(telegram_id)
    if not user or "card_number" not in user:
        return None
    return {
        "card_number": decrypt_text(user.get("card_number", "")),
        "card_expiry": decrypt_text(user.get("card_expiry", "")),
        "card_cvv": decrypt_text(user.get("card_cvv", "")),
        "card_holder": decrypt_text(user.get("card_holder", "")),
    }

async def reset_user_card(telegram_id: int) -> bool:
    """Delete and wipe stored card credentials for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key in users:
            for k in ["card_number", "card_expiry", "card_cvv", "card_holder"]:
                users[user_key].pop(k, None)
            _write_json_sync(USERS_FILE, users)
            return True
        return False


# ----------------- User UPI ID Management -----------------

async def save_user_upi(telegram_id: int, upi_id: str) -> None:
    """Save encrypted UPI ID for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}
        users[user_key]["upi_id"] = encrypt_text(upi_id.strip())
        _write_json_sync(USERS_FILE, users)

async def get_decrypted_upi(telegram_id: int) -> Optional[str]:
    """Return decrypted UPI ID for a specific Telegram chat."""
    user = await get_user(telegram_id)
    if not user or "upi_id" not in user:
        return None
    return decrypt_text(user.get("upi_id", ""))

async def reset_user_upi(telegram_id: int) -> bool:
    """Delete stored UPI ID for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key in users and "upi_id" in users[user_key]:
            del users[user_key]["upi_id"]
            _write_json_sync(USERS_FILE, users)
            return True
        return False

# ----------------- IRCTC eWallet Management -----------------

async def save_user_ewallet(telegram_id: int, ewallet_pin: str) -> None:
    """Save encrypted IRCTC eWallet Transaction PIN for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}
        users[user_key]["ewallet_pin"] = encrypt_text(ewallet_pin.strip())
        _write_json_sync(USERS_FILE, users)

async def get_decrypted_ewallet(telegram_id: int) -> Optional[str]:
    """Retrieve decrypted IRCTC eWallet Transaction PIN for a specific Telegram chat."""
    user = await get_user(telegram_id)
    if not user or "ewallet_pin" not in user:
        return None
    dec = decrypt_text(user.get("ewallet_pin", ""))
    return dec if dec else None

async def reset_user_ewallet(telegram_id: int) -> bool:
    """Delete stored IRCTC eWallet credentials and recorded balance for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        changed = False
        if user_key in users:
            if "ewallet_pin" in users[user_key]:
                del users[user_key]["ewallet_pin"]
                changed = True
            if "ewallet_balance" in users[user_key]:
                del users[user_key]["ewallet_balance"]
                changed = True
            if changed:
                _write_json_sync(USERS_FILE, users)
                return True
        return False

async def save_user_ewallet_balance(telegram_id: int, balance: float) -> None:
    """Save verified IRCTC eWallet balance for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}
        users[user_key]["ewallet_balance"] = round(float(balance), 2)
        _write_json_sync(USERS_FILE, users)

async def get_user_ewallet_balance(telegram_id: int) -> float:
    """Retrieve stored IRCTC eWallet balance for a specific Telegram chat."""
    user = await get_user(telegram_id)
    if not user:
        return 0.0
    return float(user.get("ewallet_balance", 0.0))

# ----------------- Passenger Profile Management -----------------

async def get_passenger_profiles(telegram_id: int) -> List[Dict[str, Any]]:
    """Retrieve list of all saved passenger profiles for a specific Telegram chat."""
    user = await get_user(telegram_id)
    if not user:
        return []
    if "passenger_profiles" in user and isinstance(user["passenger_profiles"], list):
        return [p for p in user["passenger_profiles"] if isinstance(p, dict) and p.get("name")]
    if "passenger_profile" in user and isinstance(user["passenger_profile"], dict) and user["passenger_profile"].get("name"):
        return [user["passenger_profile"]]
    return []

async def add_passenger_profile(
    telegram_id: int, name: str, age: int, gender: str, berth: str, set_as_primary: bool = False
) -> List[Dict[str, Any]]:
    """Adds a new passenger to the user's master list without overwriting existing ones."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}

        existing_profiles = []
        if "passenger_profiles" in users[user_key] and isinstance(users[user_key]["passenger_profiles"], list):
            existing_profiles = [p for p in users[user_key]["passenger_profiles"] if isinstance(p, dict)]
        elif "passenger_profile" in users[user_key] and isinstance(users[user_key]["passenger_profile"], dict):
            existing_profiles = [users[user_key]["passenger_profile"]]

        clean_name = name.strip()
        matched_idx = -1
        for idx, p in enumerate(existing_profiles):
            if p.get("name", "").lower() == clean_name.lower():
                p["name"] = clean_name
                p["age"] = int(age)
                p["gender"] = gender.strip()
                p["berth"] = berth.strip()
                matched_idx = idx
                break

        if matched_idx == -1:
            new_prof = {
                "id": f"p_{len(existing_profiles)+1}",
                "name": clean_name,
                "age": int(age),
                "gender": gender.strip(),
                "berth": berth.strip()
            }
            if set_as_primary:
                existing_profiles.insert(0, new_prof)
                for i, p in enumerate(existing_profiles):
                    p["id"] = f"p_{i+1}"
            else:
                existing_profiles.append(new_prof)
        else:
            if set_as_primary and matched_idx > 0:
                p = existing_profiles.pop(matched_idx)
                existing_profiles.insert(0, p)
                for i, p_item in enumerate(existing_profiles):
                    p_item["id"] = f"p_{i+1}"

        users[user_key]["passenger_profiles"] = existing_profiles
        if set_as_primary and existing_profiles:
            users[user_key]["passenger_profile"] = existing_profiles[0]
        elif "passenger_profile" not in users[user_key] and existing_profiles:
            users[user_key]["passenger_profile"] = existing_profiles[0]

        _write_json_sync(USERS_FILE, users)
        return existing_profiles

async def save_passenger_profile(
    telegram_id: int, name: str, age: int, gender: str, berth: str
) -> None:
    """Save persistent passenger profile for a specific Telegram chat (adds or updates as primary)."""
    await add_passenger_profile(telegram_id, name, age, gender, berth, set_as_primary=True)

async def delete_passenger_profile(telegram_id: int, p_name_or_idx: Any) -> bool:
    """Deletes a specific passenger by index (0-based) or name."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            return False
        profiles = users[user_key].get("passenger_profiles", [])
        if not profiles and "passenger_profile" in users[user_key]:
            profiles = [users[user_key]["passenger_profile"]]

        orig_len = len(profiles)
        if isinstance(p_name_or_idx, int) and 0 <= p_name_or_idx < len(profiles):
            profiles.pop(p_name_or_idx)
        else:
            search_str = str(p_name_or_idx).strip().lower()
            profiles = [p for p in profiles if p.get("name", "").lower() != search_str and str(p.get("id")) != search_str]

        if len(profiles) < orig_len:
            users[user_key]["passenger_profiles"] = profiles
            if profiles:
                users[user_key]["passenger_profile"] = profiles[0]
            else:
                users[user_key].pop("passenger_profile", None)
            _write_json_sync(USERS_FILE, users)
            return True
        return False

async def get_passenger_profile(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve saved primary passenger profile for a specific Telegram chat."""
    profiles = await get_passenger_profiles(telegram_id)
    return profiles[0] if profiles else None

async def reset_passenger_profile(telegram_id: int) -> bool:
    """Delete all saved passenger profiles for a specific Telegram chat."""
    async with _lock:
        users = _read_json_sync(USERS_FILE)
        user_key = str(telegram_id)
        changed = False
        if user_key in users:
            if "passenger_profile" in users[user_key]:
                del users[user_key]["passenger_profile"]
                changed = True
            if "passenger_profiles" in users[user_key]:
                del users[user_key]["passenger_profiles"]
                changed = True
            if changed:
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

async def save_task(task: Dict[str, Any]) -> None:
    """Save or update an entire task dictionary."""
    task_id = task.get("task_id")
    if not task_id:
        return
    async with _lock:
        tasks = _read_json_sync(TASKS_FILE)
        tasks[task_id] = task
        _write_json_sync(TASKS_FILE, tasks)

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

# ----------------- User Session Persistence & Crash Recovery -----------------

async def save_user_session(telegram_id: int, session_data: Dict[str, Any]) -> None:
    """Save active booking session data so restarts/redeploys never drop the user."""
    async with _lock:
        sessions = _read_json_sync(SESSIONS_FILE)
        # Store clean serializable copy
        clean_copy = {k: v for k, v in session_data.items() if isinstance(v, (str, int, float, list, dict, bool))}
        sessions[str(telegram_id)] = clean_copy
        _write_json_sync(SESSIONS_FILE, sessions)

async def get_user_session(telegram_id: int) -> Dict[str, Any]:
    """Retrieve saved booking session for user to seamlessly recover state."""
    async with _lock:
        sessions = _read_json_sync(SESSIONS_FILE)
        return sessions.get(str(telegram_id), {})

async def clear_user_session(telegram_id: int) -> None:
    """Clear session once booking is confirmed or cancelled."""
    async with _lock:
        sessions = _read_json_sync(SESSIONS_FILE)
        if str(telegram_id) in sessions:
            del sessions[str(telegram_id)]
            _write_json_sync(SESSIONS_FILE, sessions)

# ----------------- Confirmed Booking History -----------------

async def save_user_booking(telegram_id: int, booking_data: Dict[str, Any]) -> None:
    """Save completed booking for a specific user."""
    async with _lock:
        bookings = _read_json_sync(BOOKINGS_FILE)
        user_key = str(telegram_id)
        if user_key not in bookings:
            bookings[user_key] = []
        bookings[user_key].append(booking_data)
        _write_json_sync(BOOKINGS_FILE, bookings)

async def get_user_bookings(telegram_id: int) -> List[Dict[str, Any]]:
    """Retrieve list of completed bookings for user."""
    async with _lock:
        bookings = _read_json_sync(BOOKINGS_FILE)
        return bookings.get(str(telegram_id), [])

