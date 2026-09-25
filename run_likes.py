#!/usr/bin/env python3
"""
Free Fire Like Bot — Termux Edition
====================================
Sends likes to any Free Fire UID using guest accounts.

Usage:
  python3 run_likes.py                 (interactive menu)
  python3 run_likes.py --target <UID> [--count 15] [--region ME]

Requirements:
  pip install pycryptodome pyyaml requests
"""

import sys, os, json, argparse, time, random
from datetime import datetime, timezone

# Add paths
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src", "proto", "compiled"))

import requests
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad
from MajoRLoGinrEq_pb2 import MajorLogin
from MajoRLoGinrEs_pb2 import MajorLoginRes
from like_count_pb2 import Info as LikeCountInfo
from dev_generator_pb2 import dev_generator
from data_pb2 import AccountPersonalShowInfo

def utcnow():
    """Timezone-naive UTC now — utcnow() is deprecated on Python 3.12+."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

# Silence the 'Unverified HTTPS request' spam (Garena endpoints use verify=False)
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ANSI colors (Segoe UI not required — works with any Termux font)
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    GREEN   = "\033[92m"
    YELLOW  = "\033[93m"
    RED     = "\033[91m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    DIM     = "\033[2m"

# ======================== CONFIG ========================
AES_KEY = b'Yg&tc%DEuh6%Zc^8'
AES_IV  = b'6oyZDr22E3ychjM%'

REGION_CODES = {
    "ME": 7, "IND": 1, "BR": 2, "SG": 3, "TH": 4, "PH": 5,
    "VN": 6, "RU": 8, "US": 9, "PK": 10, "BD": 11, "ID": 1, "TW": 12,
}

HEADERS = {
    'User-Agent': "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
    'Connection': "Keep-Alive",
    'Accept-Encoding': "gzip",
    'Content-Type': "application/octet-stream",
    'Expect': "100-continue",
    'X-Unity-Version': "2018.4.11f1",
    'X-GA': "v1 1",
    'ReleaseVersion': "OB54",
}

GUESTS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "guests.json")

LIKE_HISTORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "like_history.json")
LIKE_COOLDOWN = 24 * 60 * 60  # FF allows 1 like per guest per target, resets every 24h

def load_history():
    try:
        with open(LIKE_HISTORY_FILE) as f:
            history = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    # Prune entries older than the 24h cooldown — keeps the file tiny forever
    pruned, now = {}, utcnow()
    for g, targets in history.items():
        for t, ts in targets.items():
            try:
                if (now - datetime.fromisoformat(ts)).total_seconds() < LIKE_COOLDOWN:
                    pruned.setdefault(g, {})[t] = ts
            except ValueError:
                pass
    return pruned

def save_history(history):
    os.makedirs(os.path.dirname(LIKE_HISTORY_FILE), exist_ok=True)
    with open(LIKE_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def save_guests(guests):
    try:
        with open(GUESTS_FILE, "w") as f:
            json.dump(guests, f, indent=2)
    except OSError as e:
        print(f"  Could not save guests.json: {e}")

RUNS_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "runs.log")

def log_run(target, sent, requested, before, after):
    try:
        os.makedirs(os.path.dirname(RUNS_LOG), exist_ok=True)
        with open(RUNS_LOG, "a") as f:
            b = f"{before:,}" if before is not None else "?"
            a = f"{after:,}" if after is not None else "?"
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M')} | target={target} "
                    f"sent={sent}/{requested} | likes {b} -> {a}\n")
    except OSError:
        pass

def cooldown_left(history, guest_uid, target_uid):
    """Return remaining cooldown string if guest already liked target in last 24h, else None."""
    ts = history.get(str(guest_uid), {}).get(str(target_uid))
    if not ts:
        return None
    elapsed = (utcnow() - datetime.fromisoformat(ts)).total_seconds()
    if elapsed < LIKE_COOLDOWN:
        h, rem = divmod(int(LIKE_COOLDOWN - elapsed), 3600)
        return f"{h}h {rem // 60}m"
    return None

def record_like(history, guest_uid, target_uid):
    history.setdefault(str(guest_uid), {})[str(target_uid)] = utcnow().isoformat()
    save_history(history)

# ======================== HELPERS ========================

def encode_varint(n):
    result = []
    while n > 0:
        b = n & 0x7F
        n >>= 7
        if n > 0: b |= 0x80
        result.append(b)
    return bytes(result)

def build_login(open_id, access_token):
    ml = MajorLogin()
    ml.event_time = str(datetime.now())[:-7]
    ml.game_name = "free fire"
    ml.platform_id = 2
    ml.client_version = "1.126.2"
    ml.client_version_code = "2024010012"
    ml.system_software = "Android OS 11 / API-30 (RQ3A.210805.001)"
    ml.system_hardware = "Handheld"
    ml.device_type = "Handheld"
    ml.telecom_operator = "Verizon"
    ml.network_operator_a = "Verizon"
    ml.network_type = "WIFI"
    ml.network_type_a = "WIFI"
    ml.screen_width = 1080
    ml.screen_height = 2400
    ml.screen_dpi = "440"
    ml.processor_details = "ARMv8"
    ml.cpu_type = 2
    ml.cpu_architecture = "64"
    ml.memory = 6144
    ml.gpu_renderer = "Adreno (TM) 650"
    ml.gpu_version = "OpenGL ES 3.2 V@1.50"
    ml.graphics_api = "OpenGLES3"
    ml.unique_device_id = f"Google|{random.randint(10**30, 10**31):x}"
    ml.client_ip = ""
    ml.language = "en"
    ml.open_id = open_id
    ml.open_id_type = "4"
    ml.login_open_id_type = 4
    ml.access_token = access_token
    ml.login_by = 3
    ml.platform_sdk_id = 2
    ml.origin_platform_type = "4"
    ml.primary_platform_type = "4"
    ml.memory_available.version = 55
    ml.memory_available.hidden_value = 81
    ml.external_storage_total = 128512
    ml.external_storage_available = random.randint(38000, 52000)
    ml.internal_storage_total = 110731
    ml.internal_storage_available = random.randint(18000, 32000)
    ml.game_disk_storage_total = 26628
    ml.game_disk_storage_available = random.randint(18000, 25000)
    ml.external_sdcard_total_storage = 119234
    ml.external_sdcard_avail_storage = random.randint(25000, 60000)
    ml.library_path = "/data/app/~~random/base.apk"
    ml.library_token = "hash|base.apk"
    ml.client_using_version = "7428b253defc164018c604a1ebbfebdf"
    ml.supported_astc_bitset = 16383
    ml.analytics_detail = b"FwQVTgUPX1UaUllDDwcWCRBpWAUOUgsvA1snWlBaO1kFYg=="
    ml.loading_time = random.randint(9000, 18000)
    ml.release_channel = "android"
    ml.channel_type = 3
    ml.reg_avatar = 1
    ml.if_push = 1
    ml.is_vpn = 0
    return AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(ml.SerializeToString(), 16))

def send_like(jwt, target_uid, region="ME"):
    region_code = REGION_CODES.get(region.upper(), 7)
    uid_varint = encode_varint(target_uid)
    raw = bytes([0x08]) + uid_varint + bytes([0x10, region_code])
    enc = AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(raw, 16))
    resp = requests.post("https://clientbp.ggpolarbear.com/LikeProfile",
        headers={**HEADERS, "Authorization": f"Bearer {jwt}"},
        data=enc, timeout=15)
    return resp.status_code, resp.content

def fetch_info(jwt, target_uid):
    """Live fetch: nickname, level, region and LIKES of any UID (GetPlayerPersonalShow)."""
    msg = dev_generator()
    msg.saturn_ = int(target_uid)
    msg.garena = 1
    enc = AES.new(AES_KEY, AES.MODE_CBC, AES_IV).encrypt(pad(msg.SerializeToString(), 16))
    info_headers = {
        "User-Agent": "Dalvik/2.1.0 (Linux; U; Android 11; ASUS_Z01QD Build/PI)",
        "Connection": "Keep-Alive",
        "Accept-Encoding": "gzip",
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Unity-Version": "2018.4.11f1",
        "X-GA": "v1 1",
        "ReleaseVersion": "OB54",
    }
    try:
        resp = requests.post("https://clientbp.ggpolarbear.com/GetPlayerPersonalShow",
            headers=info_headers, data=enc, timeout=15)
    except Exception as e:
        print(f"  Live fetch error: {e}")
        return None
    if resp.status_code != 200 or len(resp.content) < 10:
        return None
    try:
        info = AccountPersonalShowInfo()
        info.ParseFromString(resp.content)
        b = info.basic_info
        return {"nickname": b.nickname, "level": b.level,
                "likes": b.liked, "region": b.region}
    except Exception:
        return None

def guest_jwt(guest):
    """Authenticate one guest: OAuth refresh -> MajorLogin. Returns JWT or None."""
    try:
        resp = requests.post(
            "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant",
            headers={"User-Agent": "GarenaMSDK/4.0.19P10(I2404 ;Android 15;en;US;)",
                     "Content-Type": "application/json; charset=utf-8"},
            json={"client_id": 100067,
                  "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
                  "client_type": 2, "password": guest["password"],
                  "response_type": "token", "uid": int(guest["uid"])},
            timeout=15, verify=False)
        odata = resp.json().get("data", resp.json())
        guest["access_token"] = odata["access_token"]
        guest["open_id"] = odata["open_id"]
        print(f"  {C.GREEN}OAuth refreshed \u2713{C.RESET}")
    except Exception as e:
        if "access_token" not in guest:
            print(f"  {C.RED}OAuth FAIL: {e}{C.RESET}")
            return None
        print(f"  OAuth FAIL: {e} \u2014 using stored token")
    try:
        resp = requests.post("https://loginbp.ggpolarbear.com/MajorLogin",
            headers={**HEADERS, "Authorization": f"Bearer {guest['access_token']}"},
            data=build_login(guest["open_id"], guest["access_token"]), timeout=20)
        if resp.status_code != 200:
            print(f"  {C.RED}MajorLogin FAIL: HTTP {resp.status_code}{C.RESET}")
            return None
        res = MajorLoginRes()
        res.ParseFromString(resp.content)
        print(f"  {C.GREEN}JWT OK{C.RESET}")
        return res.token
    except Exception as e:
        print(f"  MajorLogin error: {e}")
        return None

# ======================== MAIN ========================

def send_likes_flow(target, count, region, per_guest=1):
    with open(GUESTS_FILE) as f:
        guests = json.load(f)

    history = load_history()
    fresh = [g for g in guests if not cooldown_left(history, g["uid"], target)]
    skipped = 0
    dead_skipped = 0
    likes_needed = count
    likes_sent = 0
    before_likes = None
    last_jwt = None
    debug_dumped = False

    print("=" * 50)
    print(f"{C.CYAN}{C.BOLD}  FREE FIRE LIKE BOT{C.RESET}")
    print(f"  Target: {target}")
    print(f"  Likes: {count}")
    print(f"  Region: {region}")
    print(f"  Guests: {len(guests)} ({len(fresh)} fresh, {len(guests) - len(fresh)} on 24h cooldown)")
    if len(fresh) < count:
        print(f"  {C.YELLOW}\u26a0 Only {len(fresh)} fresh guests for {count} likes — run will fall short{C.RESET}")
    print("=" * 50)

    for i, guest in enumerate(guests):
        if likes_sent >= likes_needed:
            break

        uid = guest["uid"]
        print(f"\n[Guest {i+1}] UID: {uid}")

        # FF rule: 1 like per guest per target per 24h — don't waste the OAuth call
        wait = cooldown_left(history, uid, target)
        if wait:
            skipped += 1
            print(f"  {C.YELLOW}Already liked this target — cooldown resets in {wait}. Skipped.{C.RESET}")
            continue

        if guest.get("status") == "dead":
            dead_skipped += 1
            print(f"  Dead account (failed 2x) — skipped. Revive via menu [5].")
            continue

        jwt = guest_jwt(guest)
        if not jwt:
            fails = guest.get("fails", 0) + 1
            guest["fails"] = fails
            if fails >= 2:
                guest["status"] = "dead"
                print(f"  Marked DEAD (auth failed {fails}x)")
            print("  Skipping guest.")
            continue
        guest["fails"] = 0
        last_jwt = jwt

        # Live check on the target before liking (uses first working guest)
        if before_likes is None:
            info = fetch_info(jwt, target)
            if info:
                before_likes = info["likes"]
                print(f"  {C.MAGENTA}LIVE: {info['nickname']} (Lv.{info['level']}, {info['region']}) — likes now: {info['likes']:,}{C.RESET}")

        likes_this_guest = 0
        for j in range(per_guest):
            if likes_sent >= likes_needed:
                break
            try:
                status, raw = send_like(jwt, target, region)
                if status != 200:
                    print(f"  [{j+1}/{per_guest}] FAIL: HTTP {status} — retrying once...")
                    time.sleep(2)
                    status, raw = send_like(jwt, target, region)
                if status == 200:
                    likes_sent += 1
                    likes_this_guest += 1
                    live = None
                    try:
                        lc = LikeCountInfo()
                        lc.ParseFromString(raw)
                        live = lc.AccountInfo.Likes
                    except Exception:
                        pass
                    if live == 0:
                        # 200 OK but zero count = server returned an empty body — like likely dropped
                        live = None
                        if not debug_dumped:
                            debug_dumped = True
                            print(f"  {C.DIM}debug: LikeProfile resp {len(raw)} bytes: {raw[:48].hex()}{C.RESET}")
                    extra = f" \u2014 target likes now: {live:,}" if live is not None else ""
                    print(f"  [{likes_this_guest}/{per_guest}] Like sent! ({likes_sent}/{count} total){extra}")
                    record_like(history, uid, target)
                else:
                    print(f"  [{j+1}/{per_guest}] FAIL: HTTP {status}")
                time.sleep(random.uniform(2.5, 4.0))  # jitter — looks less bot-like
            except Exception as e:
                print(f"  Error: {e}")
                time.sleep(2)

    # Final live verification — did the server actually count the likes?
    print(f"\n{'='*50}")
    print(f"  RESULT: {likes_sent}/{count} likes sent")
    print(f"  Target: UID {target}")
    after_likes = None
    if likes_sent and last_jwt:
        after = fetch_info(last_jwt, target)
        if after:
            after_likes = after["likes"]
            if before_likes is not None and after_likes - before_likes == 0:
                print(f"  {C.DIM}count still flat — waiting 15s and re-checking (Garena counts can lag)...{C.RESET}")
                time.sleep(15)
                again = fetch_info(last_jwt, target)
                if again:
                    after_likes = again["likes"]
        if after_likes is not None and before_likes is not None:
            gained = after_likes - before_likes
            if gained >= likes_sent:
                verdict = f"{C.GREEN}COUNTED \u2713{C.RESET}"
            elif gained > 0:
                verdict = f"{C.YELLOW}PARTIAL ({gained}/{likes_sent}){C.RESET}"
            else:
                verdict = f"{C.RED}NOT COUNTED \u2717 \u2014 accounts may be too new (Garena drops likes from fresh accounts){C.RESET}"
            print(f"  LIVE VERIFY: {before_likes:,} \u2192 {after_likes:,} likes ({gained:+d}) — {verdict}")
        elif after_likes is not None:
            print(f"  LIVE VERIFY: target now at {after_likes:,} likes")
        else:
            print("  LIVE VERIFY: final fetch failed")
    if dead_skipped:
        print(f"  Dead accounts skipped: {dead_skipped} (revive via menu [5])")
    if skipped:
        print(f"  Skipped: {skipped} guests (already liked, 24h cooldown)")

    save_guests(guests)
    log_run(target, likes_sent, count, before_likes, after_likes)
    print("=" * 50)


def check_uid_info(target):
    with open(GUESTS_FILE) as f:
        guests = json.load(f)
    if not guests:
        print("No guest accounts available.")
        return
    print(f"\nFetching live info for UID {target}...")
    jwt = None
    for guest in guests[:3]:
        print(f"[Auth] guest {guest['uid']}")
        jwt = guest_jwt(guest)
        if jwt:
            break
    if not jwt:
        print("Could not authenticate any guest.")
        return
    info = fetch_info(jwt, target)
    if not info:
        print("Fetch failed — UID may be wrong or hidden.")
        return
    print("=" * 40)
    print(f"  Nickname : {info['nickname']}")
    print(f"  Level    : {info['level']}")
    print(f"  Region   : {info['region']}")
    print(f"  {C.MAGENTA}Likes    : {info['likes']:,}{C.RESET}")
    print("=" * 40)


def cooldown_status(target):
    with open(GUESTS_FILE) as f:
        guests = json.load(f)
    history = load_history()
    print(f"\n24h cooldown status for target {target}:")
    fresh = 0
    for g in guests:
        w = cooldown_left(history, g["uid"], target)
        if w:
            print(f"  {C.YELLOW}{g['uid']:<14} liked \u2014 resets in {w}{C.RESET}")
        else:
            print(f"  {C.GREEN}{g['uid']:<14} FRESH{C.RESET}")
            fresh += 1
    print(f"\n  Fresh: {fresh}/{len(guests)}")


def view_runs():
    try:
        with open(RUNS_LOG) as f:
            lines = [l for l in f.read().strip().split("\n") if l]
    except FileNotFoundError:
        print("\n  No runs logged yet.")
        return
    print(f"\n  Last {min(len(lines), 10)} run(s):")
    for l in lines[-10:]:
        print("  " + l)

def reset_dead():
    with open(GUESTS_FILE) as f:
        guests = json.load(f)
    n = 0
    for g in guests:
        if g.get("status") == "dead" or g.get("fails"):
            g["status"], g["fails"] = "ok", 0
            n += 1
    save_guests(guests)
    print(f"  Revived {n} account flag(s).")

def menu():
    while True:
        print("\n" + "=" * 50)
        print(f"{C.CYAN}{C.BOLD}  FREE FIRE LIKE BOT \u2014 MENU{C.RESET}")
        print("=" * 50)
        print(f"  {C.CYAN}[1] Send likes to a UID{C.RESET}")
        print(f"  {C.CYAN}[2] Check a UID (live info + likes){C.RESET}")
        print(f"  {C.CYAN}[3] Show 24h cooldown status for a UID{C.RESET}")
        print(f"  {C.CYAN}[4] View recent runs{C.RESET}")
        print(f"  {C.CYAN}[5] Reset dead-account flags{C.RESET}")
        print(f"  {C.CYAN}[6] Exit{C.RESET}")
        try:
            choice = input("\n  Choose [1-6]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye o/")
            break
        try:
            if choice == "1":
                target = int(input("  Target UID: ").strip())
                count = int(input("  Likes to send [20]: ").strip() or 20)
                region = (input("  Region [ME]: ").strip() or "ME").upper()
                send_likes_flow(target, count, region)
            elif choice == "2":
                check_uid_info(int(input("  UID to check: ").strip()))
            elif choice == "3":
                cooldown_status(int(input("  Target UID: ").strip()))
            elif choice == "4":
                view_runs()
            elif choice == "5":
                reset_dead()
            elif choice == "6":
                print("  Bye o/")
                break
            else:
                print("  Pick 1-4.")
        except ValueError:
            print("  Invalid number.")


def main():
    if len(sys.argv) > 1:
        p = argparse.ArgumentParser(description="Free Fire Like Bot")
        p.add_argument("--target", type=int, required=True, help="Target UID to send likes to")
        p.add_argument("--count", type=int, default=15, help="Total likes to send (default: 15)")
        p.add_argument("--region", type=str, default="ME", help="Region (default: ME)")
        p.add_argument("--per-guest", type=int, default=1, help="Max likes per guest (default: 1 — FF limits 1 like/account/24h)")
        p.add_argument("--site", action="store_true", help="Deliver via your ff-like.noobs-api.top backend instead of direct Garena (recommended)")
        p.add_argument("--server", type=str, default="mena", help="Site delivery server: bd ind mena na pk id sg th (default: mena)")
        args = p.parse_args()
        if args.site:
            from site_delivery import site_flow
            site_flow(args.target, args.count, args.server)
        else:
            send_likes_flow(args.target, args.count, args.region, args.per_guest)
    else:
        menu()


if __name__ == "__main__":
    main()
