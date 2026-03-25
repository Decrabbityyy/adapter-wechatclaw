from __future__ import annotations

from nonebot.utils import escape_tag
from nonebot.compat import model_dump
from typing_extensions import override

from nonebot.adapters import Event as BaseEvent

from .message import Message  # noqa: TC001


class Event(BaseEvent):
    from_user_id: str = ""
    to_user_id: str = ""
    create_time_ms: int | None = None
    session_id: str | None = None
    context_token: str | None = None
    message_id: int | None = None
    seq: int | None = None
    self_id: str = ""

    @override
    def get_type(self) -> str:
        return ""

    @override
    def get_event_name(self) -> str:
        return "weixin"

    @override
    def get_event_description(self) -> str:
        return escape_tag(repr(model_dump(self)))

    @override
    def get_message(self) -> Message:
        raise ValueError("Event has no message!")

    @override
    def get_user_id(self) -> str:
        return self.from_user_id

    @override
    def get_session_id(self) -> str:
        return self.from_user_id

    @override
    def is_tome(self) -> bool:
        return True


class MessageEvent(Event):
    message: Message
    original_message: Message
    to_me: bool = True

    @override
    def get_type(self) -> str:
        return "message"

    @override
    def get_event_name(self) -> str:
        return "message.private"

    @override
    def get_event_description(self) -> str:
        return escape_tag(f"Message from {self.from_user_id}: {''.join(str(seg) for seg in self.message)}")

    @override
    def get_message(self) -> Message:
        return self.message

    @override
    def get_user_id(self) -> str:
        return self.from_user_id

    @override
    def get_session_id(self) -> str:
        return self.from_user_id

    @override
    def is_tome(self) -> bool:
        return self.to_me


class TextMessageEvent(MessageEvent):
    @override
    def get_event_name(self) -> str:
        return "message.private.text"


class ImageMessageEvent(MessageEvent):
    @override
    def get_event_name(self) -> str:
        return "message.private.image"


class VoiceMessageEvent(MessageEvent):
    @override
    def get_event_name(self) -> str:
        return "message.private.voice"


class FileMessageEvent(MessageEvent):
    @override
    def get_event_name(self) -> str:
        return "message.private.file"


class VideoMessageEvent(MessageEvent):
    @override
    def get_event_name(self) -> str:
        return "message.private.video"
