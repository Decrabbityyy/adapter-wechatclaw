"""Pydantic models mirroring the openclaw-weixin protocol types.

References: openclaw-weixin/src/api/types.ts
"""

from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Enums as int constants (matching proto values)
# ---------------------------------------------------------------------------


class UploadMediaType:
    IMAGE = 1
    VIDEO = 2
    FILE = 3
    VOICE = 4


class MessageType:
    NONE = 0
    USER = 1
    BOT = 2


class MessageItemType:
    NONE = 0
    TEXT = 1
    IMAGE = 2
    VOICE = 3
    FILE = 4
    VIDEO = 5


class MessageState:
    NEW = 0
    GENERATING = 1
    FINISH = 2


class TypingStatus:
    TYPING = 1
    CANCEL = 2


# ---------------------------------------------------------------------------
# Common request metadata
# ---------------------------------------------------------------------------


class BaseInfo(BaseModel):
    channel_version: str | None = None


# ---------------------------------------------------------------------------
# Message content items
# ---------------------------------------------------------------------------


class TextItem(BaseModel):
    text: str | None = None


class CDNMedia(BaseModel):
    encrypt_query_param: str | None = None
    aes_key: str | None = None
    encrypt_type: int | None = None


class ImageItem(BaseModel):
    media: CDNMedia | None = None
    thumb_media: CDNMedia | None = None
    aeskey: str | None = None
    url: str | None = None
    mid_size: int | None = None
    thumb_size: int | None = None
    thumb_height: int | None = None
    thumb_width: int | None = None
    hd_size: int | None = None


class VoiceItem(BaseModel):
    media: CDNMedia | None = None
    encode_type: int | None = None
    bits_per_sample: int | None = None
    sample_rate: int | None = None
    playtime: int | None = None
    text: str | None = None


class FileItem(BaseModel):
    media: CDNMedia | None = None
    file_name: str | None = None
    md5: str | None = None
    len: str | None = None


class VideoItem(BaseModel):
    media: CDNMedia | None = None
    video_size: int | None = None
    play_length: int | None = None
    video_md5: str | None = None
    thumb_media: CDNMedia | None = None
    thumb_size: int | None = None
    thumb_height: int | None = None
    thumb_width: int | None = None


class RefMessage(BaseModel):
    message_item: MessageItem | None = None
    title: str | None = None


class MessageItem(BaseModel):
    type: int | None = None
    create_time_ms: int | None = None
    update_time_ms: int | None = None
    is_completed: bool | None = None
    msg_id: str | None = None
    ref_msg: RefMessage | None = None
    text_item: TextItem | None = None
    image_item: ImageItem | None = None
    voice_item: VoiceItem | None = None
    file_item: FileItem | None = None
    video_item: VideoItem | None = None


# Rebuild RefMessage to resolve forward reference
RefMessage.model_rebuild()


# ---------------------------------------------------------------------------
# WeixinMessage — the unified message type from getUpdates
# ---------------------------------------------------------------------------


class WeixinMessage(BaseModel):
    seq: int | None = None
    message_id: int | None = None
    from_user_id: str | None = None
    to_user_id: str | None = None
    client_id: str | None = None
    create_time_ms: int | None = None
    update_time_ms: int | None = None
    delete_time_ms: int | None = None
    session_id: str | None = None
    group_id: str | None = None
    message_type: int | None = None
    message_state: int | None = None
    item_list: list[MessageItem] | None = None
    context_token: str | None = None


# ---------------------------------------------------------------------------
# API request / response models
# ---------------------------------------------------------------------------


class GetUpdatesReq(BaseModel):
    get_updates_buf: str = ""
    base_info: BaseInfo | None = None


class GetUpdatesResp(BaseModel):
    ret: int | None = None
    errcode: int | None = None
    errmsg: str | None = None
    msgs: list[WeixinMessage] | None = None
    get_updates_buf: str | None = None
    longpolling_timeout_ms: int | None = None


class SendMessageReq(BaseModel):
    msg: WeixinMessage | None = None
    base_info: BaseInfo | None = None


class SendTypingReq(BaseModel):
    ilink_user_id: str | None = None
    typing_ticket: str | None = None
    status: int | None = None
    base_info: BaseInfo | None = None


class SendTypingResp(BaseModel):
    ret: int | None = None
    errmsg: str | None = None


class GetConfigResp(BaseModel):
    ret: int | None = None
    errmsg: str | None = None
    typing_ticket: str | None = None


class GetUploadUrlReq(BaseModel):
    filekey: str | None = None
    media_type: int | None = None
    to_user_id: str | None = None
    rawsize: int | None = None
    rawfilemd5: str | None = None
    filesize: int | None = None
    thumb_rawsize: int | None = None
    thumb_rawfilemd5: str | None = None
    thumb_filesize: int | None = None
    no_need_thumb: bool | None = None
    aeskey: str | None = None
    base_info: BaseInfo | None = None


class GetUploadUrlResp(BaseModel):
    upload_param: str | None = None
    thumb_upload_param: str | None = None
