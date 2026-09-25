"""
Configuration Loader
Loads and validates YAML configuration with Pydantic models.
"""

import os
from pathlib import Path
from typing import Optional, List

import yaml
from pydantic import BaseModel, Field, ConfigDict
from pydantic_settings import BaseSettings


class BotConfig(BaseModel):
    name: str = "FF-LikeBot-Pro"
    version: str = "2.0.0"
    debug: bool = False
    max_workers: int = 20
    request_timeout: int = 45


class ServerConfig(BaseModel):
    target_region: str = "ME"
    region_name: str = "MENA"
    game_version: str = "OB54"
    client_version: str = "1.104.1"
    user_agent: str = "FreeFireMobile/1.104.1 (Android 13; SM-G998B)"


class EncryptionConfig(BaseModel):
    main_key: str = "Yg&tc%DEuh6%Zc^8"
    main_iv: str = "6oyZDr22E3ychjM%"
    key_rotation: bool = True
    fallback_keys: List[dict] = Field(default_factory=list)


class RateLimitConfig(BaseModel):
    requests_per_second: float = 8.0
    burst_size: int = 15
    guest_cooldown_seconds: int = 3
    target_daily_limit: int = 500
    global_daily_limit: int = 50000


class StreakConfig(BaseModel):
    default_count: int = 100
    max_streak: int = 1000
    delay_between_likes_ms: int = 500
    jitter_percent: int = 30


class ProxyConfig(BaseModel):
    enabled: bool = False
    rotation_strategy: str = "round_robin"
    proxy_file: str = "config/proxies.txt"
    test_url: str = "https://httpbin.org/ip"
    test_timeout: int = 10


class GuestConfig(BaseModel):
    db_path: str = "data/guests.db"
    batch_size: int = 100
    health_check_interval: int = 3600
    auto_remove_dead: bool = True
    max_age_days: int = 30


class JWTConfig(BaseModel):
    cache_enabled: bool = True
    cache_db: str = "data/jwt_cache.db"
    ttl_hours: int = 20
    refresh_before_expiry_minutes: int = 60


class LoggingConfig(BaseModel):
    level: str = "INFO"
    file: str = "data/bot.log"
    max_size_mb: int = 50
    backup_count: int = 5
    format: str = "%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s"


class DashboardConfig(BaseModel):
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8080
    auth_token: str = "change-me"


class Settings(BaseSettings):
    bot: BotConfig = Field(default_factory=BotConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    encryption: EncryptionConfig = Field(default_factory=EncryptionConfig)
    rate_limiting: RateLimitConfig = Field(default_factory=RateLimitConfig)
    streak: StreakConfig = Field(default_factory=StreakConfig)
    proxies: ProxyConfig = Field(default_factory=ProxyConfig)
    guests: GuestConfig = Field(default_factory=GuestConfig)
    jwt: JWTConfig = Field(default_factory=JWTConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)

    model_config = ConfigDict(env_prefix="FFBOT_", case_sensitive=False)


class RegionInfo(BaseModel):
    name: str
    oauth_url: str
    api_base: str
    cdn_base: str
    auth_region: str
    timezone: str


class RegionsConfig(BaseModel):
    regions: dict[str, RegionInfo]


class ConfigLoader:
    """Loads and manages bot configuration."""

    def __init__(self, config_dir: str = "config"):
        self.config_dir = Path(config_dir)
        self.settings: Optional[Settings] = None
        self.regions: Optional[RegionsConfig] = None
        self._load()

    def _load(self):
        """Load settings and regions configuration."""
        # Try local override first
        settings_file = self.config_dir / "settings.local.yaml"
        if not settings_file.exists():
            settings_file = self.config_dir / "settings.yaml"

        with open(settings_file, "r") as f:
            settings_data = yaml.safe_load(f)

        self.settings = Settings(**settings_data)

        # Load regions
        regions_file = self.config_dir / "regions.yaml"
        with open(regions_file, "r") as f:
            regions_data = yaml.safe_load(f)

        self.regions = RegionsConfig(**regions_data)

    def get_region(self, code: str) -> Optional[RegionInfo]:
        """Get region info by code."""
        if self.regions and code in self.regions.regions:
            return self.regions.regions[code]
        return None

    def get_encryption_keys(self) -> List[tuple]:
        """Get all encryption keys as (key, iv) tuples."""
        keys = [(self.settings.encryption.main_key, self.settings.encryption.main_iv)]
        for fk in self.settings.encryption.fallback_keys:
            keys.append((fk.get("key"), fk.get("iv")))
        return keys


# Global config instance
_config: Optional[ConfigLoader] = None


def get_config() -> ConfigLoader:
    """Get or create global config loader."""
    global _config
    if _config is None:
        _config = ConfigLoader()
    return _config
