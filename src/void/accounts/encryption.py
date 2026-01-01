"""
Key encryption and decryption utilities.

Uses AES-256-GCM for secure key storage.
"""

import os
import base64
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import structlog

from void.config import config

logger = structlog.get_logger()


class KeyEncryption:
    """
    Encrypt and decrypt sensitive data using AES-256-GCM.

    Keys are encrypted with a master key from environment.
    """

    def __init__(self):
        # Get encryption key from config
        key_str = config.encryption.key

        # Ensure key is 32 bytes (256 bits) for AES-256
        if len(key_str) < 32:
            # Pad with zeros
            key_str = key_str.ljust(32, '0')
        elif len(key_str) > 32:
            # Truncate
            key_str = key_str[:32]

        # Convert to bytes
        self.key = key_str.encode('utf-8')

        # Initialize AES-GCM
        self.cipher = AESGCM(self.key)

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt plaintext string.

        Args:
            plaintext: String to encrypt

        Returns:
            Base64-encoded encrypted data (nonce + ciphertext)
        """
        try:
            # Generate random nonce (96 bits for GCM)
            nonce = os.urandom(12)

            # Convert plaintext to bytes
            data = plaintext.encode('utf-8')

            # Encrypt
            ciphertext = self.cipher.encrypt(nonce, data, None)

            # Combine nonce + ciphertext
            combined = nonce + ciphertext

            # Return as base64
            return base64.b64encode(combined).decode('utf-8')

        except Exception as e:
            logger.error("encryption_failed", error=str(e))
            raise

    def decrypt(self, encrypted_b64: str) -> str:
        """
        Decrypt encrypted string.

        Args:
            encrypted_b64: Base64-encoded encrypted data

        Returns:
            Decrypted plaintext string
        """
        try:
            # Decode from base64
            combined = base64.b64decode(encrypted_b64)

            # Split nonce and ciphertext
            nonce = combined[:12]  # 96 bits
            ciphertext = combined[12:]

            # Decrypt
            plaintext_bytes = self.cipher.decrypt(nonce, ciphertext, None)

            # Convert to string
            return plaintext_bytes.decode('utf-8')

        except Exception as e:
            logger.error("decryption_failed", error=str(e))
            raise


__all__ = ["KeyEncryption"]
