import json
from decimal import Decimal

from client import BetsApiClient, BetsApiRequestError
from config import DATA_FILE
from data import BetsApiDataError, UpcomingEvent, get_upcoming_events
from logger import configure_logging, get_logger


# Преобразует точные десятичные числа коэффициентов в JSON-числа.
def _json_default(value: object) -> float:
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable.")


# Преобразует матч в структуру JSON с именами полей для проверки данных.
def _event_to_json(event: UpcomingEvent) -> dict[str, object]:
    return {
        "id": event.event_id,
        "league": event.league,
        "home": event.home,
        "away": event.away,
        "1x2_odds": [
            {"home_od": odds.home_od, "away_od": odds.away_od}
            for odds in event.odds_1x2
        ],
        "ah_odds": [
            {
                "home_od": odds.home_od,
                "away_od": odds.away_od,
                "handicap": odds.handicap,
            }
            for odds in event.ah_odds
        ],
    }


# Загружает матчи и записывает результат в файл data.json.
def main() -> int:
    configure_logging()
    logger = get_logger(__name__)

    try:
        events = get_upcoming_events(BetsApiClient())
    except (BetsApiRequestError, BetsApiDataError, ValueError) as error:
        logger.error("%s", error)
        return 1

    try:
        json_data = json.dumps(
            [_event_to_json(event) for event in events],
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
        DATA_FILE.write_text(f"{json_data}\n", encoding="utf-8")
    except OSError as error:
        logger.error("Could not write match data to %s: %s", DATA_FILE, error)
        return 1

    logger.info("Saved %d matches to %s.", len(events), DATA_FILE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())