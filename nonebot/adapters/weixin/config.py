from pydantic import Field, BaseModel


class Config(BaseModel):
    """WeChat adapter configuration."""

    weixin_token: str = ""
    """Bot token obtained from QR code login."""

    weixin_base_url: str = "https://ilinkai.weixin.qq.com"
    """Base URL for the WeChat iLink API."""

    weixin_cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    """Base URL for CDN media downloads."""

    weixin_poll_timeout: int = 35000
    """Long-poll timeout in milliseconds for getUpdates."""

    weixin_api_timeout: int = 15000
    """Timeout in milliseconds for regular API requests."""

    weixin_reconnect_interval: float = 3.0
    """Reconnect interval in seconds after connection failure."""

    weixin_max_consecutive_failures: int = 3
    """Max consecutive getUpdates failures before backoff."""

    weixin_backoff_delay: float = 30.0
    """Backoff delay in seconds after max consecutive failures."""

    weixin_account_id: str = ""
    """Account ID (ilink_bot_id), obtained from QR login. If empty, will be set after login."""

    weixin_accounts: list["WeixinAccountConfig"] = Field(default_factory=list)
    """Multiple account configurations for multi-bot deployment."""


class WeixinAccountConfig(BaseModel):
    """Per-account configuration for multi-bot deployment."""

    account_id: str = ""
    """Account ID (ilink_bot_id)."""

    token: str = ""
    """Bot token."""

    base_url: str = "https://ilinkai.weixin.qq.com"
    """Base URL for the WeChat iLink API."""

    cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    """Base URL for CDN media downloads."""

    enabled: bool = True
    """Whether this account is enabled."""
