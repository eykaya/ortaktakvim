import os
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def get_encryption_key() -> bytes:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise RuntimeError(
            "SESSION_SECRET environment variable is required for secure password encryption. "
            "Please set it in your Replit Secrets."
        )
    salt = b"calendar-aggregator-salt"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(secret.encode()))
    return key


def encrypt_password(password: str) -> str:
    if not password:
        return ""
    fernet = Fernet(get_encryption_key())
    encrypted = fernet.encrypt(password.encode())
    return encrypted.decode()


def decrypt_password(encrypted_password: str) -> str:
    if not encrypted_password:
        return ""
    fernet = Fernet(get_encryption_key())
    decrypted = fernet.decrypt(encrypted_password.encode())
    return decrypted.decode()
