"""
Free Fire Guest Account Generator — Fixed for OB54 (July 2026)
Creates new guest accounts via Garena OAuth -> MajorRegister -> MajorLogin flow.
Saves results to both SQLite (bot DB) and data/guests.json.
"""

import hmac
import hashlib
import requests
import string
import random
import json
import codecs
import time
import base64
import concurrent.futures
import threading
import os
import asyncio
import aiosqlite
from datetime import datetime

import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEX_KEY = "32656534343831396539623435393838343531343130363762323831363231383734643064356437616639643866376530306331653534373135623764316533"
HMAC_KEY = bytes.fromhex(HEX_KEY)
CLIENT_SECRET = HMAC_KEY.decode("ascii")

REGION_LANG = {
    "ME": "ar", "IND": "hi", "ID": "id", "VN": "vi",
    "TH": "th", "BD": "bn", "PK": "ur", "TW": "zh",
    "EU": "en", "RU": "ru", "NA": "en", "SAC": "es", "BR": "pt", "SG": "en",
}

REGION_URLS = {
    "IND": "https://client.ind.freefiremobile.com/",
    "ID":  "https://clientbp.ggblueshark.com/",
    "BR":  "https://client.us.freefiremobile.com/",
    "ME":  "https://clientbp.common.ggbluefox.com/",
    "VN":  "https://clientbp.ggblueshark.com/",
    "TH":  "https://clientbp.common.ggbluefox.com/",
    "RU":  "https://clientbp.ggblueshark.com/",
    "BD":  "https://clientbp.ggblueshark.com/",
    "PK":  "https://clientbp.ggblueshark.com/",
    "SG":  "https://clientbp.ggblueshark.com/",
    "NA":  "https://client.us.freefiremobile.com/",
    "SAC": "https://client.us.freefiremobile.com/",
    "EU":  "https://clientbp.ggblueshark.com/",
    "TW":  "https://clientbp.ggblueshark.com/",
}

MAJOR_LOGIN_URLS = {
    "ME":  "https://loginbp.common.ggbluefox.com/MajorLogin",
    "_DEFAULT": "https://loginbp.ggpolarbear.com/MajorLogin",
}
MAJOR_REGISTER_URL = "https://loginbp.ggblueshark.com/MajorRegister"

BASE_HEADERS = {
    "Accept-Encoding": "gzip",
    "Authorization":   "Bearer",
    "Connection":      "Keep-Alive",
    "Content-Type":    "application/x-www-form-urlencoded",
    "Expect":          "100-continue",
    "ReleaseVersion":  "OB54",
    "User-Agent":      "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
    "X-GA":            "v1 1",
    "X-Unity-Version": "2018.4.11f1",
}

_tlocal = threading.local()

def _session():
    if not hasattr(_tlocal, "s"):
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        s = requests.Session()
        r = Retry(total=1, backoff_factor=1.0, status_forcelist=[502, 503, 504])
        a = HTTPAdapter(max_retries=r, pool_connections=50, pool_maxsize=50)
        s.mount("http://", a)
        s.mount("https://", a)
        _tlocal.s = s
    return _tlocal.s

def _enc_vr(n):
    out = []
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            b |= 0x80
        out.append(b)
        if not n:
            break
    return bytes(out)

def _varint_field(fnum, val):
    return _enc_vr((fnum << 3) | 0) + _enc_vr(val)

def _len_field(fnum, val):
    enc = val.encode() if isinstance(val, str) else val
    return _enc_vr((fnum << 3) | 2) + _enc_vr(len(enc)) + enc

def _proto(fields):
    buf = bytearray()
    for f, v in fields.items():
        if isinstance(v, dict):
            nested = _proto(v)
            buf.extend(_len_field(f, nested))
        elif isinstance(v, int):
            buf.extend(_varint_field(f, v))
        else:
            buf.extend(_len_field(f, v))
    return bytes(buf)

_API_KEY = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
_API_IV  = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

def _aes_encrypt(hex_str):
    raw = bytes.fromhex(hex_str)
    c = AES.new(_API_KEY, AES.MODE_CBC, _API_IV)
    return c.encrypt(pad(raw, AES.block_size))

