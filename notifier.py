from urllib.parse import quote

import requests

from analyzer import MatchAlert
from config import (
    BOT_TOKEN,
    CHANNEL_ID,
    TELEGRAM_API_URL,
    TELEGRAM_PROXY_HOST,
    TELEGRAM_PROXY_PASSWORD,
    TELEGRAM_PROXY_PORT,
    TELEGRAM_PROXY_USERNAME,
    TELEGRAM_TIMEOUT_SECONDS,
)


class TelegramNotificationError(RuntimeError):
    pass


# Формирует URL SOCKS5-прокси и проверяет полноту его настроек.
def _get_proxy_url() -> str | None:
    if not TELEGRAM_PROXY_HOST and not TELEGRAM_PROXY_PORT:
        if TELEGRAM_PROXY_USERNAME or TELEGRAM_PROXY_PASSWORD:
            raise TelegramNotificationError(
                "SOCKS5 proxy credentials are set without a proxy host and port."
            )
        return None

    if not TELEGRAM_PROXY_HOST or not TELEGRAM_PROXY_PORT:
        raise TelegramNotificationError(
            "Both TELEGRAM_PROXY_HOST and TELEGRAM_PROXY_PORT must be set."
        )
    if "://" in TELEGRAM_PROXY_HOST or "/" in TELEGRAM_PROXY_HOST:
        raise TelegramNotificationError(
            "TELEGRAM_PROXY_HOST must contain a hostname or IP address only."
        )

    try:
        port = int(TELEGRAM_PROXY_PORT)
    except ValueError:
        raise TelegramNotificationError("TELEGRAM_PROXY_PORT must be an integer.") from None
    if not 1 <= port <= 65535:
        raise TelegramNotificationError("TELEGRAM_PROXY_PORT is outside the valid range.")

    if bool(TELEGRAM_PROXY_USERNAME) != bool(TELEGRAM_PROXY_PASSWORD):
        raise TelegramNotificationError(
            "Both TELEGRAM_PROXY_USERNAME and TELEGRAM_PROXY_PASSWORD must be set."
        )

    host = TELEGRAM_PROXY_HOST
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"

    credentials = ""
    if TELEGRAM_PROXY_USERNAME:
        username = quote(TELEGRAM_PROXY_USERNAME, safe="")
        password = quote(TELEGRAM_PROXY_PASSWORD, safe="")
        credentials = f"{username}:{password}@"

    return f"socks5h://{credentials}{host}:{port}"


# Отправляет сигнал в Telegram и проверяет подтверждение Bot API.
def send_alert(alert: MatchAlert) -> None:
    if not BOT_TOKEN:
        raise TelegramNotificationError(
            "BOT_TOKEN is not set. Add it to the environment or .env file."
        )
    if not CHANNEL_ID:
        raise TelegramNotificationError(
            "CHANNEL_ID is not set. Add it to the environment or .env file."
        )

    proxy_url = _get_proxy_url()
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    try:
        response = requests.post(
            f"{TELEGRAM_API_URL}/bot{BOT_TOKEN}/sendMessage",
            json={
                "chat_id": CHANNEL_ID,
                "text": alert.telegram_message,
                "parse_mode": "HTML",
            },
            proxies=proxies,
            timeout=TELEGRAM_TIMEOUT_SECONDS,
        )
    except requests.RequestException:
        raise TelegramNotificationError(
            "Telegram request failed due to a network or proxy error."
        ) from None

    if not response.ok:
        raise TelegramNotificationError(
            f"Telegram returned HTTP status {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError:
        raise TelegramNotificationError("Telegram returned invalid JSON.") from None

    if not isinstance(payload, dict) or payload.get("ok") is not True:
        description = payload.get("description") if isinstance(payload, dict) else None
        if not isinstance(description, str) or not description:
            description = "Telegram did not confirm the message."
        raise TelegramNotificationError(description)
