from __future__ import annotations

import re
import math
import base64

from Crypto.Cipher import AES


def encrypt_aes_ecb(plaintext: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_ECB)
    padded = _pkcs7_pad(plaintext, AES.block_size)
    return cipher.encrypt(padded)


def decrypt_aes_ecb(ciphertext: bytes, key: bytes) -> bytes:
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = cipher.decrypt(ciphertext)
    return _pkcs7_unpad(decrypted)


def aes_ecb_padded_size(plaintext_size: int) -> int:
    return math.ceil((plaintext_size + 1) / 16) * 16


def _pkcs7_pad(data: bytes, block_size: int) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _pkcs7_unpad(data: bytes) -> bytes:
    if not data:
        return data
    pad_len = data[-1]
    if pad_len < 1 or pad_len > 16:
        return data
    if data[-pad_len:] != bytes([pad_len] * pad_len):
        return data
    return data[:-pad_len]


def parse_aes_key(aes_key_base64: str) -> bytes:

    decoded = base64.b64decode(aes_key_base64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32 and re.match(rb"^[0-9a-fA-F]{32}$", decoded):
        return bytes.fromhex(decoded.decode("ascii"))
    raise ValueError(f"aes_key must decode to 16 raw bytes or 32-char hex string, got {len(decoded)} bytes")
