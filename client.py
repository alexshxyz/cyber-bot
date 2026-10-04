import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from config import (
    API_BASE_URL,
    API_KEY,
    API_MAX_RETRIES,
    API_RETRY_DELAY_SECONDS,
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
        max_attempts = API_MAX_RETRIES + 1
        for attempt in range(1, max_attempts + 1):
            try:
                with urlopen(request, timeout=API_TIMEOUT_SECONDS) as response:
                    return response.read()
            except HTTPError as error:
                should_retry = error.code == 429 or error.code == 408 or 500 <= error.code <= 599
                if not should_retry or attempt == max_attempts:
                    status_code = error.code
                    error.close()
                    raise BetsApiRequestError(
                        f"BetsAPI request for {request_description} failed with "
                        f"HTTP status {status_code} after {attempt} attempt(s)."
                    ) from None

                status_code = error.code
                error.close()
                logger.warning(
                    "BetsAPI returned HTTP %d for %s; retrying in %d seconds "
                    "(attempt %d/%d).",
                    status_code,
                    request_description,
                    API_RETRY_DELAY_SECONDS,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(API_RETRY_DELAY_SECONDS)
            except (URLError, TimeoutError) as error:
                if attempt == max_attempts:
                    raise BetsApiRequestError(
                        f"Could not complete BetsAPI request for {request_description} "
                        f"after {attempt} attempt(s): connection failed or timed out."
                    ) from error

                logger.warning(
                    "BetsAPI request for %s failed (%s); retrying in %d seconds "
                    "(attempt %d/%d).",
                    request_description,
                    error,
                    API_RETRY_DELAY_SECONDS,
                    attempt + 1,
                    max_attempts,
                )
                time.sleep(API_RETRY_DELAY_SECONDS)

        raise BetsApiRequestError(f"BetsAPI request for {request_description} failed.")
