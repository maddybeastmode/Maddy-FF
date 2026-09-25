"""
Proxy Rotator
Manages a pool of proxies with health checks and rotation strategies.
"""

import random
import asyncio
from typing import List, Optional
from dataclasses import dataclass

import httpx

from ..core.config_loader import get_config
from ..core.logger import setup_logger

logger = setup_logger("proxy")


@dataclass
class Proxy:
    url: str
    failures: int = 0
    last_used: float = 0
    healthy: bool = True


class ProxyRotator:
    """
    Rotates through proxy pool with health monitoring.
    Strategies: round_robin, random, least_used
    """

    def __init__(self):
        self.config = get_config()
        self.proxies: List[Proxy] = []
        self._current_index = 0
        self._strategy = self.config.settings.proxies.rotation_strategy

    async def load_proxies(self):
        """Load proxies from file."""
        proxy_file = self.config.settings.proxies.proxy_file
        try:
            with open(proxy_file, "r") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        self.proxies.append(Proxy(url=line))

            logger.info(f"Loaded {len(self.proxies)} proxies")

            # Health check
            await self._health_check_all()
        except FileNotFoundError:
            logger.warning(f"Proxy file not found: {proxy_file}")

    async def _health_check_all(self):
        """Test all proxies."""
        test_url = self.config.settings.proxies.test_url
        timeout = self.config.settings.proxies.test_timeout

        async def test_proxy(proxy: Proxy):
            try:
                async with httpx.AsyncClient(proxy=proxy.url, timeout=timeout) as client:
                    resp = await client.get(test_url)
                    proxy.healthy = resp.status_code == 200
            except Exception:
                proxy.healthy = False
                proxy.failures += 1

        await asyncio.gather(*[test_proxy(p) for p in self.proxies])
        healthy_count = sum(1 for p in self.proxies if p.healthy)
        logger.info(f"Proxy health check: {healthy_count}/{len(self.proxies)} healthy")

    def get_next(self) -> Optional[str]:
        """Get next proxy URL based on rotation strategy."""
        healthy = [p for p in self.proxies if p.healthy]
        if not healthy:
            return None

        if self._strategy == "round_robin":
            proxy = healthy[self._current_index % len(healthy)]
            self._current_index += 1
        elif self._strategy == "random":
            proxy = random.choice(healthy)
        elif self._strategy == "least_used":
            proxy = min(healthy, key=lambda p: p.last_used)
        else:
            proxy = healthy[0]

        proxy.last_used = asyncio.get_event_loop().time()
        return proxy.url

    def mark_failed(self, proxy_url: str):
        """Mark a proxy as failed."""
        for p in self.proxies:
            if p.url == proxy_url:
                p.failures += 1
                if p.failures >= 3:
                    p.healthy = False
                    logger.warning(f"Proxy disabled after 3 failures: {proxy_url}")
                break
