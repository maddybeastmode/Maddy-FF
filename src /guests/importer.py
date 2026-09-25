"""
Guest Account Importer
Supports JSON, CSV, TXT, and Garena MSDK / Frida output formats.
"""

import json
import csv
from pathlib import Path
from typing import List

from .manager import GuestAccount
from ..core.logger import setup_logger

logger = setup_logger("importer")

# Garena MSDK key constants
MSDK_UID_KEY = "com.garena.msdk.guest_uid"
MSDK_PWD_KEY = "com.garena.msdk.guest_password"
GUEST_INFO_KEY = "guest_account_info"


class GuestImporter:
    """Import guest accounts from various file formats."""

    @staticmethod
    def _extract_garena_guest(data: dict, region: str = "ME") -> GuestAccount | None:
        """
        Extract a guest from Garena MSDK format:
        {"guest_account_info": {"com.garena.msdk.guest_uid": "...", "com.garena.msdk.guest_password": "..."}}
        
        Also handles flat format:
        {"com.garena.msdk.guest_uid": "...", "com.garena.msdk.guest_password": "..."}
        """
        info = data
        # If it has the wrapper key, unwrap it
        if GUEST_INFO_KEY in data and isinstance(data[GUEST_INFO_KEY], dict):
            info = data[GUEST_INFO_KEY]

        uid = info.get(MSDK_UID_KEY)
        password = info.get(MSDK_PWD_KEY)

        if uid and password:
            return GuestAccount(
                uid=str(uid),
                password=str(password),
                region=data.get("region", region),
                nickname=data.get("nickname", ""),
            )
        return None

    @staticmethod
    def _extract_simple_guest(item: dict, region: str = "ME") -> GuestAccount | None:
        """Extract guest from simple format: {"uid": "...", "password": "..."}"""
        uid = item.get("uid", "")
        password = item.get("password", "")
        if uid and password:
            return GuestAccount(
                uid=str(uid),
                password=str(password),
                region=item.get("region", region),
                nickname=item.get("nickname", ""),
            )
        return None

    @staticmethod
    def _extract_guest(data: dict, region: str = "ME") -> GuestAccount | None:
        """Try all known formats to extract a guest account from a dict."""
        # Try Garena MSDK format first
        guest = GuestImporter._extract_garena_guest(data, region)
        if guest:
            return guest

        # Try simple format
        guest = GuestImporter._extract_simple_guest(data, region)
        if guest:
            return guest

        # Try nested dicts (recurse one level)
        for k, v in data.items():
            if isinstance(v, dict):
                guest = GuestImporter._extract_garena_guest(v, region)
                if guest:
                    return guest
                guest = GuestImporter._extract_simple_guest(v, region)
                if guest:
                    return guest

        return None

    @staticmethod
    async def from_json(filepath: str, region: str = "ME") -> List[GuestAccount]:
        """
        Import from JSON file. Supports multiple formats:
        
        1. Garena MSDK format (single):
           {"guest_account_info": {"com.garena.msdk.guest_uid": "...", "com.garena.msdk.guest_password": "..."}}
        
        2. Array of Garena MSDK:
           [{"guest_account_info": {...}}, ...]
        
        3. Simple format:
           [{"uid": "...", "password": "..."}, ...]
        
        4. Mixed / nested dicts
        """
        guests = []
        with open(filepath, "r") as f:
            data = json.load(f)

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    guest = GuestImporter._extract_guest(item, region)
                    if guest:
                        guests.append(guest)
        elif isinstance(data, dict):
            # Try extracting a single guest from the top-level dict
            guest = GuestImporter._extract_guest(data, region)
            if guest:
                guests.append(guest)
            else:
                # Try each top-level value as a potential guest or list of guests
                for k, v in data.items():
                    if isinstance(v, dict):
                        guest = GuestImporter._extract_guest(v, region)
                        if guest:
                            guests.append(guest)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, dict):
                                guest = GuestImporter._extract_guest(item, region)
                                if guest:
                                    guests.append(guest)

        logger.info(f"Parsed {len(guests)} guests from JSON")
        return guests

    @staticmethod
    async def from_csv(filepath: str, region: str = "ME") -> List[GuestAccount]:
        """Import from CSV file."""
        guests = []
        with open(filepath, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Support both simple and MSDK column names
                uid = row.get("uid") or row.get(MSDK_UID_KEY, "")
                password = row.get("password") or row.get(MSDK_PWD_KEY, "")
                if uid and password:
                    guests.append(GuestAccount(
                        uid=str(uid),
                        password=str(password),
                        region=row.get("region", region),
                        nickname=row.get("nickname", ""),
                    ))
        logger.info(f"Parsed {len(guests)} guests from CSV")
        return guests

    @staticmethod
    async def from_txt(filepath: str, region: str = "ME") -> List[GuestAccount]:
        """Import from TXT file (uid:password per line)."""
        guests = []
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                parts = line.split(":")
                if len(parts) >= 2:
                    guests.append(GuestAccount(
                        uid=parts[0].strip(),
                        password=parts[1].strip(),
                        region=region,
                    ))
        logger.info(f"Parsed {len(guests)} guests from TXT")
        return guests

    @staticmethod
    async def from_frida(filepath: str, region: str = "ME") -> List[GuestAccount]:
        """Import from Frida guest capture output."""
        return await GuestImporter.from_json(filepath, region)