def _rand_name(prefix):
    return prefix + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def _rand_password():
    return "MADDY-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=9)) + "-CORE"

def _encode_open_id(original):
    ks = [0x30,0x30,0x30,0x32,0x30,0x31,0x37,0x30,
          0x30,0x30,0x30,0x30,0x32,0x30,0x31,0x37,
          0x30,0x30,0x30,0x30,0x30,0x32,0x30,0x31,
          0x37,0x30,0x30,0x30,0x30,0x30,0x32,0x30]
    encoded = "".join(chr(ord(c) ^ ks[i % len(ks)]) for i, c in enumerate(original))
    escaped = ''.join(c if 32 <= ord(c) <= 126 else f'\\u{ord(c):04x}' for c in encoded)
    return codecs.decode(escaped, 'unicode_escape').encode('latin1')

def _extract_jwt_from_response(resp_bytes):
    try:
        text = resp_bytes.decode("latin1")
        idx = text.find("eyJhbGci")
        if idx != -1:
            token = text[idx:]
            end = 0
            for ch in token:
                if ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.":
                    end += 1
                else:
                    break
            return token[:end] if end > 20 else None
    except Exception:
        pass
    return None

DEBUG = os.environ.get("GEN_DEBUG", "0") == "1"

def _log(msg):
    if DEBUG:
        print(f"  [GEN] {msg}", flush=True)

def _step1_register(password):
    data = f"password={password}&client_type=2&source=2&app_id=100067"
    sig = hmac.new(HMAC_KEY, data.encode(), hashlib.sha256).hexdigest()
    headers = {
        "User-Agent":      "GarenaMSDK/4.0.19P8(ASUS_Z01QD ;Android 12;en;US;)",
        "Authorization":   "Signature " + sig,
        "Content-Type":    "application/x-www-form-urlencoded",
        "Accept-Encoding": "gzip",
        "Connection":      "Keep-Alive",
    }
    try:
        r = _session().post("https://connect.garena.com/oauth/guest/register",
            headers=headers, data=data, timeout=30)
        if r.status_code != 200:
            _log(f"Step1 FAIL: HTTP {r.status_code} - {r.text[:80]}")
            return None
        uid = r.json().get("uid")
        _log(f"Step1 OK: uid={uid}")
        return uid
    except Exception as e:
        _log(f"Step1 ERROR: {e}")
        return None

def _step2_token_grant(uid, password, max_retries=5):
    headers = {
        "Accept-Encoding": "gzip",
        "Connection":      "Keep-Alive",
        "Content-Type":    "application/x-www-form-urlencoded",
        "User-Agent":      "GarenaMSDK/4.0.19P8(ASUS_Z01QD ;Android 12;en;US;)",
    }
    body = {
        "uid": uid, "password": password,
        "response_type": "token", "client_type": "2",
        "client_secret": CLIENT_SECRET, "client_id": "100067",
    }
    for attempt in range(max_retries):
        try:
            r = _session().post("https://100067.connect.garena.com/oauth/guest/token/grant",
                headers=headers, data=body, timeout=30)
            if r.status_code == 429:
                wait = min(10 * (attempt + 1), 60)
                _log(f"Step2 429, waiting {wait}s... (attempt {attempt+1}/{max_retries})")
                time.sleep(wait)
                continue
            if r.status_code != 200:
                _log(f"Step2 FAIL: HTTP {r.status_code} - {r.text[:80]}")
                return None
            j = r.json()
            oi = j.get("open_id")
            at = j.get("access_token")
            _log(f"Step2 OK: open_id={oi[:12] if oi else None}...")
            return (oi, at) if oi and at else None
        except Exception as e:
            _log(f"Step2 ERROR: {e}")
            return None
    _log(f"Step2 FAIL: rate-limited after {max_retries} retries")
    return None

def _step3_major_register(access_token, open_id, field, name):
    payload = {1: name, 2: access_token, 3: open_id, 5: 102000007, 6: 4, 7: 1, 13: 1,
               14: field, 15: "en", 16: 1, 17: 1}
    enc = _aes_encrypt(_proto(payload).hex())
    try:
        r = _session().post(MAJOR_REGISTER_URL, headers=BASE_HEADERS, data=enc, verify=False, timeout=30)
        _log(f"Step3: HTTP {r.status_code} ({len(r.content)} bytes)")
        return r.content if r.status_code == 200 else None
    except Exception as e:
        _log(f"Step3 ERROR: {e}")
        return None

