from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from nonebot.adapters import Message as BaseMessage
from nonebot.adapters import MessageSegment as BaseMessageSegment

if TYPE_CHECKING:
    from collections.abc import Iterable


class MessageSegment(BaseMessageSegment["Message"]):
    @classmethod
    @override
    def get_message_class(cls) -> type["Message"]:
        return Message

    @override
    def __str__(self) -> str:
        if self.is_text():
            return self.data.get("text", "")
        shown_data = {k: v for k, v in self.data.items() if not k.startswith("_")}
        return f"[{self.type}: {shown_data}]"

    @override
    def is_text(self) -> bool:
        return self.type == "text"

    @staticmethod
    def text(content: str) -> "MessageSegment":
        return MessageSegment("text", {"text": content})

    @staticmethod
    def image(
        *,
        url: str | None = None,
        media_key: str | None = None,
        aes_key: str | None = None,
    ) -> "MessageSegment":
        return MessageSegment("image", {"url": url, "media_key": media_key, "aes_key": aes_key})

    @staticmethod
    def voice(
        *,
        media_key: str | None = None,
        aes_key: str | None = None,
        playtime: int | None = None,
        text: str | None = None,
    ) -> "MessageSegment":
        return MessageSegment(
            "voice",
            {
                "media_key": media_key,
                "aes_key": aes_key,
                "playtime": playtime,
                "text": text,
            },
        )

    @staticmethod
    def file(
        *,
        media_key: str | None = None,
        aes_key: str | None = None,
        file_name: str | None = None,
        file_size: str | None = None,
    ) -> "MessageSegment":
        return MessageSegment(
            "file",
            {
                "media_key": media_key,
                "aes_key": aes_key,
                "file_name": file_name,
                "file_size": file_size,
            },
        )

    @staticmethod
    def video(
        *,
        media_key: str | None = None,
        aes_key: str | None = None,
        video_size: int | None = None,
        play_length: int | None = None,
    ) -> "MessageSegment":
        return MessageSegment(
            "video",
            {
                "media_key": media_key,
                "aes_key": aes_key,
                "video_size": video_size,
                "play_length": play_length,
            },
        )

    @staticmethod
    def ref(title: str | None = None, text: str | None = None) -> "MessageSegment":
        return MessageSegment("ref", {"title": title, "text": text})


class Message(BaseMessage[MessageSegment]):
    @classmethod
    @override
    def get_segment_class(cls) -> type[MessageSegment]:
        return MessageSegment

    @staticmethod
    @override
    def _construct(msg: str) -> Iterable[MessageSegment]:
        yield MessageSegment.text(msg)

    def extract_plain_text(self) -> str:
        return "".join(seg.data.get("text", "") for seg in self if seg.is_text())
