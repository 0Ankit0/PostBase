from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from typing import Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretStoreBackend(Protocol):
    def encrypt(self, plaintext: str) -> str:
        ...

    def decrypt(self, ciphertext: str) -> str:
        ...


@dataclass
class DbEncryptedSecretStore:
    encryption_key: str

    def _derive_key(self) -> bytes:
        return hashlib.sha256(self.encryption_key.encode("utf-8")).digest()

    def encrypt(self, plaintext: str) -> str:
        key = self._derive_key()
        nonce = os.urandom(12)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        raw = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
        nonce, encrypted = raw[:12], raw[12:]
        plaintext = AESGCM(self._derive_key()).decrypt(nonce, encrypted, None)
        return plaintext.decode("utf-8")
