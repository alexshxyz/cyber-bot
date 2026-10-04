import json
import time
from decimal import Decimal

from analyzer import MatchAlert, analyze_events
from client import BetsApiClient, BetsApiRequestError
from config import DATA_FILE, MATCHES_FILE, POLL_INTERVAL_SECONDS
from data import BetsApiDataError, UpcomingEvent, get_upcoming_events
from logger import configure_logging, get_logger
from notifier import TelegramNotificationError, send_alert


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
    return {
        "event_id": alert.event_id,
        "market": alert.market,
        "message": alert.message,
    }


# Читает историю сигналов и распознает рынок в старом формате без поля market.
def _read_existing_alerts() -> tuple[list[dict[str, object]], set[tuple[str, str]]]:
    try:
        matches_text = MATCHES_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], set()

    if not matches_text.strip():
        return [], set()

    try:
        saved_alerts = json.loads(matches_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {MATCHES_FILE}: {error}") from error

    if not isinstance(saved_alerts, list):
        raise ValueError(f"Expected a JSON array in {MATCHES_FILE}.")

    existing_alerts: list[dict[str, object]] = []
    existing_keys: set[tuple[str, str]] = set()
    for index, saved_alert in enumerate(saved_alerts):
        if not isinstance(saved_alert, dict):
            raise ValueError(f"Invalid alert at index {index} in {MATCHES_FILE}.")

        event_id = saved_alert.get("event_id")
        message = saved_alert.get("message")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError(f"Invalid event_id at index {index} in {MATCHES_FILE}.")
        if not isinstance(message, str):
            raise ValueError(f"Invalid message at index {index} in {MATCHES_FILE}.")

        market = saved_alert.get("market")
        if market is None:
            if "\nDrop 1x2:" in message:
                market = "1x2_odds"
            elif "\nDrop AH:" in message:
                market = "ah_odds"
            else:
                raise ValueError(
                    f"Could not determine market for alert at index {index} "
                    f"in {MATCHES_FILE}."
                )
        elif not isinstance(market, str) or market not in {"1x2_odds", "ah_odds"}:
            raise ValueError(f"Invalid market at index {index} in {MATCHES_FILE}.")

        existing_alerts.append(saved_alert)
        existing_keys.add((event_id, market))

    return existing_alerts, existing_keys


# Выполняет один цикл загрузки матчей и записи результата.
def run_cycle() -> bool:
    logger = get_logger(__name__)
    try:
        events = get_upcoming_events(BetsApiClient())
    except (BetsApiRequestError, BetsApiDataError, ValueError) as error:
        logger.error("%s", error)
        return False

    try:
        json_data = json.dumps(
            [_event_to_json(event) for event in events],
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        )
        DATA_FILE.write_text(f"{json_data}\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        logger.error("Could not write match data to %s: %s", DATA_FILE, error)
        return False

    logger.info("Data for %d matches saved.", len(events))

    try:
        saved_alerts, existing_keys = _read_existing_alerts()
        new_alerts: list[MatchAlert] = []
        duplicate_alerts: list[MatchAlert] = []
        for alert in analyze_events(events):
            alert_key = (alert.event_id, alert.market)
            if alert_key in existing_keys:
                duplicate_alerts.append(alert)
                continue
            existing_keys.add(alert_key)
            new_alerts.append(alert)
    except (OSError, ValueError) as error:
        logger.error("Could not read alert history from %s: %s", MATCHES_FILE, error)
        return False

    for alert in duplicate_alerts:
        logger.info(
            "Skipping duplicate %s signal for match %s.",
            alert.market,
            alert.event_id,
        )

    delivered_alerts: list[MatchAlert] = []
    notification_failed = False
    for alert in new_alerts:
        try:
            send_alert(alert)
        except TelegramNotificationError as error:
            logger.error(
                "Could not send match %s for %s: %s",
                alert.event_id,
                alert.market,
                error,
            )
            notification_failed = True
            continue

        delivered_alerts.append(alert)
        logger.info("Match %s sent for %s.", alert.event_id, alert.market)

    try:
        matches_json = json.dumps(
            saved_alerts + [_alert_to_json(alert) for alert in delivered_alerts],
            ensure_ascii=False,
            indent=2,
        )
        MATCHES_FILE.write_text(f"{matches_json}\n", encoding="utf-8")
    except (OSError, ValueError) as error:
        logger.error("Could not write alerts to %s: %s", MATCHES_FILE, error)
        return False

    return not notification_failed


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