from __future__ import annotations

from typing import TYPE_CHECKING, cast
from pathlib import Path
from urllib.parse import quote

from nonebot.drivers import Request

from .crypto import parse_aes_key, decrypt_aes_ecb

if TYPE_CHECKING:
    from collections.abc import Callable, Awaitable

    from nonebot.drivers import Response

    from .message import MessageSegment

    RequestFn = Callable[[Request], Awaitable[Response]]


def build_cdn_download_url(media_key: str, cdn_base_url: str) -> str:
    return f"{cdn_base_url.rstrip('/')}/download?encrypted_query_param={quote(media_key, safe='')}"


async def download_and_decrypt_media(
    *,
    request_fn: "RequestFn",
    media_key: str,
    aes_key: str,
    cdn_base_url: str,
    timeout: float = 30.0,
) -> bytes:
    url = build_cdn_download_url(media_key, cdn_base_url)

    request = Request(method="GET", url=url, timeout=timeout)
    response = await request_fn(request)
    status_code = response.status_code or 0
    content = response.content
    content_bytes = content.encode("utf-8") if isinstance(content, str) else cast("bytes", content)
    if status_code >= 400:
        raise RuntimeError(f"CDN download HTTP {status_code}: {content}")

    key = parse_aes_key(aes_key)
    return decrypt_aes_ecb(content_bytes, key)


def guess_image_extension(data: bytes) -> str:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith(b"BM"):
        return ".bmp"
    return ".bin"


async def download_image_from_segment(
    segment: "MessageSegment",
    *,
    request_fn: "RequestFn",
    cdn_base_url: str,
    save_dir: str | Path | None = None,
    file_name: str | None = None,
    timeout: float = 30.0,
) -> bytes | Path:
    if segment.type != "image":
        raise ValueError(f"segment type must be 'image', got {segment.type!r}")

    media_key = segment.data.get("media_key")
    aes_key = segment.data.get("aes_key")
    if not media_key:
        raise ValueError("image segment missing media_key")
    if not aes_key:
        raise ValueError("image segment missing aes_key")

    plaintext = await download_and_decrypt_media(
        request_fn=request_fn,
        media_key=media_key,
        aes_key=aes_key,
        cdn_base_url=cdn_base_url,
        timeout=timeout,
    )

    if save_dir is None:
        return plaintext

    save_dir_path = Path(save_dir)
    save_dir_path.mkdir(parents=True, exist_ok=True)

    suffix = guess_image_extension(plaintext)
    output_name = file_name or f"weixin-image{suffix}"
    if Path(output_name).suffix == "":
        output_name = f"{output_name}{suffix}"

    output_path = save_dir_path / output_name
    output_path.write_bytes(plaintext)
    return output_path
