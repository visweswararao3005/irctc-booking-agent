"""Storage manager with dual Cloud Redis / Upstash REST and thread-safe local JSON persistence."""
import json
import os
import uuid
import asyncio
import tempfile
from pathlib import Path
from typing import Dict, Any, List, Optional
from config import DATA_DIR, REDIS_URL, UPSTASH_REDIS_REST_URL, UPSTASH_REDIS_REST_TOKEN
from security import encrypt_text, decrypt_text

USERS_FILE = DATA_DIR / "users.json"
TASKS_FILE = DATA_DIR / "active_tasks.json"
SESSIONS_FILE = DATA_DIR / "sessions.json"
BOOKINGS_FILE = DATA_DIR / "bookings.json"

_lock = asyncio.Lock()
_redis_client = None

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

# ----------------- Cloud Key-Value Storage Adapters -----------------

async def _get_redis_client():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if not REDIS_URL:
        return None
    try:
        import redis.asyncio as aioredis
        _redis_client = aioredis.from_url(
            REDIS_URL,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )
        await _redis_client.ping()
        print("[Storage] Connected to Cloud Redis successfully.")
        return _redis_client
    except Exception as e:
        print(f"[Storage Warning] Could not connect to Redis: {e}. Falling back to local storage.")
        _redis_client = None
        return None

async def _upstash_rest_get(key: str) -> Optional[str]:
    if not (UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN):
        return None
    import urllib.request
    try:
        url = f"{UPSTASH_REDIS_REST_URL.rstrip('/')}/get/{key}"
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}"})
        loop = asyncio.get_running_loop()
        def _fetch():
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data.get("result")
        return await loop.run_in_executor(None, _fetch)
    except Exception as e:
        print(f"[Upstash REST GET Error] {e}")
        return None

async def _upstash_rest_set(key: str, value: str) -> bool:
    if not (UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN):
        return False
    import urllib.request
    try:
        url = f"{UPSTASH_REDIS_REST_URL.rstrip('/')}/set/{key}"
        data_bytes = value.encode("utf-8")
        req = urllib.request.Request(url, data=data_bytes, headers={
            "Authorization": f"Bearer {UPSTASH_REDIS_REST_TOKEN}",
            "Content-Type": "application/json"
        }, method="POST")
        loop = asyncio.get_running_loop()
        def _post():
            with urllib.request.urlopen(req, timeout=5) as resp:
                res = json.loads(resp.read().decode())
                return res.get("result") == "OK"
        return await loop.run_in_executor(None, _post)
    except Exception as e:
        print(f"[Upstash REST SET Error] {e}")
        return False

async def _read_store(key_name: str, file_path: Path) -> Dict[str, Any]:
    """Read data dictionary from Cloud Redis or Upstash REST, falling back to local JSON."""
    redis_key = f"irctc:{key_name}"

    # 1. Try Redis connection
    r = await _get_redis_client()
    if r is not None:
        try:
            val = await r.get(redis_key)
            if val:
                return json.loads(val)
        except Exception as e:
            print(f"[Storage] Redis read error for {redis_key}: {e}")

    # 2. Try Upstash REST API
    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        try:
            val = await _upstash_rest_get(redis_key)
            if val:
                return json.loads(val)
        except Exception as e:
            print(f"[Storage] Upstash REST read error for {redis_key}: {e}")

    # 3. Fallback to local JSON file
    local_data = _read_json_sync(file_path)

    # Auto-seed Cloud Store from local JSON if cloud is connected but empty
    if local_data and (r is not None or (UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN)):
        await _write_store(key_name, file_path, local_data)

    return local_data

async def _write_store(key_name: str, file_path: Path, data: Dict[str, Any]) -> None:
    """Write data dictionary to local file (for fast backup) and sync to Cloud Redis."""
    # 1. Always keep local file updated as backup/cache
    _write_json_sync(file_path, data)

    redis_key = f"irctc:{key_name}"
    json_str = json.dumps(data, ensure_ascii=False)

    # 2. Sync to Redis
    r = await _get_redis_client()
    if r is not None:
        try:
            await r.set(redis_key, json_str)
            return
        except Exception as e:
            print(f"[Storage] Redis write error for {redis_key}: {e}")

    # 3. Sync to Upstash REST
    if UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN:
        try:
            await _upstash_rest_set(redis_key, json_str)
        except Exception as e:
            print(f"[Storage] Upstash REST write error for {redis_key}: {e}")