def _step4_major_login(access_token, open_id, region):
    """MajorLogin using the main project's compiled protobuf builder."""
    try:
        import sys
        proj_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
        if proj_root not in sys.path:
            sys.path.insert(0, proj_root)
        from src.auth.jwt_manager import _build_major_login_proto, _encrypt_major_login
        from src.proto.compiled import MajoRLoGinrEs_pb2
        
        proto_bytes = _build_major_login_proto(open_id, access_token)
        encrypted = _encrypt_major_login(proto_bytes)
        
        # Try region-specific URL first, then default
        urls_to_try = [MAJOR_LOGIN_URLS.get(region, MAJOR_LOGIN_URLS["_DEFAULT"])]
        if region != "_DEFAULT" and MAJOR_LOGIN_URLS.get(region) != MAJOR_LOGIN_URLS["_DEFAULT"]:
            urls_to_try.append(MAJOR_LOGIN_URLS["_DEFAULT"])
        
        for url in urls_to_try:
            r = _session().post(url, headers=BASE_HEADERS, data=encrypted, verify=False, timeout=30)
            _log(f"Step4: {url} -> HTTP {r.status_code} ({len(r.content)} bytes)")
            if r.status_code == 200 and len(r.content) >= 10:
                # Try to parse as protobuf first
                try:
                    ml_resp = MajoRLoGinrEs_pb2.MajorLoginRes()
                    ml_resp.ParseFromString(r.content)
                    if ml_resp.HasField("blacklist"):
                        _log(f"Step4: Blacklisted! ban_reason={ml_resp.blacklist.ban_reason}")
                        return None
                    token = ml_resp.token
                    if token:
                        _log(f"Step4: JWT from protobuf, account_id={ml_resp.account_id}")
                        return token
                except Exception:
                    pass
                # Fallback: raw text search
                jwt = _extract_jwt_from_response(r.content)
                if jwt:
                    return jwt
            time.sleep(1)
        return None
    except Exception as e:
        _log(f"Step4 ERROR: {e}")
        return None

def create_guest_account(name_prefix="BOT", region="ME"):
    try:
        password = _rand_password()
        name = _rand_name(name_prefix)
        region = region.upper()

        uid = _step1_register(password)
        if not uid:
            return None

        result = _step2_token_grant(uid, password)
        if not result:
            return None
        open_id, access_token = result

        field = _encode_open_id(open_id)
        _step3_major_register(access_token, open_id, field, name)

        jwt_token = _step4_major_login(access_token, open_id, region)
        if not jwt_token:
            return None

        try:
            _step5_get_login_data(jwt_token, access_token, open_id, region)
        except Exception:
            pass

        return {"uid": uid, "password": password, "name": name,
                "region": region, "status": "full_login"}
    except Exception as e:
        _log(f"create_guest_account ERROR: {e}")
        return None

def register_only(name_prefix="BOT", region="ME"):
    """Fast mode: register a guest account AND get OAuth tokens.
    Returns None if Step2 (token grant) fails — useless accounts are not saved.
    The like command uses the saved tokens to skip OAuth entirely."""
    try:
        password = _rand_password()
        name = _rand_name(name_prefix)
        region = region.upper()

        uid = _step1_register(password)
        if not uid:
            return None

        # Step2 is REQUIRED — without tokens, the like command can't skip OAuth
        result = _step2_token_grant(uid, password, max_retries=5)
        if not result:
            _log(f"register_only: Step2 failed for {uid}, skipping (no tokens = useless account)")
            return None

        open_id, access_token = result
        field = _encode_open_id(open_id)
        _step3_major_register(access_token, open_id, field, name)

        return {
            "uid":          str(uid),
            "password":     password,
            "name":         name,
            "region":       region,
            "status":       "registered",
            "open_id":      open_id,
            "access_token": access_token,
        }
    except Exception as e:
        _log(f"register_only ERROR: {e}")
        return None

