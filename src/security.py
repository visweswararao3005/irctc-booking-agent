"""Security and encryption utilities using Fernet (AES-256)."""
import os
from pathlib import Path
from cryptography.fernet import Fernet
from config import BASE_DIR, ENCRYPTION_KEY
KEY_FILE = BASE_DIR / "secret.key"

def _get_or_create_key() -> bytes:
    """Retrieve existing Fernet key or generate and persist a new one dynamically."""
    if ENCRYPTION_KEY:
        k = ENCRYPTION_KEY.strip().encode()
        if len(k) == 44:
            return k
    if KEY_FILE.exists():
        try:
            k = KEY_FILE.read_text().strip().encode()
            if len(k) == 44:
                return k
        except Exception:
            pass
    # Dynamically generate cryptographically strong Fernet key
    new_key = Fernet.generate_key()
    try:
        KEY_FILE.write_text(new_key.decode())
    except Exception:
        pass
    return new_key

_cipher = Fernet(_get_or_create_key())

def encrypt_text(plain_text: str) -> str:
    """Encrypt a plaintext string and return a base64 encoded token."""
    if not plain_text:
        return ""
    return _cipher.encrypt(plain_text.encode()).decode()

def decrypt_text(cipher_text: str) -> str:
    """Decrypt a base64 token back to original plaintext."""
    if not cipher_text:
        return ""
    try:
        return _cipher.decrypt(cipher_text.encode()).decode()
    except Exception as e:
        print(f"[Security Warning] Decryption failed: {e}. Master ENCRYPTION_KEY may have changed.")
        return ""

def mask_text(text: str, visible_prefix: int = 3) -> str:
    """Mask sensitive string like username or password."""
    if not text:
        return "Not Set"
    if len(text) <= visible_prefix:
        return "*" * len(text)
    return text[:visible_prefix] + "*" * (len(text) - visible_prefix)
