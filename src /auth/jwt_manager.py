"""
JWT Token Manager — Garena OAuth Flow
Uses the correct 2-step authentication:
  1. POST https://100067.connect.garena.com/oauth/guest/token/grant → open_id + access_token
  2. POST https://loginbp.ggpolarbear.com/MajorLogin (encrypted protobuf) → JWT token + server URL + key/iv
Then uses token for API calls to clientbp.ggpolarbear.com / client.XX.freefiremobile.com

Updated: Uses the complete MajorLoginRes schema with blacklist detection,
correct field names (lock_region, server_url, ak, aiv), and proper error handling.
"""

import json
import base64
import time
import random
import asyncio
import aiosqlite
from datetime import datetime
from typing import Optional, Tuple, Dict

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from ..core.config_loader import get_config
from ..core.logger import setup_logger

logger = setup_logger("jwt")


# ─────────────────────────────────────────────
# Garena OAuth constants (from TCP bot)
# ─────────────────────────────────────────────
# Try v2 first, fall back to v1
OAUTH_URL_V2 = "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant"
GARENA_OAUTH_URL = "https://100067.connect.garena.com/oauth/guest/token/grant"
GARENA_MAJOR_LOGIN_URLS = [
    "https://loginbp.ggpolarbear.com/MajorLogin",
    "https://loginbp.common.ggbluefox.com/MajorLogin",
    "https://loginbp.ggblueshark.com/MajorLogin",
]

GARENA_CLIENT_ID = "100067"
GARENA_CLIENT_SECRET = "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3"

# AES key/IV for MajorLogin protobuf encryption (from TCP bot xC4.py)
MAJOR_LOGIN_KEY = b'Yg&tc%DEuh6%Zc^8'
MAJOR_LOGIN_IV  = b'6oyZDr22E3ychjM%'

# HTTP headers for Garena API calls (from TCP bot's Hr dict)
# Using Hr headers (same as TCP bot) for both OAuth and MajorLogin
GARENA_HEADERS = {
    'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
    'Connection': "Keep-Alive",
    'Accept-Encoding': "gzip",
    'Content-Type': "application/x-www-form-urlencoded",
    'Expect': "100-continue",
    'X-Unity-Version': "2018.4.11f1",
    'X-GA': "v1 1",
    'ReleaseVersion': "OB54",
}


def _random_ua() -> str:
    """Generate random GarenaMSDK User-Agent (from TCP bot xC4.py Ua())."""
    versions = [
        '4.0.18P6', '4.0.19P7', '4.0.20P1', '4.1.0P3', '4.1.5P2',
        '4.2.1P8', '4.2.3P1', '5.0.1B2', '5.0.2P4', '5.1.0P1',
        '5.2.0B1', '5.2.5P3', '5.3.0B1', '5.3.2P2', '5.4.0P1',
        '5.4.3B2', '5.5.0P1', '5.5.2P3',
    ]
    models = [
        'SM-A125F', 'SM-A225F', 'SM-A325M', 'SM-A515F', 'SM-A725F',
        'SM-M215F', 'SM-M325FV', 'Redmi 9A', 'Redmi 9C', 'POCO M3',
        'POCO M4 Pro', 'RMX2185', 'RMX3085', 'moto g(9) play',
        'CPH2239', 'V2027', 'OnePlus Nord', 'ASUS_Z01QD',
    ]
    android_versions = ['9', '10', '11', '12', '13', '14']
    langs    = ['en-US', 'es-MX', 'pt-BR', 'id-ID', 'ru-RU', 'hi-IN']
    countries = ['USA', 'MEX', 'BRA', 'IDN', 'RUS', 'IND']
    return (
        f"GarenaMSDK/{random.choice(versions)}"
        f"({random.choice(models)};Android {random.choice(android_versions)};"
        f"{random.choice(langs)};{random.choice(countries)};)"
    )


def _encrypt_major_login(plaintext: bytes) -> bytes:
    """Encrypt MajorLogin protobuf payload with fixed AES key (from TCP bot)."""
    cipher = AES.new(MAJOR_LOGIN_KEY, AES.MODE_CBC, MAJOR_LOGIN_IV)
    return cipher.encrypt(pad(plaintext, AES.block_size))