# ----------------- User Management (Per-Chat Credentials) -----------------

async def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve user profile by Telegram chat ID."""
    async with _lock:
        users = await _read_store("users", USERS_FILE)
        return users.get(str(telegram_id))

async def save_user_credentials(telegram_id: int, irctc_user: str, irctc_pass: str) -> None:
    """Save encrypted IRCTC credentials for a specific Telegram chat."""
    async with _lock:
        users = await _read_store("users", USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}

        users[user_key]["encrypted_irctc_user"] = encrypt_text(irctc_user)
        users[user_key]["encrypted_irctc_pass"] = encrypt_text(irctc_pass)
        await _write_store("users", USERS_FILE, users)

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
        users = await _read_store("users", USERS_FILE)
        user_key = str(telegram_id)
        if user_key in users:
            users[user_key].pop("encrypted_irctc_user", None)
            users[user_key].pop("encrypted_irctc_pass", None)
            await _write_store("users", USERS_FILE, users)
            return True
        return False

# ----------------- IRCTC eWallet Management -----------------

async def save_user_ewallet(telegram_id: int, ewallet_pin: str) -> None:
    """Save encrypted IRCTC eWallet Transaction PIN for a specific Telegram chat."""
    async with _lock:
        users = await _read_store("users", USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}
        users[user_key]["ewallet_pin"] = encrypt_text(ewallet_pin.strip())
        await _write_store("users", USERS_FILE, users)

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
        users = await _read_store("users", USERS_FILE)
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
                await _write_store("users", USERS_FILE, users)
                return True
        return False

async def save_user_ewallet_balance(telegram_id: int, balance: float) -> None:
    """Save verified IRCTC eWallet balance for a specific Telegram chat."""
    async with _lock:
        users = await _read_store("users", USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            users[user_key] = {"telegram_id": telegram_id}
        users[user_key]["ewallet_balance"] = round(float(balance), 2)
        await _write_store("users", USERS_FILE, users)

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
        users = await _read_store("users", USERS_FILE)
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

        await _write_store("users", USERS_FILE, users)
        return existing_profiles

async def save_passenger_profile(
    telegram_id: int, name: str, age: int, gender: str, berth: str
) -> None:
    """Save persistent passenger profile for a specific Telegram chat (adds or updates as primary)."""
    await add_passenger_profile(telegram_id, name, age, gender, berth, set_as_primary=True)

async def delete_passenger_profile(telegram_id: int, p_name_or_idx: Any) -> bool:
    """Deletes a specific passenger by index (0-based) or name."""
    async with _lock:
        users = await _read_store("users", USERS_FILE)
        user_key = str(telegram_id)
        if user_key not in users:
            return False
        profiles = users[user_key].get("passenger_profiles", [])
        if not profiles and "passenger_profile" in users[user_key]:
            profiles = [users[user_key]["passenger_profile"]]

        orig_len = len(profiles)
        idx_to_pop = None
        if isinstance(p_name_or_idx, int) and 0 <= p_name_or_idx < len(profiles):
            idx_to_pop = p_name_or_idx
        elif isinstance(p_name_or_idx, str) and p_name_or_idx.strip().isdigit():
            val = int(p_name_or_idx.strip())
            if 0 <= val < len(profiles):
                idx_to_pop = val

        if idx_to_pop is not None:
            profiles.pop(idx_to_pop)
        else:
            search_str = str(p_name_or_idx).strip().lower()
            profiles = [p for p in profiles if p.get("name", "").lower() != search_str and str(p.get("id")).lower() != search_str]

        if len(profiles) < orig_len:
            for i, p in enumerate(profiles):
                p["id"] = f"p_{i+1}"
            users[user_key]["passenger_profiles"] = profiles
            if profiles:
                users[user_key]["passenger_profile"] = profiles[0]
            else:
                users[user_key].pop("passenger_profile", None)
            await _write_store("users", USERS_FILE, users)
            return True
        return False

async def get_passenger_profile(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve saved primary passenger profile for a specific Telegram chat."""
    profiles = await get_passenger_profiles(telegram_id)
    return profiles[0] if profiles else None

