from __future__ import annotations

import json
import base64
import asyncio
import secrets
from copy import deepcopy
from typing import Any, cast
from pathlib import Path

from nonebot.utils import escape_tag
from nonebot.compat import type_validate_python
from nonebot.drivers import Driver, Request, HTTPClientMixin
from typing_extensions import override

from nonebot import get_plugin_config
from nonebot.adapters import Adapter as BaseAdapter

from .bot import Bot
from .log import log
from .event import (
    Event,
    MessageEvent,
    FileMessageEvent,
    TextMessageEvent,
    ImageMessageEvent,
    VideoMessageEvent,
    VoiceMessageEvent,
)
from .media import UploadedFileInfo, upload_file, upload_image, upload_video, get_mime_from_filename
from .model import (
    CDNMedia,
    FileItem,
    TextItem,
    ImageItem,
    VideoItem,
    MessageItem,
    MessageType,
    MessageState,
    TypingStatus,
    GetConfigResp,
    WeixinMessage,
    GetUpdatesResp,
    MessageItemType,
)
from .config import Config
from .message import Message, MessageSegment
from .exception import NetworkError

CHANNEL_VERSION = "0.1.0"
SESSION_EXPIRED_ERRCODE = -14


class Adapter(BaseAdapter):
    @override
    def __init__(self, driver: Driver, **kwargs: Any) -> None:
        super().__init__(driver, **kwargs)
        self.weixin_config: Config = get_plugin_config(Config)
        self.tasks: set[asyncio.Task[None]] = set()
        self._setup()

    @classmethod
    @override
    def get_name(cls) -> str:
        return "Weixin"

    def _setup(self) -> None:
        if not isinstance(self.driver, HTTPClientMixin):
            log(
                "WARNING",
                f"Current driver {self.config.driver} does not support HTTP client connections! "
                "Weixin adapter requires an HTTP client driver.",
            )
            return

        self.driver.on_startup(self._start_polling)
        self.driver.on_shutdown(self._stop)

    async def _start_polling(self) -> None:
        accounts = self._resolve_accounts()
        if not accounts:
            log("WARNING", "No Weixin accounts configured. Set weixin_token and weixin_account_id in config.")
            return

        for account in accounts:
            task = asyncio.create_task(self._poll_loop(account))
            task.add_done_callback(self.tasks.discard)
            self.tasks.add(task)

    def _resolve_accounts(self) -> list[dict[str, Any]]:
        accounts: list[dict[str, Any]] = []

        if self.weixin_config.wechatclaw_accounts:
            for acc in self.weixin_config.wechatclaw_accounts:
                if not acc.enabled or not acc.token:
                    continue
                accounts.append(
                    {
                        "account_id": acc.account_id,
                        "token": acc.token,
                        "base_url": acc.base_url,
                        "cdn_base_url": acc.cdn_base_url,
                    }
                )
        elif self.weixin_config.wechatclaw_token:
            accounts.append(
                {
                    "account_id": self.weixin_config.wechatclaw_account_id,
                    "token": self.weixin_config.wechatclaw_token,
                    "base_url": self.weixin_config.wechatclaw_base_url,
                    "cdn_base_url": self.weixin_config.wechatclaw_cdn_base_url,
                }
            )

        return accounts

    async def _poll_loop(self, account: dict[str, Any]) -> None:
        account_id = account["account_id"]
        base_url = account["base_url"]
        token = account["token"]
        cdn_base_url = account["cdn_base_url"]
        poll_timeout = self.weixin_config.wechatclaw_poll_timeout
        max_failures = self.weixin_config.wechatclaw_max_consecutive_failures
        backoff_delay = self.weixin_config.wechatclaw_backoff_delay
        reconnect_interval = self.weixin_config.wechatclaw_reconnect_interval

        bot = Bot(
            self,
            self_id=account_id or "weixin",
            base_url=base_url,
            token=token,
            cdn_base_url=cdn_base_url,
        )
        self.bot_connect(bot)
        log("INFO", f"<y>Bot {escape_tag(bot.self_id)}</y> connected")

        get_updates_buf = ""
        consecutive_failures = 0
        next_timeout = poll_timeout

        while True:
            try:
                resp = await self._get_updates(
                    base_url=base_url,
                    token=token,
                    get_updates_buf=get_updates_buf,
                    timeout_ms=next_timeout,
                )
                if resp is None:
                    log("DEBUG", "getUpdates returned None, retrying...")
                    await asyncio.sleep(reconnect_interval)
                    continue

                if resp.longpolling_timeout_ms and resp.longpolling_timeout_ms > 0:
                    next_timeout = resp.longpolling_timeout_ms

                is_error = (resp.ret is not None and resp.ret != 0) or (resp.errcode is not None and resp.errcode != 0)

                if is_error:
                    if SESSION_EXPIRED_ERRCODE in (resp.errcode, resp.ret):
                        log(
                            "ERROR",
                            f"<r><bg #f8bbd0>Session expired for {escape_tag(bot.self_id)}, "
                            "waiting before retry...</bg #f8bbd0></r>",
                        )
                        consecutive_failures = 0
                        await asyncio.sleep(60)
                        continue

                    consecutive_failures += 1
                    log(
                        "ERROR",
                        f"<r><bg #f8bbd0>getUpdates failed: ret={resp.ret} errcode={resp.errcode} "
                        f"errmsg={resp.errmsg} ({consecutive_failures}/{max_failures})</bg #f8bbd0></r>",
                    )

                    if consecutive_failures >= max_failures:
                        consecutive_failures = 0
                        await asyncio.sleep(backoff_delay)
                    else:
                        await asyncio.sleep(reconnect_interval)
                    continue

                consecutive_failures = 0

                if resp.get_updates_buf:
                    get_updates_buf = resp.get_updates_buf

                for msg in resp.msgs or []:
                    try:
                        event = self._parse_message(msg, bot.self_id)
                        if event is None:
                            continue

                        if msg.context_token and msg.from_user_id:
                            bot.set_context_token(msg.from_user_id, msg.context_token)

                        task = asyncio.create_task(bot.handle_event(event))
                        task.add_done_callback(self.tasks.discard)
                        self.tasks.add(task)
                    except Exception as e:
                        log(
                            "ERROR",
                            f"<r><bg #f8bbd0>Failed to process message: {escape_tag(str(e))}</bg #f8bbd0></r>",
                        )

            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_failures += 1
                log(
                    "ERROR",
                    f"<r><bg #f8bbd0>getUpdates error ({consecutive_failures}/{max_failures}): "
                    f"{escape_tag(str(e))}</bg #f8bbd0></r>",
                )

                if consecutive_failures >= max_failures:
                    consecutive_failures = 0
                    await asyncio.sleep(backoff_delay)
                else:
                    await asyncio.sleep(reconnect_interval)

        self.bot_disconnect(bot)
        log("INFO", f"<y>Bot {escape_tag(bot.self_id)}</y> disconnected")

    async def _stop(self) -> None:
        for task in self.tasks:
            if not task.done():
                task.cancel()

        await asyncio.gather(
            *(asyncio.wait_for(task, timeout=10) for task in self.tasks),
            return_exceptions=True,
        )

    def _build_base_info(self) -> dict[str, Any]:
        return {"channel_version": CHANNEL_VERSION}

    def _build_headers(self, token: str | None, body: str) -> dict[str, str]:
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "Content-Length": str(len(body.encode("utf-8"))),
            "X-WECHAT-UIN": self._random_wechat_uin(),
        }
        if token and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        return headers

    @staticmethod
    def _random_wechat_uin() -> str:

        raw_bytes = secrets.token_bytes(4)
        uint32 = int.from_bytes(raw_bytes, "big")
        return base64.b64encode(str(uint32).encode("utf-8")).decode("utf-8")

    @staticmethod
    def _ensure_trailing_slash(url: str) -> str:
        return url if url.endswith("/") else f"{url}/"

    async def _api_fetch(
        self,
        *,
        base_url: str,
        endpoint: str,
        body: str,
        token: str | None,
        timeout_ms: int,
    ) -> bytes | str | None:
        if not isinstance(self.driver, HTTPClientMixin):
            raise NetworkError("Driver does not support HTTP client")

        base = self._ensure_trailing_slash(base_url)
        url = f"{base}{endpoint}"
        headers = self._build_headers(token, body)

        request = Request(
            method="POST",
            url=url,
            headers=headers,
            content=body,
            timeout=timeout_ms / 1000.0,
        )

        try:
            response = await self.driver.request(request)
            if response.status_code and response.status_code >= 400:
                raise NetworkError(f"{endpoint} HTTP {response.status_code}: {response.content}")
            return response.content
        except NetworkError:
            raise
        except Exception as e:
            raise NetworkError(f"{endpoint} request failed: {e!r}") from e

    async def _get_updates(
        self,
        *,
        base_url: str,
        token: str,
        get_updates_buf: str,
        timeout_ms: int,
    ) -> GetUpdatesResp | None:
        body = json.dumps(
            {
                "get_updates_buf": get_updates_buf,
                "base_info": self._build_base_info(),
            }
        )

        try:
            raw = await self._api_fetch(
                base_url=base_url,
                endpoint="ilink/bot/getupdates",
                body=body,
                token=token,
                timeout_ms=timeout_ms,
            )
            if raw is None:
                return None
            return type_validate_python(GetUpdatesResp, json.loads(raw))
        except NetworkError:
            log("DEBUG", "getUpdates: timeout or network error, returning empty response")
            return GetUpdatesResp(ret=0, msgs=[], get_updates_buf=get_updates_buf)

    async def _send_message_api(
        self,
        *,
        base_url: str,
        token: str,
        msg: WeixinMessage,
    ) -> None:
        body = json.dumps(
            {
                "msg": msg.model_dump(exclude_none=True),
                "base_info": self._build_base_info(),
            }
        )

        await self._api_fetch(
            base_url=base_url,
            endpoint="ilink/bot/sendmessage",
            body=body,
            token=token,
            timeout_ms=self.weixin_config.wechatclaw_api_timeout,
        )

    async def _send_typing_api(
        self,
        *,
        base_url: str,
        token: str,
        user_id: str,
        typing_ticket: str,
        status: int = TypingStatus.TYPING,
    ) -> None:
        body = json.dumps(
            {
                "ilink_user_id": user_id,
                "typing_ticket": typing_ticket,
                "status": status,
                "base_info": self._build_base_info(),
            }
        )

        await self._api_fetch(
            base_url=base_url,
            endpoint="ilink/bot/sendtyping",
            body=body,
            token=token,
            timeout_ms=10000,
        )

    async def _get_config_api(
        self,
        *,
        base_url: str,
        token: str,
        user_id: str,
        context_token: str | None = None,
    ) -> GetConfigResp:
        body = json.dumps(
            {
                "ilink_user_id": user_id,
                "context_token": context_token or "",
                "base_info": self._build_base_info(),
            }
        )

        raw = await self._api_fetch(
            base_url=base_url,
            endpoint="ilink/bot/getconfig",
            body=body,
            token=token,
            timeout_ms=10000,
        )

        return type_validate_python(GetConfigResp, json.loads(cast("str | bytes", raw)))

    @override
    async def _call_api(self, bot: Bot, api: str, **data: Any) -> Any:
        log("DEBUG", f"Calling API <y>{api}</y>")

        if api == "send_message":
            return await self._handle_send_message(bot, **data)
        if api == "send_typing":
            return await self._handle_send_typing(bot, **data)
        if api == "get_config":
            return await self._handle_get_config(bot, **data)
        if api in ("send_image", "send_video", "send_file", "send_voice", "send_media"):
            return await self._handle_send_media(bot, api, **data)
        raise NetworkError(f"Unknown API: {api}")

    async def _handle_send_message(self, bot: Bot, **data: Any) -> dict[str, Any]:
        to = data.get("to", "")
        text = data.get("text", "")
        context_token = data.get("context_token")

        if not context_token:
            log("WARNING", f"send_message: no context_token for user {to}")

        client_id = f"nonebot-weixin-{secrets.token_hex(8)}"

        item_list: list[MessageItem] | None = None
        if text:
            item_list = [MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text=text))]

        msg = WeixinMessage(
            from_user_id="",
            to_user_id=to,
            client_id=client_id,
            message_type=MessageType.BOT,
            message_state=MessageState.FINISH,
            item_list=item_list,
            context_token=context_token,
        )

        await self._send_message_api(
            base_url=bot.base_url,
            token=bot.token,
            msg=msg,
        )

        return {"message_id": client_id}

    async def _handle_send_typing(self, bot: Bot, **data: Any) -> None:
        await self._send_typing_api(
            base_url=bot.base_url,
            token=bot.token,
            user_id=data["user_id"],
            typing_ticket=data["typing_ticket"],
            status=data.get("status", TypingStatus.TYPING),
        )

    async def _handle_get_config(self, bot: Bot, **data: Any) -> GetConfigResp:
        return await self._get_config_api(
            base_url=bot.base_url,
            token=bot.token,
            user_id=data["user_id"],
            context_token=data.get("context_token"),
        )

    # ------------------------------------------------------------------
    # Media send
    # ------------------------------------------------------------------

    @staticmethod
    def _aeskey_hex_to_base64(hex_key: str) -> str:
        """Convert hex AES key to base64 (matching TS: Buffer.from(key).toString('base64'))."""
        return base64.b64encode(bytes.fromhex(hex_key)).decode("ascii")

    async def _handle_send_media(self, bot: Bot, api: str, **data: Any) -> dict[str, Any]:
        to = data.get("to", "")
        file_path = data.get("file_path", "")
        text = data.get("text", "")
        context_token = data.get("context_token")

        if not file_path:
            raise NetworkError(f"{api}: file_path is required")

        if api == "send_media":
            mime = get_mime_from_filename(file_path)
            if mime.startswith("image/"):
                api = "send_image"
            elif mime.startswith("video/"):
                api = "send_video"
            else:
                api = "send_file"

        base_info = self._build_base_info()

        uploaded: UploadedFileInfo
        if api == "send_image":
            uploaded = await upload_image(
                request_fn=self.request,
                file_path=file_path,
                to_user_id=to,
                base_url=bot.base_url,
                token=bot.token,
                cdn_base_url=bot.cdn_base_url,
                base_info=base_info,
            )
        elif api == "send_video":
            uploaded = await upload_video(
                request_fn=self.request,
                file_path=file_path,
                to_user_id=to,
                base_url=bot.base_url,
                token=bot.token,
                cdn_base_url=bot.cdn_base_url,
                base_info=base_info,
            )
        else:
            # send_file / send_voice
            uploaded = await upload_file(
                request_fn=self.request,
                file_path=file_path,
                to_user_id=to,
                base_url=bot.base_url,
                token=bot.token,
                cdn_base_url=bot.cdn_base_url,
                base_info=base_info,
            )

        aes_key_b64 = self._aeskey_hex_to_base64(uploaded.aeskey_hex)

        media_item = self._build_media_item(
            api=api,
            uploaded=uploaded,
            aes_key_b64=aes_key_b64,
            file_path=file_path,
        )

        items_to_send: list[MessageItem] = []
        if text:
            items_to_send.append(MessageItem(type=MessageItemType.TEXT, text_item=TextItem(text=text)))
        items_to_send.append(media_item)

        last_client_id = ""
        for item in items_to_send:
            last_client_id = f"nonebot-weixin-{secrets.token_hex(8)}"
            msg = WeixinMessage(
                from_user_id="",
                to_user_id=to,
                client_id=last_client_id,
                message_type=MessageType.BOT,
                message_state=MessageState.FINISH,
                item_list=[item],
                context_token=context_token,
            )
            await self._send_message_api(
                base_url=bot.base_url,
                token=bot.token,
                msg=msg,
            )

        return {"message_id": last_client_id}

    @staticmethod
    def _build_media_item(
        *,
        api: str,
        uploaded: UploadedFileInfo,
        aes_key_b64: str,
        file_path: str,
    ) -> MessageItem:
        cdn_media = CDNMedia(
            encrypt_query_param=uploaded.download_encrypted_query_param,
            aes_key=aes_key_b64,
            encrypt_type=1,
        )

        if api == "send_image":
            return MessageItem(
                type=MessageItemType.IMAGE,
                image_item=ImageItem(
                    media=cdn_media,
                    mid_size=uploaded.file_size_ciphertext,
                ),
            )
        if api == "send_video":
            return MessageItem(
                type=MessageItemType.VIDEO,
                video_item=VideoItem(
                    media=cdn_media,
                    video_size=uploaded.file_size_ciphertext,
                ),
            )
        file_name = Path(file_path).name
        return MessageItem(
            type=MessageItemType.FILE,
            file_item=FileItem(
                media=cdn_media,
                file_name=file_name,
                len=str(uploaded.file_size),
            ),
        )

    @classmethod
    def _parse_message(cls, msg: WeixinMessage, self_id: str) -> Event | None:
        if msg.message_type == MessageType.BOT:
            return None

        from_user = msg.from_user_id or ""
        to_user = msg.to_user_id or ""

        if not msg.item_list:
            return None

        segments: list[MessageSegment] = []
        event_cls: type[MessageEvent] = TextMessageEvent
        has_media = False

        for item in msg.item_list:
            if item.type == MessageItemType.TEXT and item.text_item:
                text = item.text_item.text or ""

                if item.ref_msg:
                    ref_title = item.ref_msg.title or ""
                    ref_text = ""
                    if item.ref_msg.message_item and item.ref_msg.message_item.text_item:
                        ref_text = item.ref_msg.message_item.text_item.text or ""
                    ref_parts = [p for p in [ref_title, ref_text] if p]
                    if ref_parts:
                        segments.append(
                            MessageSegment.ref(
                                title=ref_title or None,
                                text=ref_text or None,
                            )
                        )

                if text:
                    segments.append(MessageSegment.text(text))

            elif item.type == MessageItemType.IMAGE and item.image_item:
                has_media = True
                event_cls = ImageMessageEvent
                media_key = None
                aes_key = None
                if item.image_item.media:
                    media_key = item.image_item.media.encrypt_query_param
                    aes_key = item.image_item.media.aes_key
                segments.append(
                    MessageSegment.image(
                        url=item.image_item.url,
                        media_key=media_key,
                        aes_key=aes_key or item.image_item.aeskey,
                    )
                )

            elif item.type == MessageItemType.VOICE and item.voice_item:
                has_media = True
                event_cls = VoiceMessageEvent

                if item.voice_item.text and not has_media:
                    segments.append(MessageSegment.text(item.voice_item.text))
                else:
                    media_key = None
                    aes_key = None
                    if item.voice_item.media:
                        media_key = item.voice_item.media.encrypt_query_param
                        aes_key = item.voice_item.media.aes_key
                    segments.append(
                        MessageSegment.voice(
                            media_key=media_key,
                            aes_key=aes_key,
                            playtime=item.voice_item.playtime,
                            text=item.voice_item.text,
                        )
                    )

            elif item.type == MessageItemType.FILE and item.file_item:
                has_media = True
                event_cls = FileMessageEvent
                media_key = None
                aes_key = None
                if item.file_item.media:
                    media_key = item.file_item.media.encrypt_query_param
                    aes_key = item.file_item.media.aes_key
                segments.append(
                    MessageSegment.file(
                        media_key=media_key,
                        aes_key=aes_key,
                        file_name=item.file_item.file_name,
                        file_size=item.file_item.len,
                    )
                )

            elif item.type == MessageItemType.VIDEO and item.video_item:
                has_media = True
                event_cls = VideoMessageEvent
                media_key = None
                aes_key = None
                if item.video_item.media:
                    media_key = item.video_item.media.encrypt_query_param
                    aes_key = item.video_item.media.aes_key
                segments.append(
                    MessageSegment.video(
                        media_key=media_key,
                        aes_key=aes_key,
                        video_size=item.video_item.video_size,
                        play_length=item.video_item.play_length,
                    )
                )

        if not segments:
            return None

        message = Message(segments)

        return event_cls(
            from_user_id=from_user,
            to_user_id=to_user,
            create_time_ms=msg.create_time_ms,
            session_id=msg.session_id,
            context_token=msg.context_token,
            message_id=msg.message_id,
            seq=msg.seq,
            self_id=self_id,
            message=message,
            original_message=deepcopy(message),
        )

