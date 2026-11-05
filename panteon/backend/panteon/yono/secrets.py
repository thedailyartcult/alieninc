"""Encryption helpers for YONO-stored API keys (strix config included).

Key precedence:
1. YONO_SECRET_KEY environment variable (both the panteon service and
   CLI scripts must set it identically), else
2. a generated Fernet key file at <backend>/.yono_secret_key (0600),
   created on first use.
"""
import os
from pathlib import Path

from cryptography.fernet import Fernet

_KEY_FILE = Path(__file__).resolve().parent.parent.parent / ".yono_secret_key"

_fernet = None


def _key_bytes() -> bytes:
    env = os.environ.get("YONO_SECRET_KEY", "")
    if env:
        return env.encode("utf-8")
    if not _KEY_FILE.exists():
        _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        _KEY_FILE.write_bytes(Fernet.generate_key())
        try:
            os.chmod(_KEY_FILE, 0o600)
        except OSError:
            pass
    return _KEY_FILE.read_bytes()


def _get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_key_bytes())
    return _fernet


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
