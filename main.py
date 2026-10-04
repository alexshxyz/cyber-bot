import json
import time
from decimal import Decimal

from analyzer import MatchAlert, analyze_events
from client import BetsApiClient, BetsApiRequestError
from config import DATA_FILE, MATCHES_FILE, POLL_INTERVAL_SECONDS
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


# Преобразует уведомление в структуру JSON для последующей передачи notifier.
def _alert_to_json(alert: MatchAlert) -> dict[str, str]:
    return {"event_id": alert.event_id, "message": alert.message}


# Выполняет один цикл загрузки матчей и записи результата.
def run_cycle() -> bool:
    logger = get_logger(__name__)
    try:
        events = get_upcoming_events(BetsApiClient())
    except (BetsApiRequestError, BetsApiDataError, ValueError) as error:
        logger.error("%s", error)
        return False

    alerts = analyze_events(events)
    try:
        json_data = json.dumps(
            [_event_to_json(event) for event in events],
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
        DATA_FILE.write_text(f"{json_data}\n", encoding="utf-8")
        matches_json = json.dumps(
            [_alert_to_json(alert) for alert in alerts],
            ensure_ascii=False,
            indent=2,
        )
        MATCHES_FILE.write_text(f"{matches_json}\n", encoding="utf-8")
    except OSError as error:
        logger.error("Could not write match data or alerts: %s", error)
        return False

    logger.info("Data for %d matches saved.", len(events))
    for alert in alerts:
        logger.info("Match %s sent.", alert.event_id)
    return True


# Повторяет загрузку данных через заданный интервал до остановки пользователем.
def main() -> int:
    configure_logging()
    logger = get_logger(__name__)
    logger.info("Bot started.")

    try:
        while True:
            run_cycle()
            logger.info(
                "Sleep for %d min and start again...",
                POLL_INTERVAL_SECONDS // 60,
            )
            time.sleep(POLL_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        logger.info("Stopping match polling.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())