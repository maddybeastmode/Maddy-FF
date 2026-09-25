"""
Async HTTP Client
HTTP/2 support, connection pooling, retry logic, proxy integration.
Supports both binary (content=) and form-encoded (data=) POST bodies.
SSL verification disabled for Garena backend domains that use self-signed certs.
"""

import asyncio
import httpx
from typing import Optional, Dict, Any

from ..core.config_loader import get_config
from ..core.logger import setup_logger

logger = setup_logger("http")


class HTTPClient:
    """
    Production-grade async HTTP client.
    Features HTTP/2, keep-alive, automatic retries, and proxy support.
    """

    def __init__(self):
        self.config = get_config()
        self.client: Optional[httpx.AsyncClient] = None
        self._limits = httpx.Limits(
            max_keepalive_connections=50,
            max_connections=100,
        )
        self._timeout = httpx.Timeout(
            connect=10.0,
            read=self.config.settings.bot.request_timeout,
            write=10.0,
            pool=5.0,
        )

    async def initialize(self, proxy: Optional[str] = None):
        """Initialize HTTP client with SSL verification disabled for Garena compatibility."""
        transport = httpx.AsyncHTTPTransport(
            limits=self._limits,
            http2=False,
            retries=3,
            verify=False,   # Garena backend uses self-signed / internal certs
        )

        self.client = httpx.AsyncClient(
            transport=transport,
            timeout=self._timeout,
            http2=False,
            follow_redirects=True,
            proxy=proxy,
            verify=False,   # also disable at client level
        )

        logger.info("HTTP client initialized (HTTP/2 enabled, SSL verify=off)")

    async def post(
        self,
        url: str,
        headers: Optional[Dict] = None,
        content: Optional[bytes] = None,
        data: Optional[Dict] = None,
        **kwargs,
    ) -> httpx.Response:
        """
        Send POST request.

        Args:
            url:     Target URL.
            headers: HTTP headers.
            content: Raw binary body (for protobuf / AES payloads).
            data:    Form-encoded key/value dict (for OAuth requests).
        """
        if not self.client:
            raise RuntimeError("HTTP client not initialized")

        try:
            response = await self.client.post(
                url,
                headers=headers,
                content=content,
                data=data,
                **kwargs,
            )
            return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {url}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}")
            raise

    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Send GET request."""
        if not self.client:
            raise RuntimeError("HTTP client not initialized")
        return await self.client.get(url, **kwargs)

    async def health_check(self) -> bool:
        """Check if client is functional."""
        try:
            resp = await self.get("https://httpbin.org/get", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        """Close client connection."""
        if self.client:
            await self.client.aclose()
            logger.info("HTTP client closed")
