"""
AES Encryption Engine
Handles AES-128-CBC encryption/decryption with key rotation.
"""

import os
from typing import Optional, List, Tuple

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from ..core.config_loader import get_config
from ..core.logger import setup_logger

logger = setup_logger("aes")


class AESEngine:
    """
    AES-128-CBC encryption engine with automatic key rotation.
    Tries multiple keys until one works (for handling game updates).
    """

    def __init__(self):
        self.config = get_config()
        self.keys: List[Tuple[bytes, bytes]] = []
        self._load_keys()

    def _load_keys(self):
        """Load all encryption keys from config."""
        main_key = self.config.settings.encryption.main_key.encode("utf-8")
        main_iv = self.config.settings.encryption.main_iv.encode("utf-8")
        self.keys.append((main_key, main_iv))

        for fk in self.config.settings.encryption.fallback_keys:
            key = fk.get("key", "").encode("utf-8")
            iv = fk.get("iv", "").encode("utf-8")
            if len(key) >= 16 and len(iv) >= 16:
                self.keys.append((key[:16], iv[:16]))

        logger.info(f"Loaded {len(self.keys)} encryption keys")

    def encrypt(self, plaintext: bytes, key_idx: int = 0) -> bytes:
        """
        Encrypt plaintext with AES-128-CBC.

        Args:
            plaintext: Data to encrypt
            key_idx: Which key to use (default: primary)

        Returns:
            IV + ciphertext
        """
        key, iv = self.keys[key_idx]
        cipher = AES.new(key, AES.MODE_CBC, iv)
        padded = pad(plaintext, AES.block_size, style="pkcs7")
        ciphertext = cipher.encrypt(padded)
        return iv + ciphertext

    def decrypt(self, ciphertext: bytes, try_all_keys: bool = True) -> Optional[bytes]:
        """
        Decrypt ciphertext with AES-128-CBC.

        Args:
            ciphertext: IV + encrypted data
            try_all_keys: If True, tries all keys until one works

        Returns:
            Decrypted bytes or None if all keys fail
        """
        if len(ciphertext) < 32:
            logger.error("Ciphertext too short")
            return None

        iv = ciphertext[:16]
        data = ciphertext[16:]

        keys_to_try = self.keys if try_all_keys else [self.keys[0]]

        for idx, (key, _) in enumerate(keys_to_try):
            try:
                cipher = AES.new(key, AES.MODE_CBC, iv)
                decrypted = cipher.decrypt(data)
                return unpad(decrypted, AES.block_size, style="pkcs7")
            except ValueError:
                continue
            except Exception as e:
                logger.debug(f"Key {idx} failed: {e}")
                continue

        logger.error("All decryption keys failed — keys may be outdated")
        return None

    def decrypt_with_key(self, ciphertext: bytes, key_idx: int) -> Optional[bytes]:
        """Decrypt specifically with key at key_idx."""
        if len(ciphertext) < 32:
            return None
        iv = ciphertext[:16]
        data = ciphertext[16:]
        key, _ = self.keys[key_idx]
        try:
            cipher = AES.new(key, AES.MODE_CBC, iv)
            decrypted = cipher.decrypt(data)
            return unpad(decrypted, AES.block_size, style="pkcs7")
        except Exception:
            return None

    def test_keys(self) -> dict:
        """Test all keys with a round-trip."""
        test_data = b"FreeFireTestPayload123"
        results = {}

        for idx, (key, iv) in enumerate(self.keys):
            try:
                encrypted = self.encrypt(test_data, idx)
                decrypted = self.decrypt_with_key(encrypted, idx)
                success = decrypted == test_data
                results[f"key_{idx}"] = "✅ Valid" if success else "❌ Corrupt"
            except Exception as e:
                results[f"key_{idx}"] = f"❌ Error: {e}"

        return results
