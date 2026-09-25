"""
Like Sender
Sends likes using the Garena clientbp API:
  POST https://clientbp.ggpolarbear.com/LikeProfile
  Body: AES-encrypted protobuf (uid + region), same key/iv as TCP bot
  Authorization: Bearer <JWT from MajorLogin>
"""

import asyncio
import time
import random
import binascii
from typing import Optional, Tuple
from dataclasses import dataclass

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from ..core.config_loader import get_config
from ..core.logger import setup_logger

logger = setup_logger("sender")

# AES key/IV used for API payload encryption (from TCP bot)
API_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
API_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

# Base URL for API calls
LIKE_BASE_URL = "https://clientbp.ggpolarbear.com"

# HTTP headers for clientbp API calls (matching TCP bot's Hr dict)
API_HEADERS_BASE = {
    'User-Agent':      "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
    'Connection':      "Keep-Alive",
    'Accept-Encoding': "gzip",
    'Content-Type':    "application/octet-stream",
    'Expect':          "100-continue",
    'X-Unity-Version': "2018.4.11f1",
    'X-GA':            "v1 1",
    'ReleaseVersion':  "OB54",
}


def _encrypt_api(plain_hex: str) -> bytes:
    """Encrypt hex-encoded payload with fixed API AES key (from TCP bot encrypt_api())."""
    plain_bytes = bytes.fromhex(plain_hex)
    cipher = AES.new(API_KEY, AES.MODE_CBC, API_IV)
    return cipher.encrypt(pad(plain_bytes, AES.block_size))


def _encode_uid_protobuf(uid: int) -> str:
    """Build UID protobuf (dev_generator) and return as hex string."""
    from ..proto.compiled import dev_generator_pb2
    msg = dev_generator_pb2.dev_generator()
    msg.saturn_ = uid
    msg.garena  = 1
    return msg.SerializeToString().hex()


def _encode_varint(n: int) -> bytes:
    """Encode integer as protobuf varint."""
    result = []
    while n > 0:
        b = n & 0x7F
        n >>= 7
        if n > 0:
            b |= 0x80
        result.append(b)
    return bytes(result)


# Region code mapping (varint values used by the API, NOT string names)
REGION_CODES = {
    "ME": 7, "IND": 1, "INDONESIA": 1, "BR": 2, "BRA": 2,
    "SG": 3, "TH": 4, "PH": 5, "VN": 6, "RU": 8, "US": 9,
    "PK": 10, "BD": 11, "ID": 1, "TW": 12,
}


def _build_like_payload(target_uid: int, source_uid: int = 0, region: str = "ME") -> bytes:
    """
    Build encrypted like payload for /LikeProfile endpoint.
    Uses TCP bot format: 08{uid_varint}10{region_code} (confirmed working 2026-07-29).
    Region is encoded as a varint code (7=ME), NOT a string.
    """
    region_code = REGION_CODES.get(region.upper(), 7)  # default to ME
    uid_varint = _encode_varint(int(target_uid))
    raw = bytes([0x08]) + uid_varint + bytes([0x10, region_code])
    cipher = AES.new(API_KEY, AES.MODE_CBC, API_IV)
    return cipher.encrypt(pad(raw, AES.block_size))


@dataclass
class LikeResult:
    success: bool
    message: str
    http_code: int = 0
    retry_after: int = 0


class LikeSender:
    """
    Sends individual like requests with jitter, retry, and proxy support.
    Uses the correct clientbp.ggpolarbear.com API.
    """

    def __init__(self, http, aes, jwt_manager, guest_manager, proxy_rotator=None):
        self.http    = http
        self.aes     = aes
        self.jwt     = jwt_manager
        self.guests  = guest_manager
        self.proxies = proxy_rotator
        self.config  = get_config()

    async def send_like(
        self, guest_uid: str, password: str, target_uid: str, region: str = "ME",
        open_id: str = "", access_token: str = ""
    ) -> LikeResult:
        """
        Send a single like from a guest account.

        Flow:
          1. Get/refresh JWT via Garena OAuth + MajorLogin (skips OAuth if tokens cached)
          2. Apply jitter delay
          3. Build encrypted protobuf payload
          4. POST to /LikeProfile
          5. Parse response
        """
        try:
            # 1. Authenticate guest (use cached OAuth tokens if available to avoid rate-limit)
            jwt_result = await self.jwt.get_token(guest_uid, password, region, open_id, access_token)
            if not jwt_result:
                await self.guests.mark_used(guest_uid, target_uid, success=False, region=region)
                return LikeResult(False, "JWT generation failed", 0)

            token, lock_region, server_url = jwt_result

            # 2. Jitter delay (anti-detection)
            delay_ms  = self.config.settings.streak.delay_between_likes_ms
            jitter    = delay_ms * (self.config.settings.streak.jitter_percent / 100)
            actual_delay = (delay_ms + random.uniform(-jitter, jitter)) / 1000
            if actual_delay > 0:
                await asyncio.sleep(actual_delay)

            # 3. Build payload — like_pb2.like (uid + region) AES encrypted
            payload = _build_like_payload(int(target_uid), int(guest_uid), region)

            # 4. Send request — clientbp API (no Host header override)
            url = f"{LIKE_BASE_URL}/LikeProfile"
            headers = {**API_HEADERS_BASE, "Authorization": f"Bearer {token}"}
            logger.debug(f"LikeProfile request: URL={url} | Host={headers.get('Host','auto')} | payload={len(payload)} bytes")

            response = await self.http.post(url, headers=headers, content=payload)

            # 5. Handle response
            if response.status_code == 200:
                # Log raw response for debugging
                raw_hex = response.content.hex() if response.content else "(empty)"
                logger.info(f"📡 LikeProfile resp: {len(response.content)} bytes | hex: {raw_hex[:80]}")

                # Try to parse with like_count_pb2 (Info -> BasicInfo -> Likes)
                like_count = None
                try:
                    from ..proto.compiled import like_count_pb2
                    info = like_count_pb2.Info()
                    info.ParseFromString(response.content)
                    like_count = info.AccountInfo.Likes
                    logger.info(f"✅ Like sent | UID:{target_uid} total_likes={like_count}")
                except Exception:
                    # Try raw parse — first bytes might indicate success
                    logger.debug(f"Raw response parse failed, treating 200 as success")

                await self.guests.mark_used(guest_uid, target_uid, success=True, region=region)
                return LikeResult(True, f"Success (likes={like_count})", 200)

            elif response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                return LikeResult(False, "Rate limited", 429, retry_after)

            elif response.status_code == 401:
                await self.jwt.invalidate(guest_uid)
                return LikeResult(False, "Unauthorized — token expired", 401)

            elif response.status_code == 503:
                return LikeResult(False, "Server unavailable (503)", 503)

            else:
                return LikeResult(
                    False,
                    f"HTTP {response.status_code}: {response.text[:80]}",
                    response.status_code,
                )

        except Exception as e:
            logger.error(f"Like send error: {e}")
            return LikeResult(False, f"Exception: {str(e)[:80]}", 0)
