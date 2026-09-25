#!/usr/bin/env python3
"""
Site delivery — sends likes through your own ff-like.noobs-api.top backend.

Direct Garena HTTP is dead (server-side anti-bot sink, verified from multiple
IPs including mobile). Your site's pipeline is the ONLY working route.

TWO auth modes (auto-detected):

  MODE A - Dashboard JWT (default, needs Prime 1, no API key):
    Save it:  echo -n "eyJhbGciOi..." > data/site_jwt.txt
    (or)      export NOOBS_JWT=eyJhbGciOi...
    Uses GET /api/like?uid=&pkg=&server=  (main credits: 100 likes = 5 cr)

  MODE B - API key (needs Prime 3):
    Save it:  echo -n "noobs_XXXX" > data/site_api_key.txt
    Uses POST /api/fflike  (API credits: 100 = 5, 120 = 6, 220 = 10)

Usage:
  python3 run_likes.py --site --target <UID> --count 100 [--server mena]

Servers: bd ind mena na pk id sg th   (default: mena)
The response includes before/after like counts -> real delivery proof.
"""

import os
import sys
import json
import time
import requests

SITE = "https://ff-like.noobs-api.top"
HERE = os.path.dirname(os.path.abspath(__file__))
JWT_FILE = os.path.join(HERE, "data", "site_jwt.txt")
KEY_FILE = os.path.join(HERE, "data", "site_api_key.txt")
PACKAGES = [100, 120, 220]          # likes per package
PICK = lambda n: max([p for p in PACKAGES if p <= max(n, 100)] or [100])
DEFAULT_SERVER = "mena"


def _read(path, env):
    val = os.environ.get(env, "").strip()
    if not val and os.path.exists(path):
        with open(path) as f:
            val = f.read().strip()
    return val


def load_jwt():
    return _read(JWT_FILE, "NOOBS_JWT")


def load_api_key():
    return _read(KEY_FILE, "NOOBS_API_KEY")


def send_likes_via_site(uid, count=100, server=DEFAULT_SERVER):
    """Send likes. Uses JWT mode if available, falls back to API-key mode."""
    jwt = load_jwt()
    package = PICK(count)

    if jwt:
        r = requests.get(f"{SITE}/api/like",
                         params={"uid": str(uid), "pkg": package, "server": server},
                         headers={"Authorization": f"Bearer {jwt}"},
                         timeout=300)
        mode = "dashboard"
    else:
        key = load_api_key()
        if not key:
            print("=" * 62)
            print("  NO AUTH FOUND - do ONE of these:")
            print(f"  a) save your site JWT:   echo -n \"eyJ...\" > {JWT_FILE}")
            print(f"  b) save an API key:      echo -n \"noobs_...\" > {KEY_FILE}")
            print("  (JWT = dashboard account, Prime 1+. API key = Prime 3+)")
            print("=" * 62)
            sys.exit(1)
        r = requests.post(f"{SITE}/api/fflike",
                          headers={"Authorization": f"Bearer {key}",
                                   "Content-Type": "application/json"},
                          json={"uid": str(uid), "package": package}, timeout=300)
        mode = "apikey"

    try:
        data = r.json()
    except Exception:
        print(f"[site] HTTP {r.status_code}: {r.text[:200]}")
        return None
    data["_mode"] = mode
    data["_package"] = package
    return data


def site_flow(target, count, server=DEFAULT_SERVER):
    print("=" * 62)
    print("  SITE DELIVERY MODE (ff-like.noobs-api.top)")
    print(f"  target: {target}  count: {count}  server: {server}")
    print(f"  auth:   {'dashboard JWT' if load_jwt() else 'API key'}")
    print("=" * 62)

    print("[site] sending... (real delivery, takes up to a few minutes)")
    t0 = time.time()
    res = send_likes_via_site(target, count, server)
    if not res:
        return
    if res.get("ok"):
        name = res.get("name", "?")
        before = res.get("before", "?")
        after = res.get("after", "?")
        added = res.get("likesAddedFinal", res.get("likesAdded", "?"))
        print(f"[site] player: {name}")
        print(f"[site] VERIFIED: {before} -> {after} likes  (+{added}) "
              f"in {time.time()-t0:.0f}s")
        left = res.get("credits") or res.get("creditsRemaining") or res.get("apiCreditsRemaining")
        if left is not None:
            print(f"[site] credits left: {left}")
        per = res.get("servers") or {}
        for sid, s in per.items():
            print(f"[site]   {s.get('name', sid)}: {s.get('ok')} "
                  f"({s.get('before', '?')} -> {s.get('after', '?')})")
    else:
        msg = res.get("message") or res.get("error") or json.dumps(res)[:200]
        print(f"[site] FAILED: {msg}")
        if "inactive" in str(msg).lower():
            print("[site] account not activated yet - top up 30 BDT once (or redeem a coupon)")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--target", required=True)
    p.add_argument("--count", type=int, default=100)
    p.add_argument("--server", default=DEFAULT_SERVER)
    a = p.parse_args()
    site_flow(a.target, a.count, a.server)
