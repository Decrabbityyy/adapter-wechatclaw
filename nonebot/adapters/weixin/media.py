from __future__ import annotations

import json
import hashlib
import secrets
from typing import TYPE_CHECKING
from pathlib import Path
from urllib.parse import quote

from nonebot.drivers import Request

from .log import log
from .model import UploadMediaType
from .crypto import encrypt_aes_ecb, aes_ecb_padded_size

if TYPE_CHECKING:
    from collections.abc import Callable, Awaitable

    from nonebot.drivers import Response

    RequestFn = Callable[[Request], Awaitable[Response]]

EXTENSION_TO_MIME: dict[str, str] = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
    ".csv": "text/csv",
    ".zip": "application/zip",
    ".tar": "application/x-tar",
    ".gz": "application/gzip",
    ".mp3": "audio/mpeg",
    ".ogg": "audio/ogg",
    ".wav": "audio/wav",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

UPLOAD_MAX_RETRIES = 3


def get_mime_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return EXTENSION_TO_MIME.get(ext, "application/octet-stream")


def build_cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    return f"{cdn_base_url}/upload?encrypted_query_param={quote(upload_param)}&filekey={quote(filekey)}"


class UploadedFileInfo:
    __slots__ = ("aeskey_hex", "download_encrypted_query_param", "file_size", "file_size_ciphertext", "filekey")

    def __init__(
        self,
        filekey: str,
        download_encrypted_query_param: str,
        aeskey_hex: str,
        file_size: int,
        file_size_ciphertext: int,
    ) -> None:
        self.filekey = filekey
        self.download_encrypted_query_param = download_encrypted_query_param
        self.aeskey_hex = aeskey_hex
        self.file_size = file_size
        self.file_size_ciphertext = file_size_ciphertext


async def upload_buffer_to_cdn(
    *,
    request_fn: RequestFn,
    buf: bytes,
    upload_param: str,
    filekey: str,
    cdn_base_url: str,
    aeskey: bytes,
) -> str:
    ciphertext = encrypt_aes_ecb(buf, aeskey)
    cdn_url = build_cdn_upload_url(cdn_base_url, upload_param, filekey)

    download_param: str | None = None
    last_error: Exception | None = None

    for attempt in range(1, UPLOAD_MAX_RETRIES + 1):
        try:
            req = Request(
                method="POST",
                url=cdn_url,
                content=ciphertext,
                headers={"Content-Type": "application/octet-stream"},
                timeout=60.0,
            )
            resp = await request_fn(req)
            status = resp.status_code or 0
            resp_text = str(resp.content or "")
            resp_headers = resp.headers or {}
            if 400 <= status < 500:
                err_msg = resp_headers.get("x-error-message", resp_text)
                raise RuntimeError(f"CDN upload client error {status}: {err_msg}")
            if status != 200:
                err_msg = resp_headers.get("x-error-message", f"status {status}")
                raise RuntimeError(f"CDN upload server error: {err_msg}")

            download_param = resp_headers.get("x-encrypted-param")
            if not download_param:
                raise RuntimeError("CDN upload response missing x-encrypted-param header")
            break
        except Exception as e:
            last_error = e if isinstance(e, Exception) else RuntimeError(str(e))
            if isinstance(e, RuntimeError) and "client error" in str(e):
                raise
            if attempt < UPLOAD_MAX_RETRIES:
                log("WARNING", f"CDN upload attempt {attempt} failed: {e!r}, retrying...")
            else:
                log("ERROR", f"CDN upload all {UPLOAD_MAX_RETRIES} attempts failed: {e!r}")

    if download_param is None:
        raise last_error or RuntimeError(f"CDN upload failed after {UPLOAD_MAX_RETRIES} attempts")
    return download_param


async def get_upload_url(
    *,
    request_fn: RequestFn,
    base_url: str,
    token: str,
    filekey: str,
    media_type: int,
    to_user_id: str,
    rawsize: int,
    rawfilemd5: str,
    filesize: int,
    aeskey_hex: str,
    base_info: dict[str, str],
) -> str:
    body = json.dumps(
        {
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey_hex,
            "base_info": base_info,
        }
    )

    url = f"{base_url.rstrip('/')}/ilink/bot/getuploadurl"
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = Request(method="POST", url=url, content=body, headers=headers, timeout=15.0)
    resp = await request_fn(req)
    status = resp.status_code or 0
    resp_text = str(resp.content or "")
    if status >= 400:
        raise RuntimeError(f"getUploadUrl HTTP {status}: {resp_text}")
    data = json.loads(resp.content or "{}")
    upload_param = data.get("upload_param")
    if not upload_param:
        raise RuntimeError(f"getUploadUrl returned no upload_param: {data}")
    return upload_param


async def upload_media_to_cdn(
    *,
    request_fn: RequestFn,
    file_path: str,
    to_user_id: str,
    base_url: str,
    token: str,
    cdn_base_url: str,
    media_type: int,
    base_info: dict[str, str],
) -> UploadedFileInfo:
    plaintext = Path(file_path).read_bytes()
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    filesize = aes_ecb_padded_size(rawsize)
    filekey = secrets.token_hex(16)
    aeskey = secrets.token_bytes(16)

    upload_param = await get_upload_url(
        request_fn=request_fn,
        base_url=base_url,
        token=token,
        filekey=filekey,
        media_type=media_type,
        to_user_id=to_user_id,
        rawsize=rawsize,
        rawfilemd5=rawfilemd5,
        filesize=filesize,
        aeskey_hex=aeskey.hex(),
        base_info=base_info,
    )

    download_param = await upload_buffer_to_cdn(
        request_fn=request_fn,
        buf=plaintext,
        upload_param=upload_param,
        filekey=filekey,
        cdn_base_url=cdn_base_url,
        aeskey=aeskey,
    )

    return UploadedFileInfo(
        filekey=filekey,
        download_encrypted_query_param=download_param,
        aeskey_hex=aeskey.hex(),
        file_size=rawsize,
        file_size_ciphertext=filesize,
    )


async def upload_image(
    *,
    request_fn: RequestFn,
    file_path: str,
    to_user_id: str,
    base_url: str,
    token: str,
    cdn_base_url: str,
    base_info: dict[str, str],
) -> UploadedFileInfo:
    return await upload_media_to_cdn(
        request_fn=request_fn,
        file_path=file_path,
        to_user_id=to_user_id,
        base_url=base_url,
        token=token,
        cdn_base_url=cdn_base_url,
        media_type=UploadMediaType.IMAGE,
        base_info=base_info,
    )


async def upload_video(
    *,
    request_fn: RequestFn,
    file_path: str,
    to_user_id: str,
    base_url: str,
    token: str,
    cdn_base_url: str,
    base_info: dict[str, str],
) -> UploadedFileInfo:
    return await upload_media_to_cdn(
        request_fn=request_fn,
        file_path=file_path,
        to_user_id=to_user_id,
        base_url=base_url,
        token=token,
        cdn_base_url=cdn_base_url,
        media_type=UploadMediaType.VIDEO,
        base_info=base_info,
    )


async def upload_file(
    *,
    request_fn: RequestFn,
    file_path: str,
    to_user_id: str,
    base_url: str,
    token: str,
    cdn_base_url: str,
    base_info: dict[str, str],
) -> UploadedFileInfo:
    return await upload_media_to_cdn(
        request_fn=request_fn,
        file_path=file_path,
        to_user_id=to_user_id,
        base_url=base_url,
        token=token,
        cdn_base_url=cdn_base_url,
        media_type=UploadMediaType.FILE,
        base_info=base_info,
    )
