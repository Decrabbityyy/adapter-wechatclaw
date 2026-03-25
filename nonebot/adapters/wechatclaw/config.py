from pydantic import Field, BaseModel


class Config(BaseModel):
    """WeChat adapter configuration."""

    wechatclaw_token: str = ""
    """Bot token obtained from QR code login."""

    wechatclaw_base_url: str = "https://ilinkai.weixin.qq.com"
    """Base URL for the WeChat iLink API."""

    wechatclaw_cdn_base_url: str = "https://novac2c.cdn.weixin.qq.com/c2c"
    """Base URL for CDN media downloads."""

    wechatclaw_poll_timeout: int = 35000
    """Long-poll timeout in milliseconds for getUpdates."""

    wechatclaw_api_timeout: int = 15000
    """Timeout in milliseconds for regular API requests."""

    wechatclaw_reconnect_interval: float = 3.0
    """Reconnect interval in seconds after connection failure."""

    wechatclaw_max_consecutive_failures: int = 3
    """Max consecutive getUpdates failures before backoff."""

    wechatclaw_backoff_delay: float = 30.0
    """Backoff delay in seconds after max consecutive failures."""

    wechatclaw_account_id: str = ""
    """Account ID (ilink_bot_id), obtained from QR login. If empty, will be set after login."""

    wechatclaw_accounts: list["WeixinAccountConfig"] = Field(default_factory=list)
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
