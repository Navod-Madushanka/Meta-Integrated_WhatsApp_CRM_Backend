import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

class TokenProtector:
    def __init__(self, key: str):
        if not key:
            raise ValueError("Encryption key cannot be empty.")
        # Fernet requires a 32-byte base64-encoded key
        self.cipher_suite = Fernet(key.encode())

    def encrypt_token(self, token: str) -> str:
        """Encrypts a string and returns a string."""
        if not token:
            return ""
        return self.cipher_suite.encrypt(token.encode()).decode()

    def decrypt_token(self, encrypted_token: str) -> str:
        """Decrypts a string and returns the original string."""
        if not encrypted_token:
            return ""
        return self.cipher_suite.decrypt(encrypted_token.encode()).decode()

# Usage for your production app:
# ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY")
# protector = TokenProtector(ENCRYPTION_KEY)