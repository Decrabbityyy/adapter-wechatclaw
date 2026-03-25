from __future__ import annotations

import sys
import time
import asyncio
import argparse
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
DEFAULT_BOT_TYPE = "3"
QR_LONG_POLL_TIMEOUT_S = 35
MAX_QR_REFRESH_COUNT = 3
LOGIN_TIMEOUT_S = 480


def _ensure_trailing_slash(url: str) -> str:
    return url if url.endswith("/") else f"{url}/"


async def fetch_qrcode(base_url: str, bot_type: str = DEFAULT_BOT_TYPE) -> dict[str, str]:
    url = f"{_ensure_trailing_slash(base_url)}ilink/bot/get_bot_qrcode?bot_type={bot_type}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url)
        if resp.status_code >= 400:
            raise RuntimeError(f"fetch_qrcode HTTP {resp.status_code}: {resp.text}")
        data: dict[str, Any] = resp.json()
        return {"qrcode": data["qrcode"], "qrcode_img_content": data.get("qrcode_img_content", "")}


async def poll_qrcode_status(base_url: str, qrcode: str) -> dict[str, Any]:
    url = f"{_ensure_trailing_slash(base_url)}ilink/bot/get_qrcode_status?qrcode={qrcode}"
    headers = {"iLink-App-ClientVersion": "1"}
    async with httpx.AsyncClient(timeout=QR_LONG_POLL_TIMEOUT_S + 5) as client:
        try:
            resp = await client.get(url, headers=headers, timeout=QR_LONG_POLL_TIMEOUT_S + 5)
            if resp.status_code >= 400:
                raise RuntimeError(f"poll status HTTP {resp.status_code}: {resp.text}")
            return resp.json()
        except httpx.ReadTimeout:
            return {"status": "wait"}


async def login_with_qrcode(
    base_url: str = DEFAULT_BASE_URL,
    bot_type: str = DEFAULT_BOT_TYPE,
    timeout_s: int = LOGIN_TIMEOUT_S,
) -> dict[str, str]:
    qr_data = await fetch_qrcode(base_url, bot_type)
    qrcode = qr_data["qrcode"]
    qrcode_url = qr_data["qrcode_img_content"]

    _print_qrcode(qrcode_url)

    deadline = time.monotonic() + timeout_s
    scanned_printed = False
    refresh_count = 0

    while time.monotonic() < deadline:
        status_resp = await poll_qrcode_status(base_url, qrcode)
        status = status_resp.get("status", "wait")

        if status == "wait":
            sys.stdout.write(".")
            sys.stdout.flush()

        elif status == "scaned":
            if not scanned_printed:
                sys.stdout.write("\n已扫码, 请在微信中确认...\n")
                sys.stdout.flush()
                scanned_printed = True

        elif status == "expired":
            refresh_count += 1
            if refresh_count >= MAX_QR_REFRESH_COUNT:
                raise RuntimeError("二维码多次过期, 登录失败")

            sys.stdout.write(f"\n二维码已过期, 正在刷新... ({refresh_count}/{MAX_QR_REFRESH_COUNT})\n")
            sys.stdout.flush()
            qr_data = await fetch_qrcode(base_url, bot_type)
            qrcode = qr_data["qrcode"]
            qrcode_url = qr_data["qrcode_img_content"]
            scanned_printed = False
            _print_qrcode(qrcode_url)

        elif status == "confirmed":
            bot_token = status_resp.get("bot_token", "")
            account_id = status_resp.get("ilink_bot_id", "")
            result_base_url = status_resp.get("baseurl", base_url)
            user_id = status_resp.get("ilink_user_id", "")

            if not account_id:
                raise RuntimeError("登录确认但服务器未返回 ilink_bot_id")

            return {
                "bot_token": bot_token,
                "account_id": account_id,
                "base_url": result_base_url,
                "user_id": user_id,
            }

        await asyncio.sleep(1)

    raise RuntimeError("登录超时")


def _print_qrcode(qrcode_url: str) -> None:
    try:
        import qrcode as qr_lib  # noqa: PLC0415

        qr = qr_lib.QRCode(error_correction=1, box_size=1, border=1)
        qr.add_data(qrcode_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        pass

    sys.stdout.write(f"\n二维码链接: {qrcode_url}\n")
    sys.stdout.write("请使用微信扫描以上二维码\n\n")
    sys.stdout.flush()


def main() -> None:

    parser = argparse.ArgumentParser(description="微信 iLink Bot 扫码登录")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"API base URL (default: {DEFAULT_BASE_URL})")
    parser.add_argument("--bot-type", default=DEFAULT_BOT_TYPE, help=f"Bot type (default: {DEFAULT_BOT_TYPE})")
    parser.add_argument(
        "--timeout", type=int, default=LOGIN_TIMEOUT_S, help=f"Timeout in seconds (default: {LOGIN_TIMEOUT_S})"
    )
    args = parser.parse_args()

    try:
        result = asyncio.run(
            login_with_qrcode(
                base_url=args.base_url,
                bot_type=args.bot_type,
                timeout_s=args.timeout,
            )
        )
    except RuntimeError as e:
        sys.stderr.write(f"\n登录失败: {e}\n")
        sys.exit(1)

    sys.stdout.write("\n" + "=" * 50 + "\n")
    sys.stdout.write("登录成功! 请将以下信息添加到 .env 文件:\n")
    sys.stdout.write("=" * 50 + "\n\n")
    sys.stdout.write(f'WECHATCLAW_TOKEN="{result["bot_token"]}"\n')
    sys.stdout.write(f'WECHATCLAW_ACCOUNT_ID="{result["account_id"]}"\n')
    if result.get("base_url"):
        sys.stdout.write(f'WECHATCLAW_BASE_URL="{result["base_url"]}"\n')
    if result.get("user_id"):
        sys.stdout.write(f"\n# 扫码用户 ID (可用于 allow_from 配置): {result['user_id']}\n")
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