def _step5_get_login_data(jwt_token, access_token, open_id, region):
    try:
        payload = (
            b':\x071.114.13\xaa\x01\x02ar'
            b'\xb2\x01 55ed759fcf94f85813e57b2ec8492f5c\xba\x01\x014'
            b'\xea\x01@6fb7fdef8658fd03174ed551e82b71b21db8187fa0612c8eaf1b63aa687f1eae'
            b'\x9a\x06\x014\xa2\x06\x014'
        )
        parts = jwt_token.split('.')
        if len(parts) < 2:
            return False
        p = parts[1] + '=' * ((4 - len(parts[1]) % 4) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(p))
        ext_id = decoded.get('external_id', '')
        sig_md5 = decoded.get('signature_md5', '')
        now_str = str(datetime.now())[:19]
        payload = payload.replace(b"2023-12-24 04:21:34", now_str.encode())
        payload = payload.replace(
            b"15f5ba1de5234a2e73cc65b6f34ce4b299db1af616dd1dd8a6f31b147230e5b6",
            access_token.encode("UTF-8"))
        payload = payload.replace(
            b"4666ecda0003f1809655a7a8698573d0", ext_id.encode("UTF-8"))
        payload = payload.replace(
            b"7428b253defc164018c604a1ebbfebdf", sig_md5.encode("UTF-8"))
        enc = _aes_encrypt(payload.hex())
        base_url = REGION_URLS.get(region, "https://clientbp.ggblueshark.com/")
        hdrs = {**BASE_HEADERS, "Authorization": f"Bearer {jwt_token}"}
        r = _session().post(f"{base_url}GetLoginData", headers=hdrs, data=enc, verify=False, timeout=20)
        return r.status_code == 200
    except Exception:
        return False

# Persistence
_proj_root = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
GUESTS_JSON_PATH = os.path.join(_proj_root, "data", "guests.json")
GUESTS_DB_PATH = os.path.join(_proj_root, "data", "guests.db")

def save_to_json(accounts):
    os.makedirs(os.path.dirname(GUESTS_JSON_PATH), exist_ok=True)
    existing = []
    if os.path.exists(GUESTS_JSON_PATH):
        try:
            with open(GUESTS_JSON_PATH) as f:
                existing = json.load(f)
        except Exception:
            existing = []
    uid_set = {a["uid"] for a in existing}
    for a in accounts:
        if a["uid"] not in uid_set:
            existing.append(a)
            uid_set.add(a["uid"])
    with open(GUESTS_JSON_PATH, "w") as f:
        json.dump(existing, f, indent=2)

async def save_to_db(accounts):
    import time as _t
    db = await aiosqlite.connect(GUESTS_DB_PATH)
    await db.execute("""CREATE TABLE IF NOT EXISTS guests (
        uid TEXT PRIMARY KEY, password TEXT NOT NULL,
        region TEXT NOT NULL DEFAULT 'ME', nickname TEXT DEFAULT '',
        created_at REAL DEFAULT 0, last_used REAL DEFAULT 0,
        like_count INTEGER DEFAULT 0, is_active INTEGER DEFAULT 1,
        health_status TEXT DEFAULT 'unknown', jwt_failures INTEGER DEFAULT 0,
        open_id TEXT DEFAULT '', access_token TEXT DEFAULT '')""")
    # Also add columns to existing tables (ALTER TABLE if missing)
    try:
        await db.execute("ALTER TABLE guests ADD COLUMN open_id TEXT DEFAULT ''")
    except Exception:
        pass
    try:
        await db.execute("ALTER TABLE guests ADD COLUMN access_token TEXT DEFAULT ''")
    except Exception:
        pass
    now = _t.time()
    for a in accounts:
        try:
            await db.execute(
                "INSERT OR REPLACE INTO guests (uid,password,region,nickname,created_at,health_status,open_id,access_token,is_active,jwt_failures,like_count,last_used) "
                "VALUES (?,?,?,?,?,?,?,?,1,0,0,0)",
                (a["uid"], a["password"], a["region"], a.get("name",""), now, "unknown",
                 a.get("open_id",""), a.get("access_token","")))
        except Exception as e:
            print(f"DB save error for {a['uid']}: {e}")
    await db.commit()
    await db.close()
