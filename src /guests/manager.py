"""
Guest Account Manager
SQLite-backed guest pool with health checks, deduplication, and usage tracking.
"""

import time
import asyncio
import aiosqlite
from typing import List, Optional, Tuple
from dataclasses import dataclass

from ..core.config_loader import get_config
from ..core.logger import setup_logger

logger = setup_logger("guests")


@dataclass
class GuestAccount:
    uid: str
    password: str
    region: str
    nickname: str = ""
    created_at: float = 0
    last_used: float = 0
    like_count: int = 0
    is_active: bool = True
    health_status: str = "unknown"
    jwt_failures: int = 0
    open_id: str = ""
    access_token: str = ""


class GuestManager:
    """
    Manages guest accounts in SQLite with full CRUD and usage tracking.
    """

    def __init__(self):
        self.config = get_config()
        self.db_path = self.config.settings.guests.db_path
        self._db: Optional[aiosqlite.Connection] = None
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Initialize guest database."""
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS guests (
                uid TEXT PRIMARY KEY,
                password TEXT NOT NULL,
                region TEXT NOT NULL DEFAULT 'ME',
                nickname TEXT DEFAULT '',
                created_at REAL DEFAULT 0,
                last_used REAL DEFAULT 0,
                like_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                health_status TEXT DEFAULT 'unknown',
                jwt_failures INTEGER DEFAULT 0,
                open_id TEXT DEFAULT '',
                access_token TEXT DEFAULT ''
            )
        """)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS usage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_uid TEXT NOT NULL,
                target_uid TEXT NOT NULL,
                timestamp REAL NOT NULL,
                success INTEGER DEFAULT 1,
                region TEXT DEFAULT 'ME',
                UNIQUE(guest_uid, target_uid)
            )
        """)

        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_usage_target ON usage_history(target_uid)
        """)

        # Migrate old tables: add open_id and access_token columns if missing
        try:
            await self._db.execute("ALTER TABLE guests ADD COLUMN open_id TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists
        try:
            await self._db.execute("ALTER TABLE guests ADD COLUMN access_token TEXT DEFAULT ''")
        except Exception:
            pass  # Column already exists

        await self._db.commit()
        logger.info("Guest database initialized")

    async def add_guest(self, guest: GuestAccount) -> bool:
        """Add a single guest account."""
        async with self._lock:
            try:
                await self._db.execute(
                    """INSERT INTO guests 
                       (uid, password, region, nickname, created_at, last_used, like_count, is_active, health_status, jwt_failures, open_id, access_token)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (guest.uid, guest.password, guest.region, guest.nickname,
                     guest.created_at, guest.last_used, guest.like_count,
                     int(guest.is_active), guest.health_status, guest.jwt_failures,
                     getattr(guest, 'open_id', ''), getattr(guest, 'access_token', ''))
                )
                await self._db.commit()
                return True
            except aiosqlite.IntegrityError:
                logger.debug(f"Guest {guest.uid} already exists")
                return False

    async def add_guests_bulk(self, guests: List[GuestAccount]) -> Tuple[int, int]:
        """Bulk insert guests. Returns (added, skipped)."""
        added = 0
        skipped = 0
        for guest in guests:
            if await self.add_guest(guest):
                added += 1
            else:
                skipped += 1
        logger.info(f"Bulk insert: {added} added, {skipped} skipped")
        return added, skipped

    async def get_available_for_target(self, target_uid: str, region: str = "ME", 
                                        limit: int = 100) -> List[GuestAccount]:
        """Get guests that haven't liked this target yet."""
        async with self._lock:
            async with self._db.execute(
                """SELECT g.* FROM guests g
                   WHERE g.is_active = 1 
                   AND g.region = ?
                   AND g.uid NOT IN (
                       SELECT guest_uid FROM usage_history 
                       WHERE target_uid = ?
                   )
                   ORDER BY g.like_count ASC, g.last_used ASC
                   LIMIT ?""",
                (region, target_uid, limit)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_guest(row) for row in rows]

    async def mark_used(self, guest_uid: str, target_uid: str, success: bool = True, region: str = "ME"):
        """Mark a guest as used for a target."""
        now = time.time()
        async with self._lock:
            await self._db.execute(
                """INSERT OR IGNORE INTO usage_history 
                   (guest_uid, target_uid, timestamp, success, region)
                   VALUES (?, ?, ?, ?, ?)""",
                (guest_uid, target_uid, now, int(success), region)
            )

            if success:
                await self._db.execute(
                    "UPDATE guests SET like_count = like_count + 1, last_used = ? WHERE uid = ?",
                    (now, guest_uid)
                )
            else:
                await self._db.execute(
                    "UPDATE guests SET jwt_failures = jwt_failures + 1 WHERE uid = ?",
                    (guest_uid,)
                )

            await self._db.commit()

    async def count_total(self) -> int:
        """Total guest count."""
        async with self._lock:
            async with self._db.execute("SELECT COUNT(*) FROM guests") as cursor:
                row = await cursor.fetchone()
                return row[0]

    async def count_available(self, target_uid: str = None, region: str = "ME") -> int:
        """Count available guests for target."""
        async with self._lock:
            if target_uid:
                async with self._db.execute(
                    """SELECT COUNT(*) FROM guests g
                       WHERE g.is_active = 1 AND g.region = ?
                       AND g.uid NOT IN (
                           SELECT guest_uid FROM usage_history WHERE target_uid = ?
                       )""",
                    (region, target_uid)
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0]
            else:
                async with self._db.execute(
                    "SELECT COUNT(*) FROM guests WHERE is_active = 1"
                ) as cursor:
                    row = await cursor.fetchone()
                    return row[0]

    async def get_stats(self) -> dict:
        """Get comprehensive statistics."""
        async with self._lock:
            async with self._db.execute("SELECT COUNT(*), SUM(like_count) FROM guests") as cursor:
                row = await cursor.fetchone()
                total = row[0] if row else 0
                total_likes = row[1] if row and len(row) > 1 else 0

            async with self._db.execute(
                "SELECT COUNT(*) FROM guests WHERE is_active = 0"
            ) as cursor:
                row = await cursor.fetchone()
                inactive = row[0] if row else 0

            async with self._db.execute(
                "SELECT COUNT(DISTINCT target_uid) FROM usage_history"
            ) as cursor:
                row = await cursor.fetchone()
                targets = row[0] if row else 0

        return {
            "total_guests": total or 0,
            "active_guests": (total or 0) - (inactive or 0),
            "inactive_guests": inactive or 0,
            "total_likes_sent": total_likes or 0,
            "unique_targets": targets or 0,
        }


    async def update_tokens(self, uid: str, open_id: str, access_token: str):
        """Save OAuth tokens for a guest account."""
        async with self._lock:
            await self._db.execute(
                "UPDATE guests SET open_id = ?, access_token = ? WHERE uid = ?",
                (open_id, access_token, uid)
            )
            await self._db.commit()

    async def health_check(self) -> bool:
        """Check database health."""
        try:
            async with self._lock:
                async with self._db.execute("SELECT 1") as cursor:
                    await cursor.fetchone()
            return True
        except Exception:
            return False

    async def verify_guest(self, guest: GuestAccount, jwt_manager) -> bool:
        """
        Verify a guest account by attempting to obtain a JWT.
        Updates guest status, health, and nickname in database.
        Returns True if valid, False otherwise.
        """
        # Invalidate token cache to force a fresh login check
        await jwt_manager.invalidate(guest.uid)
        
        # Try to get/generate token (no DB lock needed for network request)
        token_result = await jwt_manager.get_token(guest.uid, guest.password, guest.region)
        if token_result:
            token, lock_region, server_url = token_result
            # Try to decode JWT to get guest details if needed, e.g., nickname
            payload = await jwt_manager.decode(token)
            nickname = guest.nickname
            if payload and "nickname" in payload:
                nickname = payload["nickname"]
            elif payload and "name" in payload:
                nickname = payload["name"]
                
            async with self._lock:
                await self._db.execute(
                    """UPDATE guests SET 
                       health_status = 'healthy', 
                       is_active = 1, 
                       jwt_failures = 0,
                       nickname = ?,
                       region = ?
                       WHERE uid = ?""",
                    (nickname, lock_region, guest.uid)
                )
                await self._db.commit()
            logger.info(f"Guest {guest.uid} verified successfully (Region: {lock_region})")
            return True
        else:
            # JWT generation failed
            async with self._lock:
                await self._db.execute(
                    """UPDATE guests SET 
                       health_status = 'dead', 
                       jwt_failures = jwt_failures + 1
                       WHERE uid = ?""",
                    (guest.uid,)
                )
                await self._db.commit()
                
                # If failures exceed threshold and auto_remove_dead is enabled, deactivate
                if self.config.settings.guests.auto_remove_dead:
                    async with self._db.execute("SELECT jwt_failures FROM guests WHERE uid = ?", (guest.uid,)) as cursor:
                        row = await cursor.fetchone()
                        failures = row[0] if row else 0
                    if failures >= 3:
                        await self._db.execute(
                            "UPDATE guests SET is_active = 0 WHERE uid = ?",
                            (guest.uid,)
                        )
                        await self._db.commit()
                        logger.warning(f"Guest {guest.uid} deactivated due to {failures} failures")
            return False

    async def verify_all_guests(self, jwt_manager, progress_callback=None, concurrency: int = 10) -> Tuple[int, int]:
        """
        Verify all guest accounts in database concurrently.
        Returns (healthy_count, dead_count).
        """
        async with self._lock:
            async with self._db.execute("SELECT * FROM guests WHERE is_active = 1") as cursor:
                rows = await cursor.fetchall()
                guests = [self._row_to_guest(row) for row in rows]
            
        if not guests:
            return 0, 0
            
        semaphore = asyncio.Semaphore(concurrency)
        healthy = 0
        dead = 0
        lock = asyncio.Lock()
        
        async def verify_one(guest):
            nonlocal healthy, dead
            async with semaphore:
                success = await self.verify_guest(guest, jwt_manager)
                async with lock:
                    if success:
                         healthy += 1
                    else:
                         dead += 1
                    if progress_callback:
                         progress_callback(guest, success, healthy, dead, len(guests))
                         
        await asyncio.gather(*[verify_one(g) for g in guests])
        return healthy, dead

    async def close(self):
        """Close database connection."""
        if self._db:
            await self._db.close()

    def _row_to_guest(self, row) -> GuestAccount:
        """Convert DB row to GuestAccount (includes open_id + access_token)."""
        kwargs = dict(
            uid=row[0],
            password=row[1],
            region=row[2],
            nickname=row[3],
            created_at=row[4],
            last_used=row[5],
            like_count=row[6],
            is_active=bool(row[7]),
            health_status=row[8],
            jwt_failures=row[9],
        )
        if len(row) > 10:
            kwargs['open_id'] = row[10] or ""
        if len(row) > 11:
            kwargs['access_token'] = row[11] or ""
        return GuestAccount(**kwargs)
