"""
Main Bot Orchestrator
Coordinates all subsystems for like streak execution.
"""

import asyncio
from typing import Optional
from dataclasses import dataclass

from .config_loader import get_config
from .logger import setup_logger
from ..auth.jwt_manager import JWTManager
from ..crypto.aes_engine import AESEngine
from ..guests.manager import GuestManager
from ..likes.sender import LikeSender
from ..likes.streak_engine import StreakEngine
from ..network.http_client import HTTPClient
from ..network.proxy_rotator import ProxyRotator

logger = setup_logger("bot")


@dataclass
class BotStats:
    """Runtime bot statistics."""
    guests_total: int = 0
    guests_available: int = 0
    likes_sent: int = 0
    likes_failed: int = 0
    active_workers: int = 0
    jwt_cache_hits: int = 0
    jwt_cache_misses: int = 0


class FreeFireBot:
    """
    Main bot controller.

    Usage:
        bot = FreeFireBot()
        await bot.initialize()
        stats = await bot.send_likes(target_uid="123456", count=100)
        await bot.shutdown()
    """

    def __init__(self):
        self.config = get_config()
        self.stats = BotStats()

        # Subsystems
        self.http: Optional[HTTPClient] = None
        self.proxy_rotator: Optional[ProxyRotator] = None
        self.aes: Optional[AESEngine] = None
        self.jwt_manager: Optional[JWTManager] = None
        self.guest_manager: Optional[GuestManager] = None
        self.like_sender: Optional[LikeSender] = None
        self.streak_engine: Optional[StreakEngine] = None

        self._initialized = False

    async def initialize(self):
        """Initialize all bot subsystems."""
        if self._initialized:
            return

        logger.info("🚀 Initializing Free Fire Like Bot Pro v2.0.0")

        # HTTP client with HTTP/2
        self.http = HTTPClient()
        await self.http.initialize()

        # Proxy rotation
        if self.config.settings.proxies.enabled:
            self.proxy_rotator = ProxyRotator()
            await self.proxy_rotator.load_proxies()

        # AES encryption engine
        self.aes = AESEngine()

        # JWT manager
        self.jwt_manager = JWTManager(self.http, self.aes)
        await self.jwt_manager.initialize()

        # Guest manager
        self.guest_manager = GuestManager()
        await self.guest_manager.initialize()

        # Like sender
        self.like_sender = LikeSender(
            http=self.http,
            aes=self.aes,
            jwt_manager=self.jwt_manager,
            guest_manager=self.guest_manager,
            proxy_rotator=self.proxy_rotator,
        )

        # Streak engine
        self.streak_engine = StreakEngine(self.like_sender)

        # Update stats
        self.stats.guests_total = await self.guest_manager.count_total()
        self.stats.guests_available = await self.guest_manager.count_available()

        self._initialized = True
        logger.info(f"✅ Bot ready | Guests: {self.stats.guests_total} | Region: {self.config.settings.server.target_region}")

    async def send_likes(self, target_uid: str, count: int = None, region: str = None) -> BotStats:
        """
        Execute a like streak.

        Args:
            target_uid: Target player UID
            count: Number of likes (default from config)
            region: Target region (default from config)

        Returns:
            Updated BotStats
        """
        if not self._initialized:
            raise RuntimeError("Bot not initialized. Call initialize() first.")

        count = count or self.config.settings.streak.default_count
        region = region or self.config.settings.server.target_region

        logger.info(f"🎯 Starting like streak: {count} likes → UID {target_uid} (Region: {region})")

        result = await self.streak_engine.execute(
            target_uid=target_uid,
            count=count,
            region=region,
        )

        self.stats.likes_sent += result.success
        self.stats.likes_failed += result.failed

        return self.stats

    async def health_check(self) -> dict:
        """Run system health check."""
        checks = {
            "http_client": self.http is not None and await self.http.health_check(),
            "aes_engine": self.aes is not None,
            "jwt_manager": self.jwt_manager is not None,
            "guest_manager": self.guest_manager is not None,
            "database": await self.guest_manager.health_check() if self.guest_manager else False,
        }
        checks["overall"] = all(checks.values())
        return checks

    async def shutdown(self):
        """Gracefully shutdown all subsystems."""
        logger.info("🛑 Shutting down bot...")

        if self.http:
            await self.http.close()

        if self.guest_manager:
            await self.guest_manager.close()

        if self.jwt_manager:
            await self.jwt_manager.close()

        self._initialized = False
        logger.info("👋 Bot shutdown complete")
