from nonebot.exception import ActionFailed as BaseActionFailed
from nonebot.exception import NetworkError as BaseNetworkError
from nonebot.exception import ApiNotAvailable as BaseApiNotAvailable
from nonebot.exception import AdapterException


class WeixinAdapterException(AdapterException):
    def __init__(self) -> None:
        super().__init__("Weixin")


class NetworkError(BaseNetworkError, WeixinAdapterException):
    """网络错误。"""

    def __init__(self, msg: str | None = None) -> None:
        super().__init__()
        self.msg: str | None = msg

    def __repr__(self) -> str:
        return f"NetworkError(message={self.msg!r})"


class ActionFailed(BaseActionFailed, WeixinAdapterException):
    """API 请求返回错误信息。"""

    def __init__(self, **kwargs: object) -> None:
        super().__init__()
        self.info = kwargs

    def __repr__(self) -> str:
        return "ActionFailed(" + ", ".join(f"{k}={v!r}" for k, v in self.info.items()) + ")"


class ApiNotAvailable(BaseApiNotAvailable, WeixinAdapterException):
    def __init__(self, msg: str | None = None) -> None:
        super().__init__()
        self.msg: str | None = msg


class SessionExpired(WeixinAdapterException):
    """Session expired, need re-login."""

    def __init__(self, msg: str | None = None) -> None:
        super().__init__()
        self.msg: str | None = msg

    def __repr__(self) -> str:
        return f"SessionExpired(message={self.msg!r})"
