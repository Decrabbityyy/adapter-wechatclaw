from __future__ import annotations

from typing import TYPE_CHECKING, Any

from nonebot.message import handle_event
from typing_extensions import override

from nonebot.adapters import Bot as BaseBot

from .utils import download_and_decrypt_media, download_image_from_segment
from .message import Message, MessageSegment

if TYPE_CHECKING:
    from pathlib import Path

    from .event import Event
    from .model import GetConfigResp
    from .adapter import Adapter


class Bot(BaseBot):
    adapter: "Adapter"

    @override
    def __init__(
        self,
        adapter: "Adapter",
        self_id: str,
        *,
        base_url: str = "",
        token: str = "",
        cdn_base_url: str = "",
    ) -> None:
        super().__init__(adapter, self_id)
        self.base_url = base_url
        self.token = token
        self.cdn_base_url = cdn_base_url
        self._context_tokens: dict[str, str] = {}

    def set_context_token(self, user_id: str, token: str) -> None:
        self._context_tokens[user_id] = token

    def get_context_token(self, user_id: str) -> str | None:
        return self._context_tokens.get(user_id)

    async def handle_event(self, event: Event) -> None:
        await handle_event(self, event)

    @override
    async def send(
        self,
        event: Event,
        message: str | Message | MessageSegment,
        **kwargs: Any,
    ) -> Any:
        if isinstance(message, str):
            message = Message(message)
        elif isinstance(message, MessageSegment):
            message = Message([message])

        to_user_id = event.from_user_id
        context_token = self.get_context_token(to_user_id)

        text_parts: list[str] = []
        media_segs: list[MessageSegment] = []

        for seg in message:
            if seg.is_text():
                text_parts.append(seg.data.get("text", ""))
            elif seg.type in ("image", "video", "file", "voice"):
                media_segs.append(seg)

        text = "".join(text_parts)

        if media_segs:
            seg = media_segs[0]
            file_path = seg.data.get("file_path", "")
            if not file_path:
                file_path = seg.data.get("url", "")

            if file_path and seg.type == "image":
                return await self.send_image(to=to_user_id, file_path=file_path, text=text, context_token=context_token)
            if file_path and seg.type == "video":
                return await self.send_video(to=to_user_id, file_path=file_path, text=text, context_token=context_token)
            if file_path and seg.type == "file":
                return await self.send_file(to=to_user_id, file_path=file_path, text=text, context_token=context_token)
            if file_path and seg.type == "voice":
                return await self.send_voice(to=to_user_id, file_path=file_path, text=text, context_token=context_token)

        if not text and not message:
            return None

        return await self.send_text_message(to=to_user_id, text=text, context_token=context_token)

    async def send_text_message(
        self,
        *,
        to: str,
        text: str,
        context_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.call_api(
            "send_message",
            to=to,
            text=text,
            context_token=context_token,
        )

    async def send_image(
        self,
        *,
        to: str,
        file_path: str,
        text: str = "",
        context_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.call_api(
            "send_image",
            to=to,
            file_path=file_path,
            text=text,
            context_token=context_token,
        )

    async def send_video(
        self,
        *,
        to: str,
        file_path: str,
        text: str = "",
        context_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.call_api(
            "send_video",
            to=to,
            file_path=file_path,
            text=text,
            context_token=context_token,
        )

    async def send_file(
        self,
        *,
        to: str,
        file_path: str,
        text: str = "",
        context_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.call_api(
            "send_file",
            to=to,
            file_path=file_path,
            text=text,
            context_token=context_token,
        )

    async def send_voice(
        self,
        *,
        to: str,
        file_path: str,
        text: str = "",
        context_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.call_api(
            "send_voice",
            to=to,
            file_path=file_path,
            text=text,
            context_token=context_token,
        )

    async def send_media(
        self,
        *,
        to: str,
        file_path: str,
        text: str = "",
        context_token: str | None = None,
    ) -> dict[str, Any]:
        return await self.call_api(
            "send_media",
            to=to,
            file_path=file_path,
            text=text,
            context_token=context_token,
        )

    async def send_typing(
        self,
        *,
        user_id: str,
        typing_ticket: str,
        status: int = 1,
    ) -> None:
        await self.call_api(
            "send_typing",
            user_id=user_id,
            typing_ticket=typing_ticket,
            status=status,
        )

    async def get_config(
        self,
        *,
        user_id: str,
        context_token: str | None = None,
    ) -> GetConfigResp:
        return await self.call_api(
            "get_config",
            user_id=user_id,
            context_token=context_token,
        )

    async def download_media(
        self,
        *,
        media_key: str,
        aes_key: str,
        cdn_base_url: str | None = None,
        timeout: float = 30.0,
    ) -> bytes:
        return await download_and_decrypt_media(
            request_fn=self.adapter.request,
            media_key=media_key,
            aes_key=aes_key,
            cdn_base_url=cdn_base_url or self.cdn_base_url,
            timeout=timeout,
        )

    async def download_image(
        self,
        segment: MessageSegment,
        *,
        cdn_base_url: str | None = None,
        save_dir: str | Path | None = None,
        file_name: str | None = None,
        timeout: float = 30.0,
    ) -> bytes | Path:
        return await download_image_from_segment(
            segment,
            request_fn=self.adapter.request,
            cdn_base_url=cdn_base_url or self.cdn_base_url,
            save_dir=save_dir,
            file_name=file_name,
            timeout=timeout,
        )