async def reset_passenger_profile(telegram_id: int) -> bool:
    """Delete all saved passenger profiles for a specific Telegram chat."""
    async with _lock:
        users = await _read_store("users", USERS_FILE)
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
                await _write_store("users", USERS_FILE, users)
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
        tasks = await _read_store("tasks", TASKS_FILE)
        tasks[task_id] = task_data
        await _write_store("tasks", TASKS_FILE, tasks)
    return task_id

async def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a specific task by task_id."""
    async with _lock:
        tasks = await _read_store("tasks", TASKS_FILE)
        return tasks.get(task_id)

async def get_active_tasks() -> List[Dict[str, Any]]:
    """Get all tasks currently in MONITORING status."""
    async with _lock:
        tasks = await _read_store("tasks", TASKS_FILE)
        return [t for t in tasks.values() if t.get("status") == "MONITORING"]

async def get_user_active_tasks(telegram_id: int) -> List[Dict[str, Any]]:
    """Get all active tasks for a specific Telegram user."""
    async with _lock:
        tasks = await _read_store("tasks", TASKS_FILE)
        return [
            t for t in tasks.values()
            if t.get("telegram_id") == telegram_id and t.get("status") == "MONITORING"
        ]

async def update_task(task_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Update specific fields of an active task."""
    async with _lock:
        tasks = await _read_store("tasks", TASKS_FILE)
        if task_id in tasks:
            tasks[task_id].update(updates)
            await _write_store("tasks", TASKS_FILE, tasks)
            return tasks[task_id]
        return None

async def save_task(task: Dict[str, Any]) -> None:
    """Save or update an entire task dictionary."""
    task_id = task.get("task_id")
    if not task_id:
        return
    async with _lock:
        tasks = await _read_store("tasks", TASKS_FILE)
        tasks[task_id] = task
        await _write_store("tasks", TASKS_FILE, tasks)

async def delete_task(task_id: str) -> bool:
    """
    Purge task from storage once completed, booked, expired, or cancelled.
    Keeps files and memory lean.
    """
    async with _lock:
        tasks = await _read_store("tasks", TASKS_FILE)
        if task_id in tasks:
            del tasks[task_id]
            await _write_store("tasks", TASKS_FILE, tasks)
            return True
        return False

# ----------------- User Session Persistence & Crash Recovery -----------------

async def save_user_session(telegram_id: int, session_data: Dict[str, Any]) -> None:
    """Save active booking session data so restarts/redeploys never drop the user."""
    async with _lock:
        sessions = await _read_store("sessions", SESSIONS_FILE)
        # Store clean serializable copy
        clean_copy = {k: v for k, v in session_data.items() if isinstance(v, (str, int, float, list, dict, bool))}
        sessions[str(telegram_id)] = clean_copy
        await _write_store("sessions", SESSIONS_FILE, sessions)

async def get_user_session(telegram_id: int) -> Dict[str, Any]:
    """Retrieve saved booking session for user to seamlessly recover state."""
    async with _lock:
        sessions = await _read_store("sessions", SESSIONS_FILE)
        return sessions.get(str(telegram_id), {})

async def clear_user_session(telegram_id: int) -> None:
    """Clear session once booking is confirmed or cancelled."""
    async with _lock:
        sessions = await _read_store("sessions", SESSIONS_FILE)
        if str(telegram_id) in sessions:
            del sessions[str(telegram_id)]
            await _write_store("sessions", SESSIONS_FILE, sessions)

# ----------------- Confirmed Booking History -----------------

async def save_user_booking(telegram_id: int, booking_data: Dict[str, Any]) -> None:
    """Save completed booking for a specific user."""
    async with _lock:
        bookings = await _read_store("bookings", BOOKINGS_FILE)
        user_key = str(telegram_id)
        if user_key not in bookings:
            bookings[user_key] = []
        bookings[user_key].append(booking_data)
        await _write_store("bookings", BOOKINGS_FILE, bookings)

async def get_user_bookings(telegram_id: int) -> List[Dict[str, Any]]:
    """Retrieve list of completed bookings for user."""
    async with _lock:
        bookings = await _read_store("bookings", BOOKINGS_FILE)
        return bookings.get(str(telegram_id), [])
