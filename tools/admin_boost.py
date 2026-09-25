#!/usr/bin/env python3
"""
admin_boost.py — one-shot booster for YOUR OWN ff-like.noobs-api.top account.

Run this on your laptop after logging in to the site once with Google.
It will:
  1. upgrade your account to ADMIN (needs the admin password)
  2. set your credits to 100,000
  3. create + redeem a 15,000 coupon -> totalTopupBdt 15,000 -> PRIME 15 (max)

HOW TO GET YOUR JWT (one time):
  - open https://ff-like.noobs-api.top and log in with Google
  - press F12 -> Console tab -> type:  localStorage.getItem('ff_jwt_token')
  - copy the eyJ... string (with quotes is fine, it gets stripped)

Usage:
  python3 tools/admin_boost.py --jwt "eyJ..." [--credits 100000] [--prime 15000]

NOTE: never commit your JWT or the admin password anywhere public.
"""
#!/usr/bin/env python3
"""
admin_boost.py — Account administration script for custom panel domain.
Usage:
  python3 tools/admin_boost.py --site "https://your-app.wispbyte.app" --jwt "YOUR_JWT_TOKEN"
"""

import argparse
import json
import requests

def api(method, url, jwt, body=None, params=None):
    headers = {
        "Authorization": f"Bearer {jwt}",
        "Content-Type": "application/json"
    }
    r = requests.request(method, url, headers=headers, json=body, params=params, timeout=30)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"error": r.text[:200]}

def main():
    p = argparse.ArgumentParser(description="Admin Boost Helper")
    p.add_argument("--site", required=True, help="Base URL of your deployed site (e.g. https://my-app.wispbyte.app)")
    p.add_argument("--jwt", required=True, help="Your JWT token from localStorage")
    p.add_argument("--credits", type=int, default=100000, help="Credits amount")
    p.add_argument("--prime", type=int, default=15000, help="Prime level boost amount")
    a = p.parse_args()

    base_site = a.site.rstrip('/')
    jwt = a.jwt.strip().strip('"').strip("'")

    print(f"Connecting to: {base_site}")

    # Check profile state
    code, me = api("GET", f"{base_site}/api/user/profile", jwt)
    if code != 200:
        print(f"Failed to fetch profile. Response code: {code}, Message: {me}")
        return

    profile = me.get('profile', {})
    print(f"[1] Logged in as: {profile.get('email', '?')} | Credits: {profile.get('credits')} | Prime: {profile.get('primeLevel')}")

    # Admin Auth
    pw = input("[2] Enter Admin Password: ").strip()
    code, res = api("POST", f"{base_site}/api/user/admin-login", jwt, {"password": pw})
    if code != 200:
        print("Admin login failed:", res)
        return
    print("Admin access granted.")

    email = profile.get("email", "")
    code, found = api("GET", f"{base_site}/api/user/all", jwt, params={"page": 1, "limit": 20, "search": email})
    users = found.get("users", [])
    mine = next((u for u in users if u.get("email") == email), None)
    if not mine:
        print("Could not locate user account record:", found.get("error", "Unknown error"))
        return

    gid = mine.get("googleId")
    print(f"[3] Account Google ID: {gid}")

    # Update credits
    code, res = api("PUT", f"{base_site}/api/user/admin/{gid}", jwt, {
        "displayName": mine.get("displayName") or "Admin",
        "credits": a.credits,
        "role": "admin"
    })
    if code != 200:
        print("Failed to update credits:", res)
        return
    print(f"Credits successfully updated to {a.credits}.")

    # Redeem Prime Coupon
    code, res = api("POST", f"{base_site}/api/topup/admin/coupons", jwt, {
        "code": f"PRIME{a.prime}",
        "amount": a.prime
    })
    
    code, res = api("POST", f"{base_site}/api/topup/redeem-coupon", jwt, {"couponCode": f"PRIME{a.prime}"})
    if code == 200:
        print(f"Coupon redeemed successfully. Updated Credits: {res.get('credits')}")
    else:
        print("Coupon redemption message:", res.get("message") or res)

    # Final summary
    _, me = api("GET", f"{base_site}/api/user/profile", jwt)
    prof = me.get("profile", {})
    print(f"[4] Final Status -> Credits: {prof.get('credits')} | Prime Level: {prof.get('primeLevel')}")

if __name__ == "__main__":
    main()