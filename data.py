from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from config import MAX_MATCH_START_HOURS
from logger import get_logger

if TYPE_CHECKING:
    from client import BetsApiClient


logger = get_logger(__name__)


class BetsApiDataError(RuntimeError):
    pass


# Хранит ID матча, название лиги и названия обеих команд.
@dataclass(frozen=True)
class UpcomingEvent:
    event_id: str
    league: str
    home: str
    away: str
    odds_1x2: list[MatchOdds] = field(default_factory=list)
    ah_odds: list[HandicapOdds] = field(default_factory=list)


# Хранит коэффициенты домашней и гостевой команд в рынке 1X2.
@dataclass(frozen=True)
class MatchOdds:
    home_od: Decimal
    away_od: Decimal


# Хранит коэффициенты и фору одной записи азиатского гандикапа.
@dataclass(frozen=True)
class HandicapOdds:
    home_od: Decimal
    away_od: Decimal
    handicap: Decimal


# Разбирает JSON-ответ API и проверяет его структуру.
def _parse_response(response_body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(response_body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise BetsApiDataError("BetsAPI returned invalid JSON.") from None
    if not isinstance(payload, dict):
        raise BetsApiDataError("BetsAPI returned an invalid response.")
    return payload


# Возвращает предстоящие матчи с названием лиги и обеих команд.
def get_upcoming_events(client: BetsApiClient, day: str = "TODAY") -> list[UpcomingEvent]:
    events_with_start_times: list[tuple[UpcomingEvent, int]] = []
    seen_ids: set[str] = set()
    records_read = 0
    page = 1
    total: int | None = None

    logger.info("Requesting upcoming matches ID from BetsAPI...")
    while total is None or records_read < total:
        payload = _parse_response(client.get_upcoming_events_page(page=page, day=day))
        if payload.get("success") not in (1, "1"):
            raise BetsApiDataError("BetsAPI reported that the upcoming-events request failed.")

        results = payload.get("results")
        if not isinstance(results, list):
            raise BetsApiDataError("BetsAPI returned an invalid results field.")

        pager = payload.get("pager")
        if not isinstance(pager, dict):
            raise BetsApiDataError("BetsAPI returned an invalid pager field.")
        try:
            parsed_total = int(pager.get("total"))
        except (TypeError, ValueError):
            raise BetsApiDataError("BetsAPI returned an invalid total match count.") from None
        if parsed_total < 0:
            raise BetsApiDataError("BetsAPI returned an invalid total match count.")
        if total is not None and parsed_total != total:
            raise BetsApiDataError("BetsAPI changed the total match count during pagination.")
        total = parsed_total

        if not results and records_read < total:
            raise BetsApiDataError("BetsAPI returned an empty page before all matches were read.")

        for result in results:
            if not isinstance(result, dict):
                raise BetsApiDataError("BetsAPI returned an invalid match record.")
            event_id = result.get("id")
            if not isinstance(event_id, (str, int)) or not str(event_id):
                raise BetsApiDataError("BetsAPI returned a match without a valid ID.")
            event_id = str(event_id)
            if event_id not in seen_ids:
                seen_ids.add(event_id)
                league = _get_name(result, "league")
                home = _get_name(result, "home")
                away = _get_name(result, "away")
                start_time = _get_start_time(result, event_id)
                events_with_start_times.append(
                    (UpcomingEvent(event_id, league, home, away), start_time)
                )

        records_read += len(results)
        logger.debug(
            "Processed upcoming events page %d (%d/%d records).",
            page,
            records_read,
            total,
        )
        page += 1

    if not events_with_start_times:
        return []

    now = time.time()
    maximum_wait_seconds = MAX_MATCH_START_HOURS * 60 * 60
    skipped_count = sum(
        start_time - now > maximum_wait_seconds
        for _, start_time in events_with_start_times
    )
    events = [
        event
        for event, start_time in events_with_start_times
        if 0 <= start_time - now <= maximum_wait_seconds
    ]
    if not events:
        logger.info(
            "No matches starting within %d hours; skipping odds requests.",
            MAX_MATCH_START_HOURS,
        )
        return []

    logger.info(
        "Found %d matches starting within %d hours (%d skipped), requesting odds...",
        len(events),
        MAX_MATCH_START_HOURS,
        skipped_count,
    )

    logger.info("Getting data...")
    with ThreadPoolExecutor(max_workers=len(events)) as executor:
        futures = [
            executor.submit(_enrich_event, client, event)
            for event in events
        ]
        enriched_events = [future.result() for future in futures]
        return [event for event in enriched_events if event is not None]


# Проверяет и преобразует Unix-время начала матча из ответа BetsAPI.
def _get_start_time(event: dict[str, Any], event_id: str) -> int:
    value = event.get("time")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise BetsApiDataError(
            f"BetsAPI returned an invalid start time for event {event_id}."
        )
    try:
        start_time = int(value)
    except ValueError:
        raise BetsApiDataError(
            f"BetsAPI returned an invalid start time for event {event_id}."
        ) from None
    if start_time < 0:
        raise BetsApiDataError(
            f"BetsAPI returned an invalid start time for event {event_id}."
        )
    return start_time


# Проверяет объект участника матча и возвращает его название.
def _get_name(event: dict[str, Any], participant: str) -> str:
    details = event.get(participant)
    if not isinstance(details, dict):
        raise BetsApiDataError(f"BetsAPI returned a match without valid {participant} data.")
    name = details.get("name")
    if not isinstance(name, str) or not name.strip():
        raise BetsApiDataError(f"BetsAPI returned a match without a valid {participant} name.")
    return name.strip()


# Получает для матча историю 1X2 и азиатского гандикапа в хронологическом порядке.
def _get_event_odds(
    client: BetsApiClient, event_id: str
) -> tuple[list[MatchOdds], list[HandicapOdds]] | None:
    payload = _parse_response(client.get_event_odds(event_id))
    if payload.get("success") not in (1, "1"):
        raise BetsApiDataError(f"BetsAPI reported that odds retrieval failed for event {event_id}.")

    results = payload.get("results")
    if not isinstance(results, dict):
        raise BetsApiDataError(f"BetsAPI returned invalid odds results for event {event_id}.")
    odds = results.get("odds", {})
    if not isinstance(odds, dict):
        raise BetsApiDataError(f"BetsAPI returned invalid odds data for event {event_id}.")

    one_x_two = _get_market_records(odds, "151_1", event_id)
    handicap = _get_market_records(odds, "151_2", event_id)
    if any(record.get("ss") is not None for record in (*one_x_two, *handicap)):
        logger.info("Skipping live match %s.", event_id)
        return None

    one_x_two = _filter_unavailable_odds(one_x_two, ("home_od", "away_od"))
    handicap = _filter_unavailable_odds(
        handicap,
        ("home_od", "away_od", "handicap"),
    )

    return (
        [
            MatchOdds(
                home_od=_get_decimal(record, "home_od", event_id),
                away_od=_get_decimal(record, "away_od", event_id),
            )
            for record in one_x_two
        ],
        [
            HandicapOdds(
                home_od=_get_decimal(record, "home_od", event_id),
                away_od=_get_decimal(record, "away_od", event_id),
                handicap=_get_decimal(record, "handicap", event_id),
            )
            for record in handicap
        ],
    )


# Удаляет записи рынка с незаданными коэффициентами, обозначенными дефисом.
def _filter_unavailable_odds(
    records: list[dict[str, Any]], fields: tuple[str, ...]
) -> list[dict[str, Any]]:
    return [
        record
        for record in records
        if not any(
            isinstance(record.get(field), str) and record[field].strip() == "-"
            for field in fields
        )
    ]


# Получает коэффициенты для матча и возвращает его дополненную запись.
def _enrich_event(
    client: BetsApiClient, event: UpcomingEvent
) -> UpcomingEvent | None:
    logger.debug("Requesting odds for event %s.", event.event_id)
    odds = _get_event_odds(client, event.event_id)
    if odds is None:
        return None
    odds_1x2, ah_odds = odds
    return replace(event, odds_1x2=odds_1x2, ah_odds=ah_odds)


# Проверяет записи выбранного рынка и возвращает их исходный список.
def _get_market_records(
    odds: dict[str, Any], market: str, event_id: str
) -> list[dict[str, Any]]:
    records = odds.get(market, [])
    if not isinstance(records, list):
        raise BetsApiDataError(
            f"BetsAPI returned invalid market {market} data for event {event_id}."
        )
    if any(not isinstance(record, dict) for record in records):
        raise BetsApiDataError(
            f"BetsAPI returned an invalid odds record for event {event_id}."
        )
    return records


# Преобразует значение коэффициента или форы в точное десятичное число.
def _get_decimal(record: dict[str, Any], field: str, event_id: str) -> Decimal:
    value = record.get(field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BetsApiDataError(
            f"BetsAPI returned an invalid {field} value for event {event_id}."
        ) from None
    if not number.is_finite():
        raise BetsApiDataError(
            f"BetsAPI returned a non-finite {field} value for event {event_id}."
        )
    return number