def _build_major_login_proto(open_id: str, access_token: str) -> bytes:
    """Build and return the serialised MajorLogin protobuf bytes."""
    from ..proto.compiled import MajoRLoGinrEq_pb2
    ml = MajoRLoGinrEq_pb2.MajorLogin()
    ml.event_time           = str(datetime.now())[:-7]
    ml.game_name            = "free fire"
    ml.platform_id          = 2
    ml.client_version       = "1.126.2"
    ml.client_version_code  = "2024010012"
    ml.system_software      = "Android OS 11 / API-30 (RQ3A.210805.001)"
    ml.system_hardware      = "Handheld"
    ml.device_type          = "Handheld"
    ml.telecom_operator     = "Verizon"
    ml.network_operator_a   = "Verizon"
    ml.network_type         = "WIFI"
    ml.network_type_a       = "WIFI"
    ml.screen_width         = 1080
    ml.screen_height        = 2400
    ml.screen_dpi           = "440"
    ml.processor_details    = "ARMv8"
    ml.cpu_type             = 2
    ml.cpu_architecture     = "64"
    ml.memory               = 6144
    ml.gpu_renderer         = "Adreno (TM) 650"
    ml.gpu_version          = "OpenGL ES 3.2 V@1.50"
    ml.graphics_api         = "OpenGLES3"
    ml.unique_device_id     = "Google|34a7dcdf-a7d5-4cb6-8d7e-3b0e448a0c57"
    ml.client_ip            = ""
    ml.language             = "en"
    ml.open_id              = open_id
    ml.open_id_type         = "4"
    ml.login_open_id_type   = 4
    ml.access_token         = access_token
    ml.login_by             = 3
    ml.platform_sdk_id      = 2
    ml.origin_platform_type  = "4"
    ml.primary_platform_type = "4"
    ml.memory_available.version      = 55
    ml.memory_available.hidden_value = 81
    ml.external_storage_total           = 128512
    ml.external_storage_available       = random.randint(38000, 52000)
    ml.internal_storage_total           = 110731
    ml.internal_storage_available       = random.randint(18000, 32000)
    ml.game_disk_storage_total          = 26628
    ml.game_disk_storage_available      = random.randint(18000, 25000)
    ml.external_sdcard_total_storage    = 119234
    ml.external_sdcard_avail_storage    = random.randint(25000, 60000)
    ml.library_path                     = "/data/app/~~random/base.apk"
    ml.library_token                    = "hash|base.apk"
    ml.client_using_version             = "7428b253defc164018c604a1ebbfebdf"
    ml.supported_astc_bitset            = 16383
    ml.analytics_detail                 = b"FwQVTgUPX1UaUllDDwcWCRBpWAUOUgsvA1snWlBaO1kFYg=="
    ml.loading_time                     = random.randint(9000, 18000)
    ml.release_channel                  = "android"
    ml.channel_type                     = 3
    ml.reg_avatar                       = 1
    ml.if_push                          = 1
    ml.is_vpn                           = 0
    ml.android_engine_init_flag         = 110009
    return ml.SerializeToString()


# ─────────────────────────────────────────────────────────────────────────────
# Region → API base mapping (used when MajorLogin returns empty URL)
# ─────────────────────────────────────────────────────────────────────────────
REGION_API_BASE = {
    "ME":  "https://clientbp.ggpolarbear.com",
    "IND": "https://clientbp.ggpolarbear.com",
    "BD":  "https://clientbp.ggpolarbear.com",
    "PK":  "https://clientbp.ggpolarbear.com",
    "SG":  "https://clientbp.ggpolarbear.com",
    "ID":  "https://clientbp.ggpolarbear.com",
    "TH":  "https://clientbp.ggpolarbear.com",
    "VN":  "https://clientbp.ggpolarbear.com",
    "TW":  "https://clientbp.ggpolarbear.com",
    "BR":  "https://clientbp.ggpolarbear.com",
    "US":  "https://clientbp.ggpolarbear.com",
    "EU":  "https://clientbp.ggpolarbear.com",
    "CIS": "https://clientbp.ggpolarbear.com",
}


