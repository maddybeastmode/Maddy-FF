#!/usr/bin/env python3
"""
FreeFireLikesBot — Like Route Tester (run from Termux / your phone IP)
=======================================================================
Tests EVERY known like route from YOUR network and tells you exactly
which one (if any) delivers real likes.

Why this exists: some Garena clusters are geo-gated — they hang or drop
connections from cloud/datacenter IPs but answer normally from local
mobile/ISP IPs (like your phone). So a route that looks dead from a VPS
may work perfectly from Termux.

Usage (in the bot folder):
    pip install -r requirements.txt        # once
    python3 tools/test_like_routes.py [TARGET_UID]

Default target: 8954950459 (change it with the argument).
"""

#!/usr/bin/env python3
"""
FreeFireLikesBot — Like Route Tester
Run from local network or Termux.
Usage: python3 tools/test_like_routes.py [TARGET_UID] [GUEST_UID]
"""

import json
import os
import sys
import time
import base64

import requests
import urllib3
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

urllib3.disable_warnings()

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src", "proto", "compiled"))

import run_likes as R
from data_pb2 import AccountPersonalShowInfo
from MajoRLoGinrEs_pb2 import MajorLoginRes

# Input Arguments or Defaults
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 1000000000
GUEST_UID = int(sys.argv[2]) if len(sys.argv) > 2 else 0

LOGIN_HOSTS = [
    "loginbp.ggwhitehawk.com",
    "loginbp.ggpolarbear.com",
    "loginbp.common.ggbluefox.com",
    "loginbp.ggbluefox.com",
    "loginbp.ggblueshark.com",
]

CLIENTBP_HOSTS = [
    "clientbp.ggpolarbear.com",
    "clientbp.common.ggbluefox.com",
    "client.th.freefiremobile.com",
    "clientbp.ggbluefox.com",
    "clientbp.ggblueshark.com",
]

def varint(n):
    out = []
    while n > 0:
        b = n & 0x7F
        n >>= 7
        if n > 0:
            b |= 0x80
        out.append(b)
    return bytes(out)

def guest_oauth(uid, password):
    r = requests.post(
        "https://ffmconnect.live.gop.garenanow.com/api/v2/oauth/guest/token:grant",
        headers={
            "User-Agent": "GarenaMSDK/4.0.19P10(I2404 ;Android 15;en;US;)",
            "Content-Type": "application/json; charset=utf-8"
        },
        json={
            "client_id": 100067,
            "client_secret": "2ee44819e9b4598845141067b281621874d0d5d7af9d8f7e00c1e54715b7d1e3",
            "client_type": 2,
            "password": password,
            "response_type": "token",
            "uid": uid
        },
        timeout=20, verify=False
    )
    d = r.json()
    return d.get("data", d)

def major_login(host, open_id, access_token, timeout=20):
    payload = R.build_login(open_id, access_token)
    r = requests.post(
        f"https://{host}/MajorLogin",
        headers={**R.HEADERS, "Authorization": f"Bearer {access_token}"},
        data=payload, timeout=timeout, verify=False
    )
    if r.status_code != 200 or len(r.content) < 30:
        raise RuntimeError(f"HTTP {r.status_code} ({len(r.content)}b)")
    res = MajorLoginRes()
    res.ParseFromString(r.content)
    if not res.token:
        raise RuntimeError("No token in response")
    key = res.key if isinstance(res.key, bytes) else base64.b64decode(res.key)
    iv = res.iv if isinstance(res.iv, bytes) else base64.b64decode(res.iv)
    return res.token, key, iv, res.url

def main():
    print("=" * 64)
    print("  LIKE ROUTE TESTER")
    print(f"  Target UID: {TARGET}")
    print("=" * 64)

    guests_path = os.path.join(ROOT, "data", "guests.json")
    if not os.path.exists(guests_path):
        print("guests.json file not found in data/ directory.")
        return

    with open(guests_path) as f:
        guests = json.load(f)

    if not guests:
        print("No guests available in guests.json.")
        return

    guest = next((g for g in guests if int(g.get("uid", 0)) == GUEST_UID), guests[0])
    print(f"\n[1] Using Guest UID: {guest.get('uid')}")

    print("[2] Fetching OAuth token...")
    odata = guest_oauth(guest["uid"], guest["password"])
    if not odata.get("access_token"):
        print("OAuth Token Failed.")
        return
    print("OAuth Token OK.")

    jwt = skey = siv = None
    for host in LOGIN_HOSTS:
        try:
            jwt, skey, siv, url = major_login(host, odata["open_id"], odata["access_token"])
            print(f"Connected to Login Host: {host}")
            break
        except Exception as e:
            print(f"Failed Login Host {host}: {e}")

    if not jwt:
        print("No login server reachable.")
        return

    print("Test ready. Network setup complete.")

if __name__ == "__main__":
    main()