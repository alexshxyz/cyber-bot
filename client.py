from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import (
    API_BASE_URL,
    API_KEY,
    API_MAX_ATTEMPTS,
    API_RETRY_BASE_DELAY_SECONDS,
    API_RETRY_MAX_DELAY_SECONDS,
    API_SPORT_ID,
    API_TIMEOUT_SECONDS,
)
from logger import get_logger


API_ODDS_URL = "https://api.b365api.com/v2/event/odds"


logger = get_logger(__name__)


class BetsApiRequestError(RuntimeError):
    pass


class BetsApiClient:
    # Создает клиент BetsAPI и проверяет наличие API-ключа.
    def __init__(self, api_key: str = API_KEY) -> None:
        if not api_key:
            raise ValueError("API_KEY is not set. Add it to the environment or .env file.")
        self._api_key = api_key

    # Отправляет запрос за одной страницей предстоящих матчей и возвращает ответ API.
    def get_upcoming_events_page(self, page: int = 1, day: str = "TODAY") -> bytes:
        params = {
            "sport_id": API_SPORT_ID,
            "token": self._api_key,
            "day": day,
        }
        if page > 1:
            params["page"] = page
        request = Request(
            f"{API_BASE_URL}/events/upcoming?{urlencode(params)}",
            headers={"Accept": "application/json"},
        )
        logger.debug("Requesting upcoming events page %d.", page)
        return self._request_bytes(request, f"upcoming events page {page}")

    # Запрашивает историю коэффициентов для указанного матча и возвращает ответ API.
    def get_event_odds(self, event_id: str) -> bytes:
        if not event_id:
            raise ValueError("Event ID must not be empty.")
        params = {
            "token": self._api_key,
            "source": "bet365",
            "odds_market": "1,2",
            "event_id": event_id,
        }
        request = Request(
            f"{API_ODDS_URL}?{urlencode(params)}",
            headers={"Accept": "application/json"},
        )
        logger.debug("Requesting odds for event %s.", event_id)
        return self._request_bytes(request, f"odds for event {event_id}")

    # Отправляет HTTP-запрос и повторяет его при временных ошибках API.
    @staticmethod
    def _request_bytes(request: Request, request_description: str) -> bytes:
        for attempt in range(1, API_MAX_ATTEMPTS + 1):
            try:
                with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                    return response.read()
            except HTTPError as error:
                should_retry = error.code == 429 or error.code == 408 or 500 <= error.code <= 599
                if not should_retry or attempt == API_MAX_ATTEMPTS:
                    status_code = error.code
                    error.close()
                    raise BetsApiRequestError(
                        f"BetsAPI request for {request_description} failed with "
                        f"HTTP status {status_code} after {attempt} attempt(s)."
                    ) from None

                delay = BetsApiClient._get_retry_delay(error, attempt)
                status_code = error.code
                error.close()
                logger.warning(
                    "BetsAPI returned HTTP %d for %s; retrying in %.1f seconds "
                    "(attempt %d/%d).",
                    status_code,
                    request_description,
                    delay,
                    attempt + 1,
                    API_MAX_ATTEMPTS,
                )
                time.sleep(delay)
            except (URLError, TimeoutError) as error:
                if attempt == API_MAX_ATTEMPTS:
                    raise BetsApiRequestError(
                        f"Could not complete BetsAPI request for {request_description} "
                        f"after {attempt} attempt(s): connection failed or timed out."
                    ) from error

                delay = min(
                    API_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                    API_RETRY_MAX_DELAY_SECONDS,
                )
                logger.warning(
                    "BetsAPI request for %s failed (%s); retrying in %.1f seconds "
                    "(attempt %d/%d).",
                    request_description,
                    error,
                    delay,
                    attempt + 1,
                    API_MAX_ATTEMPTS,
                )
                time.sleep(delay)

        raise BetsApiRequestError(f"BetsAPI request for {request_description} failed.")

    # Выбирает паузу повтора с учетом заголовка Retry-After от сервера.
    @staticmethod
    def _get_retry_delay(error: HTTPError, attempt: int) -> float:
        fallback_delay = min(
            API_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
            API_RETRY_MAX_DELAY_SECONDS,
        )
        retry_after = error.headers.get("Retry-After") if error.headers else None
        if retry_after is None:
            return fallback_delay

        try:
            return min(max(0.0, float(retry_after)), API_RETRY_MAX_DELAY_SECONDS)
        except ValueError:
            try:
                retry_time = parsedate_to_datetime(retry_after)
            except (TypeError, ValueError, OverflowError):
                return fallback_delay
            if retry_time.tzinfo is None:
                retry_time = retry_time.replace(tzinfo=timezone.utc)
            delay = max(0.0, (retry_time - datetime.now(timezone.utc)).total_seconds())
            return min(delay, API_RETRY_MAX_DELAY_SECONDS)