# ─────────────────────────────────────────────────────────────────────────────
class JWTCredentials:
    """Cached JWT credentials for one guest account."""
    def __init__(self, uid, token, region, server_url, created_at, expires_at,
                 session_key=None, session_iv=None):
        self.uid         = uid
        self.token       = token
        self.region      = region
        self.server_url  = server_url
        self.created_at  = created_at
        self.expires_at  = expires_at
        self.session_key = session_key   # per-session AES key from MajorLoginRes.key
        self.session_iv  = session_iv    # per-session AES IV from MajorLoginRes.iv


class JWTManager:
    """
    Manages JWT tokens using the correct Garena OAuth + MajorLogin flow.

    Flow per guest account:
      1. GET open_id + access_token from Garena OAuth endpoint.
      2. Build encrypted MajorLogin protobuf, POST to loginbp.ggpolarbear.com.
      3. Parse MajorLoginRes → extract JWT token + server URL + session key/iv.
      4. Detect blacklisting/protection responses and log appropriately.
      5. Cache result in SQLite for TTL hours.
    """

    def __init__(self, http_client, aes_engine):
        self.http   = http_client
        self.aes    = aes_engine            # kept for API compatibility; not used in auth
        self.config = get_config()
        self.db_path = self.config.settings.jwt.cache_db
        self._cache: Dict[str, JWTCredentials] = {}
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    # ── lifecycle ──────────────────────────────────────────────────────────
    async def initialize(self):
        """Initialise SQLite JWT cache."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS jwt_cache (
                uid        TEXT PRIMARY KEY,
                token      TEXT NOT NULL,
                region     TEXT NOT NULL,
                server_url TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)
        await self._db.commit()
        await self._load_cache()
        logger.info("JWT cache initialized")

    async def close(self):
        if self._db:
            await self._db.close()

    # ── public API ─────────────────────────────────────────────────────────
    async def get_token(
        self, uid: str, password: str, region: str,
        open_id: str = "", access_token: str = ""
    ) -> Optional[Tuple[str, str, str]]:
        """
        Return (token, region, server_url) for the account.
        Uses cache; regenerates when expired/missing.
        Passes open_id/access_token to skip OAuth when available.
        """
        now = time.time()
        margin = self.config.settings.jwt.refresh_before_expiry_minutes * 60

        if uid in self._cache:
            creds = self._cache[uid]
            if now < (creds.expires_at - margin):
                logger.debug(f"JWT cache hit for {uid}")
                return creds.token, creds.region, creds.server_url
            logger.debug(f"JWT cache expired for {uid}")

        return await self._generate_token(uid, password, region, open_id, access_token)

    async def get_session_keys(self, uid: str) -> Optional[Tuple[bytes, bytes]]:
        """Return per-session (key, iv) from MajorLoginRes if available."""
        if uid in self._cache:
            creds = self._cache[uid]
            if creds.session_key and creds.session_iv:
                return creds.session_key, creds.session_iv
        return None

    async def invalidate(self, uid: str):
        """Remove cached token for account."""
        self._cache.pop(uid, None)
        async with self._lock:
            await self._db.execute("DELETE FROM jwt_cache WHERE uid = ?", (uid,))
            await self._db.commit()

    async def decode(self, token: str) -> Optional[dict]:
        """Base64-decode JWT payload (no signature verification)."""
        try:
            parts = token.split(".")
            if len(parts) != 3:
                return None
            payload = parts[1]
            padding = 4 - len(payload) % 4
            if padding != 4:
                payload += "=" * padding
            return json.loads(base64.urlsafe_b64decode(payload))
        except Exception as e:
            logger.error(f"JWT decode error: {e}")
            return None

    # ── internal ───────────────────────────────────────────────────────────
    async def _generate_token(
        self, uid: str, password: str, region: str,
        open_id: str = "", access_token: str = ""
    ) -> Optional[Tuple[str, str, str]]:
        """Full 2-step Garena auth -> JWT token. Skips OAuth if tokens provided."""
        try:
            logger.info(f"🔑 Authenticating guest {uid}...")

            # Step 1: Garena OAuth guest token grant
            # Skip if we already have open_id + access_token (from generator)
            if not (open_id and access_token):
                oauth_data = {
                    "uid":             uid,
                    "password":        password,
                    "response_type":   "token",
                    "client_type":     "2",
                    "client_secret":   GARENA_CLIENT_SECRET,
                    "client_id":       GARENA_CLIENT_ID,
                }

                max_retries = 3
                resp1 = None
                for attempt in range(max_retries):
                    resp1 = await self.http.post(
                        GARENA_OAUTH_URL,
                        headers=GARENA_HEADERS,
                        data=oauth_data,
                    )
                    if resp1.status_code == 200:
                        break
                    elif resp1.status_code == 429:
                        wait_time = 10 * (attempt + 1)
                        logger.warning(f"OAuth rate-limited (429) for {uid}, waiting {wait_time}s... (attempt {attempt+1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(f"Garena OAuth failed: HTTP {resp1.status_code}")
                        return None

                if resp1 is None or resp1.status_code != 200:
                    logger.error(f"Garena OAuth failed after {max_retries} retries")
                    return None

                oauth_json = resp1.json()
                open_id      = oauth_json.get("open_id")
                access_token = oauth_json.get("access_token")
                if not open_id or not access_token:
                    logger.error(f"Missing open_id/access_token in OAuth response")
                    return None
                logger.debug(f"OAuth OK for {uid}: open_id={open_id[:8]}...")
            else:
                logger.info(f"✅ Using cached OAuth tokens for {uid} (skipping OAuth)")

            # Step 2: MajorLogin
            proto_bytes = _build_major_login_proto(open_id, access_token)
            encrypted   = _encrypt_major_login(proto_bytes)

            login_resp = None
            for login_url in GARENA_MAJOR_LOGIN_URLS:
                login_resp = await self.http.post(
                    login_url,
                    headers=GARENA_HEADERS,
                    content=encrypted,
                )
                if login_resp.status_code == 200:
                    break
                logger.warning(f"MajorLogin {login_url} -> HTTP {login_resp.status_code}")
                await asyncio.sleep(1)

            if login_resp is None or login_resp.status_code != 200:
                logger.error(f"MajorLogin failed on all URLs")
                return None

            from ..proto.compiled import MajoRLoGinrEs_pb2
            ml_resp = MajoRLoGinrEs_pb2.MajorLoginRes()
            ml_resp.ParseFromString(login_resp.content)

            if ml_resp.HasField("blacklist"):
                bl = ml_resp.blacklist
                logger.error(f"⚠️  Guest {uid} BLACKLISTED | ban_reason={bl.ban_reason}")
                return None

            jwt_token = ml_resp.token
            if not jwt_token:
                logger.error(f"MajorLogin empty token for {uid}")
                return None

            session_key = ml_resp.key if ml_resp.key else None
            session_iv  = ml_resp.iv if ml_resp.iv else None

            lock_region = ml_resp.lock_region or ml_resp.noti_region or region
            server_url  = ml_resp.url or REGION_API_BASE.get(region, "https://clientbp.ggpolarbear.com")

            decoded = await self.decode(jwt_token)
            if decoded and "exp" in decoded:
                expires_at = decoded["exp"]
            else:
                expires_at = time.time() + self.config.settings.jwt.ttl_hours * 3600

            now = time.time()
            creds = JWTCredentials(
                uid=uid, token=jwt_token, region=lock_region,
                server_url=server_url, created_at=now, expires_at=expires_at,
                session_key=session_key, session_iv=session_iv,
            )
            self._cache[uid] = creds
            await self._store_cache(creds)

            logger.info(f"✅ JWT acquired for {uid} | Region: {lock_region} | Server: {server_url}")
            return jwt_token, lock_region, server_url

        except Exception as e:
            logger.error(f"JWT generation error for {uid}: {e}")
            return None

    async def _load_cache(self):
        async with self._lock:
            async with self._db.execute("SELECT * FROM jwt_cache") as cur:
                async for row in cur:
                    self._cache[row[0]] = JWTCredentials(
                        uid=row[0], token=row[1], region=row[2],
                        server_url=row[3], created_at=row[4], expires_at=row[5],
                    )
        logger.debug(f"Loaded {len(self._cache)} cached JWTs")

    async def _store_cache(self, creds: JWTCredentials):
        async with self._lock:
            await self._db.execute(
                """INSERT OR REPLACE INTO jwt_cache
                   (uid, token, region, server_url, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (creds.uid, creds.token, creds.region, creds.server_url,
                 creds.created_at, creds.expires_at),
            )
            await self._db.commit()
