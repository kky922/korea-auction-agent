import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional


def _get_env(name: str) -> str:
    return (os.getenv(name, "") or "").strip()


def is_configured() -> bool:
    return bool(_get_env("AUCTION_TELEGRAM_BOT_TOKEN") and _get_env("AUCTION_TELEGRAM_CHAT_ID"))


def send_message(text: str, timeout: int = 8, code_block: bool = False, html: bool = False) -> bool:
    token = _get_env("AUCTION_TELEGRAM_BOT_TOKEN")
    chat_id = _get_env("AUCTION_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    if code_block:
        send_text = f"<pre>{text}</pre>"
        parse_mode = "HTML"
    elif html:
        send_text = text
        parse_mode = "HTML"
    else:
        send_text = text
        parse_mode = ""

    payload_dict: dict = {
        "chat_id": chat_id,
        "text": send_text,
        "disable_web_page_preview": "true",
    }
    if parse_mode:
        payload_dict["parse_mode"] = parse_mode
    payload = urllib.parse.urlencode(payload_dict).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
            return bool(data.get("ok"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return False


def send_lines(title: str, lines: list[str]) -> bool:
    message = title
    if lines:
        message += "\n" + "\n".join(lines)
    return send_message(message)

